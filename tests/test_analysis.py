import copy
import math

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
    assert condition["oracle_success_rate"]["standard_error"] == pytest.approx(0.25)
    assert condition["oracle_success_rate"]["task_count"] == 2
    assert condition["metrics"]["decode_throughput"]["value"] == 10


def test_task_bootstrap_retains_seed_pairing_and_conditions():
    a = [cell("t1", "a", 1, [True]), cell("t1", "a", 2, [False]),
         cell("t2", "a", 1, [False]), cell("t2", "a", 2, [True])]
    b = [dict(copy.deepcopy(item), condition={**item["condition"], "id": "b", "method": "b"})
         for item in a]
    result = analyze_cells(a + b, bootstrap_samples=300, seed=5)
    comparison = result["paired_comparisons"][0]
    estimate = comparison["oracle_success_rate"]
    assert estimate["value"] == 0 and estimate["ci95"] == [0, 0]
    assert estimate["standard_error"] == 0 and estimate["bootstrap_degenerate"]
    assert estimate["bounded_mean_ci95"] == [-1, 1]
    assert estimate["uncertainty_notes"]
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
    assert result["mean_peak_kv_bytes"]["value"] == 100
    assert result["mean_peak_kv_bytes"]["task_count"] == 1
    assert result["mean_peak_kv_bytes"]["coverage"]["complete_cells"] == 1


def test_resource_means_preserve_task_and_seed_clusters_and_pairing():
    first = []
    for task, peaks in (("t1", (100, 300)), ("t2", (500, 700))):
        for seed, peak in enumerate(peaks):
            record = cell(task, "a", seed, [False, False])
            for index, attempt in enumerate(record["attempts"]):
                attempt["metrics"]["peak_kv_bytes"] = peak - 50 * index
                attempt["metrics"]["peak_total_vram_bytes"] = 1000 + peak - 50 * index
            first.append(record)
    second = copy.deepcopy(first)
    for record in second:
        record["condition"].update(id="b", method="b")
        for attempt in record["attempts"]:
            attempt["metrics"]["peak_kv_bytes"] += 25
    result = analyze_cells(first + second, bootstrap_samples=300)
    estimate = result["conditions"]["a"]["mean_peak_kv_bytes"]
    assert estimate["value"] == 400
    assert estimate["standard_error"] == pytest.approx(200)
    assert estimate["ci95"] == [200, 600]
    assert estimate["task_count"] == 2
    assert estimate["coverage"] == {
        "observed_attempts": 8, "total_attempts": 8,
        "complete_cells": 4, "total_cells": 4, "complete_tasks": 2, "total_tasks": 2,
    }
    assert result["conditions"]["a"]["metrics"]["peak_kv_bytes"]["value"] == 700
    assert result["conditions"]["a"]["mean_peak_total_vram_bytes"]["value"] == 1400
    difference = result["paired_comparisons"][0]["mean_peak_kv_bytes"]
    assert difference["value"] == 25 and difference["standard_error"] == 0
    assert difference["ci95"] == [25, 25] and difference["paired_tasks"] == ["t1", "t2"]


def test_resource_missing_attempt_or_seed_is_not_zero_or_partial_maximum():
    records = [cell(task, condition, seed, [False, False])
               for condition in ("a", "b") for task in ("t1", "t2") for seed in (1, 2)]
    for record in records:
        if record["condition"]["id"] == "a" and record["seed"] == 2:
            record["attempts"][1]["metrics"].pop("peak_kv_bytes")
    result = analyze_cells(records, bootstrap_samples=50)
    estimate = result["conditions"]["a"]["mean_peak_kv_bytes"]
    assert estimate["value"] is None and estimate["standard_error"] is None
    assert estimate["ci95"] is None and estimate["task_count"] == 0
    assert estimate["coverage"]["observed_attempts"] == 6
    assert estimate["coverage"]["complete_cells"] == 2
    assert estimate["coverage"]["complete_tasks"] == 0
    difference = result["paired_comparisons"][0]["mean_peak_kv_bytes"]
    assert difference["value"] is None and difference["paired_tasks"] == []
    assert result["conditions"]["a"]["metrics"]["peak_kv_bytes"]["value"] == 100


