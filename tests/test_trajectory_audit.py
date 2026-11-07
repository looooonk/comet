import json

import pytest

from comet.trajectory_audit import audit, summarize


def test_error_streak_and_first_match():
    result = summarize({"turns": [
        {"action": "a", "observation": "Execution failed HTTP 401 TypeError"},
        {"action": "a", "observation": "Invalid action"},
        {"action": "b", "observation": "ok"},
        {"action": "a", "observation": "Execution failed NameError"},
    ]})
    assert result["first_error_turn"] == 1
    assert result["longest_error_streak"] == 2
    assert result["repeated_action_strings"] == 2
    assert result["categories"] == {"HTTP 401": 1, "Invalid action": 1, "NameError": 1}


def test_no_error_and_missing_actions():
    result = summarize({"turns": [{"action": None, "observation": {"ok": True}}]})
    assert result["first_error_turn"] is None
    assert result["error_turns"] == result["repeated_action_strings"] == 0


def test_empty_run_is_not_silent_success(tmp_path):
    with pytest.raises(ValueError, match="No saved trajectories"):
        audit(tmp_path)


@pytest.mark.parametrize("status", [401, 422])
@pytest.mark.parametrize("prefix", ["HTTP ", "Response status code is "])
def test_actual_http_messages(status, prefix):
    observation = f"Execution failed. {prefix}{status}: TypeError"
    assert summarize({"turns": [{"observation": observation}]})["categories"] == {
        f"HTTP {status}": 1,
    }
    for text in (f"Execution failed {prefix}{status}0", f"{prefix}{status}"):
        assert f"HTTP {status}" not in summarize({"turns": [{"observation": text}]})["categories"]


def test_legacy_audit_is_reproducible(tmp_path):
    trajectory = {"turns": [{"observation": "Execution failed. Response status code is 401"}]}
    (tmp_path / "trajectory.json").write_text(json.dumps(trajectory))
    old = audit(tmp_path, schema_version=1)
    new = audit(tmp_path)
    assert old["schema_version"] == 1 and new["schema_version"] == 2
    assert old["trajectories"][0]["categories"] == {"other execution error": 1}
    assert new["trajectories"][0]["categories"] == {"HTTP 401": 1}
    assert old["trajectories"][0]["sha256"] == new["trajectories"][0]["sha256"]
