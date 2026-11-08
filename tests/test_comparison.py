import copy
from pathlib import Path

import pytest

from comet.analysis import analyze_runs
from comet.artifacts import read_json, write_json
from comet.comparison import compare_protocol_runs
from comet.config import Experiment, digest
from comet.evaluation import execution_digest


def scored_pair(tmp_path):
    config = Experiment.load(Path("configs/pilot-sampling-control-qwen8b.json")).to_dict()
    config.update(task_ids=["task1", "task2"], seeds=[17, 18])
    provenance = {"source_hashes": {"runner.py": "same"}, "installed_packages": {"appworld": "same"}}
    paths = []
    for arm in ("control", "candidate"):
        directory = tmp_path / arm
        settings = copy.deepcopy(config)
        settings.update(experiment_id=arm, notes=arm)
        settings["agent"]["max_consecutive_errors"] = 0 if arm == "control" else 5
        manifest = {
            "schema_version": 1, "run_id": arm, "stage": "pilot", "status": "completed",
            "config": settings, "config_digest": digest(settings), "integration_smoke": True,
            "engine": {"device_name": "fixture GPU", "model": settings["engine"]["model"]},
            "provenance": provenance, "dependencies": {"engine": "pinned"}, "cells": [],
        }
        cells = []
        for index, (task, seed) in enumerate((task, seed) for task in settings["task_ids"]
                                             for seed in settings["seeds"]):
            interrupted = arm == "candidate" and index == 3
            attempt_dir = f"cells/{task}-{seed}/attempt-000"
            attempt = {
                "attempt_index": 0, "artifact_dir": attempt_dir,
                "status": "interrupted" if interrupted else "completed",
                "elapsed_seconds": 0 if interrupted else (index + 1) * (10 if arm == "control" else 4),
                "metrics": {}, "recovery_events": [],
            }
            if interrupted:
                attempt["reserved_budget_seconds"] = settings["budget_seconds"]
            cell = {
                "schema_version": 1, "run_id": arm, "stage": "pilot",
                "config_digest": manifest["config_digest"], "task_id": task, "seed": seed,
                "condition": settings["conditions"][0], "completed": True,
                "elapsed_seconds": settings["budget_seconds"] if interrupted else attempt["elapsed_seconds"],
                "budget_seconds": settings["budget_seconds"], "attempts": [attempt],
            }
            cell_path = f"cells/{task}-{seed}/cell.json"
            manifest["cells"].append({"id": f"{task}-{seed}", "path": cell_path,
                                      "task_id": task, "condition_id": "full_once", "seed": seed})
            write_json(directory / cell_path, cell)
            observations = ["Execution failed: HTTP 401", "Execution failed: TypeError", "ok"]
            if arm == "candidate":
                observations = ["Execution failed: HTTP 401"] if interrupted else ["ok", "ok"]
            write_json(directory / attempt_dir / "trajectory.json", {
                "turns": [{"action": f"print({number})", "observation": text}
                          for number, text in enumerate(observations)]})
            scored = copy.deepcopy(cell)
            scored["attempts"][0].update(success=arm == "candidate" and index == 0, evaluation={})
            cells.append(scored)
        write_json(directory / "manifest.json", manifest)
        write_json(directory / "scores.json", {
            "status": "completed", "run_id": arm, "stage": "pilot",
            "config_digest": manifest["config_digest"], "cells": cells,
            "execution_digest": execution_digest(directory, manifest),
            "evaluation_provenance": provenance,
        })
        paths.append(directory)
    return paths


def test_protocol_comparison_preserves_pairing_failures_and_observation_coverage(tmp_path):
    control, candidate = scored_pair(tmp_path)
    result = compare_protocol_runs(control, candidate, tmp_path / "comparison.json",
                                   protocol_fields=["agent"], bootstrap_samples=100)
    condition = result["conditions"]["full_once"]
    assert result["changed_protocol_fields"] == ["agent"]
    assert result["arms"]["control"]["run_id"] == "control"
    assert result["arms"]["candidate"]["run_id"] == "candidate"
    assert result["task_count"] == 2 and result["replicate_seeds"] == [17, 18]
    assert condition["paired_comparison"]["direction"] == "candidate minus control"
    assert condition["paired_comparison"]["oracle_success_rate"]["value"] == 0.25
    assert condition["control"]["oracle_success_rate"]["bounded_mean_ci95"][1] > 0
    assert condition["candidate"]["attempt_status_counts"] == {"completed": 3, "interrupted": 1}
    behavior = condition["candidate"]["behavior"]
    assert behavior["error_rate"]["value"] == 0.25
    assert behavior["error_rate"]["task_count"] == 2
    assert behavior["attempt_duration_seconds"]["value"] == 6
    assert behavior["attempt_duration_seconds"]["task_count"] == 1
    assert behavior["coverage"]["interrupted_prefixes"] == 1
    assert behavior["reserved_budget_seconds"] == 600
    assert len(behavior["trajectories"]) == 4
    assert all(len(row["sha256"]) == 64 for row in behavior["trajectories"])
    with pytest.raises(ValueError, match="incompatible frozen"):
        analyze_runs([control, candidate], tmp_path / "ordinary.json", bootstrap_samples=10)


