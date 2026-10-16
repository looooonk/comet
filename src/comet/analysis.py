"""Task-clustered analysis of separately scored runs."""

from __future__ import annotations

import itertools
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from comet.evaluation import _read, _write, execution_digest


def _quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    left = math.floor(index)
    right = math.ceil(index)
    return ordered[left] + (ordered[right] - ordered[left]) * (index - left)


def _estimate(values: list[float], bootstrap: list[float]) -> dict[str, Any]:
    return {"value": mean(values), "ci95": [_quantile(bootstrap, 0.025),
                                             _quantile(bootstrap, 0.975)]}


def _metric(attempts: list[dict[str, Any]], key: str, unit: str, aggregation: str) -> dict[str, Any]:
    values = [attempt["metrics"][key] for attempt in attempts
              if isinstance(attempt.get("metrics", {}).get(key), (int, float))]
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError(f"Invalid recorded metric: {key}")
    value = (sum(values) if aggregation == "sum" else max(values)) if values else None
    return {"value": value, "unit": unit, "aggregation": aggregation,
            "observed_attempts": len(values), "total_attempts": len(attempts)}


def analyze_cells(cells: list[dict[str, Any]], *, bootstrap_samples: int = 2000,
                  seed: int = 0) -> dict[str, Any]:
    if not cells or bootstrap_samples < 1:
        raise ValueError("Analysis needs scored cells and at least one bootstrap draw.")
    by_condition: dict[str, dict[tuple[str, int], dict[str, Any]]] = defaultdict(dict)
    conditions: dict[str, dict[str, Any]] = {}
    for cell in cells:
        condition = cell["condition"]
        condition_id = condition["id"]
        identity = (cell["task_id"], cell["seed"])
        if identity in by_condition[condition_id]:
            raise ValueError(f"Duplicate task/seed cell for {condition_id}: {identity}")
        if condition_id in conditions and conditions[condition_id] != condition:
            raise ValueError(f"Condition {condition_id} has inconsistent settings.")
        if (not cell.get("completed") or any(type(attempt.get("success")) is not bool
                                            for attempt in cell["attempts"])):
            raise ValueError("Analysis requires completed, separately scored attempts.")
        for attempt in cell["attempts"]:
            if attempt["status"] != "completed" and attempt["success"]:
                raise ValueError("Execution failures cannot count as successful attempts.")
        conditions[condition_id] = condition
        by_condition[condition_id][identity] = cell
    identities = set(next(iter(by_condition.values())))
    if any(set(group) != identities for group in by_condition.values()):
        raise ValueError("Conditions must contain exactly the same paired tasks and replicate seeds.")
    tasks = sorted({task for task, _ in identities})
    task_seeds = {task: sorted(seed_ for task_, seed_ in identities if task_ == task) for task in tasks}
    if len({tuple(seeds) for seeds in task_seeds.values()}) != 1:
        raise ValueError("Every task must use the same frozen replicate seed schedule.")
    rng = random.Random(seed)
    draws = [[rng.randrange(len(tasks)) for _ in tasks] for _ in range(bootstrap_samples)]
    result: dict[str, Any] = {
        "schema_version": 1,
        "primary_metric": "oracle task success within budget (perfect-selection upper bound)",
        "uncertainty": {"method": "paired task bootstrap, percentile 95% CI",
                        "samples": bootstrap_samples, "seed": seed,
                        "resampling_unit": "task, retaining all attempts and paired replicate seeds"},
        "task_count": len(tasks), "tasks": tasks, "replicate_seeds": task_seeds[tasks[0]],
        "conditions": {}, "paired_comparisons": [],
    }
    task_values: dict[str, dict[str, list[float]]] = {}
    bootstraps: dict[str, dict[str, list[float]]] = {}
    for condition_id, group in sorted(by_condition.items()):
        values: dict[str, list[float]] = {name: [] for name in (
            "oracle_success_rate", "single_attempt_success_rate", "actual_attempts", "latency_seconds"
        )}
        for task in tasks:
            paired = [group[(task, seed_)] for seed_ in task_seeds[task]]
            values["oracle_success_rate"].append(mean(
                float(any(attempt["success"] for attempt in cell["attempts"])) for cell in paired
            ))
            values["single_attempt_success_rate"].append(mean(
                float(bool(cell["attempts"] and cell["attempts"][0]["success"])) for cell in paired
            ))
            values["actual_attempts"].append(mean(len(cell["attempts"]) for cell in paired))
            values["latency_seconds"].append(mean(cell["elapsed_seconds"] for cell in paired))
        task_values[condition_id] = values
        bootstraps[condition_id] = {
            metric: [sum(samples[index] for index in draw) / len(tasks) for draw in draws]
            for metric, samples in values.items()
        }
        attempts = [attempt for cell in group.values() for attempt in cell["attempts"]]
        metrics = {
            "estimated_flops": _metric(attempts, "estimated_flops", "estimated FLOPs", "sum"),
            "peak_total_vram_bytes": _metric(attempts, "peak_total_vram_bytes", "bytes", "max"),
            "peak_kv_bytes": _metric(attempts, "peak_kv_bytes", "bytes", "max"),
            "generated_tokens": _metric(attempts, "generated_tokens", "tokens", "sum"),
            "prefill_tokens": _metric(attempts, "prefill_tokens", "tokens", "sum"),
        }
        decoding = [attempt["metrics"] for attempt in attempts
                    if isinstance(attempt.get("metrics", {}).get("decode_tokens"), (int, float))
                    and isinstance(attempt.get("metrics", {}).get("decode_seconds"), (int, float))]
        if any(not math.isfinite(item["decode_seconds"]) or item["decode_seconds"] < 0
               for item in decoding):
            raise ValueError("Invalid recorded decode_seconds.")
        decode_seconds = sum(item["decode_seconds"] for item in decoding)
        metrics["decode_throughput"] = {
            "value": sum(item["decode_tokens"] for item in decoding) / decode_seconds
                     if decode_seconds else None,
            "unit": "decode tokens / decode second", "aggregation": "ratio of sums",
            "observed_attempts": len(decoding), "total_attempts": len(attempts),
        }
        methods = {attempt.get("metrics", {}).get("flops_estimation_method") for attempt in attempts}
        metrics["estimated_flops"]["methods"] = sorted(method for method in methods if method)
        result["conditions"][condition_id] = {
            "condition": conditions[condition_id],
            **{name: _estimate(value, bootstraps[condition_id][name])
               for name, value in values.items()},
            "attempt_status_counts": dict(Counter(attempt["status"] for attempt in attempts)),
            "infeasible_cells": sum(bool(cell.get("infeasible")) or
                                    any(attempt["status"] == "infeasible" for attempt in cell["attempts"])
                                    for cell in group.values()),
            "zero_attempt_cells": sum(not cell["attempts"] for cell in group.values()),
            "metrics": metrics,
        }
    for left, right in itertools.combinations(sorted(by_condition), 2):
        comparison: dict[str, Any] = {"left": left, "right": right, "direction": "right minus left"}
        for metric in ("oracle_success_rate", "single_attempt_success_rate", "latency_seconds"):
            differences = [right_value - left_value for left_value, right_value in
                           zip(task_values[left][metric], task_values[right][metric], strict=True)]
            samples = [right_value - left_value for left_value, right_value in
                       zip(bootstraps[left][metric], bootstraps[right][metric], strict=True)]
            comparison[metric] = _estimate(differences, samples)
        result["paired_comparisons"].append(comparison)
    return result


