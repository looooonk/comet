import gc
import weakref
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from comet.artifacts import read_json, write_json
from comet.budget import Budget
from comet.config import AgentProtocol, Condition, Experiment, attempt_seed, comparison_matrix
from comet.engine.contracts import MODEL_REVISION
from comet.errors import BudgetExpired, FatalAcceleratorError, MemoryCapExceeded
from comet.policies import decide
from comet.runner import Runner


@pytest.fixture
def config():
    return Experiment.from_dict(
        {
            "schema_version": 1,
            "experiment_id": "fixture",
            "stage": "pilot",
            "split": "dev",
            "task_ids": ["fixture_1"],
            "seeds": [7],
            "budget_seconds": 100,
            "peak_vram_bytes": 40_000_000_000,
            "max_attempts": 2,
            "engine": {
                "model": "Qwen/Qwen3-8B",
                "model_revision": MODEL_REVISION,
                "tokenizer_revision": MODEL_REVISION,
                "dtype": "bfloat16",
                "max_context_tokens": 100,
                "workspace_reserve_bytes": 1_000_000,
                "prefill_chunk_tokens": 16,
            },
            "sampling": {
                "temperature": 0.7,
                "top_p": 0.9,
                "max_new_tokens": 8,
                "enable_thinking": False,
            },
            "triggers": {
                "fixed_tool_calls": 1,
                "dynamic_context_tokens": 3,
                "dynamic_tool_calls": 1,
                "dynamic_rule": "and",
            },
            "conditions": [asdict(Condition("streaming_50", "streamingllm", 0.5, "fixed", 2))],
            "prompt": "Complete task with Python.",
            "checkpoint_after_tool_calls": None,
            "frozen": None,
            "notes": "fixture only",
        }
    )


class Clock:
    now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeEngine:
    def __init__(self, clock):
        self.clock = clock
        self.raw_token_ids = []
        self.recoveries = []
        self.starts = []
        self.tokenizer = SimpleNamespace(
            apply_chat_template=lambda *a, **kw: [10],
            encode=lambda *a, **kw: [20],
            decode=lambda *a, **kw: "```python\nvalue = 1\n```",
        )

    def start(self, seed):
        self.raw_token_ids = []
        self.starts.append(seed)
        self.clock.advance(1)

    def set_policy(self, method, retention):
        pass

    def generate(self, tokens, **kwargs):
        self.clock.advance(2)
        self.raw_token_ids.extend(tokens + [30])
        return {
            "token_ids": [30],
            "finished": True,
            "decode_seconds": 1,
            "prefill_seconds": 1,
            "prompt_tokens": len(tokens),
            "estimated_flops": 100,
        }

    def recover(self, tokens, **kwargs):
        assert tokens[: len(self.raw_token_ids)] == self.raw_token_ids
        self.raw_token_ids = list(tokens)
        self.recoveries.append(list(tokens))
        self.clock.advance(1)
        return {"admitted": True, "seconds": 1}

    def memory_stats(self):
        return {"peak_total_vram_bytes": 1000, "peak_kv_bytes": 100}

    def checkpoint(self, path):
        write_json(path / "fake.json", {"tokens": self.raw_token_ids})
        self.clock.advance(1)

    def restore(self, path, **kwargs):
        self.raw_token_ids = read_json(path / "fake.json")["tokens"]
        self.clock.advance(1)

    def close(self):
        pass


class FakeEnvironment:
    def __init__(self, clock, all_environments):
        self.clock, self.count = clock, 0
        all_environments.append(self)

    def reset(self, *args):
        self.count = 0
        self.clock.advance(1)

    def initial_prompt(self):
        return "task"

    def execute(self, action, **kwargs):
        self.count += 1
        self.clock.advance(3)
        return str(self.count)

    def completed(self):
        return self.count == 2

    def save(self, path):
        self.clock.advance(1)
        write_json(path / "fixture.json", {"count": self.count})
        return {"path": str(path)}

    def checkpoint(self, path):
        self.clock.advance(1)
        write_json(path / "fake.json", {"count": self.count})

    def restore(self, path):
        self.clock.advance(1)
        self.count = read_json(path / "fake.json")["count"]

    def close(self):
        pass


