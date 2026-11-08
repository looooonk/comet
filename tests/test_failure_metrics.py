from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_pipeline import Clock, FakeEngine, FakeEnvironment
from test_pipeline import config as config

from comet import engine as engine_module
from comet.artifacts import read_json, write_json
from comet.engine.native import MiniSGLangEngine
from comet.errors import BudgetExpired, MemoryCapExceeded
from comet.runner import Runner


class OutOfMemoryError(RuntimeError):
    pass


@pytest.fixture
def native_engine(monkeypatch):
    import sys

    class DetokenizeMsg:
        def __init__(self, next_token):
            self.next_token = next_token

    class TokenizerErrorMsg:
        pass

    monkeypatch.setitem(sys.modules, "minisgl.core", SimpleNamespace(SamplingParams=SimpleNamespace))
    monkeypatch.setitem(sys.modules, "minisgl.message", SimpleNamespace(
        DetokenizeMsg=DetokenizeMsg, TokenizerErrorMsg=TokenizerErrorMsg, UserMsg=SimpleNamespace,
    ))
    clock = Clock()
    monkeypatch.setattr(engine_module.native, "monotonic", clock)
    engine = MiniSGLangEngine.__new__(MiniSGLangEngine)
    engine._session_id, engine._uid, engine._next_logits = "test", 0, None
    engine._raw, engine._phase, engine._semantic = [], [], []
    engine._recoveries = 0
    engine.settings = SimpleNamespace(max_context_tokens=100, peak_vram_bytes=100,
                                      workspace_reserve_bytes=5, method="agentkv")
    engine.torch = SimpleNamespace(
        tensor=lambda values, **kwargs: list(values), int32=None, inference_mode=nullcontext,
        cuda=SimpleNamespace(synchronize=lambda: None, OutOfMemoryError=OutOfMemoryError,
                             mem_get_info=lambda: (100, 100), memory_reserved=lambda: 0,
                             memory_allocated=lambda: 0),
    )
    engine._append_phases = lambda values: None
    engine._check_deadline = lambda deadline: None
    engine._sample_memory = lambda: None
    engine.memory_stats = lambda: {"peak_total_vram_bytes": 42}
    engine.parameter_count, engine._attention_flop_factor = 10, 4
    prefill = SimpleNamespace(reqs=[SimpleNamespace(extend_len=2, physical_cached_len=0)],
                              is_prefill=True, size=1)
    decode = SimpleNamespace(reqs=[SimpleNamespace(extend_len=1, physical_cached_len=2)],
                             is_prefill=False, size=1)
    batches = iter([prefill, decode])
    scheduler = engine.scheduler = SimpleNamespace(
        engine=SimpleNamespace(stream=SimpleNamespace(wait_stream=lambda other: None), num_pages=100),
        stream=None, engine_stream_ctx=nullcontext(),
        prefill_manager=SimpleNamespace(runnable=True),
        decode_manager=SimpleNamespace(runnable=False),
        _process_one_msg=lambda message: None,
        _schedule_next_batch=lambda: SimpleNamespace(batch=next(batches)),
    )

    def process(data):
        engine._raw.append(30)
        engine._replies.append(DetokenizeMsg(30))

    scheduler._process_last_data = process
    return engine, clock


@pytest.mark.parametrize("failure", [BudgetExpired("timeout"), OutOfMemoryError("oom")])
def test_native_generation_preserves_completed_work_and_failed_forward_time(native_engine, failure):
    engine, clock = native_engine

    def forward(value):
        clock.advance(2)
        if not value.batch.is_prefill:
            raise failure
        return None

    engine.scheduler._forward = forward
    expected = MemoryCapExceeded if isinstance(failure, OutOfMemoryError) else BudgetExpired
    with pytest.raises(expected):
        engine.generate([10, 20], 2, 0.7, 0.9, 100)
    progress = engine.last_generation
    assert progress["status"] == "failed"
    assert progress["prompt_tokens"] == 2
    assert progress["decode_tokens"] == 0
    assert progress["token_ids"] == [30]
    assert engine.raw_token_ids == [10, 20, 30]
    assert progress["estimated_flops"] == 52
    assert progress["incomplete_forward_estimated_flops"] == 32
    assert progress["incomplete_forward_tokens"] == 1
    assert progress["prefill_seconds"] == progress["decode_seconds"] == 2


