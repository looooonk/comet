import copy
import json

import pytest
from test_analysis import cell

from comet.analysis import _attempt_times, analyze_cells
from comet.artifacts import write_json


def timed_cell(task, condition, seed, successes, times, statuses=None):
    record = cell(task, condition, seed, successes, statuses)
    record.update(budget_seconds=20, elapsed_seconds=20)
    for attempt, seconds in zip(record["attempts"], times, strict=True):
        if seconds is not None:
            attempt["budget_elapsed_seconds"] = seconds
    return record


def curve(result, condition="a"):
    return result["conditions"][condition]["observations"]["attained_oracle_curve"]


def test_success_time_preserves_task_seed_means_and_existing_paired_draws():
    first = [timed_cell("t1", "a", 1, [False, True], [2, 5]),
             timed_cell("t1", "a", 2, [False], [4]),
             timed_cell("t2", "a", 1, [True], [8]),
             timed_cell("t2", "a", 2, [True], [8])]
    second = copy.deepcopy(first)
    for record in second:
        record["condition"].update(id="b", method="b")
        if record["task_id"] == "t2":
            record["attempts"][0]["budget_elapsed_seconds"] = 10
    result = analyze_cells(first + second, bootstrap_samples=100, seed=3)
    points = curve(result)["points"]
    assert [point["seconds"] for point in points] == [0, 5, 8, 10, 20]
    assert [point["value"] for point in points] == [0, 0.25, 0.75, 0.75, 0.75]
    assert all(left["value"] <= right["value"] for left, right in zip(points, points[1:]))
    for condition in ("a", "b"):
        estimate = result["conditions"][condition]["oracle_success_rate"]
        endpoint = curve(result, condition)["points"][-1]
        assert {key: endpoint[key] for key in estimate} == estimate
    assert curve(result)["coverage"]["complete_cells"] == 4


def test_failed_zero_attempt_and_interrupted_cells_stay_in_curve_denominator():
    records = [timed_cell("t1", "a", 1, [False], [20], ["interrupted"]),
               timed_cell("t2", "a", 1, [], []),
               timed_cell("t3", "a", 1, [False], [23], ["timeout"])]
    records[0]["attempts"][0]["reserved_budget_seconds"] = 20
    records[2]["elapsed_seconds"] = 23
    result = analyze_cells(records, bootstrap_samples=20)
    observed = result["conditions"]["a"]["observations"]
    assert observed["attempts"][0]["budget_elapsed_seconds"] == 20
    assert observed["attempts"][0]["completion_seconds"] is None
    assert observed["attempts"][0]["timing_status"] == "interrupted"
    assert curve(result)["status"] == "available"
    assert curve(result)["coverage"]["complete_cells"] == 3
    for point in curve(result)["points"]:
        assert point["value"] == 0 and point["ci95"] == [0, 0]
        assert point["task_count"] == 3 and point["bounded_mean_ci95"][1] > 0


def test_unknown_first_success_time_has_no_duration_or_cell_time_fallback():
    record = timed_cell("t1", "a", 1, [True, True], [None, 10])
    record["attempts"][0]["elapsed_seconds"] = 3
    record["reserved_budget_seconds"] = 5
    result = analyze_cells([record, timed_cell("t2", "a", 1, [False], [4])], bootstrap_samples=20)
    observed = result["conditions"]["a"]["observations"]
    assert observed["cells"][0]["first_success_time"]["seconds"] is None
    assert curve(result)["status"] == "unavailable" and curve(result)["points"] == []
    assert curve(result)["coverage"] == {
        "total_cells": 2, "complete_cells": 1, "success_cells": 1, "timed_success_cells": 0,
        "unavailable_cells": [{"task_id": "t1", "seed": 1, "reasons": ["missing_timestamp"]}],
    }
    assert result["conditions"]["a"]["oracle_success_rate"]["value"] == 0.5


@pytest.mark.parametrize("later_interruption", [False, True])
def test_earlier_measured_success_survives_later_reservation(later_interruption):
    record = timed_cell("t1", "a", 1, [True, not later_interruption], [5, None],
                        ["completed", "interrupted" if later_interruption else "completed"])
    if later_interruption:
        record["attempts"][1].update(budget_elapsed_seconds=20, reserved_budget_seconds=15)
    else:
        record["reserved_budget_seconds"] = 10
    result = analyze_cells([record], bootstrap_samples=20)
    assert curve(result)["status"] == "available"
    points = curve(result)["points"]
    assert [(point["seconds"], point["value"]) for point in points] == [(0, 0), (5, 1), (20, 1)]
    assert points[-1]["bounded_mean_ci95"][0] < 1 and points[-1]["ci95"] == [1, 1]


@pytest.mark.parametrize(("timestamp", "reason"), [
    (None, "missing_timestamp"), (-1, "invalid_timestamp"), (float("nan"), "invalid_timestamp"),
    (True, "invalid_timestamp"), (25, "success_after_declared_budget"),
])
def test_invalid_success_timestamps_are_explicitly_unavailable(timestamp, reason):
    record = timed_cell("t1", "a", 1, [True], [timestamp])
    record["elapsed_seconds"] = 30
    result = analyze_cells([record], bootstrap_samples=10)
    assert curve(result)["status"] == "unavailable"
    assert curve(result)["coverage"]["unavailable_cells"][0]["reasons"] == [reason]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("reserved", [False, True])