def run_fixture(config, output):
    clock, environments, engines = Clock(), [], []

    def factory(condition):
        engine = FakeEngine(clock)
        engines.append(engine)
        return engine

    runner = Runner(
        config, output, factory, lambda: FakeEnvironment(clock, environments), clock=clock
    )
    manifest = runner.run()
    cells = [read_json(output / item["path"]) for item in manifest["cells"]]
    return runner, cells, engines, environments


@pytest.mark.parametrize("failure_site", ["generate", "synchronize", "memory_stats"])
def test_fatal_cuda_failure_preserves_cell_and_leaves_later_tasks_unstarted(
    config, tmp_path, failure_site
):
    config = replace(config, task_ids=["fixture_1", "fixture_2"])
    clock, environments = Clock(), []

    class PoisonedEngine(FakeEngine):
        pass

    def fail(*args, **kwargs):
        raise RuntimeError("CUDA error: an illegal memory access was encountered")

    setattr(PoisonedEngine, failure_site, fail)
    engine = PoisonedEngine(clock)
    runner = Runner(
        config, tmp_path, lambda _: engine,
        lambda: FakeEnvironment(clock, environments), clock=clock,
    )
    with pytest.raises(FatalAcceleratorError, match="remaining cells left unstarted"):
        runner.run()
    manifest = read_json(tmp_path / "manifest.json")
    first_path = tmp_path / manifest["cells"][0]["path"]
    first = read_json(first_path)
    assert first["completed"] and not first["inflight"]
    assert len(first["attempts"]) == len(engine.starts) == 1
    assert first["attempts"][0]["status"] == "error"
    assert first["elapsed_seconds"] == config.budget_seconds
    assert first["reserved_budget_seconds"] > 0
    assert not (tmp_path / manifest["cells"][1]["path"]).exists()
    saved = first_path.read_bytes()

    healthy = FakeEngine(clock)
    resumed = Runner(
        config, tmp_path, lambda _: healthy,
        lambda: FakeEnvironment(clock, environments), clock=clock,
    ).run(resume=True)
    assert resumed["status"] == "completed"
    assert first_path.read_bytes() == saved
    assert len(healthy.starts) == config.conditions[0].max_attempts


def test_allocator_oom_does_not_poison_following_cells(config, tmp_path):
    config = replace(config, task_ids=["fixture_1", "fixture_2"])
    clock, environments = Clock(), []

    class LimitedEngine(FakeEngine):
        def generate(self, *args, **kwargs):
            raise MemoryCapExceeded("CUDA allocator out of memory at the configured cap")

    engine = LimitedEngine(clock)
    manifest = Runner(
        config, tmp_path, lambda _: engine,
        lambda: FakeEnvironment(clock, environments), clock=clock,
    ).run()
    assert manifest["status"] == "completed"
    assert len(engine.starts) == 4
    for reference in manifest["cells"]:
        cell = read_json(tmp_path / reference["path"])
        assert [attempt["status"] for attempt in cell["attempts"]] == ["oom", "oom"]


def test_matrix_and_seed_pairing():
    matrix = comparison_matrix(4)
    assert len(matrix) == 29
    assert len({c.id for c in matrix}) == 29
    assert {c.retention for c in matrix if c.method != "full"} == {0.25, 0.5, 0.8}
    assert len({attempt_seed(42, i) for i in range(4)}) == 4
    assert attempt_seed(42, 0) == attempt_seed(42, 0)


@pytest.mark.parametrize("operation", ["generate", "recover"])
def test_failed_inference_releases_frame_objects_without_cyclic_gc(config, tmp_path, operation):
    clock, environments, references = Clock(), [], []

    class TemporaryTensor:
        pass

    class FailingEngine(FakeEngine):
        def fail(self, *args, **kwargs):
            temporary = TemporaryTensor()
            references.append(weakref.ref(temporary))
            raise MemoryError("fixture allocation failed")

    engine = FailingEngine(clock)
    setattr(engine, operation, engine.fail)
    runner = Runner(
        config, tmp_path, lambda condition: engine,
        lambda: FakeEnvironment(clock, environments), clock=clock,
    )
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        runner.run()
        assert references
        assert all(reference() is None for reference in references)
    finally:
        if was_enabled:
            gc.enable()
        gc.collect()


