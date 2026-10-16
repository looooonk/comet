"""Post-hoc scoring from completed execution artifacts."""

from __future__ import annotations

import hashlib
import itertools
import shutil
import uuid
from pathlib import Path
from typing import Any, Callable

from comet.appworld import APPWORLD_DATA_VERSION, APPWORLD_REVISION, verify_appworld_revision
from comet.artifacts import provenance, run_lock
from comet.artifacts import read_json as _read
from comet.artifacts import write_json as _write


def _inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Artifact path escapes its run: {relative}")
    return path


def execution_digest(run_dir: Path, manifest: dict[str, Any]) -> str:
    digest = hashlib.sha256((run_dir / "manifest.json").read_bytes())
    for expected in manifest["cells"]:
        cell_path = _inside(run_dir, expected["path"])
        digest.update(cell_path.read_bytes())
        for attempt in _read(cell_path)["attempts"]:
            if attempt["status"] != "completed":
                continue
            environment = _inside(run_dir, attempt["artifact_dir"]) / "environment"
            for path in sorted(environment.rglob("*")):
                relative = path.relative_to(environment)
                if path.is_file() and "evaluation" not in relative.parts:
                    digest.update(str(relative).encode())
                    with path.open("rb") as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                            digest.update(chunk)
    return digest.hexdigest()


def score_environment(path: Path) -> dict[str, Any]:
    reference = _read(path / "reference.json")
    if (reference.get("appworld_revision") != APPWORLD_REVISION or
            reference.get("data_version") != APPWORLD_DATA_VERSION):
        raise ValueError("Saved environment has incompatible AppWorld code or data.")
    verify_appworld_revision()
    from appworld import AppWorld, update_root
    from appworld.evaluator import evaluate_task

    root = Path(reference["appworld_root"])
    update_root(str(root))
    AppWorld.close_all()
    experiment_name = f"comet-scoring/{uuid.uuid4().hex}"
    destination = root / "experiments" / "outputs" / experiment_name / "tasks" / reference["task_id"]
    shutil.copytree(_inside(path, reference["task_directory"]), destination)
    try:
        tracker = evaluate_task(
            task_id=reference["task_id"], experiment_name=experiment_name,
            suppress_errors=True, save_report=True,
        )
        result = tracker.to_dict()
        shutil.copytree(destination / "evaluation", path / "evaluation", dirs_exist_ok=True)
        return result
    finally:
        AppWorld.close_all()
        shutil.rmtree(root / "experiments" / "outputs" / experiment_name)


def evaluate_run(
    run_dir: str | Path, *, scorer: Callable[[Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    with run_lock(run_dir):
        return _evaluate_run(run_dir, scorer=scorer)


def _evaluate_run(
    run_dir: Path, *, scorer: Callable[[Path], dict[str, Any]] | None,
) -> dict[str, Any]:
    manifest_path = run_dir / "manifest.json"
    manifest = _read(manifest_path)
    if manifest.get("schema_version") != 1 or manifest.get("status") != "completed":
        raise ValueError("Scoring requires a completed version-1 execution manifest.")
    config = manifest["config"]
    required = set(itertools.product(config["task_ids"],
                                     (condition["id"] for condition in config["conditions"]),
                                     config["seeds"]))
    listed = [(cell["task_id"], cell["condition_id"], cell["seed"]) for cell in manifest["cells"]]
    if set(listed) != required or len(listed) != len(required):
        raise ValueError("Manifest must include every configured task, condition and seed exactly once.")
    conditions = {condition["id"]: condition for condition in config["conditions"]}
    cells: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for expected in manifest["cells"]:
        cell_path = _inside(run_dir, expected["path"])
        cell = _read(cell_path)
        identity = (cell["task_id"], cell["condition"]["id"], cell["seed"])
        if identity in seen:
            raise ValueError(f"Duplicate execution cell: {identity}")
        seen.add(identity)
        if (not cell.get("completed") or cell.get("schema_version") != 1 or
                cell.get("config_digest") != manifest["config_digest"] or
                cell.get("run_id") != manifest["run_id"] or
                cell.get("stage") != manifest["stage"] or
                cell["condition"] != conditions[expected["condition_id"]] or
                identity != (expected["task_id"], expected["condition_id"], expected["seed"])):
            raise ValueError(f"Incomplete or incompatible execution cell: {expected['id']}")
        attempts = cell["attempts"]
        if [attempt["attempt_index"] for attempt in attempts] != list(range(len(attempts))):
            raise ValueError("Attempt indices must be contiguous and ordered from zero.")
        if len(attempts) > cell["condition"]["max_attempts"]:
            raise ValueError("Execution exceeds its frozen attempt limit.")
        if any(attempt["status"] not in {"completed", "timeout", "oom", "context_limit", "error",
                                         "interrupted", "infeasible"} for attempt in attempts):
            raise ValueError("Every attempt must have a terminal status before scoring.")
        cells.append(cell)
    if not cells:
        raise ValueError("Execution manifest contains no cells.")
    source_digest = execution_digest(run_dir, manifest)
    output_path = run_dir / "scores.json"
    prior: dict[str, dict[str, Any]] = {}
    evaluation_provenance = provenance()
    if output_path.exists():
        existing = _read(output_path)
        if existing.get("execution_digest") != source_digest:
            raise ValueError("Execution artifacts changed since scoring; use a separate run.")
        previous = existing.get("evaluation_provenance", {})
        for key in ("source_hashes", "installed_packages"):
            if key not in previous or previous[key] != evaluation_provenance[key]:
                raise ValueError(f"Scoring requires the original evaluator ({key} differs or is missing).")
        evaluation_provenance = previous
        prior = {cell["id"]: cell for cell in existing["cells"]}
    output: dict[str, Any] = {
        "schema_version": 1, "run_id": manifest["run_id"], "stage": manifest["stage"],
        "config_digest": manifest["config_digest"], "execution_digest": source_digest,
        "integration_smoke": manifest.get("integration_smoke", False),
        "evaluation_provenance": evaluation_provenance,
        "status": "scoring", "metric": "oracle task success within budget (perfect-selection upper bound)",
        "cells": [],
    }
    scorer = scorer or score_environment
    for expected, cell in zip(manifest["cells"], cells, strict=True):
        scored = dict(cell, id=expected["id"], attempts=[])
        old_attempts = prior.get(expected["id"], {}).get("attempts", [])
        for attempt in cell["attempts"]:
            index = attempt["attempt_index"]
            if index < len(old_attempts):
                evaluated = old_attempts[index]
            elif attempt["status"] == "completed":
                environment = _inside(run_dir, attempt["artifact_dir"]) / "environment"
                result = scorer(environment)
                if type(result.get("success")) is not bool:
                    raise ValueError("AppWorld scorer must return a boolean success.")
                evaluated = dict(attempt, success=result["success"], evaluation=result)
            else:
                evaluated = dict(attempt, success=False,
                                 evaluation={"skipped": "execution failure", "status": attempt["status"]})
            scored["attempts"].append(evaluated)
        scored["oracle_success"] = any(item["success"] for item in scored["attempts"])
        scored["single_attempt_success"] = bool(scored["attempts"] and scored["attempts"][0]["success"])
        scored["actual_attempts"] = len(scored["attempts"])
        output["cells"].append(scored)
        _write(output_path, output)
    output["status"] = "completed"
    _write(output_path, output)
    return output
