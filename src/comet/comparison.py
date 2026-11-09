"""Explicit paired protocol comparisons, separate from ordinary run pooling."""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from statistics import mean

from comet.analysis import (
    _bootstrap,
    _estimate,
    analyze_cells,
    environment_initialization_summary,
    read_scored_run,
    reserved_seconds,
)
from comet.artifacts import read_json, write_json
from comet.config import Experiment, digest
from comet.evaluation import _inside
from comet.trajectory_audit import summarize


def _validated_cells(directory: Path, manifest: dict, scores: dict) -> list[dict]:
    config = Experiment.from_dict(manifest["config"])
    if config.digest != manifest["config_digest"]:
        raise ValueError("Manifest configuration digest is inconsistent")
    required = set(itertools.product(config.task_ids, (c.id for c in config.conditions), config.seeds))
    listed = [(item["task_id"], item["condition_id"], item["seed"]) for item in manifest["cells"]]
    scored = {(cell["task_id"], cell["condition"]["id"], cell["seed"]): cell
              for cell in scores["cells"]}
    if (set(listed) != required or len(listed) != len(required)
            or set(scored) != required or len(scored) != len(scores["cells"])):
        raise ValueError("Each protocol arm must contain every declared task/condition/seed exactly once")
    conditions = {condition.id: condition for condition in config.conditions}
    for reference in manifest["cells"]:
        recorded = read_json(_inside(directory, reference["path"]))
        identity = (reference["task_id"], reference["condition_id"], reference["seed"])
        cell = scored[identity]
        if (not recorded.get("completed")
                or recorded.get("condition") != asdict(conditions[identity[1]])
                or (recorded.get("task_id"), recorded.get("seed")) != (identity[0], identity[2])
                or any(recorded.get(key) != manifest[key] for key in ("run_id", "stage", "config_digest"))
                or any(cell.get(key) != value for key, value in recorded.items() if key != "attempts")
                or len(cell["attempts"]) != len(recorded["attempts"])
                or len(cell["attempts"]) > conditions[identity[1]].max_attempts):
            raise ValueError("Scored cells differ from completed execution artifacts")
        for index, (original, attempt) in enumerate(zip(recorded["attempts"], cell["attempts"], strict=True)):
            if (attempt.get("attempt_index") != index
                    or any(attempt.get(key) != value for key, value in original.items())
                    or attempt["status"] not in {"completed", "timeout", "oom", "context_limit",
                                                "error", "interrupted", "infeasible"}):
                raise ValueError("Scored attempts differ from terminal execution artifacts")
    return scores["cells"]


def _behavior(directory: Path, cells: list[dict], samples: int, seed: int) -> dict:
    rng = random.Random(seed)
    rows = []
    categories = Counter()
    total_attempts = observed = interrupted_prefixes = 0
    task_cells = defaultdict(list)
    for cell in cells:
        turns = errors = 0
        available = True
        durations = []
        for attempt in cell["attempts"]:
            total_attempts += 1
            path = _inside(directory, attempt["artifact_dir"]) / "trajectory.json"
            if path.exists():
                raw = path.read_bytes()
                audit = summarize(json.loads(raw))
                rows.append({"task_id": cell["task_id"], "seed": cell["seed"],
                             "attempt_index": attempt["attempt_index"],
                             "path": str(path.relative_to(directory)),
                             "sha256": hashlib.sha256(raw).hexdigest(), **audit})
                turns += audit["turns"]
                errors += audit["error_turns"]
                categories.update(audit["categories"])
                observed += 1
                interrupted_prefixes += attempt["status"] == "interrupted"
            else:
                available = False
            seconds = attempt.get("elapsed_seconds")
            if attempt["status"] != "interrupted" and isinstance(seconds, (int, float)):
                if not math.isfinite(seconds) or seconds < 0:
                    raise ValueError("Invalid measured attempt duration")
                durations.append(seconds)
        task_cells[cell["task_id"]].append({
            "error_rate": errors / turns if available and turns else None,
            "attempt_duration_seconds": mean(durations)
            if durations and len(durations) == len(cell["attempts"]) else None,
        })
    estimates = {}
    for metric in ("error_rate", "attempt_duration_seconds"):
        values = [mean(row[metric] for row in records) for records in task_cells.values()
                  if all(row[metric] is not None for row in records)]
        estimates[metric] = _estimate(values, _bootstrap(values, rng, samples),
                                      bounds=(0, 1) if metric == "error_rate" else None)
    return {
        **estimates, "saved_turns": sum(row["turns"] for row in rows),
        "error_turns": sum(row["error_turns"] for row in rows),
        "error_categories": dict(categories), "trajectories": rows,
        "coverage": {"observed_trajectories": observed, "total_attempts": total_attempts,
                     "interrupted_prefixes": interrupted_prefixes,
                     "total_tasks": len(task_cells)},
        "reserved_budget_seconds": sum(reserved_seconds(cell) for cell in cells),
        "definitions": {
            "error_rate": "error turns / saved turns per cell, averaged across seeds within task",
            "attempt_duration_seconds": "mean measured attempt duration per cell, then seeds within task; interrupted attempts unavailable",
            "coverage": "task estimates require every paired seed; saved interrupted prefixes remain visible in error rates",
        },
    }