def test_one_task_and_all_failure_uncertainty_are_explicit():
    single = analyze_cells([cell("t1", "a", 1, [False])], bootstrap_samples=50)
    estimate = single["conditions"]["a"]["oracle_success_rate"]
    assert estimate["value"] == 0 and estimate["ci95"] == [0, 0]
    assert estimate["standard_error"] is None and estimate["bootstrap_degenerate"]
    assert estimate["bounded_mean_ci95"] == [0, 1]
    assert len(estimate["uncertainty_notes"]) == 2
    repeated = [cell(f"t{task}", "a", seed, [False])
                for task in range(8) for seed in (17, 29)]
    multiple = analyze_cells(repeated, bootstrap_samples=50)
    estimate = multiple["conditions"]["a"]["oracle_success_rate"]
    assert estimate["task_count"] == 8 and estimate["standard_error"] == 0
    assert estimate["bounded_mean_ci95"] == [0, pytest.approx(math.sqrt(math.log(40) / 16))]
    assert estimate["bootstrap_degenerate"] and estimate["uncertainty_notes"]


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


def test_recovery_summary_retains_denials_failures_and_unknown_interruption(tmp_path):
    records = [cell(f"t{index}", "a", 1, [False], [status])
               for index, status in enumerate(("completed", "oom", "interrupted", "completed"))]
    for record in records:
        record["budget_seconds"] = 100
        record["attempts"][0]["recovery_events"] = []
    records[0]["attempts"][0]["recovery_events"] = [
        {"triggered": False, "reason": "below_threshold"},
        {"triggered": True, "result": {"admitted": False, "status": "denied", "seconds": 1,
                                       "reason": "transient_cap"}},
        {"triggered": True, "result": {"admitted": True, "status": "completed", "seconds": 3}},
    ]
    records[1]["attempts"][0]["recovery_events"] = [
        {"triggered": True, "result": {"admitted": True, "status": "failed", "seconds": 2,
                                       "failure_reason": "out of memory"}},
    ]
    records[2]["attempts"][0]["recovery_events"] = [
        {"triggered": True, "result": {"admitted": None, "status": "pending"}},
    ]
    result = analyze_cells(records, bootstrap_samples=10)["conditions"]["a"]["recovery"]
    assert result["decision_count"] == 5 and result["requested_count"] == 4
    assert result["admitted_count"] == 2
    assert result["admission_rate"] == {"value": pytest.approx(2 / 3),
                                          "observed_requests": 3, "total_requests": 4}
    assert result["result_status_counts"] == {"denied": 1, "completed": 1, "failed": 1, "pending": 1}
    assert result["refusal_reasons"] == {"transient_cap": 1}
    assert result["failure_reasons"] == {"out of memory": 1}
    assert result["recorded_seconds"]["value"] == 6
    assert result["mean_cell_budget_fraction"] == {
        "value": pytest.approx(0.02), "complete_cells": 3, "total_cells": 4}
    assert result["coverage"]["unknown_admission_requests"] == 1


def test_partial_failure_costs_remain_visible_with_coverage():
    records = [cell("t1", "a", 1, [False, False], ["completed", "oom"])]
    records[0]["attempts"][0]["metrics"]["metric_coverage"] = {"estimated_flops": "complete"}
    records[0]["attempts"][1]["metrics"]["metric_coverage"] = {"estimated_flops": "lower_bound"}
    result = analyze_cells(records, bootstrap_samples=10)["conditions"]["a"]
    assert result["metrics"]["estimated_flops"]["value"] == 400
    assert result["metrics"]["estimated_flops"]["coverage"] == {"complete": 1, "lower_bound": 1}
    assert result["recovery"]["recorded_seconds"]["value"] is None
    assert result["recovery"]["coverage"]["attempts_with_decisions"] == 0


def test_terminal_journal_reservations_are_separate_from_measured_latency():
    records = [cell("t1", "a", 1, [True]), cell("t2", "a", 1, [False], ["interrupted"])]
    records[0].update(elapsed_seconds=100, observed_elapsed_seconds=20, reserved_budget_seconds=80)
    records[1].update(elapsed_seconds=100)
    records[1]["attempts"][0]["reserved_budget_seconds"] = 100
    result = analyze_cells(records, bootstrap_samples=10)["conditions"]["a"]
    assert result["latency_seconds"]["value"] == 100
    assert result["reserved_budget_seconds"]["value"] == 90
    assert result["oracle_success_rate"]["value"] == 0.5