@pytest.mark.parametrize("field,value", [
    ("budget_seconds", 700), ("seeds", [17]),
    ("prompt", "An undeclared prompt intervention"),
])
def test_protocol_comparison_rejects_undeclared_or_numerical_changes(tmp_path, field, value):
    control, candidate = scored_pair(tmp_path)
    manifest = read_json(candidate / "manifest.json")
    manifest["config"][field] = value
    write_json(candidate / "manifest.json", manifest)
    scores = read_json(candidate / "scores.json")
    scores["execution_digest"] = execution_digest(candidate, manifest)
    write_json(candidate / "scores.json", scores)
    with pytest.raises(ValueError, match="outside the declared"):
        compare_protocol_runs(control, candidate, tmp_path / "result.json", protocol_fields=["agent"])


@pytest.mark.parametrize("field", ["engine", "provenance", "dependencies", "evaluation_provenance"])
def test_protocol_comparison_rejects_mixed_implementations_and_hardware(tmp_path, field):
    control, candidate = scored_pair(tmp_path)
    manifest = read_json(candidate / "manifest.json")
    scores = read_json(candidate / "scores.json")
    if field == "evaluation_provenance":
        scores[field]["source_hashes"]["evaluation.py"] = "different"
    elif field == "provenance":
        manifest[field]["installed_packages"]["appworld"] = "different"
    else:
        manifest[field]["different"] = True
    write_json(candidate / "manifest.json", manifest)
    scores["execution_digest"] = execution_digest(candidate, manifest)
    write_json(candidate / "scores.json", scores)
    with pytest.raises(ValueError, match="identical source"):
        compare_protocol_runs(control, candidate, tmp_path / "result.json", protocol_fields=["agent"])


def test_protocol_comparison_rejects_stale_scores_and_missing_pairs(tmp_path):
    control, candidate = scored_pair(tmp_path)
    scores_path = candidate / "scores.json"
    scores = read_json(scores_path)
    original = copy.deepcopy(scores)
    scores["cells"].pop()
    write_json(scores_path, scores)
    with pytest.raises(ValueError, match="every declared"):
        compare_protocol_runs(control, candidate, tmp_path / "result.json", protocol_fields=["agent"])
    original["cells"][0]["attempts"][0]["elapsed_seconds"] = 0
    write_json(scores_path, original)
    with pytest.raises(ValueError, match="differ from terminal"):
        compare_protocol_runs(control, candidate, tmp_path / "result.json", protocol_fields=["agent"])


def test_missing_trajectory_does_not_become_zero_error_or_zero_duration(tmp_path):
    control, candidate = scored_pair(tmp_path)
    next((candidate / "cells/task1-17").rglob("trajectory.json")).unlink()
    result = compare_protocol_runs(control, candidate, tmp_path / "result.json",
                                   protocol_fields=["agent"], bootstrap_samples=10)
    behavior = result["conditions"]["full_once"]["candidate"]["behavior"]
    assert behavior["error_rate"]["task_count"] == 1
    assert behavior["error_rate"]["value"] == 0.5
    assert behavior["coverage"]["observed_trajectories"] == 3
    assert behavior["attempt_duration_seconds"]["value"] == 6


def test_protocol_comparison_requires_declared_change_and_new_external_output(tmp_path):
    control, candidate = scored_pair(tmp_path)
    with pytest.raises(ValueError, match="Declare unique"):
        compare_protocol_runs(control, candidate, tmp_path / "result.json", protocol_fields=["sampling"])
    with pytest.raises(ValueError, match="outside both"):
        compare_protocol_runs(control, candidate, control / "result.json", protocol_fields=["agent"])
