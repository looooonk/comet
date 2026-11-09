import copy
import random
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from statistics import mean

import pytest

from comet.analysis import _estimate, analyze_runs
from comet.artifacts import read_json, write_json
from comet.budget_sweep import analyze_budget_sweep, plot_budget_sweep
from comet.cli import main
from comet.config import Experiment, digest
from comet.evaluation import execution_digest


def _run(path, budget, conditions):
    config = Experiment.load(Path("tests/fixtures/full-cache.json")).to_dict()
    config.update(experiment_id=f"budget-{budget}", task_ids=["task1", "task2", "task3"],
                  seeds=[17, 18], budget_seconds=budget, max_attempts=2, conditions=conditions)
    provenance = {"source_hashes": {"runner.py": "same"}, "installed_packages": {"appworld": "same"}}
    manifest = {
        "schema_version": 1, "run_id": path.name, "stage": "pilot", "status": "completed",
        "config": config, "config_digest": digest(config), "integration_smoke": True,
        "engine": {"device_name": "fixture GPU", "model": config["engine"]["model"]},
        "provenance": provenance, "dependencies": {"engine": "pinned"}, "cells": [],
    }
    outcomes = ([[("completed", False), ("completed", True)], [("timeout", False)], [],
                 [("interrupted", False)], [("completed", True)], [("completed", True)]] if budget == 60 else
                [[("completed", False)], [("oom", False)], [], [("error", False)],
                 [("completed", True)], [("completed", True)]])
    scored = []
    for condition in conditions:
        for index, (task, seed) in enumerate((task, seed) for task in config["task_ids"] for seed in config["seeds"]):
            identity = f"{condition['id']}-{task}-{seed}"
            attempts = [{"attempt_index": number, "status": status, "elapsed_seconds": 2,
                         "artifact_dir": f"cells/{identity}/attempt-{number:03d}", "metrics": {}}
                        for number, (status, _) in enumerate(outcomes[index])]
            if attempts and attempts[0]["status"] == "interrupted":
                attempts[0]["reserved_budget_seconds"] = budget
            cell = {
                "schema_version": 1, "run_id": path.name, "stage": "pilot",
                "config_digest": manifest["config_digest"], "task_id": task, "seed": seed,
                "condition": condition, "completed": True, "elapsed_seconds": budget,
                "budget_seconds": budget, "attempts": attempts,
            }
            location = f"cells/{identity}/cell.json"
            write_json(path / location, cell)
            manifest["cells"].append({"id": identity, "path": location, "task_id": task,
                                      "condition_id": condition["id"], "seed": seed})
            cell = copy.deepcopy(cell)
            for attempt, (_, success) in zip(cell["attempts"], outcomes[index], strict=True):
                attempt["success"] = success
            scored.append(cell)
    write_json(path / "manifest.json", manifest)
    write_json(path / "scores.json", {
        "status": "completed", "run_id": path.name, "stage": "pilot",
        "config_digest": manifest["config_digest"], "execution_digest": execution_digest(path, manifest),
        "evaluation_provenance": provenance, "cells": scored,
    })
    return path


def _sweep(tmp_path):
    conditions = [{"id": "full", "method": "full", "retention": 1.0, "recovery": "never", "max_attempts": 2},
                  {"id": "agent", "method": "agentkv", "retention": 0.5, "recovery": "never", "max_attempts": 2}]
    return [_run(tmp_path / "short-full", 60, conditions[:1]),
            _run(tmp_path / "short-agent", 60, conditions[1:]),
            _run(tmp_path / "long", 120, conditions)]


def _manifest_change(path, mutate):
    manifest = read_json(path / "manifest.json")
    mutate(manifest)
    write_json(path / "manifest.json", manifest)
    scores = read_json(path / "scores.json")
    scores["execution_digest"] = execution_digest(path, manifest)
    write_json(path / "scores.json", scores)


def test_independent_endpoints_pool_shards_and_preserve_pairing_failures(tmp_path):
    paths = _sweep(tmp_path)
    result = analyze_budget_sweep(paths, tmp_path / "budget.json", bootstrap_samples=50, seed=4)
    assert result["budgets_seconds"] == [60, 120]
    assert result["task_count"] == 3 and result["replicate_seeds"] == [17, 18]
    points = result["conditions"]["full"]["points"]
    assert [point["oracle_success_rate"]["value"] for point in points] == [0.5, 1 / 3]
    assert points[0]["single_attempt_success_rate"]["value"] == 1 / 3
    assert points[0]["zero_attempt_cells"] == points[1]["zero_attempt_cells"] == 1
    assert points[0]["attempt_status_counts"] == {"completed": 4, "timeout": 1, "interrupted": 1}
    assert points[1]["attempt_status_counts"] == {"completed": 3, "oom": 1, "error": 1}
    assert points[0]["coverage"] == {"complete_cells": 6, "expected_cells": 6,
                                      "scored_attempts": 6, "started_attempts": 6}
    assert points[0]["reserved_budget_seconds"]["value"] == 10
    assert points[0]["budget_accounted_seconds"]["value"] == 60
    assert "latency_seconds" not in points[0]
    assert len(points[0]["observations"]) == 6
    rng = random.Random(4)
    draws = [[rng.randrange(3) for _ in range(3)] for _ in range(50)]
    assert result["uncertainty"]["task_draws_sha256"] == digest(draws)
    for point, values in zip(points, ([0.5, 0, 1], [0, 0, 1]), strict=True):
        expected = _estimate(values, [mean(values[index] for index in draw) for draw in draws], bounds=(0, 1))
        assert point["oracle_success_rate"] == expected
    assert [point["oracle_success_rate"] for point in result["conditions"]["agent"]["points"]] == [
        point["oracle_success_rate"] for point in points]
    assert all(len(source["scores_sha256"]) == 64 for source in result["source_runs"])
    with pytest.raises(ValueError, match="incompatible frozen"):
        analyze_runs(paths, tmp_path / "ordinary.json", bootstrap_samples=10)


