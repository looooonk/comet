"""Validate and summarize saved matched-history measurements without GPU access."""
from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from comet.artifacts import read_json, write_json
from comet.config import digest
from comet.engine import EngineSettings, retention_target
from comet.history_benchmark import CONDITIONS, PASSES

VARIABLE_SPEC_FIELDS = {
    "benchmark_id", "logical_lengths", "repetitions", "cell_timeout_seconds", "warmup_timeout_seconds",
}
METRICS = {
    "occupied_kv_bytes": ("prefill", "Occupied KV (GiB)", 2**-30),
    "peak_occupied_kv_bytes": ("prefill", "Peak occupied KV (GiB)", 2**-30),
    "reserved_kv_pool_bytes": ("prefill", "Reserved KV pool (GiB)", 2**-30),
    "total_vram_bytes": ("prefill", "Total VRAM after prefill (GiB)", 2**-30),
    "peak_total_vram_bytes": ("prefill", "Prefill peak total VRAM (GiB)", 2**-30),
    "decode_peak_total_vram_bytes": ("decode", "Peak total VRAM (GiB)", 2**-30),
    "prefill_tokens_per_second": ("prefill", "Prefill loop (tokens/s)", 1),
    "decode_tokens_per_second": ("decode", "Decode loop (tokens/s)", 1),
    "prefill_pass_seconds": ("prefill", "Whole prefill pass (s)", 1),
    "decode_pass_seconds": ("decode", "Whole decode pass (s)", 1),
    "prefill_inference_seconds": ("prefill", "Prefill inference call (s)", 1),
    "decode_inference_seconds": ("decode", "Decode inference call (s)", 1),
    "selection_seconds": ("instrumented", "Selection over whole replay (ms)", 1000),
    "compaction_seconds": ("instrumented", "Compaction over whole replay (ms)", 1000),
    "instrumented_pass_seconds": ("instrumented", "Whole instrumented pass (s)", 1),
}
_ENGINE_KEYS = {
    "backend", "model", "model_revision", "tokenizer_revision", "dtype", "device_name",
    "device_total_bytes", "minisgl_revision", "patch_file_sha256", "packages",
    "cuda_runtime", "driver_version",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    _require(not Path(relative).is_absolute() and path.is_relative_to(root.resolve()),
             "Artifact path escapes the benchmark directory")
    return path


def _number(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


def _validate_spec(manifest: dict, settings: EngineSettings) -> None:
    spec = manifest["spec"]
    expected = VARIABLE_SPEC_FIELDS | {"schema_version", "histories", "decode_tokens", "seed", "engine"}
    _require(set(spec) == expected and spec["schema_version"] == 1 and spec["benchmark_id"],
             "Expected complete version-1 benchmark specification")
    lengths = spec["logical_lengths"]
    _require(isinstance(lengths, list) and bool(lengths)
             and all(type(length) is int and length > 0 for length in lengths)
             and lengths == sorted(set(lengths)), "Invalid logical lengths")
    _require(all(type(spec[key]) is int and spec[key] >= minimum
                 for key, minimum in (("decode_tokens", 1), ("repetitions", 1), ("seed", 0))),
             "Invalid decode count, repetitions or seed")
    _require(all(_number(spec[key]) and spec[key] > 0
                 for key in ("cell_timeout_seconds", "warmup_timeout_seconds")), "Invalid time bounds")
    _require(max(lengths) + spec["decode_tokens"] + 1 <= settings.max_context_tokens,
             "Declared history exceeds context capacity")
    _require(spec["engine"] == {key: getattr(settings, key) for key in (
        "max_context_tokens", "peak_vram_bytes", "workspace_reserve_bytes",
        "prefill_chunk_tokens", "device_name")}, "Specification and engine settings differ")
    source = manifest["source"]["manifest"]
    _require(source.get("status") == "completed" and source["config"]["split"] in {"train", "dev"},
             "Histories require a completed train/dev source run")
    for key in ("model", "model_revision", "tokenizer_revision"):
        _require(source["config"]["engine"].get(key) == source.get("engine", {}).get(key)
                 == getattr(settings, key), "Source and replay model identity differ")
    engine = manifest.get("engine")
    if engine is not None:
        _require(all(engine.get(key) == getattr(settings, key) for key in (
            "model", "model_revision", "tokenizer_revision", "device_name")),
            "Observed runtime and declared model/hardware differ")
        _require(engine.get("dtype") == "bfloat16", "Matched-history inference must use BF16")
        _require(_number(engine.get("device_total_bytes"))
                 and engine["device_total_bytes"] >= settings.peak_vram_bytes,
                 "Recorded hardware cannot hold the declared cap")


def _contract(manifest: dict) -> dict:
    spec = manifest["spec"]
    provenance = manifest["provenance"]
    source_fields = ("code_commit", "local_changes", "source_hashes", "installed_packages", "python")
    _require(all(key in provenance for key in source_fields), "Source provenance is incomplete")
    return {
        "source_manifest_sha256": manifest["source"]["manifest_sha256"],
        "source_manifest_digest": digest(manifest["source"]["manifest"]),
        "provenance": {key: provenance[key] for key in source_fields},
        "engine_settings": {key: value for key, value in manifest["engine_settings"].items()
                            if key != "model_path"},
        "specification": {key: value for key, value in spec.items() if key not in VARIABLE_SPEC_FIELDS},
        "histories": [{key: value for key, value in item.items() if key != "prefix_sha256"}
                      for item in manifest["histories"]],
        "measurement_contract": manifest["measurement_contract"],
    }


def _runtime(manifest: dict) -> dict | None:
    engine = manifest.get("engine")
    if engine is None:
        return None
    _require(_ENGINE_KEYS <= engine.keys() and all(engine[key] is not None for key in _ENGINE_KEYS),
             "Runtime hardware/model provenance is incomplete")
    return {key: value for key, value in engine.items() if key not in {"model_path", "memory", "warmup"}}


def _inputs(directory: Path, manifest: dict) -> dict:
    histories = {}
    spec = manifest["spec"]
    for reference in manifest["histories"]:
        history = read_json(_path(directory, f"inputs/{reference['id']}.json"))
        _require({key: value for key, value in history.items() if key != "raw_token_ids"} == reference,
                 "Saved input identity differs from manifest")
        tokens = history["raw_token_ids"]
        _require(isinstance(tokens, list) and all(type(token) is int and token >= 0 for token in tokens),
                 "Saved input must contain nonnegative integer token IDs")
        _require(len(tokens) == max(spec["logical_lengths"]) + spec["decode_tokens"] + 1,
                 "Saved input length differs from specification")
        _require(history["prefix_sha256"] == {str(length): digest(tokens[:length])
                                             for length in spec["logical_lengths"]},
                 "Saved input prefix hash differs")
        _require(reference["id"] not in histories, "Duplicate history identity")
        histories[reference["id"]] = history
    _require(spec["histories"] == [{key: item[key] for key in ("trajectory", "sha256")}
                                   for item in histories.values()], "Declared histories differ")
    return histories


def _verify_completed(record: dict, history: dict, reference: dict, spec: dict) -> None:
    count = 1 if record["pass"] == "prefill" else spec["decode_tokens"] + 1
    length = reference["logical_length"]
    tokens = history["raw_token_ids"][:length + count]
    generation = record.get("generation", {})
    _require(record.get("history_verified") is True
             and record.get("raw_token_sha256") == digest(tokens)
             and generation.get("token_ids") == tokens[length:]
             and record.get("forced_tokens") == {"expected_tokens": count, "emitted_tokens": count},
             "Completed pass does not verify its exact forced history")
    _require(generation.get("prompt_tokens") == length and generation.get("decode_tokens") == count - 1,
             "Completed pass token accounting differs")
    memory = record.get("memory", {})
    logical = length + count - 1
    physical = retention_target(logical, reference["retention"], reference["method"])
    _require(memory.get("logical_cached_tokens") == logical
             and memory.get("physical_cached_tokens") == physical,
             "Completed pass retention accounting differs")
    if record.get("actual_retention") is not None:
        _require(math.isclose(record["actual_retention"], physical / logical),
                 "Actual retention differs from occupancy")
    peak = memory.get("peak_total_vram_bytes")
    _require(peak is None or (_number(peak) and peak <= spec["engine"]["peak_vram_bytes"]),
             "Completed pass exceeds its total VRAM cap")
    for phase, counter in (("prefill", "prompt_tokens"), ("decode", "decode_tokens")):
        rate, seconds = record.get(f"{phase}_tokens_per_second"), generation.get(f"{phase}_seconds")
        if rate is not None:
            _require(_number(rate) and _number(seconds) and seconds > 0
                     and math.isclose(rate, generation[counter] / seconds, rel_tol=1e-9),
                     "Recorded throughput disagrees with token/time accounting")


def _pass(directory: Path, cell: dict, name: str, history: dict, spec: dict) -> dict:
    entry = next((item for item in cell["passes"] if item["pass"] == name), None)
    path = _path(directory, f"{name}.json")
    if entry is None and not path.exists():
        return {"pass": name, "status": "not_attempted", "metric_coverage": "unavailable",
                "journaled": False}
    if entry is not None:
        _require(entry["path"] == path.name and path.exists() and _sha(path) == entry["sha256"],
                 "Pass artifact missing or SHA-256 differs")
    record = read_json(path)
    _require(record.get("pass") == name and record.get("reference") == cell["reference"]
             and record.get("spec_digest") == digest(spec)
             and record.get("history_sha256") == history["sha256"], "Pass identity differs")
    _require(entry is None or entry["status"] == record["status"], "Pass journal status differs")
    _require(record.get("throughput_comparable") == (name != "instrumented"),
             "Instrumented and ordinary pass roles differ")
    if record["status"] == "completed":
        _verify_completed(record, history, cell["reference"], spec)
    return {**record, "artifact_sha256": _sha(path), "journaled": entry is not None}


def _metric(record: dict, key: str) -> dict:
    eligible = (record["status"] == "completed" and record.get("metric_coverage") == "complete"
                and record["journaled"])
    memory = record.get("memory", {})
    if key in {"peak_occupied_kv_bytes", "reserved_kv_pool_bytes", "peak_total_vram_bytes",
               "decode_peak_total_vram_bytes"}:
        source = {"peak_occupied_kv_bytes": "peak_kv_cache_bytes",
                  "decode_peak_total_vram_bytes": "peak_total_vram_bytes"}.get(key, key)
        value = memory.get(source)
    elif key.endswith("_pass_seconds"):
        value = record.get("elapsed_seconds")
    elif key.endswith("_inference_seconds"):
        value = record.get("timings", {}).get("inference")
    elif key in {"selection_seconds", "compaction_seconds"}:
        overhead = (record.get("eviction_overhead") or {}).get(key.removesuffix("_seconds"), {})
        eligible = (eligible and overhead.get("coverage") == "complete"
                    and overhead.get("calls") == overhead.get("completed_calls")
                    and type(overhead.get("calls")) is int)
        value = overhead.get("seconds")
    else:
        value = record.get(key)
    available = eligible and _number(value)
    return {"value": value if available else None, "observed_value": value,
            "coverage": "complete" if available else "unavailable",
            "pass": record["pass"], "pass_status": record["status"]}


def analyze_histories(run_dirs: list[Path], output: Path) -> dict:
    """Pool compatible measured repetitions, preserving every expected failed or absent cell."""
    _require(bool(run_dirs), "Provide at least one matched-history run")
    contract, runtime, prior_inputs = None, None, {}
    runs, cells, identities = [], [], set()
    for directory in run_dirs:
        manifest_path = directory / "manifest.json"
        manifest = read_json(manifest_path)
        _require(manifest.get("schema_version") == 1
                 and manifest.get("kind") == "matched_history_forced_replay",
                 "Expected a version-1 matched-history benchmark")
        _require(manifest.get("status") in {"running", "completed"}, "Unknown benchmark status")
        spec = manifest["spec"]
        settings = EngineSettings(**manifest["engine_settings"])
        _validate_spec(manifest, settings)
        _require(manifest["identity"] == digest({"spec": spec,
                 "source": manifest["source"]["manifest_sha256"],
                 "engine_settings": settings.fingerprint()}), "Benchmark identity differs")
        _require(manifest["identity"] not in identities, "Duplicate benchmark identity")
        identities.add(manifest["identity"])
        current_contract, current_runtime = _contract(manifest), _runtime(manifest)
        if contract is None:
            contract = current_contract
        _require(current_contract == contract, "Incompatible source, history or numerical settings")
        if current_runtime is not None:
            if runtime is None:
                runtime = current_runtime
            _require(current_runtime == runtime, "Incompatible runtime hardware or dependencies")
        histories = _inputs(directory, manifest)
        for name, history in histories.items():
            tokens = history["raw_token_ids"]
            earlier = prior_inputs.get(name, tokens)
            _require(earlier[:min(len(earlier), len(tokens))] == tokens[:min(len(earlier), len(tokens))],
                     "Input tokens differ across logical lengths")
            prior_inputs[name] = max((earlier, tokens), key=len)
        expected = [{"id": f"{history}-l{length}-{method}-{int(retention * 100)}-r{repeat}",
                     "history_id": history, "logical_length": length, "method": method,
                     "retention": retention, "repetition": repeat}
                    for history in histories for length in spec["logical_lengths"]
                    for method, retention in CONDITIONS for repeat in range(spec["repetitions"])]
        _require(manifest["cells"] == expected, "Expected complete ten-condition cell matrix")
        counts = Counter()
        for reference in expected:
            cell_dir = _path(directory, f"cells/{reference['id']}")
            path = cell_dir / "cell.json"
            if not path.exists():
                _require(manifest["status"] != "completed", "Completed benchmark missing cell artifact")
                cell = {"reference": reference, "status": "not_started", "passes": []}
            else:
                cell = read_json(path)
                _require(cell.get("identity") == manifest["identity"]
                         and cell.get("reference") == reference, "Cell identity differs")
                _require([item["pass"] for item in cell["passes"]] == list(PASSES[:len(cell["passes"])]),
                         "Pass journal order differs")
            records = {name: _pass(cell_dir, cell, name, histories[reference["history_id"]], spec)
                       for name in PASSES}
            if cell["status"] == "completed":
                _require(all(record["status"] == "completed" and record["journaled"]
                             for record in records.values()), "Completed cell missing completed pass")
            _require(current_runtime is not None or all(record["status"] == "not_attempted"
                     for record in records.values()), "Measured passes require runtime provenance")
            metrics = {key: _metric(records[name], key) for key, (name, _, _) in METRICS.items()}
            counts[cell["status"]] += 1
            cells.append({"run_identity": manifest["identity"], "benchmark_id": spec["benchmark_id"],
                          **reference, "status": cell["status"],
                          "failure_reason": cell.get("failure_reason"),
                          "budget_accounted_seconds": cell.get("budget_accounted_seconds"),
                          "observed_elapsed_seconds": cell.get("observed_elapsed_seconds"),
                          "reserved_timeout_seconds": cell.get("reserved_timeout_seconds", 0),
                          "cell_timeout_seconds": spec["cell_timeout_seconds"],
                          "metrics": metrics, "passes": records})
        if manifest["status"] == "completed":
            _require(dict(counts) == manifest["cell_status_counts"] and "running" not in counts,
                     "Completed manifest status counts differ")
        runs.append({"identity": manifest["identity"], "benchmark_id": spec["benchmark_id"],
                     "path": str(directory.resolve()), "manifest_sha256": _sha(manifest_path),
                     "status": manifest["status"], "runtime_verified": current_runtime is not None,
                     "spec": spec, "cell_status_counts": dict(counts),
                     "launches": manifest.get("launches", []),
                     "setup_failures": manifest.get("setup_failures", [])})
    grouped = defaultdict(list)
    for cell in cells:
        grouped[(cell["history_id"], cell["logical_length"], cell["method"], cell["retention"])].append(cell)
    points = []
    for (history, length, method, retention), rows in sorted(grouped.items()):
        metrics = {}
        for key in METRICS:
            values = [row["metrics"][key]["value"] for row in rows if row["metrics"][key]["value"] is not None]
            metrics[key] = {"median": median(values) if values else None,
                            "minimum": min(values) if values else None,
                            "maximum": max(values) if values else None,
                            "observed": len(values), "expected": len(rows), "values": values}
        points.append({"history_id": history, "logical_length": length, "method": method,
                       "retention": retention, "cell_status_counts": dict(Counter(row["status"] for row in rows)),
                       "metrics": metrics})
    result = {"schema_version": 1, "kind": "matched_history_analysis", "contract": contract,
              "runtime": runtime, "runs": runs, "cells": cells, "points": points,
              "metric_definitions": {key: {"pass": name, "plot_label": label, "plot_scale": scale}
                                     for key, (name, label, scale) in METRICS.items()},
              "summary": {"expected_cells": len(cells),
                          "cell_status_counts": dict(Counter(cell["status"] for cell in cells)),
                          "logical_lengths": sorted({cell["logical_length"] for cell in cells}),
                          "histories": list(prior_inputs)},
              "interpretation": {
                  "scope": "Forced recorded histories measure cost, not model accuracy or task success.",
                  "ordinary_timing": "Synchronized native loops include eviction and output processing; surrounding scheduling, reset and verification are excluded.",
                  "overhead": "Selection and compaction sum synchronized calls over the whole instrumented prefix-plus-continuation replay, not per-token rates. They are disjoint nested costs, not additions to loop or whole-pass durations.",
                  "summary": "Medians and observed ranges over retained run/repetition identities; no fitted trend or confidence interval.",
                  "coverage": "Only completed, journaled passes with complete metric coverage enter summaries. All other cells and partial values remain explicit.",
                  "memory": "Prefill memory uses the declared prefix. Decode-pass peak total VRAM covers ordinary prefix-plus-continuation execution; it is distinct from prefill-only memory. Instrumented memory remains in raw pass records.",
              }}
    write_json(output, result)
    return result