@pytest.mark.parametrize(
    "field,value", [("budget_seconds", float("nan")), ("peak_vram_bytes", True), ("seeds", [1, 1])]
)
def test_invalid_config(config, field, value):
    raw = config.to_dict()
    raw[field] = value
    with pytest.raises(ValueError):
        Experiment.from_dict(raw)


def test_frozen_final_rejects_changed_setting(config):
    raw = config.to_dict()
    raw.update(stage="final", split="test_normal")
    with pytest.raises(ValueError, match="frozen"):
        Experiment.from_dict(raw)
    pending = Experiment.from_dict(raw, allow_unfrozen=True)
    raw["frozen"] = {"settings_digest": pending.settings_digest, "pilot_evidence": ["fixture"]}
    Experiment.from_dict(raw)
    raw["triggers"]["fixed_tool_calls"] = 5
    with pytest.raises(ValueError, match="frozen"):
        Experiment.from_dict(raw)


def test_config_inheritance_resolves_before_digest(config, tmp_path):
    write_json(tmp_path / "base.json", config.to_dict())
    write_json(tmp_path / "child.json", {"extends": "base.json", "sampling": {"temperature": 0}})
    child = Experiment.load(tmp_path / "child.json")
    assert child.sampling.temperature == 0
    assert child.sampling.top_p == config.sampling.top_p
    assert child.digest != config.digest
    write_json(tmp_path / "a.json", {"extends": "b.json"})
    write_json(tmp_path / "b.json", {"extends": "a.json"})
    with pytest.raises(ValueError, match="cycle"):
        Experiment.load(tmp_path / "a.json")


@pytest.mark.parametrize("diagnostic,comments", [(False, False), (False, True), (True, False)])
def test_agent_failure_limit_preserves_budget_history_and_checkpoint_state(
    config, tmp_path, diagnostic, comments,
):
    bounded = replace(
        config, agent=AgentProtocol(3), max_attempts=1,
        conditions=[Condition("full_once", "full", 1.0, "never", 1)],
        stage="diagnostic" if diagnostic else "pilot",
        checkpoint_after_tool_calls=2 if diagnostic else None,
    )
    clock, environments = Clock(), []
    engine = FakeEngine(clock)
    if comments:
        engine.tokenizer.decode = lambda *a, **kw: "```python\n# hypothetical login\n```"

    class FailingEnvironment(FakeEnvironment):
        def execute(self, action, **kwargs):
            super().execute(action, **kwargs)
            return 'Execution failed. Response status code is 401: missing token'

        def completed(self):
            return False

    runner = Runner(bounded, tmp_path, lambda _: engine,
                    lambda: FailingEnvironment(clock, environments), clock=clock)
    manifest = runner.run()
    cell = read_json(tmp_path / manifest["cells"][0]["path"])
    assert len(cell["attempts"]) == 1
    attempt = cell["attempts"][0]
    assert attempt["status"] == "error"
    assert attempt["failure_reason"] == "AgentProtocolError: 3 consecutive execution/action failures"
    assert 0 < cell["elapsed_seconds"] < bounded.budget_seconds
    trajectory = read_json(tmp_path / attempt["artifact_dir"] / "trajectory.json")
    assert trajectory["consecutive_errors"] == 3
    assert len(trajectory["turns"]) == 3
    assert attempt["tool_calls"] == (0 if comments else 3)
    assert all(turn["agent_feedback"] for turn in trajectory["turns"])
    assert "execution_feedback" not in trajectory["turns"][-1]["observation"]
    if diagnostic:
        saved = read_json(tmp_path / "checkpoints/fixture_1-7/agent.json")
        assert saved["consecutive_errors"] == 2
        assert attempt["timings"]["shared_checkpoint_preparation"] > 0


