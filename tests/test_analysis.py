import copy

import pytest

from comet.analysis import analyze_cells, analyze_runs
from comet.artifacts import write_json
from comet.evaluation import execution_digest


def cell(task, condition, seed, successes, statuses=None):
    statuses = statuses or ["completed"] * len(successes)
    return {
        "task_id": task, "condition": {"id": condition, "method": condition,
                                        "retention": 1, "recovery": "never", "max_attempts": 20},
        "seed": seed, "completed": True, "elapsed_seconds": 10,
        "attempts": [{"attempt_index": index, "status": status, "success": success,
                      "metrics": {"generated_tokens": 21, "decode_tokens": 20, "decode_seconds": 2,
                                  "estimated_flops": 200, "peak_kv_bytes": 100,
                                  "peak_total_vram_bytes": 900}}
                     for index, (success, status) in enumerate(zip(successes, statuses, strict=True))],
    }


def test_oracle_is_per_task_and_replicate_seeds_are_averaged():
    cells = [cell("t1", "a", 1, [False, True]), cell("t1", "a", 2, [False, False]),
             cell("t2", "a", 1, [False] * 20), cell("t2", "a", 2, [False] * 20)]
    result = analyze_cells(cells, bootstrap_samples=300)
    condition = result["conditions"]["a"]
    assert condition["oracle_success_rate"]["value"] == 0.25
    assert condition["single_attempt_success_rate"]["value"] == 0
    assert condition["actual_attempts"]["value"] == 11
    assert condition["oracle_success_rate"]["ci95"] == [0, 0.5]
    assert condition["metrics"]["decode_throughput"]["value"] == 10


def test_task_bootstrap_retains_seed_pairing_and_conditions():
    a = [cell("t1", "a", 1, [True]), cell("t1", "a", 2, [False]),
         cell("t2", "a", 1, [False]), cell("t2", "a", 2, [True])]
    b = [dict(copy.deepcopy(item), condition={**item["condition"], "id": "b", "method": "b"})
         for item in a]
    result = analyze_cells(a + b, bootstrap_samples=300, seed=5)
    comparison = result["paired_comparisons"][0]
    assert comparison["oracle_success_rate"] == {"value": 0, "ci95": [0, 0]}
    assert result == analyze_cells(a + b, bootstrap_samples=300, seed=5)
    with pytest.raises(ValueError, match="same paired"):
        analyze_cells(a + b[:-1])


def test_failures_zero_attempts_and_missing_metrics_are_retained():
    cells = [cell("t1", "a", 1, [False, False], ["timeout", "oom"]),
             cell("t2", "a", 1, []), cell("t3", "a", 1, [False], ["infeasible"])]
    cells[0]["attempts"][1]["metrics"] = {}
    cells[1]["infeasible"] = True
    result = analyze_cells(cells, bootstrap_samples=50)["conditions"]["a"]
    assert result["oracle_success_rate"]["value"] == 0
    assert result["zero_attempt_cells"] == 1
    assert result["infeasible_cells"] == 2
    assert result["attempt_status_counts"] == {"timeout": 1, "oom": 1, "infeasible": 1}
    assert result["metrics"]["peak_kv_bytes"]["observed_attempts"] == 2
    assert result["metrics"]["peak_kv_bytes"]["total_attempts"] == 3


def test_analysis_rejects_duplicates_and_failed_success():
    record = cell("t1", "a", 1, [True], ["timeout"])
    with pytest.raises(ValueError, match="failures"):
        analyze_cells([record])
    record["attempts"][0]["status"] = "completed"
    with pytest.raises(ValueError, match="Duplicate"):
        analyze_cells([record, record])


def _metadata():
    return {
        "engine": {"backend": "fixture", "packages": {"torch": "same"}, "device_name": "A100",
                   "model_path": "/one/model", "memory": {"peak": 1}, "warmup": {"seconds": 1}},
        "provenance": {"source_hashes": {"runner.py": "same"},
                       "installed_packages": {"appworld": "same"}, "hostname": "one"},
        "evaluation_provenance": {"source_hashes": {"evaluation.py": "same"},
                                  "installed_packages": {"appworld": "same"}},
    }


def _scored_run(path, condition, metadata):
    record = cell("t1", condition, 1, [True])
    record["attempts"][0]["artifact_dir"] = "attempts/0"
    manifest = {
        "schema_version": 1, "run_id": condition, "stage": "pilot", "status": "completed",
        "config_digest": condition, "integration_smoke": False,
        "config": {"task_ids": ["t1"], "seeds": [1], "conditions": [record["condition"]]},
        "engine": metadata["engine"], "provenance": metadata["provenance"],
        "cells": [{"path": "cell.json"}],
    }
    write_json(path / "cell.json", record)
    write_json(path / "manifest.json", manifest)
    write_json(path / "scores.json", {
        "status": "completed", "run_id": condition, "stage": "pilot", "config_digest": condition,
        "execution_digest": execution_digest(path, manifest), "cells": [record],
        "evaluation_provenance": metadata["evaluation_provenance"],
    })
    return path


@pytest.mark.parametrize("keys", [
    ("engine", "packages", "torch"),
    ("engine", "device_name"),
    ("provenance", "source_hashes", "runner.py"),
    ("provenance", "installed_packages", "appworld"),
    ("evaluation_provenance", "source_hashes", "evaluation.py"),
    ("evaluation_provenance", "installed_packages", "appworld"),
])
def test_analysis_refuses_mixed_execution_or_evaluator_provenance(tmp_path, keys):
    first = _scored_run(tmp_path / "first", "a", _metadata())
    changed = _metadata()
    target = changed
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = "different"
    second = _scored_run(tmp_path / "second", "b", changed)
    with pytest.raises(ValueError, match="different source, evaluator, runtime or hardware"):
        analyze_runs([first, second], tmp_path / "analysis.json", bootstrap_samples=10)


def test_analysis_ignores_locations_and_transient_engine_measurements(tmp_path):
    first = _scored_run(tmp_path / "first", "a", _metadata())
    changed = _metadata()
    changed["engine"].update(model_path="/two/model", memory={"peak": 2}, warmup={"seconds": 3})
    changed["provenance"]["hostname"] = "two"
    second = _scored_run(tmp_path / "second", "b", changed)
    result = analyze_runs([first, second], tmp_path / "analysis.json", bootstrap_samples=10)
    assert set(result["conditions"]) == {"a", "b"}