@pytest.mark.parametrize("failure", [BudgetExpired("timeout"), OutOfMemoryError("oom")])
def test_native_rebuild_failure_consumes_allowance_and_preserves_partial_cost(native_engine, failure):
    engine, clock = native_engine
    engine._raw = [10]

    def prefill(deadline):
        assert engine.recovery_count == 1
        assert engine.last_recovery["admitted"] is True
        progress = engine._last_recovery
        progress.update(prompt_tokens=1, estimated_flops=20)
        clock.advance(3)
        raise failure

    engine._prefill_history = prefill
    expected = MemoryCapExceeded if isinstance(failure, OutOfMemoryError) else BudgetExpired
    with pytest.raises(expected):
        engine.recover([10, 20], 100)
    progress = engine.last_recovery
    assert progress["status"] == "failed"
    assert progress["admitted"] and progress["allowance_consumed"]
    assert progress["prompt_tokens"] == 1 and progress["estimated_flops"] == 20
    assert progress["seconds"] == 3
    assert engine.raw_token_ids == [10, 20]
    assert engine.recover([10, 20], 100).reason == "recovery_limit"


def run_engine(config, output, engine):
    clock, environments = engine.clock, []
    runner = Runner(replace(config, max_attempts=1,
                            conditions=[replace(config.conditions[0], max_attempts=1)]),
                    output, lambda _: engine, lambda: FakeEnvironment(clock, environments), clock=clock)
    manifest = runner.run()
    cell = read_json(output / manifest["cells"][0]["path"])
    return runner, cell, cell["attempts"][0]


@pytest.mark.parametrize("failure,status", [(BudgetExpired("timeout"), "timeout"),
                                            (MemoryCapExceeded("oom"), "oom")])
def test_runner_retains_partial_generation_metrics_and_primary_failure(config, tmp_path, failure, status):
    engine = FakeEngine(Clock())

    def generate(tokens, **kwargs):
        engine.raw_token_ids.extend(tokens + [30])
        engine.clock.advance(3)
        engine.last_generation = {
            "status": "failed", "token_ids": [30], "prompt_tokens": 1, "decode_tokens": 0,
            "estimated_flops": 12, "prefill_seconds": 1, "decode_seconds": 2,
            "incomplete_forward_tokens": 1, "incomplete_forward_estimated_flops": 8,
            "memory": {"peak_total_vram_bytes": 42},
        }
        raise failure

    def memory():
        raise RuntimeError("memory probe unavailable")

    engine.generate, engine.memory_stats = generate, memory
    _, cell, attempt = run_engine(config, tmp_path, engine)
    assert attempt["status"] == status
    assert attempt["failure_reason"] == str(failure)
    metrics = attempt["metrics"]
    assert metrics["generated_tokens"] == 1
    assert metrics["estimated_flops"] == 12
    assert metrics["decode_seconds"] == 2
    assert metrics["peak_total_vram_bytes"] == 42
    assert metrics["metric_coverage"]["estimated_flops"] == "lower_bound"
    assert metrics["metric_coverage"]["decode_seconds"] == "partial"
    assert "memory probe" in metrics["memory_error"]
    assert attempt["timings"]["inference"] == 3
    assert len(cell["attempts"]) == 1
    trajectory = read_json(tmp_path / attempt["artifact_dir"] / "trajectory.json")
    assert trajectory["raw_token_ids"] == [10, 30]


@pytest.mark.parametrize("failure,status", [(BudgetExpired("timeout"), "timeout"),
                                            (MemoryCapExceeded("oom"), "oom")])