@pytest.mark.parametrize("require_executable", [False, True])
def test_comment_validation_can_continue_without_an_error_cutoff(config, tmp_path, require_executable):
    config = replace(config, agent=AgentProtocol(require_executable=require_executable),
                     max_attempts=1, conditions=[Condition("full_once", "full", 1.0, "never", 1)])
    clock, environments, actions, observations = Clock(), [], [], []
    engine = FakeEngine(clock)
    responses = iter(["```python\n# unable to authenticate\n```"] * 6 + ["```python\nvalue = 1\n```"])
    engine.tokenizer.decode = lambda *a, **kw: next(responses)

    def encode(text, **kwargs):
        observations.append(text)
        return [20]

    engine.tokenizer.encode = encode

    class ObservedEnvironment(FakeEnvironment):
        def execute(self, action, **kwargs):
            super().execute(action, **kwargs)
            actions.append(action)
            return "Execution successful."

        def completed(self):
            return bool(actions and actions[-1] == "value = 1")

    manifest = Runner(config, tmp_path, lambda _: engine,
                      lambda: ObservedEnvironment(clock, environments), clock=clock).run()
    cell = read_json(tmp_path / manifest["cells"][0]["path"])
    assert len(cell["attempts"]) == 1
    attempt = cell["attempts"][0]
    assert attempt["status"] == "completed"
    assert attempt["tool_calls"] == len(actions) == (1 if require_executable else 7)
    trajectory = read_json(tmp_path / attempt["artifact_dir"] / "trajectory.json")
    assert len(trajectory["turns"]) == 7
    assert attempt["timings"]["inference"] == 14
    assert attempt["timings"]["tool"] == 3 * len(actions)
    assert all("agent_feedback" not in turn for turn in trajectory["turns"])
    if require_executable:
        assert actions == ["value = 1"]
        assert all(turn["action"] is None for turn in trajectory["turns"][:6])
        assert all("Invalid action:" in text and "comment-only" in text for text in observations[:6])
    else:
        assert actions[:6] == ["# unable to authenticate"] * 6
        assert all("Execution successful." in text for text in observations)


def test_agent_successful_execution_resets_error_streak(config, tmp_path):
    bounded = replace(config, agent=AgentProtocol(3), max_attempts=1,
                      conditions=[Condition("full_once", "full", 1.0, "never", 1)])
    clock, environments = Clock(), []
    engine = FakeEngine(clock)

    class CorrectingEnvironment(FakeEnvironment):
        def execute(self, action, **kwargs):
            super().execute(action, **kwargs)
            return "Execution failed. TypeError: wrong shape" if self.count % 3 else "inspected"

        def completed(self):
            return self.count == 6

    manifest = Runner(bounded, tmp_path, lambda _: engine,
                      lambda: CorrectingEnvironment(clock, environments), clock=clock).run()
    cell = read_json(tmp_path / manifest["cells"][0]["path"])
    attempt = cell["attempts"][0]
    assert attempt["status"] == "completed"
    trajectory = read_json(tmp_path / attempt["artifact_dir"] / "trajectory.json")
    assert [t["consecutive_errors"] for t in trajectory["turns"]] == [1, 2, 0, 1, 2, 0]


def test_policy_observables_and_once_limit(config):
    t = config.triggers
    assert not decide("dynamic", t, 100, 0, 0).triggered
    assert decide("dynamic", t, 100, 1, 0).triggered
    assert not decide("dynamic", t, 100, 20, 1).triggered
    assert not decide("never", t, 100, 20, 0).triggered
    assert decide("fixed", t, 0, 1, 0).triggered


def test_shared_budget_and_charged_failure():
    clock = Clock()
    budget = Budget(5, clock=clock)
    with budget.charge("reset"):
        clock.advance(2)
    with pytest.raises(BudgetExpired):
        with budget.charge("tool"):
            clock.advance(4)
    assert budget.elapsed == 6
    assert budget.timings == {"reset": 2, "tool": 4}
    assert budget.remaining == 0


