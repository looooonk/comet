import hashlib
from types import SimpleNamespace

import pytest

from comet import history_benchmark as benchmark
from comet.artifacts import read_json, write_json
from comet.engine import retention_target
from comet.engine.contracts import MODEL_REVISION
from comet.errors import MemoryCapExceeded, UnsupportedPath


class Tensor(list):
    device = "cuda:0"

    def __getitem__(self, index):
        value = super().__getitem__(index)
        return Tensor(value) if isinstance(index, slice) else value


class Sampler:
    device = "cuda:0"

    def sample(self, logits, args):
        raise AssertionError("Ordinary sampling must not run during forced replay")


class Manager:
    def _select_compaction_indices(self):
        return [1]

    def compact_session_req(self):
        return None


class Engine:
    kv_bytes_per_token = 4

    def __init__(self, settings, *, fail_method=None, device="fixture GPU"):
        self.settings, self.fail_method, self.device = settings, fail_method, device
        self.scheduler = SimpleNamespace(engine=SimpleNamespace(sampler=Sampler()), eviction_manager=Manager())
        self.torch = SimpleNamespace(int64="int64", tensor=lambda values, **kwargs: Tensor(values),
                                     cuda=SimpleNamespace(mem_get_info=lambda: (800, 1000)))
        self.raw_token_ids, self.calls = [], []
        self.closed, self.logical = False, 0
        self.last_generation = {}

    def warmup(self, **kwargs):
        pass

    def provenance(self):
        return {"device_name": self.device, "minisgl_revision": "fixture"}

    def set_policy(self, method, retention):
        self.method, self.retention = method, retention

    def start(self, seed):
        self.raw_token_ids = []
        self.last_generation = {}
        self.seed = seed

    def generate(self, prefix, count, temperature, top_p, deadline, *, ignore_eos):
        assert temperature == 0 and top_p == 1 and ignore_eos
        self.raw_token_ids = list(prefix)
        self.calls.append((self.method, self.retention, list(prefix), count, self.seed))
        generated = []
        logits = SimpleNamespace(ndim=2, shape=(1, 100), device="cuda:0")
        for _ in range(count):
            token = self.scheduler.engine.sampler.sample(logits, None)[0]
            generated.append(token)
            self.raw_token_ids.append(token)
            if self.method != "full":
                self.scheduler.eviction_manager._select_compaction_indices()
                self.scheduler.eviction_manager.compact_session_req()
            if self.method == self.fail_method:
                self.last_generation = {"status": "failed", "token_ids": generated,
                                        "estimated_flops": 5, "prefill_seconds": 1}
                raise MemoryCapExceeded("fixture workspace failure")
        self.logical = len(self.raw_token_ids) - 1
        self.last_generation = {
            "status": "completed", "token_ids": generated, "prompt_tokens": len(prefix),
            "decode_tokens": count - 1, "prefill_seconds": 2, "decode_seconds": (count - 1) / 2,
            "estimated_flops": 10, "memory": self.memory_stats(),
        }
        return self.last_generation

    def memory_stats(self):
        occupied = retention_target(self.logical, self.retention, self.method)
        return {"physical_cached_tokens": occupied, "logical_cached_tokens": self.logical,
                "peak_kv_bytes": self.logical * 4, "reserved_kv_bytes": 256,
                "peak_total_vram_bytes": 220}

    def synchronize(self):
        pass

    def close(self):
        self.closed = True


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    source = tmp_path / "source"
    relative = "cells/task-full-7/attempt-000/trajectory.json"
    write_json(source / relative, {"raw_token_ids": list(range(80)),
                                   "turns": [{"action": "raise AssertionError('never execute')"}]})
    model = {"model": "Qwen/Qwen3-8B", "model_revision": MODEL_REVISION,
             "tokenizer_revision": MODEL_REVISION}
    write_json(source / "manifest.json", {
        "status": "completed", "run_id": "fixture", "config": {"split": "dev", "engine": model},
        "engine": model, "cells": [{"path": "cells/task-full-7/cell.json"}],
    })
    write_json(source / "cells/task-full-7/cell.json", {
        "task_id": "task", "condition": {"method": "full"}, "attempts": [{
            "artifact_dir": "cells/task-full-7/attempt-000", "seed": 7,
            "attempt_index": 0, "status": "timeout",
        }],
    })
    spec = {
        "schema_version": 1, "benchmark_id": "fixture",
        "histories": [{"trajectory": relative,
                       "sha256": hashlib.sha256((source / relative).read_bytes()).hexdigest()}],
        "logical_lengths": [24, 40], "decode_tokens": 2, "repetitions": 1,
        "seed": 7, "cell_timeout_seconds": 10, "warmup_timeout_seconds": 10,
        "engine": {"max_context_tokens": 64, "peak_vram_bytes": 1000,
                   "workspace_reserve_bytes": 100, "prefill_chunk_tokens": 4,
                   "device_name": "fixture GPU"},
    }
    monkeypatch.setattr(benchmark, "provenance", lambda: {
        "code_commit": "fixture", "local_changes": "", "source_hashes": {},
        "installed_packages": {}, "python": "fixture",
    })
    return spec, source, tmp_path / "model", tmp_path / "output"