def compare_protocol_runs(control_run: str | Path, candidate_run: str | Path,
                          output: str | Path, *, protocol_fields: list[str],
                          bootstrap_samples: int = 2000, seed: int = 0) -> dict:
    fields = set(protocol_fields)
    if not fields or fields - {"prompt", "agent"} or len(fields) != len(protocol_fields):
        raise ValueError("Declare unique protocol fields from prompt and agent")
    directories = [Path(control_run).resolve(), Path(candidate_run).resolve()]
    if directories[0] == directories[1]:
        raise ValueError("A protocol comparison needs two distinct runs")
    loaded = [read_scored_run(directory) for directory in directories]
    manifests = [item[0] for item in loaded]
    if manifests[0]["run_id"] == manifests[1]["run_id"]:
        raise ValueError("A protocol comparison needs independently identified runs")
    if any(manifest["stage"] != "pilot" or manifest["config"]["split"] not in {"train", "dev"}
           for manifest in manifests):
        raise ValueError("Protocol diagnostics require declared train/dev pilot runs")
    if (loaded[0][2] != loaded[1][2]
            or any(not manifest.get("dependencies") for manifest in manifests)
            or manifests[0]["dependencies"] != manifests[1]["dependencies"]):
        raise ValueError("Protocol arms require identical source, evaluator, runtime, hardware and dependencies")
    runtime = loaded[0][2]
    if (not all(runtime["engine"].get(key) for key in ("model", "device_name"))
            or any(not runtime[label][key] for label in ("execution", "evaluation")
                   for key in ("source_hashes", "installed_packages"))):
        raise ValueError("Protocol comparison requires recorded model, hardware, source and package identities")
    if manifests[0].get("integration_smoke", False) != manifests[1].get("integration_smoke", False):
        raise ValueError("Protocol arms cannot mix integration and research runs")
    excluded = fields | {"experiment_id", "notes"}
    configs = [manifest["config"] for manifest in manifests]
    comparable = [{key: value for key, value in config.items() if key not in excluded}
                  for config in configs]
    if comparable[0] != comparable[1]:
        raise ValueError("Protocol arms differ outside the declared prompt/agent fields")
    changed = sorted(field for field in fields if configs[0].get(field) != configs[1].get(field))
    if not changed:
        raise ValueError("No declared protocol field differs between the two arms")
    cells = [_validated_cells(directory, manifest, scores)
             for directory, (manifest, scores, _) in zip(directories, loaded, strict=True)]
    output = Path(output).resolve()
    if output.exists() or any(output.is_relative_to(directory) for directory in directories):
        raise ValueError("Save comparisons to a new output outside both immutable run directories")
    result = {
        "schema_version": 1, "kind": "paired_protocol_comparison", "stage": "pilot",
        "integration_smoke": manifests[0].get("integration_smoke", False),
        "declared_protocol_fields": sorted(fields), "changed_protocol_fields": changed,
        "arms": {
            name: {"run_id": manifest["run_id"], "experiment_id": manifest["config"]["experiment_id"],
                   "run_directory": str(directory), "config_digest": manifest["config_digest"],
                   "execution_digest": scores["execution_digest"],
                   "environment_initialization": environment_initialization_summary(manifest),
                   "protocol": {field: manifest["config"].get(field) for field in sorted(fields)}}
            for name, directory, (manifest, scores, _) in zip(
                ("control", "candidate"), directories, loaded, strict=True)
        },
        "runtime_contract_digest": digest(loaded[0][2]),
        "engine": loaded[0][2]["engine"],
        "dependencies_digest": digest(manifests[0]["dependencies"]), "conditions": {},
    }
    for condition in configs[0]["conditions"]:
        groups = [[cell for cell in arm if cell["condition"] == condition] for arm in cells]
        paired = []
        for name, group in zip(("control", "intervention"), groups, strict=True):
            for cell in group:
                copy_cell = copy.deepcopy(cell)
                copy_cell["condition"]["id"] = name
                paired.append(copy_cell)
        analysis = analyze_cells(paired, bootstrap_samples=bootstrap_samples, seed=seed)
        summaries = {}
        for name, identity, directory, group in zip(
                ("control", "candidate"), ("control", "intervention"), directories, groups, strict=True):
            summaries[name] = analysis["conditions"][identity]
            summaries[name]["condition"] = condition
            summaries[name]["behavior"] = _behavior(directory, group, bootstrap_samples, seed)
        comparison = analysis["paired_comparisons"][0]
        comparison.update(left="control", right="candidate", direction="candidate minus control")
        result["conditions"][condition["id"]] = {
            "condition": condition, **summaries, "paired_comparison": comparison,
        }
        result.update(task_count=analysis["task_count"], tasks=analysis["tasks"],
                      replicate_seeds=analysis["replicate_seeds"], uncertainty=analysis["uncertainty"])
    write_json(output, result)
    return result