def test_attempt_isolation_recovery_and_offline_scoring(config, tmp_path):
    runner, cells, engines, environments = run_fixture(config, tmp_path)
    cell = cells[0]
    assert [a["status"] for a in cell["attempts"]] == ["completed", "completed"]
    assert len(environments) == 2 and all(e.count == 2 for e in environments)
    assert engines[0].recoveries == [[10, 30, 20], [10, 30, 20]]
    assert all(a["rebuilds"] == 1 for a in cell["attempts"])
    assert all("reset" in a["timings"] and "tool" in a["timings"] for a in cell["attempts"])
    assert not (tmp_path / "scores.json").exists()
    assert runner.run(resume=True)["status"] == "completed"
    assert len(engines) == 1


def test_timeout_consumes_budget_without_free_retry(config, tmp_path):
    config = replace(config, budget_seconds=5)
    _, cells, _, _ = run_fixture(config, tmp_path)
    assert len(cells[0]["attempts"]) == 1
    assert cells[0]["attempts"][0]["status"] == "timeout"
    assert cells[0]["elapsed_seconds"] >= 5


@pytest.mark.parametrize("missing_artifact", [False, True])
@pytest.mark.parametrize("load_failure", [False, True])
def test_resume_inflight_conservatively_consumes_budget(
    config, tmp_path, missing_artifact, load_failure
):
    runner, cells, engines, _ = run_fixture(config, tmp_path)
    manifest = read_json(tmp_path / "manifest.json")
    manifest["status"] = "running"
    write_json(tmp_path / "manifest.json", manifest)
    cell = cells[0]
    cell.update(completed=False, inflight=True, elapsed_seconds=1)
    cell["attempts"] = cell["attempts"][:1]
    cell["attempts"][0]["status"] = "running"
    write_json(tmp_path / manifest["cells"][0]["path"], cell)
    attempt_path = tmp_path / cell["attempts"][0]["artifact_dir"] / "attempt.json"
    if missing_artifact:
        attempt_path.unlink()
    else:
        write_json(attempt_path, cell["attempts"][0])
    if load_failure:
        def unavailable(_condition):
            raise MemoryCapExceeded("model does not fit")

        runner.engine_factory = unavailable
    runner.run(resume=True)
    restored = read_json(tmp_path / manifest["cells"][0]["path"])
    assert restored["attempts"][0]["status"] == "interrupted"
    assert restored["elapsed_seconds"] == config.budget_seconds
    assert len(restored["attempts"]) == 1
    assert restored["completed"] and not restored["inflight"]
    assert read_json(attempt_path) == restored["attempts"][0]
    assert restored["attempts"][0]["reserved_budget_seconds"] == config.budget_seconds - 1
    assert restored["attempts"][0]["budget_elapsed_seconds"] == config.budget_seconds
    if not load_failure:
        assert engines[-1].starts == []


def test_resume_rejects_config_change(config, tmp_path):
    runner, _, _, _ = run_fixture(config, tmp_path)
    runner.config = replace(config, budget_seconds=200)
    with pytest.raises(ValueError, match="configuration"):
        runner.run(resume=True)


def test_model_memory_infeasibility_retains_task_denominator(config, tmp_path):
    def unavailable(condition):
        raise MemoryCapExceeded("model does not fit")

    runner = Runner(config, tmp_path, unavailable, lambda: None)
    manifest = runner.run()
    assert manifest["status"] == "completed"
    cell = read_json(tmp_path / manifest["cells"][0]["path"])
    assert cell["infeasible"] and cell["completed"]
    assert cell["attempts"] == []
    assert cell["elapsed_seconds"] == 0


def test_resume_refuses_changed_native_runtime(config, tmp_path):
    runner, _, engines, _ = run_fixture(config, tmp_path)
    manifest = read_json(tmp_path / "manifest.json")
    manifest.update(status="running", engine={"backend": "old"})
    write_json(tmp_path / "manifest.json", manifest)
    with pytest.raises(ValueError, match="runtime"):
        runner.run(resume=True)
    assert not engines[-1].starts


def test_warmup_failure_closes_initialized_engine(config, tmp_path):
    engine = FakeEngine(Clock())
    closed = []

    def failed():
        raise RuntimeError("kernel compile failed")

    engine.warmup = failed
    engine.close = lambda: closed.append(True)
    runner = Runner(config, tmp_path, lambda _: engine, lambda: None)
    with pytest.raises(RuntimeError, match="kernel"):
        runner.run()
    assert closed == [True]