@pytest.mark.parametrize("change,match", [
    (lambda spec: spec["histories"][0].update(sha256="wrong"), "SHA-256"),
    (lambda spec: spec.update(logical_lengths=[63]), "context"),
    (lambda spec: spec.update(decode_tokens=0), "positive"),
    (lambda spec: spec["engine"].update(max_context_tokens=128), None),
])
def test_prepare_inputs_validates_declared_history_and_limits(inputs, change, match):
    spec, source, model, _ = inputs
    change(spec)
    if match:
        with pytest.raises(ValueError, match=match):
            benchmark.prepare_inputs(spec, source, model)
    else:
        settings, histories, metadata = benchmark.prepare_inputs(spec, source, model)
        assert settings.model_revision == MODEL_REVISION
        assert histories[0]["status"] == "timeout"
        assert histories[0]["raw_token_ids"] == list(range(43))
        assert metadata["manifest"]["config"]["split"] == "dev"


def test_source_model_provenance_and_transcript_length_are_required(inputs):
    spec, source, model, _ = inputs
    path = source / "manifest.json"
    manifest = read_json(path)
    manifest["engine"]["tokenizer_revision"] = "different"
    write_json(path, manifest)
    with pytest.raises(ValueError, match="provenance"):
        benchmark.prepare_inputs(spec, source, model)
    manifest["engine"]["tokenizer_revision"] = MODEL_REVISION
    write_json(path, manifest)
    spec["logical_lengths"] = [79]
    spec["engine"]["max_context_tokens"] = 128
    with pytest.raises(ValueError, match="shorter"):
        benchmark.prepare_inputs(spec, source, model)


def test_sampler_and_profiler_hooks_restore_after_exception(inputs):
    spec, source, model, _ = inputs
    settings, _, _ = benchmark.prepare_inputs(spec, source, model)
    engine = Engine(settings)
    sampler, manager = engine.scheduler.engine.sampler, engine.scheduler.eviction_manager
    with pytest.raises(UnsupportedPath, match="row"):
        with benchmark.profile_eviction(engine) as profile, benchmark.force_recorded_tokens(engine, [1]):
            manager._select_compaction_indices()
            sampler.sample(SimpleNamespace(ndim=2, shape=(2, 100), device="cuda:0"), None)
    assert "sample" not in vars(sampler)
    assert "_select_compaction_indices" not in vars(manager)
    assert "compact_session_req" not in vars(manager)
    assert profile["selection"]["calls"] == 1
    assert profile["compaction"]["calls"] == 0


def test_forced_sampler_rejects_extra_or_missing_output_calls(inputs):
    spec, source, model, _ = inputs
    settings, _, _ = benchmark.prepare_inputs(spec, source, model)
    engine = Engine(settings)
    sampler = engine.scheduler.engine.sampler
    logits = SimpleNamespace(ndim=2, shape=(1, 100), device="cuda:0")
    with pytest.raises(UnsupportedPath, match="exceeds"):
        with benchmark.force_recorded_tokens(engine, [7]):
            assert sampler.sample(logits, None) == [7]
            sampler.sample(logits, None)
    with pytest.raises(UnsupportedPath, match="stopped before"):
        with benchmark.force_recorded_tokens(engine, [7, 8]):
            sampler.sample(logits, None)
    assert "sample" not in vars(sampler)


def test_forced_replay_matrix_preserves_identical_histories_and_separate_instrumentation(inputs):
    spec, source, model, output = inputs
    engines = []

    def factory(settings):
        engine = Engine(settings)
        engines.append(engine)
        return engine

    result = benchmark.run_benchmark(spec, source, model, output, engine_factory=factory)
    assert result["cell_status_counts"] == {"completed": 20}
    assert engines[0].closed
    assert len(engines[0].calls) == 60
    for reference in result["cells"]:
        directory = output / "cells" / reference["id"]
        prefill, decode, instrumented = [read_json(directory / f"{name}.json") for name in benchmark.PASSES]
        assert prefill["memory"]["logical_cached_tokens"] == reference["logical_length"]
        assert decode["memory"]["logical_cached_tokens"] == reference["logical_length"] + spec["decode_tokens"]
        assert decode["generation"]["token_ids"] == list(range(reference["logical_length"], reference["logical_length"] + 3))
        assert decode["raw_token_sha256"] == instrumented["raw_token_sha256"]
        assert decode["decode_tokens_per_second"] == 2
        assert decode["eviction_overhead"] is None
        assert instrumented["eviction_overhead"]["selection"]["calls"] == (0 if reference["method"] == "full" else 3)
        assert prefill["occupied_kv_bytes"] == prefill["memory"]["physical_cached_tokens"] * 4
        assert prefill["total_vram_bytes"] == 200
    benchmark.run_benchmark(spec, source, model, output, resume=True, engine_factory=factory)
    assert len(engines) == 1


