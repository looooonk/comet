import pytest

from comet.trigger_timing import (
    arm_summary,
    paired_tasks,
    prefix_report,
    shared_prefix,
    turns_before_rebuild,
)

LISTING = "print(apis.api_docs.show_api_descriptions(app_name='spotify'))"
SEARCH = "print(apis.api_docs.search_api_docs(query='playlist'))"


def _attempt(actions, status="completed", success=False, rebuilds=0, index=0):
    return {"attempt_index": index, "status": status, "success": success, "rebuilds": rebuilds,
            "tool_calls": sum(bool(a) for a in actions),
            "turns": [{"action": a, "obs_chars": 10, "obs_head": ""} for a in actions]}


def _cell(task, attempts, oracle=False, first=False):
    return {"task_id": task, "seed": 17, "condition": {"id": "agentkv_50_fixed"},
            "oracle_success": oracle, "single_attempt_success": first, "attempts": attempts}


def test_shared_prefix_counts_identical_leading_actions():
    assert shared_prefix(["a", "b", "c"], ["a", "b", "x", "c"]) == 2
    assert shared_prefix([], ["a"]) == 0
    assert shared_prefix(["a"], ["a"]) == 1


def test_turns_before_rebuild_skips_turns_without_an_executed_action():
    assert turns_before_rebuild(["a", "", "b", "c"], 2) == 3
    assert turns_before_rebuild(["a", "b"], 6) == 2
    assert turns_before_rebuild([], 1) == 0


def test_prefix_report_flags_attempts_that_diverge_before_the_rebuild():
    reference = [_cell("t1", [_attempt(["a", "b", "c", "d"])]), _cell("t2", [_attempt(["a", "b"])])]
    cells = [_cell("t1", [_attempt(["a", "b", "x"])]), _cell("t2", [_attempt(["z", "b"])])]
    report = prefix_report(cells, reference, threshold=2)
    assert report["attempts_compared"] == 2
    assert report["consistent"] == 1
    assert report["divergent"] == [{"task_id": "t2", "seed": 17, "attempt_index": 0, "shared": 0, "expected": 2}]


def test_prefix_report_ignores_attempts_missing_from_the_reference():
    reference = [_cell("t1", [_attempt(["a"])])]
    cells = [_cell("t1", [_attempt(["a"]), _attempt(["b"], index=1)]), _cell("t9", [_attempt(["a"])])]
    report = prefix_report(cells, reference, threshold=1)
    assert report["attempts_compared"] == 1 and report["consistent"] == 1


def test_arm_summary_counts_outcomes_endings_and_rebuilds():
    cells = [
        _cell("t1", [_attempt([SEARCH, SEARCH], status="context_limit"),
                     _attempt([LISTING, "x"], success=True, rebuilds=1, index=1)], oracle=True),
        _cell("t2", [_attempt([LISTING], status="timeout", rebuilds=1)]),
    ]
    summary = arm_summary(cells)
    assert summary["cells"] == 2 and summary["attempts"] == 3
    assert summary["tasks_solved"] == 1 and summary["first_attempt_solved"] == 0
    assert summary["passing_attempts"] == 1
    assert summary["context_limit_attempts"] == 1
    assert summary["rebuilt_attempts"] == 2
    assert summary["status"] == {"context_limit": 1, "completed": 1, "timeout": 1}
    assert summary["by_opening"] == {
        "listing": {"attempts": 2, "passed": 1, "context_limit": 0},
        "search": {"attempts": 1, "passed": 0, "context_limit": 1},
    }


def test_arm_summary_reports_unscored_cells_instead_of_counting_them_as_failures():
    cells = [{**_cell("t1", [_attempt([LISTING])]), "oracle_success": None, "single_attempt_success": None}]
    summary = arm_summary(cells)
    assert summary["unscored_cells"] == 1 and summary["tasks_solved"] is None


def test_paired_tasks_lists_gains_and_losses_by_task():
    left = [_cell("t1", [], oracle=True), _cell("t2", [], oracle=False), _cell("t3", [], oracle=True)]
    right = [_cell("t1", [], oracle=False), _cell("t2", [], oracle=True), _cell("t3", [], oracle=True)]
    paired = paired_tasks(left, right)
    assert paired == {"pairs": 3, "unscored_pairs": 0, "both": 1, "left_only": ["t1"],
                      "right_only": ["t2"], "neither": 0}


def test_paired_tasks_sets_unscored_pairs_aside_instead_of_counting_a_gain():
    left = [{**_cell("t1", []), "oracle_success": None}, _cell("t2", [], oracle=True), _cell("t9", [])]
    right = [_cell("t1", [], oracle=True), _cell("t2", [], oracle=True)]
    paired = paired_tasks(left, right)
    assert paired == {"pairs": 1, "unscored_pairs": 1, "both": 1, "left_only": [],
                      "right_only": [], "neither": 0}


def test_duplicate_cells_are_rejected_rather_than_double_counted():
    twice = [_cell("t1", [], oracle=True), _cell("t1", [], oracle=True)]
    once = [_cell("t1", [], oracle=False)]
    with pytest.raises(ValueError, match="Duplicate cell"):
        paired_tasks(twice, once)
    with pytest.raises(ValueError, match="Duplicate cell"):
        paired_tasks(once, twice)
    with pytest.raises(ValueError, match="Duplicate cell"):
        prefix_report(once, twice, threshold=1)
    repeated = [_cell("t1", [_attempt(["a"]), _attempt(["a"])])]
    with pytest.raises(ValueError, match="Duplicate attempt"):
        prefix_report(once, repeated, threshold=1)


def test_thresholds_below_one_are_rejected():
    with pytest.raises(ValueError, match="threshold"):
        turns_before_rebuild(["a", "b"], 0)
    with pytest.raises(ValueError, match="threshold"):
        prefix_report([], [], threshold=0)


def test_turns_before_rebuild_when_the_threshold_falls_on_the_last_turn():
    assert turns_before_rebuild(["a", "b"], 2) == 2
    assert turns_before_rebuild(["", ""], 1) == 2


def test_prefix_report_caps_the_expectation_at_a_shorter_reference_and_handles_empty_attempts():
    reference = [_cell("t1", [_attempt(["a"])]), _cell("t2", [_attempt([])])]
    cells = [_cell("t1", [_attempt(["a", "b", "c"])]), _cell("t2", [_attempt([])])]
    report = prefix_report(cells, reference, threshold=3)
    assert report["attempts_compared"] == 2 and report["consistent"] == 2
    assert report["tool_call_mismatches"] == 0


def test_prefix_report_counts_attempts_whose_tool_calls_differ_from_executed_actions():
    odd = {**_attempt(["a", "b"]), "tool_calls": 3}
    report = prefix_report([_cell("t1", [odd])], [_cell("t1", [_attempt(["a", "b"])])], threshold=1)
    assert report["tool_call_mismatches"] == 1


def test_arm_summary_scores_each_metric_separately():
    cells = [{**_cell("t1", [_attempt([LISTING])], oracle=True), "single_attempt_success": None}]
    summary = arm_summary(cells)
    assert summary["tasks_solved"] == 1 and summary["first_attempt_solved"] is None
    unscored = arm_summary([{**_cell("t1", []), "oracle_success": None, "single_attempt_success": None}])
    assert unscored["tasks_solved"] is None and unscored["first_attempt_solved"] is None