def test_artifact_finalization_cannot_create_over_budget_success(config, tmp_path, monkeypatch):
    from comet import runner as module

    clock, environments = Clock(), []
    engine = FakeEngine(clock)
    original = module.write_json

    def slow_final_write(path, value):
        original(path, value)
        if path.name == "attempt.json":
            clock.advance(100)

    monkeypatch.setattr(module, "write_json", slow_final_write)
    runner = Runner(
        config,
        tmp_path,
        lambda _: engine,
        lambda: FakeEnvironment(clock, environments),
        clock=clock,
    )
    manifest = runner.run()
    cell = read_json(tmp_path / manifest["cells"][0]["path"])
    assert len(cell["attempts"]) == 1
    assert cell["attempts"][0]["status"] == "timeout"


def test_cell_journal_cost_cannot_escape_shared_budget(config, tmp_path, monkeypatch):
    from comet import runner as module

    clock, environments = Clock(), []
    original = module.write_json

    def slow_journal(path, value):
        original(path, value)
        if path.name == "cell.json" and not value.get("inflight"):
            clock.advance(100)

    monkeypatch.setattr(module, "write_json", slow_journal)
    runner = Runner(
        config,
        tmp_path,
        lambda _: FakeEngine(clock),
        lambda: FakeEnvironment(clock, environments),
        clock=clock,
    )
    manifest = runner.run()
    cell = read_json(tmp_path / manifest["cells"][0]["path"])
    assert cell["attempts"][0]["status"] == "timeout"
    assert len(cell["attempts"]) == 1


@pytest.mark.parametrize("failure", [False, True])
def test_gpu_cleanup_is_charged_and_cannot_skip_environment_close(config, tmp_path, failure):
    clock, environments = Clock(), []
    engine = FakeEngine(clock)

    def synchronize():
        clock.advance(150)
        if failure:
            raise MemoryCapExceeded("asynchronous GPU failure")

    def environment():
        result = FakeEnvironment(clock, environments)
        result.close = lambda: setattr(result, "closed", True)
        return result

    engine.synchronize = synchronize
    runner = Runner(config, tmp_path, lambda _: engine, environment, clock=clock)
    manifest = runner.run()
    cell = read_json(tmp_path / manifest["cells"][0]["path"])
    assert cell["attempts"][0]["status"] == ("oom" if failure else "timeout")
    assert cell["attempts"][0]["timings"]["cleanup"] == 150
    assert environments[0].closed


def test_diagnostic_branches_identical_state_and_charges_preparation(config, tmp_path):
    conditions = [
        Condition("full", "full", 1.0, "never", 1),
        Condition("compressed", "streamingllm", 0.5, "fixed", 1),
    ]
    config = replace(
        config,
        stage="diagnostic",
        max_attempts=1,
        checkpoint_after_tool_calls=1,
        conditions=conditions,
    )
    _, cells, engines, environments = run_fixture(config, tmp_path)
    assert [c["attempts"][0]["status"] for c in cells] == ["completed", "completed"]
    assert [e.count for e in environments] == [1, 2, 2]
    assert engines[0].recoveries == [[10, 30, 20]]
    assert all(c["attempts"][0]["timings"]["shared_checkpoint_preparation"] == 9 for c in cells)
    assert all(c["elapsed_seconds"] >= 19 for c in cells)
    trajectories = [
        read_json(tmp_path / c["attempts"][0]["artifact_dir"] / "trajectory.json") for c in cells
    ]
    assert trajectories[0]["turns"][0] == trajectories[1]["turns"][0]


