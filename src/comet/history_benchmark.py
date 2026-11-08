"""Matched-history inference diagnostics, isolated from task execution and scoring."""
from __future__ import annotations

import argparse
import hashlib
import math
from collections import Counter
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, is_dataclass
from pathlib import Path

from comet.artifacts import provenance, read_json, run_lock, write_json
from comet.budget import Budget
from comet.clocks import monotonic, wall_time
from comet.config import digest
from comet.engine import EngineSettings, MiniSGLangEngine, retention_target
from comet.engine.contracts import validate_model
from comet.errors import BudgetExpired, MemoryCapExceeded, UnsupportedPath

CONDITIONS = [("full", 1.0)] + [
    (method, retention)
    for method in ("streamingllm", "rkv", "agentkv")
    for retention in (0.8, 0.5, 0.25)
]
PASSES = ("prefill", "decode", "instrumented")
_MISSING = object()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _within(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError("History paths must remain relative to the source run")
    return path


def prepare_inputs(spec: dict, source_run: Path, model_path: Path) -> tuple[EngineSettings, list[dict], dict]:
    expected = {"schema_version", "benchmark_id", "histories", "logical_lengths", "decode_tokens",
                "repetitions", "seed", "cell_timeout_seconds", "warmup_timeout_seconds", "engine"}
    if set(spec) != expected or spec["schema_version"] != 1 or not spec["benchmark_id"]:
        raise ValueError("Provide the complete version-1 history benchmark specification")
    lengths = spec["logical_lengths"]
    if not isinstance(lengths, list) or not lengths:
        raise ValueError("logical_lengths must be a nonempty, increasing list")
    for name, value in [("logical length", value) for value in lengths] + [
        (name, spec[name]) for name in ("decode_tokens", "repetitions", "seed")
    ]:
        if type(value) is not int or value < (0 if name == "seed" else 1):
            raise ValueError(f"{name} must be an explicit positive integer (seed may be zero)")
    if lengths != sorted(set(lengths)):
        raise ValueError("logical_lengths must be a nonempty, increasing list")
    for name in ("cell_timeout_seconds", "warmup_timeout_seconds"):
        value = spec[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    engine_fields = {"max_context_tokens", "peak_vram_bytes", "workspace_reserve_bytes",
                     "prefill_chunk_tokens", "device_name"}
    if set(spec["engine"]) != engine_fields or not spec["engine"]["device_name"]:
        raise ValueError("Declare all engine limits and the exact device_name")
    if any(type(value) is not int or value <= 0 for name, value in spec["engine"].items()
           if name != "device_name"):
        raise ValueError("Engine context, memory and chunk limits must be positive integers")
    source_path = source_run / "manifest.json"
    source = read_json(source_path)
    if source.get("status") != "completed" or source["config"]["split"] not in {"train", "dev"}:
        raise ValueError("Use completed train/dev source runs; failed task outcomes may supply histories")
    model = {name: source["config"]["engine"][name]
             for name in ("model", "model_revision", "tokenizer_revision")}
    validate_model(model["model"], model["model_revision"], model["tokenizer_revision"])
    if any(source.get("engine", {}).get(name) != value for name, value in model.items()):
        raise ValueError("Source engine/model/tokenizer provenance is missing or inconsistent")
    settings = EngineSettings(model_path=str(model_path), method="full", retention=1.0,
                              require_a100=False, **model, **spec["engine"])
    if max(lengths) + spec["decode_tokens"] + 1 > settings.max_context_tokens:
        raise ValueError("Logical length plus decode tokens and first prefill output exceeds context")
    if not isinstance(spec["histories"], list) or not spec["histories"]:
        raise ValueError("Declare at least one source history and its SHA-256")
    attempts = {}
    for reference in source["cells"]:
        cell_path = _within(source_run, reference["path"])
        cell = read_json(cell_path)
        for attempt in cell["attempts"]:
            relative = str(Path(attempt["artifact_dir"]) / "trajectory.json")
            attempts[relative] = {"task_id": cell["task_id"], "condition": cell["condition"],
                                  "seed": attempt["seed"], "attempt_index": attempt["attempt_index"],
                                  "status": attempt["status"]}
    histories = []
    for index, item in enumerate(spec["histories"]):
        if set(item) != {"trajectory", "sha256"} or item["trajectory"] not in attempts:
            raise ValueError("History must identify an attempt listed in the source manifest")
        path = _within(source_run, item["trajectory"])
        if _sha(path) != item["sha256"]:
            raise ValueError(f"Source trajectory SHA-256 differs: {item['trajectory']}")
        tokens = read_json(path)["raw_token_ids"]
        if not isinstance(tokens, list) or any(type(token) is not int or token < 0 for token in tokens):
            raise ValueError("History must contain nonnegative integer raw token IDs")
        required = max(lengths) + spec["decode_tokens"] + 1
        if len(tokens) < required:
            raise ValueError("History is shorter than a declared prefix plus its forced continuation")
        histories.append({"id": f"history-{index:03d}", **item, **attempts[item["trajectory"]],
                          "source_token_count": len(tokens), "raw_token_ids": tokens[:required],
                          "prefix_sha256": {str(length): digest(tokens[:length]) for length in lengths}})
    if len({item["trajectory"] for item in histories}) != len(histories):
        raise ValueError("Do not list the same source history twice")
    return settings, histories, {"manifest_sha256": _sha(source_path), "manifest": source}


def _restore_attribute(owner, name, previous):
    if previous is _MISSING:
        delattr(owner, name)
    else:
        setattr(owner, name, previous)


@contextmanager
def force_recorded_tokens(engine, token_ids: list[int]):
    """Replace only sampled IDs; model forwards and cache policies remain native."""
    sampler = engine.scheduler.engine.sampler
    previous = vars(sampler).get("sample", _MISSING)
    tokens = engine.torch.tensor(token_ids, dtype=engine.torch.int64, device=sampler.device)
    record = {"expected_tokens": len(token_ids), "emitted_tokens": 0}

    def sample(logits, args):
        if logits.ndim != 2 or logits.shape[0] != 1 or logits.device != sampler.device:
            raise UnsupportedPath("Forced history replay requires one native sampler row on its device")
        index = record["emitted_tokens"]
        if index >= len(token_ids) or token_ids[index] >= logits.shape[1]:
            raise UnsupportedPath("Forced continuation exceeds the declared tokens or model vocabulary")
        record["emitted_tokens"] += 1
        return tokens[index:index + 1]

    sampler.sample = sample
    try:
        yield record
        if record["emitted_tokens"] != len(token_ids):
            raise UnsupportedPath("Native generation stopped before the forced continuation finished")
    finally:
        _restore_attribute(sampler, "sample", previous)


@contextmanager
def profile_eviction(engine):
    """Measure disjoint selection and compaction calls in a separate replay pass."""
    manager = engine.scheduler.eviction_manager
    methods = {"selection": "_select_compaction_indices", "compaction": "compact_session_req"}
    if any(not callable(getattr(manager, name, None)) for name in methods.values()):
        raise UnsupportedPath("Pinned eviction profiling boundaries are unavailable")
    saved, records = {}, {}

    def measure(original, record):
        def wrapped(*args, **kwargs):
            engine.synchronize()
            started = monotonic()
            completed = False
            try:
                result = original(*args, **kwargs)
                engine.synchronize()
                completed = True
                return result
            finally:
                record["seconds"] += monotonic() - started
                record["calls"] += 1
                record["completed_calls"] += int(completed)
                if not completed:
                    record["coverage"] = "partial"
        return wrapped

    try:
        for label, name in methods.items():
            saved[name] = vars(manager).get(name, _MISSING)
            records[label] = {"seconds": 0.0, "calls": 0, "completed_calls": 0, "coverage": "complete"}
            setattr(manager, name, measure(getattr(manager, name), records[label]))
        yield records
    finally:
        for name, previous in saved.items():
            _restore_attribute(manager, name, previous)


def _status(error: BaseException) -> str:
    if isinstance(error, BudgetExpired):
        return "timeout"
    if isinstance(error, MemoryError) or type(error).__name__ == "OutOfMemoryError":
        return "oom"
    if isinstance(error, UnsupportedPath):
        return "infeasible"
    return "error" if isinstance(error, Exception) else "interrupted"


def _measure_pass(engine, history: dict, reference: dict, spec: dict, name: str,
                  directory: Path, budget: Budget) -> dict:
    record = {"pass": name, "status": "running", "failure_reason": None, "timings": {},
              "throughput_comparable": name != "instrumented", "reference": reference,
              "spec_digest": digest(spec), "history_sha256": history["sha256"]}
    path = directory / f"{name}.json"
    write_json(path, record)
    before, old_timings = budget.elapsed, dict(budget.timings)
    length = reference["logical_length"]
    count = 1 if name == "prefill" else spec["decode_tokens"] + 1
    tokens = history["raw_token_ids"][:length + count]
    called = False
    try:
        with budget.charge("reset"):
            engine.set_policy(reference["method"], reference["retention"])
            engine.start(spec["seed"])
        profiling = profile_eviction(engine) if name == "instrumented" else nullcontext(None)
        with profiling as overhead, force_recorded_tokens(engine, tokens[length:]) as forced:
            record["eviction_overhead"] = overhead
            record["forced_tokens"] = forced
            with budget.charge("inference"):
                called = True
                generated = engine.generate(tokens[:length], count, 0.0, 1.0,
                                            budget.deadline, ignore_eos=True)
                record["generation"] = asdict(generated) if is_dataclass(generated) else dict(generated)
            with budget.charge("verify"):
                if engine.raw_token_ids != tokens or record["generation"]["token_ids"] != tokens[length:]:
                    raise UnsupportedPath("Forced replay diverged from the saved raw token history")
                if (record["generation"]["prompt_tokens"] != length
                        or record["generation"]["decode_tokens"] != count - 1):
                    raise UnsupportedPath("Native prefill/decode counts differ from the declared replay")
                memory = engine.memory_stats()
                logical = length + count - 1
                expected = retention_target(logical, reference["retention"], reference["method"])
                if memory["logical_cached_tokens"] != logical or memory["physical_cached_tokens"] != expected:
                    raise UnsupportedPath("Native KV occupancy differs from the declared relative retention")
                if memory["peak_total_vram_bytes"] > spec["engine"]["peak_vram_bytes"]:
                    raise MemoryCapExceeded("Forced replay exceeded its declared total VRAM cap")
                record["history_verified"] = True
                record["raw_token_sha256"] = digest(tokens)
                record["memory"] = memory
                record["actual_retention"] = memory["physical_cached_tokens"] / logical
                record["occupied_kv_bytes"] = memory["physical_cached_tokens"] * engine.kv_bytes_per_token
                free, total = engine.torch.cuda.mem_get_info()
                record["total_vram_bytes"] = total - free
        record["status"] = "completed"
    except BaseException as error:
        record.update(status=_status(error), failure_reason=f"{type(error).__name__}: {error}")
        if not isinstance(error, Exception):
            raise
    finally:
        if called and getattr(engine, "last_generation", None):
            record["generation"] = {**record.get("generation", {}), **engine.last_generation}
        if called:
            record["retention_events"] = getattr(engine, "retention_events", [])
        cleanup = budget.elapsed
        try:
            engine.synchronize()
        except Exception as error:
            record["cleanup_error"] = f"{type(error).__name__}: {error}"
            if record["status"] == "completed":
                record.update(status=_status(error), failure_reason=record["cleanup_error"])
        budget.timings["cleanup"] = budget.timings.get("cleanup", 0) + budget.elapsed - cleanup
        if record["status"] == "completed" and not budget.remaining:
            record.update(status="timeout", failure_reason="Shared diagnostic cell timeout expired")
        record["elapsed_seconds"] = budget.elapsed - before
        record["budget_elapsed_seconds"] = budget.elapsed
        record["timings"] = {key: value - old_timings.get(key, 0) for key, value in budget.timings.items()}
        generation = record.get("generation", {})
        record["metric_coverage"] = "complete" if record["status"] == "completed" else "partial"
        for phase, counter in (("prefill", "prompt_tokens"), ("decode", "decode_tokens")):
            seconds = generation.get(f"{phase}_seconds", 0)
            record[f"{phase}_tokens_per_second"] = (
                generation.get(counter, 0) / seconds if seconds > 0 and record["status"] == "completed" else None
            )
        write_json(path, record)
    return record


def _source_contract(record: dict) -> dict:
    return {key: record[key] for key in ("code_commit", "local_changes", "source_hashes",
                                        "installed_packages", "python")}


def _engine_contract(record: dict) -> dict:
    return {key: value for key, value in record.items() if key not in {"model_path", "memory", "warmup"}}


def _reconcile_passes(cell: dict, directory: Path, spec: dict, history: dict) -> None:
    reference = cell["reference"]
    for index, name in enumerate(PASSES):
        path = directory / f"{name}.json"
        saved = cell["passes"][index] if index < len(cell["passes"]) else None
        if saved is None and (cell["status"] != "running" or not path.exists()):
            break
        if saved is not None and (saved["pass"] != name or saved["path"] != path.name
                                  or not path.exists() or _sha(path) != saved["sha256"]):
            raise ValueError("Saved benchmark pass is missing or its hash differs")
        record = read_json(path)
        if (record.get("reference") != reference or record.get("spec_digest") != digest(spec)
                or record.get("history_sha256") != history["sha256"] or record.get("pass") != name):
            raise ValueError("Saved benchmark pass identity differs")
        if saved is not None and saved["status"] != record["status"]:
            raise ValueError("Saved benchmark pass status differs from its journal")
        if saved is None:
            if record["status"] == "running":
                record.update(status="interrupted", metric_coverage="partial",
                              failure_reason="Process interrupted before pass finalization")
                write_json(path, record)
            cell["passes"].append({"pass": name, "status": record["status"],
                                   "path": path.name, "sha256": _sha(path)})
            cell["budget_accounted_seconds"] = max(cell.get("budget_accounted_seconds", 0),
                                                   record.get("budget_elapsed_seconds", 0))
    if cell["status"] == "completed" and len(cell["passes"]) != len(PASSES):
        raise ValueError("Completed benchmark cell is missing a pass")


def run_benchmark(spec: dict, source_run: Path, model_path: Path, output: Path, *,
                  resume: bool = False, engine_factory=MiniSGLangEngine) -> dict:
    settings, histories, source = prepare_inputs(spec, source_run, model_path)
    current = provenance()
    launcher = Path(__file__).resolve().parents[2] / "scripts/benchmark_histories.py"
    current["source_hashes"]["scripts/benchmark_histories.py"] = _sha(launcher)
    identity = digest({"spec": spec, "source": source["manifest_sha256"],
                       "engine_settings": settings.fingerprint()})
    with run_lock(output):
        path = output / "manifest.json"
        if path.exists():
            if not resume:
                raise FileExistsError("Benchmark exists; resume only its unchanged specification")
            manifest = read_json(path)
            if manifest["identity"] != identity or _source_contract(manifest["provenance"]) != _source_contract(current):
                raise ValueError("Resume requires identical inputs, settings, source and installed packages")
            for history in histories:
                if read_json(output / "inputs" / f"{history['id']}.json") != history:
                    raise ValueError("Saved benchmark input differs from the verified source history")
        else:
            if resume:
                raise FileNotFoundError("Cannot resume without a benchmark manifest")
            manifest = {
                "schema_version": 1, "kind": "matched_history_forced_replay", "status": "running",
                "identity": identity, "spec": spec, "source": source, "provenance": current,
                "engine_settings": asdict(settings), "started_at_unix": wall_time(),
                "measurement_contract": {
                    "tokens": "forced recorded outputs; no sampling or tools",
                    "decode_tokens": "decode forwards; one additional output comes from prefill",
                    "instrumentation": "synchronized host time at selection and compaction method boundaries",
                    "selection_boundary": "EvictionManager._select_compaction_indices",
                    "compaction_boundary": "EvictionManager.compact_session_req",
                    "overhead_exclusions": ["maybe_compact guards and dispatch", "other scheduler operations"],
                    "instrumented_throughput": "excluded from ordinary throughput comparisons",
                },
                "histories": [{key: value for key, value in history.items() if key != "raw_token_ids"}
                              for history in histories],
                "cells": [{"id": f"{history['id']}-l{length}-{method}-{int(retention * 100)}-r{repeat}",
                           "history_id": history["id"], "logical_length": length,
                           "method": method, "retention": retention, "repetition": repeat}
                          for history in histories for length in spec["logical_lengths"]
                          for method, retention in CONDITIONS for repeat in range(spec["repetitions"])],
            }
            write_json(path, manifest)
            for history in histories:
                write_json(output / "inputs" / f"{history['id']}.json", history)
        pending = []
        by_id = {history["id"]: history for history in histories}
        for reference in manifest["cells"]:
            cell_path = output / "cells" / reference["id"] / "cell.json"
            if not cell_path.exists():
                if manifest["status"] == "completed":
                    raise ValueError("Completed benchmark is missing a cell artifact")
                pending.append(reference)
                continue
            cell = read_json(cell_path)
            if cell.get("identity") != identity or cell.get("reference") != reference:
                raise ValueError("Saved benchmark cell identity differs")
            _reconcile_passes(cell, cell_path.parent, spec, by_id[reference["history_id"]])
            if cell["status"] == "running":
                observed = cell.get("budget_accounted_seconds", 0)
                cell.update(status="interrupted", failure_reason="Process interrupted; cell is not retried",
                            observed_elapsed_seconds=observed,
                            reserved_timeout_seconds=max(0, spec["cell_timeout_seconds"] - observed),
                            budget_accounted_seconds=max(observed, spec["cell_timeout_seconds"]))
                write_json(cell_path, cell)
        if pending:
            started = monotonic()
            try:
                engine = engine_factory(settings)
            except Exception as error:
                manifest.setdefault("setup_failures", []).append({
                    "at_unix": wall_time(), "seconds": monotonic() - started,
                    "failure_reason": f"{type(error).__name__}: {error}",
                })
                write_json(path, manifest)
                raise
            try:
                engine.warmup(deadline=monotonic() + spec["warmup_timeout_seconds"])
                metadata = engine.provenance()
                if manifest.get("engine") and _engine_contract(manifest["engine"]) != _engine_contract(metadata):
                    raise ValueError("Resume runtime or GPU hardware differs from the benchmark")
                manifest["engine"] = metadata
                manifest.setdefault("launches", []).append({"at_unix": wall_time(), "engine": metadata,
                                                             "setup_seconds": monotonic() - started})
                write_json(path, manifest)
                for reference in pending:
                    directory = output / "cells" / reference["id"]
                    cell_path = directory / "cell.json"
                    cell = {"identity": identity, "reference": reference, "status": "running", "passes": []}
                    budget = Budget(spec["cell_timeout_seconds"])
                    write_json(cell_path, cell)
                    for name in PASSES:
                        record = _measure_pass(engine, by_id[reference["history_id"]], reference,
                                               spec, name, directory, budget)
                        cell["passes"].append({"pass": name, "status": record["status"],
                                               "path": f"{name}.json", "sha256": _sha(directory / f"{name}.json")})
                        cell["budget_accounted_seconds"] = budget.elapsed
                        write_json(cell_path, cell)
                        if record["status"] != "completed":
                            cell.update(status=record["status"], failure_reason=record["failure_reason"])
                            break
                    else:
                        cell["status"] = "completed"
                    cell["budget_accounted_seconds"] = budget.elapsed
                    if cell["status"] == "completed" and not budget.remaining:
                        cell.update(status="timeout", failure_reason="Benchmark journal exceeded cell timeout")
                    write_json(cell_path, cell)
                    if cell["status"] == "completed" and not budget.remaining:
                        cell.update(status="timeout", failure_reason="Final benchmark journal exceeded cell timeout",
                                    budget_accounted_seconds=budget.elapsed)
                        write_json(cell_path, cell)
            except Exception as error:
                manifest["last_failure"] = {"at_unix": wall_time(),
                                            "failure_reason": f"{type(error).__name__}: {error}"}
                write_json(path, manifest)
                raise
            finally:
                engine.close()
        counts = Counter(read_json(output / "cells" / item["id"] / "cell.json")["status"]
                         for item in manifest["cells"])
        manifest.update(status="completed", cell_status_counts=dict(counts), finished_at_unix=wall_time())
        write_json(path, manifest)
        return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    manifest = run_benchmark(read_json(args.spec), args.source_run, args.model_path,
                             args.output, resume=args.resume)
    print(f"{manifest['kind']}: {manifest['cell_status_counts']}")
