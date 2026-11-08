"""Task-clustered analysis of separately scored runs."""

from __future__ import annotations

import itertools
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from comet.evaluation import _read, _write, execution_digest


def _quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    left = math.floor(index)
    right = math.ceil(index)
    return ordered[left] + (ordered[right] - ordered[left]) * (index - left)


def _estimate(values: list[float], bootstrap: list[float], *,
              bounds: tuple[float, float] | None = None) -> dict[str, Any]:
    count = len(values)
    degenerate = bool(bootstrap) and min(bootstrap) == max(bootstrap)
    notes = []
    if count < 2:
        notes.append("Fewer than two observed tasks; task-level standard error is unavailable.")
    if degenerate:
        notes.append("A degenerate bootstrap interval does not establish zero population uncertainty.")
    result = {
        "value": mean(values) if values else None,
        "ci95": [_quantile(bootstrap, 0.025), _quantile(bootstrap, 0.975)] if bootstrap else None,
        "standard_error": stdev(values) / math.sqrt(count) if count > 1 else None,
        "task_count": count,
        "bootstrap_degenerate": degenerate,
        "uncertainty_notes": notes,
    }
    if bounds is not None:
        radius = (bounds[1] - bounds[0]) * math.sqrt(math.log(40) / (2 * count)) if count else 0
        result["bounded_mean_ci95"] = [max(bounds[0], mean(values) - radius),
                                       min(bounds[1], mean(values) + radius)] if count else None
    return result


def _bootstrap(values: list[float], rng: random.Random, samples: int) -> list[float]:
    return [mean(rng.choices(values, k=len(values))) for _ in range(samples)] if values else []


def _resource_tasks(group: dict, tasks: list[str], task_seeds: dict, key: str) -> tuple[dict, dict]:
    values, cells = {}, {}
    observed_attempts = total_attempts = 0
    for identity, cell in group.items():
        measured = [attempt["metrics"][key] for attempt in cell["attempts"]
                    if isinstance(attempt.get("metrics", {}).get(key), (int, float))]
        total_attempts += len(cell["attempts"])
        observed_attempts += len(measured)
        if measured and len(measured) == len(cell["attempts"]):
            cells[identity] = max(measured)
    for task in tasks:
        if all((task, seed) in cells for seed in task_seeds[task]):
            values[task] = mean(cells[(task, seed)] for seed in task_seeds[task])
    return values, {
        "observed_attempts": observed_attempts, "total_attempts": total_attempts,
        "complete_cells": len(cells), "total_cells": len(group),
        "complete_tasks": len(values), "total_tasks": len(tasks),
    }


def _metric(attempts: list[dict[str, Any]], key: str, unit: str, aggregation: str) -> dict[str, Any]:
    values = [attempt["metrics"][key] for attempt in attempts
              if isinstance(attempt.get("metrics", {}).get(key), (int, float))]
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError(f"Invalid recorded metric: {key}")
    value = (sum(values) if aggregation == "sum" else max(values)) if values else None
    return {"value": value, "unit": unit, "aggregation": aggregation,
            "observed_attempts": len(values), "total_attempts": len(attempts),
            "coverage": dict(Counter(
                attempt.get("metrics", {}).get("metric_coverage", {}).get(key, "unspecified")
                if isinstance(attempt.get("metrics", {}).get(key), (int, float)) else "unavailable"
                for attempt in attempts
            ))}


def reserved_seconds(cell: dict) -> float:
    return cell.get("reserved_budget_seconds", 0) + sum(
        attempt.get("reserved_budget_seconds", 0) for attempt in cell["attempts"]
    )