def test_runner_journals_rebuild_before_execution_and_finalizes_failure(config, tmp_path, failure, status):
    engine = FakeEngine(Clock())

    def recover(tokens, **kwargs):
        saved = list(tmp_path.glob("cells/*/attempt-000/recovery_events.json"))
        assert len(saved) == 1
        event = read_json(saved[0])[-1]
        assert event["triggered"] and event["result"]["status"] == "pending"
        engine.clock.advance(3)
        engine.raw_token_ids = list(tokens)
        engine.last_recovery = {
            "status": "failed", "admitted": True, "allowance_consumed": True,
            "reason": None, "seconds": 3, "prompt_tokens": 2, "estimated_flops": 20,
            "input_tokens": len(tokens), "failure_reason": str(failure),
        }
        raise failure

    engine.recover = recover
    _, _, attempt = run_engine(config, tmp_path, engine)
    assert attempt["status"] == status
    assert attempt["rebuilds"] == 1
    result = attempt["recovery_events"][-1]["result"]
    assert result["status"] == "failed" and result["admitted"]
    assert result["allowance_consumed"]
    assert attempt["metrics"]["estimated_flops"] == 120
    assert attempt["metrics"]["rebuild_seconds"] == 3
    assert attempt["metrics"]["rebuild_prefill_tokens"] == 2
    assert attempt["metrics"]["metric_coverage"]["estimated_flops"] == "lower_bound"
    assert attempt["timings"]["rebuild"] == 3
    assert read_json(tmp_path / attempt["artifact_dir"] / "recovery_events.json") == attempt["recovery_events"]


@pytest.mark.parametrize("terminal", [False, True])
def test_interruption_preserves_newer_attempt_journal(config, tmp_path, terminal):
    runner, cell, attempt = run_engine(config, tmp_path, FakeEngine(Clock()))
    path = tmp_path / attempt["artifact_dir"] / "attempt.json"
    latest = dict(attempt, status="completed" if terminal else "running")
    latest["metrics"] = {"estimated_flops": 12}
    latest["recovery_events"] = [{"triggered": True, "result": {"status": "pending"}}]
    write_json(path, latest)
    original = path.read_bytes()
    cell.update(inflight=True, completed=False, elapsed_seconds=2)
    cell["attempts"][0] = {**attempt, "status": "running", "metrics": {}, "recovery_events": []}
    runner._interrupt_cell(cell)
    assert cell["attempts"][0]["metrics"] == latest["metrics"]
    assert cell["attempts"][0]["recovery_events"] == latest["recovery_events"]
    assert cell["elapsed_seconds"] == config.budget_seconds
    if terminal:
        assert cell["attempts"][0]["status"] == "completed"
        assert path.read_bytes() == original
        observed = max(attempt.get("budget_elapsed_seconds", 0), 2 + attempt["elapsed_seconds"])
        assert cell["observed_elapsed_seconds"] == observed
        assert cell["reserved_budget_seconds"] == config.budget_seconds - observed
    else:
        assert cell["attempts"][0]["status"] == "interrupted"
        assert read_json(path) == cell["attempts"][0]


@pytest.mark.parametrize("observed", [99, 100, 120])
def test_terminal_journal_cannot_preserve_success_at_or_beyond_budget(config, tmp_path, observed):
    runner, cell, attempt = run_engine(config, tmp_path, FakeEngine(Clock()))
    path = tmp_path / attempt["artifact_dir"] / "attempt.json"
    latest = dict(attempt, status="completed", elapsed_seconds=observed - 2,
                  budget_elapsed_seconds=observed)
    write_json(path, latest)
    original = path.read_bytes()
    cell.update(inflight=True, completed=False, elapsed_seconds=2)
    cell["attempts"][0] = {**attempt, "status": "running"}

    runner._interrupt_cell(cell)

    finalized = cell["attempts"][0]
    assert cell["observed_elapsed_seconds"] == observed
    assert cell["reserved_budget_seconds"] == max(0, config.budget_seconds - observed)
    assert cell["elapsed_seconds"] == max(config.budget_seconds, observed)
    if observed < config.budget_seconds:
        assert finalized["status"] == "completed"
        assert path.read_bytes() == original
    else:
        assert finalized["status"] == "timeout"
        assert "shared budget" in finalized["failure_reason"]
        assert finalized["budget_elapsed_seconds"] == observed
        assert read_json(path) == finalized