def analyze_runs(run_dirs: list[str | Path], output: str | Path, *, bootstrap_samples: int = 2000,
                 seed: int = 0) -> dict[str, Any]:
    cells: list[dict[str, Any]] = []
    contract: str | None = None
    sources: list[str] = []
    stage: str | None = None
    integration_smoke: bool | None = None
    for directory in run_dirs:
        directory = Path(directory).resolve()
        manifest = _read(directory / "manifest.json")
        scores = _read(directory / "scores.json")
        if scores.get("status") != "completed" or manifest.get("status") != "completed":
            raise ValueError("Run execution and scoring must both be completed before analysis.")
        if (scores["config_digest"] != manifest["config_digest"] or
                scores["run_id"] != manifest["run_id"] or scores["stage"] != manifest["stage"]):
            raise ValueError("Scoring does not match the execution manifest.")
        if execution_digest(directory, manifest) != scores["execution_digest"]:
            raise ValueError("Execution artifacts changed after scoring.")
        smoke = manifest.get("integration_smoke", False)
        if integration_smoke is not None and smoke != integration_smoke:
            raise ValueError("Integration smoke outputs cannot be mixed with research results.")
        integration_smoke = smoke
        comparable = {key: value for key, value in manifest["config"].items()
                      if key not in ("conditions", "run_id", "notes")}
        current = json.dumps(comparable, sort_keys=True)
        if contract is not None and (current != contract or stage != scores["stage"]):
            raise ValueError("Do not pool stages or incompatible frozen experiment settings.")
        contract, stage = current, scores["stage"]
        cells.extend(scores["cells"])
        sources.append(str(directory))
    result = analyze_cells(cells, bootstrap_samples=bootstrap_samples, seed=seed)
    result.update(stage=stage, source_runs=sources, integration_smoke=integration_smoke)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    _write(output, result)
    return result