@pytest.mark.parametrize("key,value", [
    ("prompt", "different prompt"), ("seeds", [17]), ("task_ids", ["task1"]),
    ("peak_vram_bytes", 35 << 30), ("max_attempts", 3),
])
def test_budget_sweep_rejects_undeclared_contract_changes(tmp_path, key, value):
    paths = _sweep(tmp_path)
    _manifest_change(paths[-1], lambda manifest: manifest["config"].update({key: value}))
    with pytest.raises(ValueError, match="outside budget_seconds"):
        analyze_budget_sweep(paths, tmp_path / "result.json")


@pytest.mark.parametrize("field", ["engine", "provenance", "dependencies", "evaluation_provenance"])
def test_budget_sweep_rejects_runtime_or_evaluator_mixing(tmp_path, field):
    paths = _sweep(tmp_path)
    if field == "evaluation_provenance":
        scores = read_json(paths[-1] / "scores.json")
        scores[field]["source_hashes"]["evaluation.py"] = "different"
        write_json(paths[-1] / "scores.json", scores)
    else:
        def change(manifest):
            target = manifest[field]["source_hashes"] if field == "provenance" else manifest[field]
            target["different"] = True
        _manifest_change(paths[-1], change)
    with pytest.raises(ValueError, match="identical source"):
        analyze_budget_sweep(paths, tmp_path / "result.json")


def test_budget_sweep_rejects_incomplete_pairing_and_changed_scored_cells(tmp_path):
    paths = _sweep(tmp_path)
    scores = read_json(paths[-1] / "scores.json")
    original = copy.deepcopy(scores)
    scores["cells"].pop()
    write_json(paths[-1] / "scores.json", scores)
    with pytest.raises(ValueError, match="every declared"):
        analyze_budget_sweep(paths, tmp_path / "result.json")
    original["cells"][0]["attempts"][0]["elapsed_seconds"] = 999
    write_json(paths[-1] / "scores.json", original)
    with pytest.raises(ValueError, match="differ from terminal"):
        analyze_budget_sweep(paths, tmp_path / "result.json")


def test_budget_sweep_rejects_duplicate_executions_and_missing_condition_points(tmp_path):
    paths = _sweep(tmp_path)
    revision = tmp_path / "scoring-revision"
    shutil.copytree(paths[0], revision)
    with pytest.raises(ValueError, match="Duplicate execution"):
        analyze_budget_sweep(paths + [revision], tmp_path / "result.json")
    with pytest.raises(ValueError, match="same condition definitions"):
        analyze_budget_sweep([paths[0], paths[-1]], tmp_path / "result.json")
    with pytest.raises(ValueError, match="two independently"):
        analyze_budget_sweep(paths[:2], tmp_path / "result.json")


@pytest.mark.parametrize("stage", ["diagnostic", "final"])
def test_budget_sweep_is_pilot_only(tmp_path, stage):
    paths = _sweep(tmp_path)
    def change(manifest):
        manifest["config"]["stage"] = stage
    _manifest_change(paths[-1], change)
    with pytest.raises(ValueError, match="ordinary train/dev pilot"):
        analyze_budget_sweep(paths, tmp_path / "result.json")


def test_budget_sweep_does_not_use_success_timestamps_and_rejects_failed_success(tmp_path):
    paths = _sweep(tmp_path)
    scores = read_json(paths[0] / "scores.json")
    scores["cells"][1]["attempts"][0]["success"] = True
    write_json(paths[0] / "scores.json", scores)
    with pytest.raises(ValueError, match="failures cannot"):
        analyze_budget_sweep(paths, tmp_path / "result.json")
    scores["cells"][1]["attempts"][0]["success"] = False
    for cell in scores["cells"]:
        for attempt in cell["attempts"]:
            attempt["success"] = False
    write_json(paths[0] / "scores.json", scores)
    result = analyze_budget_sweep(paths, tmp_path / "result.json", bootstrap_samples=10)
    point = result["conditions"]["full"]["points"][0]
    assert point["oracle_success_rate"]["value"] == 0
    assert point["oracle_success_rate"]["bounded_mean_ci95"][1] > 0


def test_budget_sweep_cli_plot_and_immutable_output(tmp_path):
    pytest.importorskip("matplotlib")
    paths = _sweep(tmp_path)
    result, figure = tmp_path / "result.json", tmp_path / "figure.svg"
    main(["analyze-budget-sweep", *map(str, paths), "--output", str(result), "--bootstrap-samples", "10"])
    main(["plot-budget-sweep", str(result), "--output", str(figure), "--title", "Synthetic validation only"])
    svg = " ".join(" ".join(ET.parse(figure).getroot().itertext()).split())
    assert "Synthetic validation only" in svg and "Independently executed budget (s)" in svg
    assert "no smoothing or monotonicity constraint" in svg
    assert "Failures and zero-attempt cells remain" in svg
    assert "Integration diagnostic" in svg
    with pytest.raises(ValueError, match="new output outside"):
        analyze_budget_sweep(paths, result)
    with pytest.raises(ValueError, match="new output outside"):
        analyze_budget_sweep(paths, paths[0] / "analysis.json")
    write_json(tmp_path / "attained.json", {"kind": "attained_oracle_curve"})
    with pytest.raises(ValueError, match="not attained-success"):
        plot_budget_sweep(tmp_path / "attained.json", figure)
