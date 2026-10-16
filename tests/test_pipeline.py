from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from comet.artifacts import read_json, write_json
from comet.budget import Budget
from comet.config import Condition, Experiment, attempt_seed, comparison_matrix
from comet.errors import BudgetExpired, MemoryCapExceeded
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
                "model_revision": "a" * 40,
                "tokenizer_revision": "a" * 40,
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


def test_matrix_and_seed_pairing():
    matrix = comparison_matrix(4)
    assert len(matrix) == 29
    assert len({c.id for c in matrix}) == 29
    assert {c.retention for c in matrix if c.method != "full"} == {0.25, 0.5, 0.8}
    assert len({attempt_seed(42, i) for i in range(4)}) == 4
    assert attempt_seed(42, 0) == attempt_seed(42, 0)


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


def test_resume_inflight_conservatively_consumes_budget(config, tmp_path):
    runner, cells, engines, _ = run_fixture(config, tmp_path)
    manifest = read_json(tmp_path / "manifest.json")
    manifest["status"] = "running"
    write_json(tmp_path / "manifest.json", manifest)
    cell = cells[0]
    cell.update(completed=False, inflight=True, elapsed_seconds=1)
    cell["attempts"] = cell["attempts"][:1]
    cell["attempts"][0]["status"] = "running"
    write_json(tmp_path / manifest["cells"][0]["path"], cell)
    runner.run(resume=True)
    restored = read_json(tmp_path / manifest["cells"][0]["path"])
    assert restored["attempts"][0]["status"] == "interrupted"
    assert restored["elapsed_seconds"] == config.budget_seconds
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


def test_evaluator_not_reachable_from_runner():
    import ast

    import comet.runner

    tree = ast.parse(Path(comet.runner.__file__).read_text())
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert "comet.evaluation" not in imports
    assert "appworld.evaluator" not in imports