def recovery_summary(cells: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe recorded decisions without treating absent failure records as denials."""
    attempts = [attempt for cell in cells for attempt in cell["attempts"]]
    events = [event for attempt in attempts for event in attempt.get("recovery_events", [])]
    requests = [event for event in events if event.get("triggered")]
    results = [event.get("result", {}) for event in requests]
    admissions = [result["admitted"] for result in results
                  if type(result.get("admitted")) is bool]
    allowances = [result["allowance_consumed"] for result in results
                  if type(result.get("allowance_consumed")) is bool]
    statuses = Counter(
        result.get("status", "completed" if result.get("admitted") is True else
                   "denied" if result.get("admitted") is False else "unknown")
        for result in results
    )
    durations = [result["seconds"] for result in results
                 if isinstance(result.get("seconds"), (int, float))]
    if any(not math.isfinite(value) or value < 0 for value in durations):
        raise ValueError("Invalid recorded recovery seconds")
    fractions = []
    for cell in cells:
        requested = [event for attempt in cell["attempts"]
                     for event in attempt.get("recovery_events", []) if event.get("triggered")]
        measured = [event.get("result", {}).get("seconds") for event in requested]
        complete = all("recovery_events" in attempt and attempt["status"] != "interrupted"
                       for attempt in cell["attempts"])
        budget = cell.get("budget_seconds")
        if (complete and isinstance(budget, (int, float)) and budget > 0
                and all(isinstance(value, (int, float)) for value in measured)):
            fractions.append(sum(measured) / budget)
    return {
        "decision_count": len(events), "requested_count": len(requests),
        "admitted_count": sum(admissions),
        "allowance_consumed_count": sum(allowances),
        "admission_rate": {
            "value": mean(admissions) if admissions else None,
            "observed_requests": len(admissions), "total_requests": len(requests),
        },
        "result_status_counts": dict(statuses),
        "refusal_reasons": dict(Counter(
            result.get("reason", "unspecified") for result in results
            if result.get("admitted") is False
        )),
        "failure_reasons": dict(Counter(
            result.get("failure_reason", "unspecified") for result in results
            if result.get("status") == "failed"
        )),
        "recorded_seconds": {
            "value": sum(durations) if durations else None,
            "observed_requests": len(durations), "total_requests": len(requests),
            "includes": "admission checks and admitted rebuilds, including observed failure time",
        },
        "mean_cell_budget_fraction": {
            "value": mean(fractions) if fractions else None,
            "complete_cells": len(fractions), "total_cells": len(cells),
        },
        "coverage": {
            "attempts_with_decisions": sum("recovery_events" in attempt for attempt in attempts),
            "interrupted_attempts": sum(attempt["status"] == "interrupted" for attempt in attempts),
            "total_attempts": len(attempts),
            "unknown_admission_requests": len(requests) - len(admissions),
            "requests_with_allowance_state": len(allowances),
        },
    }


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
                        "resampling_unit": "task, retaining all attempts and paired replicate seeds",
                        "standard_error_method": "sample standard deviation of task means / sqrt(tasks)",
                        "bounded_mean_method": "Hoeffding, clipped to [0,1] for success and [-1,1] for differences",
                        "interval_scope": "pointwise 95%; not simultaneous across conditions or metrics",
                        "assumption": "independent sampled tasks; repeats do not increase task count"},
        "task_count": len(tasks), "tasks": tasks, "replicate_seeds": task_seeds[tasks[0]],
        "conditions": {}, "paired_comparisons": [],
    }
    task_values: dict[str, dict[str, list[float]]] = {}
    bootstraps: dict[str, dict[str, list[float]]] = {}
    resource_values: dict[str, dict[str, dict[str, float]]] = {}
    resource_fields = {"mean_peak_kv_bytes": "peak_kv_bytes",
                       "mean_peak_total_vram_bytes": "peak_total_vram_bytes"}
    for condition_id, group in sorted(by_condition.items()):
        values: dict[str, list[float]] = {name: [] for name in (
            "oracle_success_rate", "single_attempt_success_rate", "actual_attempts", "latency_seconds",
            "reserved_budget_seconds",
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
            values["reserved_budget_seconds"].append(mean(reserved_seconds(cell) for cell in paired))
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
            "coverage": dict(Counter(
                "complete" if all(item.get("metric_coverage", {}).get(key) == "complete"
                                  for key in ("decode_tokens", "decode_seconds"))
                else "partial" if any(item.get("metric_coverage", {}).get(key) in
                                      {"partial", "lower_bound", "unavailable"}
                                      for key in ("decode_tokens", "decode_seconds"))
                else "unspecified" for item in decoding
            )),
        }
        methods = {attempt.get("metrics", {}).get("flops_estimation_method") for attempt in attempts}
        metrics["estimated_flops"]["methods"] = sorted(method for method in methods if method)
        result["conditions"][condition_id] = {
            "condition": conditions[condition_id],
            **{name: _estimate(value, bootstraps[condition_id][name],
                              bounds=(0, 1) if name.endswith("success_rate") else None)
               for name, value in values.items()},
            "attempt_status_counts": dict(Counter(attempt["status"] for attempt in attempts)),
            "infeasible_cells": sum(bool(cell.get("infeasible")) or
                                    any(attempt["status"] == "infeasible" for attempt in cell["attempts"])
                                    for cell in group.values()),
            "zero_attempt_cells": sum(not cell["attempts"] for cell in group.values()),
            "metrics": metrics,
            "recovery": recovery_summary(list(group.values())),
        }
        resource_values[condition_id] = {}
        for name, key in resource_fields.items():
            observed, coverage = _resource_tasks(group, tasks, task_seeds, key)
            resource_values[condition_id][name] = observed
            values_ = list(observed.values())
            result["conditions"][condition_id][name] = {
                **_estimate(values_, _bootstrap(values_, rng, bootstrap_samples)),
                "unit": "bytes", "coverage": coverage,
                "aggregation": "maximum across attempts per cell, mean across seeds per task, mean across tasks",
            }
    for left, right in itertools.combinations(sorted(by_condition), 2):
        comparison: dict[str, Any] = {"left": left, "right": right, "direction": "right minus left"}
        for metric in ("oracle_success_rate", "single_attempt_success_rate", "latency_seconds"):
            differences = [right_value - left_value for left_value, right_value in
                           zip(task_values[left][metric], task_values[right][metric], strict=True)]
            samples = [right_value - left_value for left_value, right_value in
                       zip(bootstraps[left][metric], bootstraps[right][metric], strict=True)]
            comparison[metric] = _estimate(
                differences, samples, bounds=(-1, 1) if metric.endswith("success_rate") else None,
            )
        for metric in resource_fields:
            left_values, right_values = resource_values[left][metric], resource_values[right][metric]
            paired_tasks = sorted(left_values.keys() & right_values.keys())
            differences = [right_values[task] - left_values[task] for task in paired_tasks]
            comparison[metric] = {
                **_estimate(differences, _bootstrap(differences, rng, bootstrap_samples)),
                "unit": "bytes", "paired_tasks": paired_tasks, "total_tasks": len(tasks),
            }
        result["paired_comparisons"].append(comparison)
    return result


def read_scored_run(directory: str | Path) -> tuple[dict, dict, dict]:
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
    runtime: dict[str, Any] = {
        "engine": {key: value for key, value in manifest.get("engine", {}).items()
                   if key not in {"model_path", "memory", "warmup"}},
    }
    for label, recorded in (("execution", manifest.get("provenance", {})),
                            ("evaluation", scores.get("evaluation_provenance", {}))):
        if not all(key in recorded for key in ("source_hashes", "installed_packages")):
            raise ValueError(f"Run is missing {label} source or runtime provenance.")
        runtime[label] = {key: recorded[key] for key in ("source_hashes", "installed_packages")}
    return manifest, scores, runtime


def analyze_runs(run_dirs: list[str | Path], output: str | Path, *, bootstrap_samples: int = 2000,
                 seed: int = 0) -> dict[str, Any]:
    cells: list[dict[str, Any]] = []
    contract: str | None = None
    sources: list[str] = []
    stage: str | None = None
    integration_smoke: bool | None = None
    runtime_contract: dict[str, Any] | None = None
    for directory in run_dirs:
        directory = Path(directory).resolve()
        manifest, scores, runtime = read_scored_run(directory)
        smoke = manifest.get("integration_smoke", False)
        if integration_smoke is not None and smoke != integration_smoke:
            raise ValueError("Integration smoke outputs cannot be mixed with research results.")
        integration_smoke = smoke
        if runtime_contract is not None and runtime != runtime_contract:
            raise ValueError("Do not pool runs with different source, evaluator, runtime or hardware.")
        runtime_contract = runtime
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