@pytest.mark.parametrize("completion_after", [1, 2])
def test_diagnostic_rejects_completed_source_before_or_at_boundary(config, tmp_path, completion_after):
    config = replace(config, stage="diagnostic", max_attempts=1, checkpoint_after_tool_calls=2,
                     conditions=[Condition("full", "full", 1.0, "never", 1),
                                 Condition("compressed", "streamingllm", 0.5, "fixed", 1)])
    clock, environments = Clock(), []
    engine = FakeEngine(clock)

    class CompletedEnvironment(FakeEnvironment):
        def completed(self):
            self.clock.advance(1)
            return self.count >= completion_after

    runner = Runner(config, tmp_path, lambda _: engine,
                    lambda: CompletedEnvironment(clock, environments), clock=clock)
    manifest = runner.run()
    source = tmp_path / "checkpoints/fixture_1-7"
    preparation = read_json(source / "preparation.json")
    assert preparation["status"] == "failed"
    assert preparation["source_completed"] is True and not preparation["checkpoint_eligible"]
    assert preparation["timings"]["checkpoint_eligibility"] == 1
    assert preparation["tool_calls"] == completion_after
    assert (source / "trajectory.json").is_file()
    assert not any((source / name).exists() for name in ("engine", "environment", "agent.json"))
    assert [environment.count for environment in environments] == [completion_after, 0, 0]
    for reference in manifest["cells"]:
        attempt = read_json(tmp_path / reference["path"])["attempts"][0]
        assert attempt["status"] == "infeasible" and attempt["tool_calls"] == 0
        assert "at or before" in attempt["failure_reason"]
        assert attempt["timings"]["shared_checkpoint_preparation"] == preparation["elapsed_seconds"]
        assert attempt["metrics"]["estimated_flops"] == 100 * completion_after
        assert attempt["checkpoint_preparation"]["tool_calls"] == completion_after
        assert "reset" not in attempt["timings"]
        trajectory = read_json(tmp_path / attempt["artifact_dir"] / "trajectory.json")
        assert trajectory["raw_token_ids"] == [] and trajectory["turns"] == []
    assert len(engine.starts) == 1


@pytest.mark.parametrize("exhausted_budget", [False, True])
def test_diagnostic_failed_checkpoint_preserves_prefix_costs_once(config, tmp_path, exhausted_budget):
    from comet.errors import UnsupportedPath

    config = replace(config, stage="diagnostic", max_attempts=1, checkpoint_after_tool_calls=1,
                     budget_seconds=10 if exhausted_budget else config.budget_seconds,
                     conditions=[Condition("full", "full", 1.0, "never", 1)])
    clock, environments = Clock(), []
    engine = FakeEngine(clock)

    class UnsupportedEnvironment(FakeEnvironment):
        def checkpoint(self, path):
            if exhausted_budget:
                return super().checkpoint(path)
            self.clock.advance(1)
            raise UnsupportedPath("unsupported fixture execution value")

    runner = Runner(config, tmp_path, lambda _: engine,
                    lambda: UnsupportedEnvironment(clock, environments), clock=clock)
    manifest = runner.run()
    preparation = read_json(tmp_path / "checkpoints/fixture_1-7/preparation.json")
    attempt = read_json(tmp_path / manifest["cells"][0]["path"])["attempts"][0]
    source_status = "completed" if exhausted_budget else "failed"
    assert preparation["status"] == source_status and preparation["checkpoint_eligible"]
    assert attempt["status"] == ("timeout" if exhausted_budget else "infeasible")
    assert attempt["tool_calls"] == 0
    assert attempt["metrics"]["estimated_flops"] == preparation["metrics"]["estimated_flops"] == 100
    assert attempt["metrics"]["metric_coverage"] == preparation["metrics"]["metric_coverage"]
    assert attempt["checkpoint_preparation"] == {
        "artifact_dir": "checkpoints/fixture_1-7", "status": source_status, "tool_calls": 1, "rebuilds": 0,
    }
    assert attempt["timings"]["shared_checkpoint_preparation"] == preparation["elapsed_seconds"]
    assert preparation["elapsed_seconds"] == (9 if exhausted_budget else 8)
    assert attempt["elapsed_seconds"] == (11 if exhausted_budget else 8)
    assert attempt["timings"].get("reset", 0) == (2 if exhausted_budget else 0)
    assert "checkpoint_restore" not in attempt["timings"]
    assert len(engine.starts) == (2 if exhausted_budget else 1)
    assert [environment.count for environment in environments] == [1, 0]
    runner.run(resume=True)
    assert len(environments) == 2
    assert read_json(tmp_path / manifest["cells"][0]["path"])["attempts"][0] == attempt