def test_success_time_rejects_nonmonotone_or_reserved_prior_schedule(reserved):
    record = timed_cell("t1", "a", 1, [False, True], [15, 10])
    if reserved:
        record["attempts"][0]["reserved_budget_seconds"] = 15
    result = analyze_cells([record], bootstrap_samples=10)
    expected = "unobserved_prior_reservation" if reserved else "nonmonotone_schedule"
    assert curve(result)["coverage"]["unavailable_cells"][0]["reasons"] == [expected]


@pytest.mark.parametrize("reservation", [None, -1, float("nan"), float("inf"), True])
def test_malformed_reservation_invalidates_current_and_later_completion_times(reservation):
    record = timed_cell("t1", "a", 1, [True, True], [5, 10])
    record["attempts"][0]["reserved_budget_seconds"] = reservation
    times = _attempt_times(record)
    assert [attempt["completion_seconds"] for attempt in times] == [None, None]
    assert [attempt["timing_status"] for attempt in times] == [
        "invalid_reservation", "unobserved_prior_reservation"]
    json.dumps(times, allow_nan=False)
    with pytest.raises(ValueError, match="Invalid recorded reserved_budget_seconds"):
        analyze_cells([record], bootstrap_samples=10)


@pytest.mark.parametrize("budget", [None, 0, float("nan")])
def test_legacy_missing_budget_marks_curve_unavailable_without_inventing_axis(budget):
    record = timed_cell("t1", "a", 1, [False], [None])
    record["budget_seconds"] = budget
    result = analyze_cells([record], bootstrap_samples=10)
    assert curve(result)["status"] == "unavailable" and curve(result)["budget_seconds"] is None
    assert curve(result)["coverage"]["unavailable_cells"][0]["reasons"] == ["missing_or_invalid_budget"]
    json.dumps(result, allow_nan=False)


def test_inconsistent_cell_budgets_are_not_pooled_into_a_curve():
    records = [timed_cell("t1", "a", 1, [True], [5]), timed_cell("t2", "a", 1, [False], [7])]
    records[1]["budget_seconds"] = 30
    result = analyze_cells(records, bootstrap_samples=10)
    assert curve(result)["status"] == "unavailable" and curve(result)["budget_seconds"] is None
    assert all(cell["reasons"] == ["inconsistent_cell_budgets"]
               for cell in curve(result)["coverage"]["unavailable_cells"])


def plot_fixture():
    records = []
    conditions = [{"id": "full", "method": "full", "retention": 1, "recovery": "never", "max_attempts": 1}]
    conditions += [{"id": f"{method}-{retention}-{policy}", "method": method, "retention": retention,
                    "recovery": policy, "max_attempts": 1}
                   for method in ("streamingllm", "rkv", "agentkv")
                   for retention in (0.8, 0.5, 0.25) for policy in ("never", "fixed", "dynamic")]
    for condition in conditions:
        for task, success in (("t1", True), ("t2", False)):
            record = timed_cell(task, condition["id"], 17, [success], [5])
            record["condition"] = condition
            records.append(record)
    result = analyze_cells(records, bootstrap_samples=20)
    result["stage"] = "synthetic layout validation"
    return result


@pytest.mark.parametrize("additional_ceiling", [False, True])
def test_success_time_plot_uses_compact_grid_and_at_most_four_curves(tmp_path, monkeypatch, additional_ceiling):
    pytest.importorskip("matplotlib")
    from comet import policy_plots

    source, output = tmp_path / "analysis.json", tmp_path / "layout.svg"
    analysis = plot_fixture()
    if additional_ceiling:
        extra = copy.deepcopy(analysis["conditions"]["full"])
        extra["condition"].update(id="full2", max_attempts=2)
        analysis["conditions"]["full2"] = extra
    write_json(source, analysis)
    save = policy_plots._save

    def inspect_save(fig, *args, **kwargs):
        visible = [axis for axis in fig.axes if axis.get_visible()]
        assert len(visible) == (10 if additional_ceiling else 9)
        assert all(axis.get_subplotspec().get_gridspec().ncols == 3 for axis in fig.axes)
        assert all(len(axis.get_legend().get_texts()) <= 4 for axis in visible)
        if additional_ceiling:
            assert visible[-1].get_title() == "Full KV attempt limits"
            assert [text.get_text() for text in visible[-1].get_legend().get_texts()] == [
                "Full KV N=1 (2/2)", "Full KV N=2 (2/2)"]
        save(fig, *args, **kwargs)

    monkeypatch.setattr(policy_plots, "_save", inspect_save)
    policy_plots.plot_attained_oracle(source, output, title="Synthetic layout validation only")
    svg = output.read_text()
    assert "Synthetic layout validation only" in svg and "not simultaneous" in svg
    assert "smaller-budget rerun" in svg


def test_success_time_cli_renders_explicit_missing_coverage(tmp_path):
    pytest.importorskip("matplotlib")
    from comet.cli import main

    analysis = plot_fixture()
    full = analysis["conditions"]["full"]
    full["observations"]["attained_oracle_curve"].update(status="unavailable", points=[])
    full["observations"]["attained_oracle_curve"]["coverage"].update(
        complete_cells=1, unavailable_cells=[{"task_id": "t1", "seed": 17, "reasons": ["missing_timestamp"]}])
    analysis["conditions"] = {"full": full}
    source, output = tmp_path / "missing.json", tmp_path / "missing.svg"
    write_json(source, analysis)
    main(["plot-success-time", str(source), "--output", str(output)])
    svg = output.read_text()
    assert "Full KV (1/2) unavailable" in svg and "missing timestamp" in svg