def test_failed_and_interrupted_cells_remain_without_free_retry(inputs):
    spec, source, model, output = inputs
    result = benchmark.run_benchmark(spec, source, model, output,
                                     engine_factory=lambda settings: Engine(settings, fail_method="rkv"))
    assert result["cell_status_counts"] == {"completed": 14, "oom": 6}
    first = output / "cells" / result["cells"][0]["id"] / "cell.json"
    cell = read_json(first)
    cell["status"] = "running"
    write_json(first, cell)
    completed_pass = first.parent / "prefill.json"
    original = completed_pass.read_bytes()

    def forbidden(settings):
        raise AssertionError("Terminal cells and interruptions must not start another engine")

    resumed = benchmark.run_benchmark(spec, source, model, output, resume=True, engine_factory=forbidden)
    assert resumed["cell_status_counts"] == {"completed": 13, "interrupted": 1, "oom": 6}
    assert read_json(first)["budget_accounted_seconds"] == spec["cell_timeout_seconds"]
    assert completed_pass.read_bytes() == original


def test_resume_rejects_runtime_changes_and_missing_completed_artifacts(inputs):
    spec, source, model, output = inputs
    result = benchmark.run_benchmark(spec, source, model, output, engine_factory=Engine)
    path = output / "cells" / result["cells"][-1]["id"] / "cell.json"
    path.unlink()
    with pytest.raises(ValueError, match="missing a cell"):
        benchmark.run_benchmark(spec, source, model, output, resume=True, engine_factory=Engine)
    result["status"] = "running"
    write_json(output / "manifest.json", result)
    with pytest.raises(ValueError, match="runtime or GPU"):
        benchmark.run_benchmark(spec, source, model, output, resume=True,
                                engine_factory=lambda settings: Engine(settings, device="different GPU"))
    spec["seed"] += 1
    with pytest.raises(ValueError, match="identical inputs"):
        benchmark.run_benchmark(spec, source, model, output, resume=True, engine_factory=Engine)


def test_resume_checks_pass_artifact_integrity(inputs):
    spec, source, model, output = inputs
    result = benchmark.run_benchmark(spec, source, model, output, engine_factory=Engine)
    path = output / "cells" / result["cells"][0]["id"] / "decode.json"
    path.write_text("{}\n")
    with pytest.raises(ValueError, match="pass is missing or its hash differs"):
        benchmark.run_benchmark(spec, source, model, output, resume=True, engine_factory=Engine)


@pytest.mark.parametrize("saved_status", ["running", "completed"])
def test_resume_recovers_pass_saved_before_cell_journal_update(inputs, saved_status):
    spec, source, model, output = inputs
    result = benchmark.run_benchmark(spec, source, model, output, engine_factory=Engine)
    directory = output / "cells" / result["cells"][0]["id"]
    cell = read_json(directory / "cell.json")
    cell.update(status="running", budget_accounted_seconds=0)
    cell["passes"].pop()
    write_json(directory / "cell.json", cell)
    path = directory / "instrumented.json"
    record = read_json(path)
    record.update(status=saved_status, budget_elapsed_seconds=4)
    write_json(path, record)
    original = path.read_bytes()

    benchmark.run_benchmark(spec, source, model, output, resume=True, engine_factory=Engine)

    finalized = read_json(directory / "cell.json")
    assert finalized["status"] == "interrupted"
    assert len(finalized["passes"]) == 3
    assert finalized["observed_elapsed_seconds"] == 4
    assert finalized["reserved_timeout_seconds"] == 6
    assert finalized["passes"][-1]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    if saved_status == "completed":
        assert path.read_bytes() == original
        assert finalized["passes"][-1]["status"] == "completed"
    else:
        assert read_json(path)["status"] == "interrupted"
        assert finalized["passes"][-1]["status"] == "interrupted"


def test_native_forward_count_mismatch_is_infeasible(inputs):
    spec, source, model, output = inputs

    class WrongCounts(Engine):
        def generate(self, *args, **kwargs):
            result = super().generate(*args, **kwargs)
            result["prompt_tokens"] += 1
            return result

    result = benchmark.run_benchmark(spec, source, model, output, engine_factory=WrongCounts)
    assert result["cell_status_counts"] == {"infeasible": 20}
    first = output / "cells" / result["cells"][0]["id"] / "prefill.json"
    record = read_json(first)
    assert "prefill/decode counts" in record["failure_reason"]
    assert record["generation"]["prompt_tokens"] == 25
