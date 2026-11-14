import pytest

from comet.instruction_errors import (
    arm_summary,
    clustered_share_difference,
    turn_violations,
    twin_rows,
)

LISTING = "print(apis.api_docs.show_api_descriptions(app_name='spotify'))"
LOGIN = "r = apis.spotify.login(username='spotify', password=p)"
BAD_LOGIN = 'Execution failed. Traceback:\n  File "<python-input>", line 1\nException: Response status code is 401:\n{"message":"Invalid credentials"}'


def turn(action, observation=""):
    return {"action": action, "obs_head": observation[:500], "obs_tail": ""}


def attempt(turns, *, success=False, rebuilt_after=None, index=0):
    trigger = {"tool_calls": rebuilt_after, "context_tokens": 5000} if rebuilt_after else None
    return {"attempt_index": index, "success": success, "status": "completed", "rebuilds": int(bool(rebuilt_after)),
            "recovery_trigger": trigger, "tool_calls": sum(bool(t["action"]) for t in turns), "turns": turns}


def cell(task, attempts, condition, seed=17):
    return {"task_id": task, "seed": seed, "condition": {"id": condition}, "attempts": attempts}


def test_each_violation_is_read_from_the_observation_or_the_action():
    assert turn_violations(turn(LOGIN, BAD_LOGIN)) == {"credentials"}
    assert turn_violations(turn("x", "Invalid action: Return exactly one nonempty fenced Python block.")) == {"format"}
    assert turn_violations(turn("apis.spotify.foo()", "Exception: No API named 'foo' found in the spotify app.")) == {"unknown_api"}
    assert turn_violations(turn("apis.spotify.foo()", '{"message":"No APIs with name foo found for the spotify app."}')) == {"unknown_api"}
    assert turn_violations(turn(LOGIN, "Exception: Unexpected parameter 'account_name' passed to the login API")) == {"wrong_arguments"}
    assert turn_violations(turn("import requests\nrequests.get('http://x')", "Execution failed.")) == {"prohibited"}
    assert turn_violations(turn(LISTING, "login: Log in")) == set()
    # The prompt forbids importing the API objects and calling URLs, not the standard library.
    assert turn_violations(turn("import json\nfrom datetime import date\nprint(json.dumps({}))", "{}")) == set()
    assert turn_violations(turn("from apis import spotify", "Execution failed.")) == {"prohibited"}
    assert turn_violations(turn("r = get('https://api.spotify.com/v1/me')", "Execution failed.")) == {"prohibited"}
    assert turn_violations(turn("import os, requests", "")) == {"prohibited"}
    assert turn_violations(turn("x = 1; import requests as r", "")) == {"prohibited"}
    assert turn_violations(turn("from apis.spotify import login", "")) == {"prohibited"}
    assert turn_violations(turn("r = requests.get(u)", "")) == {"prohibited"}
    # Venmo tasks hold payment requests in a variable of that name; a URL in a comment is not a call.
    assert turn_violations(turn("requests = []\nrequests.extend(apis.venmo.show_received_payment_requests())", "[]")) == set()
    assert turn_violations(turn("# see https://example.com\nx = 1", "")) == set()
    # A task-level refusal is not an instruction violation.
    assert turn_violations(turn("apis.venmo.pay()", '{"message":"The payment card has expired."}')) == set()


def test_the_message_may_sit_in_the_saved_tail_of_a_long_observation():
    long = {"action": LOGIN, "obs_head": "Execution failed. Traceback:" + "x" * 480, "obs_tail": '{"message":"Invalid credentials"}'}
    assert turn_violations(long) == {"credentials"}


def test_arm_summary_counts_attempts_and_turns_per_violation():
    cells = [cell("a_1", [attempt([turn(LISTING), turn(LOGIN, BAD_LOGIN), turn(LOGIN, BAD_LOGIN)]),
                          attempt([turn(LISTING)], index=1)], "agentkv_50_never")]
    summary = arm_summary(cells)
    assert summary["attempts"] == 2
    assert summary["violations"]["credentials"] == {"attempts": 1, "turns": 2}
    assert summary["violations"]["format"] == {"attempts": 0, "turns": 0}


