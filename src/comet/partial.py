"""Offline snapshots of fully covered conditions from an unfinished study."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import itertools
import json
import multiprocessing
import shutil
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from comet.analysis import analyze_cells
from comet.artifacts import provenance, read_json, write_json
from comet.config import Experiment
from comet.evaluation import _inside, score_environment

TERMINAL_STATUSES = {"completed", "timeout", "oom", "context_limit", "error", "interrupted", "infeasible"}


def snapshot_study(partitions: Path, run: Path, output: Path) -> dict:
    partitions, run, output = (path.resolve() for path in (partitions, run, output))
    if output.is_relative_to(run) or run.is_relative_to(output):
        raise ValueError("Keep the partial report separate from live execution.")
    if output.exists():
        raise FileExistsError("Use a fresh partial-report directory.")
    cutoff = time.time()
    index = read_json(partitions / "index.json")
    study = Experiment.load(partitions / index["study_config"])
    if study.digest != index["study_digest"]:
        raise ValueError("Partition index differs from the frozen study.")
    conditions = {condition.id: condition for condition in study.conditions}
    required = set(itertools.product(study.task_ids, study.seeds))
    groups = {name: {} for name in conditions}
    manifests, declared, runtime = {}, set(), None
    for entry in index["partitions"]:
        config = Experiment.load(partitions / entry["config"])
        if config.digest != entry["digest"] or config.frozen.get("condition_partition_of") != study.digest:
            raise ValueError("Partition differs from the declared study.")
        settings = config.to_dict()
        parent = study.to_dict()
        if any(settings[key] != value for key, value in parent.items()
               if key not in {"conditions", "frozen", "notes"}):
            raise ValueError("Partition changes frozen experiment settings.")
        configured_conditions = {condition["id"]: condition for condition in settings["conditions"]}
        for condition in config.conditions:
            if condition != conditions.get(condition.id) or condition.id in declared:
                raise ValueError("Changed or duplicate partition condition.")
            declared.add(condition.id)
        name = Path(entry["config"]).stem
        directory = run / name
        if not (directory / "manifest.json").exists():
            continue
        manifest = read_json(directory / "manifest.json")
        if manifest["config_digest"] != config.digest or manifest.get("integration_smoke"):
            raise ValueError("Execution does not match the declared research partition.")
        current = {
            "engine": {key: value for key, value in manifest["engine"].items()
                       if key not in {"model_path", "memory", "warmup"}},
            "source": {key: manifest["provenance"][key]
                       for key in ("source_hashes", "installed_packages")},
        }
        if runtime is not None and runtime != current:
            raise ValueError("Cannot pool different source, runtime or hardware.")
        runtime = current
        manifests[name] = manifest
        for reference in manifest["cells"]:
            path = _inside(directory, reference["path"])
            if not path.exists() or path.stat().st_mtime > cutoff:
                continue
            content = path.read_bytes()
            cell = json.loads(content)
            if not cell.get("completed"):
                continue
            identity = (cell["task_id"], cell["seed"])
            condition = cell["condition"]["id"]
            if (
                cell.get("inflight") or identity not in required
                or cell["run_id"] != manifest["run_id"]
                or cell["config_digest"] != config.digest
                or cell["condition"] != configured_conditions.get(condition)
                or identity != (reference["task_id"], reference["seed"])
                or condition != reference["condition_id"]
                or identity in groups[condition]
            ):
                raise ValueError("Invalid or duplicate completed cell.")
            if any(attempt["status"] not in TERMINAL_STATUSES for attempt in cell["attempts"]):
                raise ValueError("Completed cell contains a nonterminal attempt.")
            groups[condition][identity] = (name, directory, reference, cell, content)
    if declared != set(conditions):
        raise ValueError("Partition index omits declared conditions.")
    included = [name for name, group in groups.items() if set(group) == required]
    if not included:
        raise ValueError("No condition has finished the full paired task set yet.")
    output.mkdir(parents=True)
    records = []
    for condition in included:
        for name, directory, reference, original, content in groups[condition].values():
            cell = copy.deepcopy(original)
            destination = output / "cells" / name / reference["id"]
            for attempt in cell["attempts"]:
                source = _inside(directory, attempt["artifact_dir"])
                target = destination / f"attempt-{attempt['attempt_index']:03d}"
                if attempt["status"] == "completed":
                    shutil.copytree(source / "environment", target / "environment")
                attempt["artifact_dir"] = str(target.relative_to(output))
            if _inside(directory, reference["path"]).read_bytes() != content:
                raise RuntimeError("A terminal cell changed during the snapshot; take a fresh snapshot.")
            cell["id"] = reference["id"]
            path = destination / "cell.json"
            write_json(path, cell)
            records.append({"path": str(path.relative_to(output)), "partition": name,
                            "source_cell": reference["path"],
                            "source_cell_sha256": hashlib.sha256(content).hexdigest()})
    for name, manifest in manifests.items():
        write_json(output / "sources" / name / "manifest.json", manifest)
    result = {
        "schema_version": 1, "kind": "partial-study-snapshot", "provisional": True,
        "status": "ready", "captured_at_unix": cutoff, "study": study.to_dict(),
        "study_digest": study.digest, "included_conditions": included,
        "coverage": {name: {"completed_cells": len(group), "expected_cells": len(required),
                            "included": name in included} for name, group in groups.items()},
        "selection": "Every condition with the complete paired task/seed set at capture time; no outcome filtering.",
        "cells": records,
    }
    write_json(output / "snapshot.json", result)
    return result


def _score_cell(output, reference, scorer):
    cell = read_json(_inside(output, reference["path"]))
    for attempt in cell["attempts"]:
        if attempt["status"] == "completed":
            environment = _inside(output, attempt["artifact_dir"]) / "environment"
            cache = environment / "partial-score.json"
            outcome = read_json(cache) if cache.exists() else scorer(environment)
            if type(outcome.get("success")) is not bool:
                raise ValueError("AppWorld scorer must return a boolean success.")
            write_json(cache, outcome)
            attempt.update(success=outcome["success"], evaluation=outcome)
        else:
            attempt.update(success=False, evaluation={"skipped": "execution failure",
                                                      "status": attempt["status"]})
    cell["oracle_success"] = any(attempt["success"] for attempt in cell["attempts"])
    cell["single_attempt_success"] = bool(cell["attempts"] and cell["attempts"][0]["success"])
    cell["actual_attempts"] = len(cell["attempts"])
    return cell


def score_snapshot(output: Path, *, scorer=None, bootstrap_samples=2000, workers=1) -> dict:
    if workers < 1:
        raise ValueError("Use at least one scoring worker.")
    snapshot = read_json(output / "snapshot.json")
    if snapshot.get("kind") != "partial-study-snapshot" or snapshot["status"] != "ready":
        raise ValueError("Require a prepared partial-study snapshot.")
    evaluator = provenance()
    evaluator_path = output / "evaluator.json"
    if evaluator_path.exists():
        previous = read_json(evaluator_path)
        if any(previous[key] != evaluator[key] for key in ("source_hashes", "installed_packages")):
            raise ValueError("Resume partial scoring with the same evaluator and runtime.")
    else:
        write_json(evaluator_path, evaluator)
    scorer = scorer or score_environment
    if workers == 1:
        scored = [_score_cell(output, reference, scorer) for reference in snapshot["cells"]]
    else:
        # AppWorld owns process-global database state, so threads cannot isolate evaluations.
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
            scored = list(pool.map(_score_cell, itertools.repeat(output), snapshot["cells"],
                                   itertools.repeat(scorer)))
    analysis = analyze_cells(scored, bootstrap_samples=bootstrap_samples)
    cuda_errors = {}
    for cell in scored:
        count = sum("illegal memory access" in (attempt.get("failure_reason") or "")
                    for attempt in cell["attempts"])
        if count:
            name = cell["condition"]["id"]
            cuda_errors[name] = cuda_errors.get(name, 0) + count
    analysis["execution_warnings"] = {"cuda_illegal_access_attempts": cuda_errors}
    analysis["partial_study"] = {key: snapshot[key] for key in (
        "provisional", "captured_at_unix", "study_digest", "included_conditions", "coverage", "selection")}
    write_json(output / "scores.json", {"provisional": True, "status": "completed",
                                       "evaluation_provenance": evaluator, "scoring_workers": workers,
                                       "cells": scored})
    write_json(output / "analysis.json", analysis)
    with (output / "summary.csv").open("w") as stream:
        columns = ["condition", "completed_cells", "expected_cells", "reported_tasks",
                   "first_attempt_success_percent", "oracle_success_percent",
                   "oom_attempts", "cuda_illegal_access_attempts"]
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for condition, coverage in snapshot["coverage"].items():
            row = {"condition": condition, "completed_cells": coverage["completed_cells"],
                   "expected_cells": coverage["expected_cells"], "reported_tasks": 0}
            if condition in analysis["conditions"]:
                result = analysis["conditions"][condition]
                row.update(reported_tasks=analysis["task_count"],
                           first_attempt_success_percent=100 * result["single_attempt_success_rate"]["value"],
                           oracle_success_percent=100 * result["oracle_success_rate"]["value"],
                           oom_attempts=result["attempt_status_counts"].get("oom", 0),
                           cuda_illegal_access_attempts=cuda_errors.get(condition, 0))
            writer.writerow(row)
    return analysis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot")
    snapshot.add_argument("partitions", type=Path)
    snapshot.add_argument("run", type=Path)
    snapshot.add_argument("output", type=Path)
    score = commands.add_parser("score")
    score.add_argument("output", type=Path)
    score.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if args.command == "snapshot":
        result = snapshot_study(args.partitions, args.run, args.output)
        print(json.dumps({"conditions": len(result["included_conditions"]), "cells": len(result["cells"])}))
    else:
        result = score_snapshot(args.output, workers=args.workers)
        print(json.dumps({"tasks": result["task_count"], "conditions": len(result["conditions"])}))


if __name__ == "__main__":
    main()
