import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "trajectory_audit", Path(__file__).parents[1] / "scripts/audit_trajectories.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_error_streak_and_first_match():
    result = module.summarize({"turns": [
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
    result = module.summarize({"turns": [{"action": None, "observation": {"ok": True}}]})
    assert result["first_error_turn"] is None
    assert result["error_turns"] == result["repeated_action_strings"] == 0


def test_empty_run_is_not_silent_success(tmp_path):
    with pytest.raises(ValueError, match="No saved trajectories"):
        module.audit(tmp_path)