def test_twin_rows_compare_only_turns_after_the_rebuild_of_first_attempts():
    # A rejected login and an empty action precede the rebuild; neither may be counted.
    shared = [turn(LOGIN, BAD_LOGIN), turn("", "Invalid action: Return exactly one nonempty fenced Python block."), turn("a = 1", "ok")]
    rebuilt = cell("a_1", [attempt(shared + [turn(LOGIN, "ok")], success=True, rebuilt_after=2)], "agentkv_50_fixed")
    never = cell("a_1", [attempt(shared + [turn(LOGIN, BAD_LOGIN), turn(LOGIN, BAD_LOGIN)])], "agentkv_50_never")
    rows = twin_rows([rebuilt], [never])
    assert len(rows) == 1
    row = rows[0]
    assert (row["task_id"], row["seed"], row["turns_before_rebuild"]) == ("a_1", 17, 3)
    assert row["rebuilt"]["credentials"] == 0 and row["never"]["credentials"] == 2
    assert row["rebuilt"]["format"] == 0 and row["never"]["format"] == 0
    assert (row["rebuilt_turns"], row["never_turns"]) == (1, 2)
    assert (row["rebuilt_passed"], row["never_passed"]) == (True, False)


def test_twin_rows_keep_pairs_that_differ_only_after_the_rebuild_and_drop_short_twins():
    shared = [turn(LISTING), turn("a = 1", "ok")]
    rebuilt = [cell("a_1", [attempt(shared + [turn("b = 2", "ok")], rebuilt_after=2)], "agentkv_50_fixed"),
               cell("b_1", [attempt(shared + [turn("b = 2", "ok")], rebuilt_after=2)], "agentkv_50_fixed")]
    never = [cell("a_1", [attempt(shared + [turn("c = 3", "ok")])], "agentkv_50_never"),
             cell("b_1", [attempt(shared[:1])], "agentkv_50_never")]
    assert [row["task_id"] for row in twin_rows(rebuilt, never)] == ["a_1"]


def test_twin_rows_reject_inconsistent_rebuild_records_and_duplicate_cells():
    shared = [turn(LISTING), turn("a = 1", "ok")]
    never = [cell("a_1", [attempt(shared)], "agentkv_50_never")]
    missing = attempt(shared, rebuilt_after=2)
    missing["recovery_trigger"] = None
    with pytest.raises(ValueError, match="no recovery trigger"):
        twin_rows([cell("a_1", [missing], "agentkv_50_fixed")], never)
    with pytest.raises(ValueError, match="fewer executed actions"):
        twin_rows([cell("a_1", [attempt(shared, rebuilt_after=5)], "agentkv_50_fixed")], never)
    with pytest.raises(ValueError, match="Duplicate cell"):
        twin_rows([cell("a_1", [attempt(shared, rebuilt_after=2)], "agentkv_50_fixed")], never * 2)


def test_twin_rows_set_aside_attempts_without_a_rebuild_or_with_a_different_prefix():
    base = [turn(LISTING), turn("a = 1", "ok"), turn(LOGIN, "ok")]
    not_rebuilt = cell("a_1", [attempt(base)], "agentkv_50_fixed")
    diverged = cell("b_1", [attempt([turn("other")] + base, rebuilt_after=2)], "agentkv_50_fixed")
    never = [cell("a_1", [attempt(base)], "agentkv_50_never"), cell("b_1", [attempt(base)], "agentkv_50_never")]
    assert twin_rows([not_rebuilt, diverged], never) == []


def test_clustered_share_difference_resamples_families():
    rows = [{"task_id": f"{family}_1", "seed": 17, "rebuilt": {"credentials": 0}, "never": {"credentials": int(family in "ab")}}
            for family in "abcd"]
    result = clustered_share_difference(rows, "credentials", draws=2000, seed=3)
    assert result["rebuilt_share"] == 0 and result["never_share"] == pytest.approx(0.5)
    assert result["difference"] == pytest.approx(-0.5)
    low, high = result["ci95"]
    assert -1.0 <= low < -0.5 < high <= 0.0
    assert (result["pairs"], result["families"]) == (4, 4)
    with pytest.raises(ValueError, match="two families"):
        clustered_share_difference(rows[:1], "credentials")
