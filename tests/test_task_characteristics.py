import pytest

from comet.task_characteristics import (
    action_kind,
    attempt_profile,
    documentation_calls,
    flood_summary,
    opening_api,
    opening_summary,
    spearman,
    task_outcomes,
    task_table,
)


def _turn(action, chars, head=""):
    return {"action": action, "obs_chars": chars, "obs_head": head, "obs_tail": ""}


def test_action_kind_separates_documentation_from_task_calls():
    assert action_kind("print(apis.api_docs.show_api_doc(app_name='x', api_name='y'))") == "documentation"
    assert action_kind("print(apis.supervisor.show_profile())") == "supervisor"
    assert action_kind("r = apis.spotify.show_song_library(access_token=t)\nprint(r)") == "task_api"
    assert action_kind("print(1 + 1)") == "other"
    assert action_kind("") == "none"


def test_attempt_profile_counts_volume_by_kind_and_repeats():
    listing = "print(apis.api_docs.show_api_descriptions(app_name='spotify'))"
    attempt = {"status": "context_limit", "tool_calls": 3, "logical_cached_tokens": 16384, "turns": [
        _turn(listing, 9000), _turn(listing, 9000),
        _turn("print(apis.spotify.show_song_library(access_token=t))", 500, "Execution failed. HTTP 401"),
    ]}
    profile = attempt_profile(attempt)
    assert profile["observation_chars"] == 18500
    assert profile["chars_by_kind"] == {"documentation": 18000, "task_api": 500}
    assert profile["repeated_actions"] == 1 and profile["error_turns"] == 1
    assert profile["largest_turn"] == {"index": 0, "chars": 9000, "kind": "documentation",
                                       "api": "api_docs.show_api_descriptions"}


def test_flood_summary_only_counts_context_limit_attempts():
    big = {"status": "context_limit", "tool_calls": 1, "turns": [
        _turn("print(apis.api_docs.show_api_descriptions(app_name='a'))", 40000)]}
    small = {"status": "completed", "tool_calls": 1, "turns": [_turn("print(1)", 10)]}
    summary = flood_summary([big, small, big])
    assert summary["context_limit_attempts"] == 2 and summary["attempts"] == 3
    assert summary["largest_turn_kind"] == {"documentation": 2}
    assert summary["largest_turn_api"] == {"api_docs.show_api_descriptions": 2}


def test_task_outcomes_scores_tolerance_and_recovery_benefit():
    solved = {"full_once": True, "full_best_of_n": True, "rkv_80_never": True, "agentkv_80_never": True,
              "rkv_50_never": False, "agentkv_50_never": False, "agentkv_50_fixed": True,
              "agentkv_50_dynamic": False, "rkv_50_fixed": False, "rkv_50_dynamic": False}
    outcome = task_outcomes(solved)
    assert outcome["full_cache_solved"] is True
    assert outcome["tolerance"] == 2 and outcome["tolerance_arms"] == 4
    assert outcome["recovery_benefit"] == {"agentkv_50": 1, "rkv_50": 0}
    assert outcome["any_recovery_gain"] is True


def test_task_outcomes_requires_every_arm():
    with pytest.raises(KeyError):
        task_outcomes({"full_once": True})


def test_spearman_handles_ties_and_constant_input():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 1, 2, 2], [1, 2, 1, 2]) == pytest.approx(0.0)
    assert spearman([1, 1, 1], [1, 2, 3]) is None


def test_task_table_joins_metadata_full_cache_behaviour_and_outcomes():
    export = {
        "tasks": {"t_1": {"instruction": "How many?", "metadata": {"difficulty": 2, "num_apps": 1, "num_apis": 5},
                          "is_question": True, "required_apps": ["spotify"], "ground_truth_api_calls": 6}},
        "cells": [{"task_id": "t_1", "condition": {"id": "full_once"}, "seed": 17, "attempts": [
            {"status": "completed", "tool_calls": 4, "logical_cached_tokens": 7000, "elapsed_seconds": 20.0, "turns": [
                _turn("print(apis.api_docs.show_api_doc(app_name='spotify', api_name='x'))", 800),
                _turn("print(apis.spotify.x(access_token=t))", 200)]}]}],
    }
    conditions = ["full_once", "full_best_of_n", "rkv_80_never", "agentkv_80_never", "rkv_50_never",
                  "agentkv_50_never", "agentkv_50_fixed", "agentkv_50_dynamic", "rkv_50_fixed", "rkv_50_dynamic"]
    solved = {("t_1", condition, 17): condition.startswith("full") for condition in conditions}
    (row,) = task_table(export, solved)
    assert row["task_id"] == "t_1" and row["is_question"] is True and row["difficulty"] == 2
    assert row["full_cache_tool_calls"] == 4 and row["full_cache_documentation_chars"] == 800
    assert row["full_cache_context_tokens"] == 7000
    assert row["tolerance"] == 0 and row["recovery_benefit"] == {"agentkv_50": 0, "rkv_50": 0}


def test_opening_summary_cross_tabulates_the_first_call_with_how_attempts_end():
    listing = _turn("print(apis.api_docs.show_api_descriptions(app_name='spotify'))", 9000)
    search = _turn("print(apis.api_docs.search_api_docs(query='spotify', page_limit=20))", 15000)
    attempts = [
        {"status": "completed", "turns": [listing]},
        {"status": "context_limit", "turns": [search, search]},
        {"status": "context_limit", "turns": [search]},
        {"status": "error", "turns": []},
    ]
    assert opening_api(attempts[0]) == "api_docs.show_api_descriptions"
    assert opening_api(attempts[3]) is None
    summary = opening_summary(attempts)
    assert summary["api_docs.show_api_descriptions"] == {"attempts": 1, "status": {"completed": 1}}
    assert summary["api_docs.search_api_docs"] == {"attempts": 2, "status": {"context_limit": 2}}
    assert summary["none"] == {"attempts": 1, "status": {"error": 1}}


def test_documentation_calls_reports_count_and_size_per_api():
    attempts = [{"status": "context_limit", "turns": [
        _turn("print(apis.api_docs.search_api_docs(query='a'))", 15000),
        _turn("print(apis.api_docs.search_api_docs(query='b'))", 21000),
        _turn("print(apis.api_docs.show_api_doc(app_name='a', api_name='b'))", 900),
        _turn("print(apis.spotify.login(username=u, password=p))", 300),
    ]}]
    assert documentation_calls(attempts) == {
        "search_api_docs": {"calls": 2, "median_chars": 18000, "max_chars": 21000},
        "show_api_doc": {"calls": 1, "median_chars": 900, "max_chars": 900},
    }
