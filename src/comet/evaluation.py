"""Post-hoc scoring from completed execution artifacts."""

from __future__ import annotations

import hashlib
import itertools
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

from comet.appworld import (
    APPWORLD_DATA_VERSION,
    APPWORLD_REVISION,
    configure_appworld_database_paths,
)
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
    configure_appworld_database_paths()
    from appworld import AppWorld, update_root
    from appworld.apps.lib.models.db import ModelHashHandler
    from appworld.evaluator import evaluate_task
    from appworld.task import Task

    root = Path(reference["appworld_root"])
    update_root(str(root))
    AppWorld.close_all()
    ModelHashHandler.reset()
    experiment_name = f"comet-scoring/{uuid.uuid4().hex}"
    destination = root / "experiments" / "outputs" / experiment_name / "tasks" / reference["task_id"]
    try:
        shutil.copytree(_inside(path, reference["task_directory"]), destination)
        # Counters are only a shortcut; force the pinned evaluator to inspect actual state.
        task = Task.load(task_id=reference["task_id"], load_ground_truth=False)
        models = task.model_collection
        models.reset_db_home_path()
        start_counters = models.model_hashes()
        end_counters: dict[str, dict[str, int]] = {}
        for name, count in start_counters.items():
            app, model = name.split(".")
            end_counters.setdefault(app, {})[model] = count + 1
        counter_path = destination / "dbs" / "model_hashes.json"
        state_check = {
            "policy": "exhaustive-model-comparison-v1",
            "original_counter_sha256": hashlib.sha256(counter_path.read_bytes()).hexdigest(),
            "models_checked": len(start_counters),
            "start_counters": start_counters,
            "comparison_counters": end_counters,
            "scope": "Temporary scoring metadata only; saved SQL, rows and actions are unchanged.",
        }
        _write(counter_path, end_counters)
        AppWorld.close_all()
        ModelHashHandler.reset()
        tracker = evaluate_task(
            task_id=reference["task_id"], experiment_name=experiment_name,
            suppress_errors=True, save_report=True,
        )
        result = tracker.to_dict()
        shutil.copytree(destination / "evaluation", path / "evaluation", dirs_exist_ok=True)
        _write(path / "evaluation" / "state-comparison.json", state_check)
        result["state_comparison"] = {
            key: state_check[key] for key in ("policy", "original_counter_sha256", "models_checked")
        }
        return result
    finally:
        primary_error = sys.exception()
        cleanup_errors = []
        scoring_root = root / "experiments" / "outputs" / experiment_name
        for cleanup in (AppWorld.close_all, ModelHashHandler.reset,
                        lambda: shutil.rmtree(scoring_root) if scoring_root.exists() else None):
            try:
                cleanup()
            except BaseException as error:
                cleanup_errors.append(error)
        if primary_error is not None:
            for error in cleanup_errors:
                primary_error.add_note(f"Scoring cleanup also failed: {type(error).__name__}: {error}")
        elif cleanup_errors:
            raise cleanup_errors[0]


def rescore_run(
    source: str | Path, output: str | Path, *, scorer: Callable[[Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Make an immutable-input scoring revision without changing the original results."""
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("Rescoring output must be separate from the source run.")
    if output.exists():
        raise FileExistsError("Rescoring output already exists; use evaluate to resume it.")
    with run_lock(source):
        manifest = _read(source / "manifest.json")
        if manifest.get("schema_version") != 1 or manifest.get("status") != "completed":
            raise ValueError("Rescoring requires a completed version-1 execution manifest.")
        original_digest = execution_digest(source, manifest)
        if (source / "scores.json").exists():
            if _read(source / "scores.json").get("execution_digest") != original_digest:
                raise ValueError("Original execution artifacts changed since scoring.")
        output.mkdir(parents=True)
        derivation = {
            "schema_version": 1,
            "preparation_complete": False,
            "source_run_id": manifest["run_id"],
            "source_manifest_sha256": hashlib.sha256((source / "manifest.json").read_bytes()).hexdigest(),
            "source_execution_digest": original_digest,
            "prior_output_sha256": {},
            "execution_repeated": False,
            "execution_artifacts_changed": False,
            "scoring_provenance": provenance(),
        }
        derivation_path = output / "rescoring" / "derivation.json"
        _write(derivation_path, derivation)
        shutil.copyfile(source / "manifest.json", output / "manifest.json")
        for name in ("cells", "checkpoints"):
            if (source / name).exists():
                shutil.copytree(source / name, output / name,
                                ignore=shutil.ignore_patterns("evaluation", ".lock"))
        if execution_digest(output, manifest) != original_digest:
            raise ValueError("Rescoring copy differs from the original execution artifacts.")
        prior_outputs = {}
        for name in ("scores.json", "analysis.json"):
            if (source / name).exists():
                content = (source / name).read_bytes()
                prior_outputs[name] = hashlib.sha256(content).hexdigest()
                archive = output / "rescoring" / f"prior-{name}"
                archive.parent.mkdir(exist_ok=True)
                archive.write_bytes(content)
        derivation.update(preparation_complete=True, prior_output_sha256=prior_outputs)
        _write(derivation_path, derivation)
    return evaluate_run(output, scorer=scorer)


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
    derivation_path = run_dir / "rescoring" / "derivation.json"
    derivation = _read(derivation_path) if derivation_path.exists() else None
    if derivation is not None and derivation.get("preparation_complete") is not True:
        raise ValueError("Rescoring copy preparation is incomplete; create a new revision directory.")
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
    if derivation is not None and (
        derivation.get("source_execution_digest") != source_digest or
        derivation.get("source_manifest_sha256") != hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    ):
        raise ValueError("Rescoring copy changed after preparation.")
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