@pytest.mark.parametrize("failure", ["close", "memory"])
@pytest.mark.parametrize("primary_error", [False, True])
def test_diagnostic_cleanup_preserves_prefix_and_primary_error(config, tmp_path, failure, primary_error):
    config = replace(config, stage="diagnostic", max_attempts=1, checkpoint_after_tool_calls=1,
                     conditions=[Condition("full", "full", 1.0, "never", 1)])
    clock, environments = Clock(), []

    class Engine(FakeEngine):
        def memory_stats(self):
            self.clock.advance(3)
            if failure == "memory":
                raise RuntimeError("fixture memory probe failed")
            return super().memory_stats()

    class Environment(FakeEnvironment):
        def checkpoint(self, path):
            if primary_error:
                self.clock.advance(1)
                raise RuntimeError("fixture checkpoint failed")
            return super().checkpoint(path)

        def close(self):
            if self.count:
                self.clock.advance(2)
                if failure == "close":
                    raise RuntimeError("fixture close failed")

    engine = Engine(clock)
    runner = Runner(config, tmp_path, lambda _: engine, lambda: Environment(clock, environments), clock=clock)
    manifest = runner.run()
    source = read_json(tmp_path / "checkpoints/fixture_1-7/preparation.json")
    attempt = read_json(tmp_path / manifest["cells"][0]["path"])["attempts"][0]
    assert source["status"] == "failed" and source["tool_calls"] == 1 and source["rebuilds"] == 0
    assert source["metrics"]["estimated_flops"] == attempt["metrics"]["estimated_flops"] == 100
    assert source["timings"]["cleanup"] == 5
    assert source["elapsed_seconds"] == (13 if primary_error else 14)
    if primary_error:
        assert source["failure_reason"] == "RuntimeError: fixture checkpoint failed"
    else:
        assert "cleanup failed" in source["failure_reason"] if failure == "close" else \
            "memory measurement failed" in source["failure_reason"]
    if failure == "close":
        assert source["cleanup_errors"] == ["RuntimeError: fixture close failed"]
    else:
        assert source["metrics"]["memory_error"] == "RuntimeError: fixture memory probe failed"
    assert attempt["status"] == "infeasible" and len(engine.starts) == 1
    assert attempt["timings"]["shared_checkpoint_preparation"] == source["elapsed_seconds"]


def test_diagnostic_cleanup_overrun_invalidates_source_but_retains_costs(config, tmp_path):
    config = replace(config, stage="diagnostic", max_attempts=1, checkpoint_after_tool_calls=1,
                     budget_seconds=10, conditions=[Condition("full", "full", 1.0, "never", 1)])
    clock, environments = Clock(), []
    engine = FakeEngine(clock)

    class SlowCloseEnvironment(FakeEnvironment):
        def close(self):
            if self.count:
                self.clock.advance(2)

    runner = Runner(config, tmp_path, lambda _: engine,
                    lambda: SlowCloseEnvironment(clock, environments), clock=clock)
    manifest = runner.run()
    source = read_json(tmp_path / "checkpoints/fixture_1-7/preparation.json")
    attempt = read_json(tmp_path / manifest["cells"][0]["path"])["attempts"][0]
    assert source["status"] == "failed"
    assert source["failure_reason"] == "Budget expired during preparation cleanup"
    assert source["timings"]["cleanup"] == 2 and source["elapsed_seconds"] == 11
    assert source["metrics"]["estimated_flops"] == attempt["metrics"]["estimated_flops"] == 100
    assert attempt["status"] == "infeasible" and len(engine.starts) == 1
    assert attempt["timings"]["shared_checkpoint_preparation"] == 11


def test_evaluator_not_reachable_from_runner():
    import ast

    import comet.runner

    tree = ast.parse(Path(comet.runner.__file__).read_text())
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert "comet.evaluation" not in imports
    assert "appworld.evaluator" not in imports
