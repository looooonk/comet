import json
import os
import random

import pytest

from comet.appworld import AppWorldAdapter, validate_tasks
from comet.budget import Budget
from comet.errors import BudgetExpired
from comet.evaluation import score_environment


@pytest.mark.appworld
def test_live_fresh_state_checkpoint_and_offline_scoring(tmp_path):
    root = os.environ.get("COMET_APPWORLD_ROOT")
    if not root:
        pytest.skip("Set COMET_APPWORLD_ROOT to run against installed pinned AppWorld data.")
    from appworld import load_task_ids, update_root

    update_root(root)
    task_id = load_task_ids("train")[0]
    validate_tasks("train", [task_id])
    environment = AppWorldAdapter(root)
    try:
        environment.reset(task_id, 9, tmp_path / "first")
        prompt = json.loads(environment.initial_prompt())
        assert prompt["instruction"] and "api_docs" in prompt["api_docs"]
        assert environment.world.task.ground_truth is None
        assert not environment.completed()
        environment.execute("marker = {'value': [1]}\napis.supervisor.complete_task()")
        assert environment.completed()
        environment.checkpoint(tmp_path / "checkpoint")
        expected_random = random.random()
        environment.execute("marker['value'].append(2)")
        environment.reset(task_id, 9, tmp_path / "second")
        assert not environment.completed()
        environment.restore(tmp_path / "checkpoint")
        assert environment.completed()
        assert environment.world.shell.user_ns["marker"] == {"value": [1]}
        assert random.random() == expected_random
        assert environment.world.num_interactions == 1
        observation = environment.execute("marker['value'].append(3)\nprint(marker)")
        assert json.loads(observation) == {"value": [1, 3]}
        environment.save(tmp_path / "second")
        environment.close()
        outcome = score_environment(tmp_path / "second")
        assert type(outcome["success"]) is bool
        assert (tmp_path / "second/evaluation/report.md").is_file()
        environment.reset(task_id, 9, tmp_path / "third")
        assert not environment.completed()
        assert "marker" not in environment.world.shell.user_ns
        budget = Budget(0.05)
        with pytest.raises(BudgetExpired):
            with budget.charge("tool"):
                environment.execute("while True: pass", timeout_seconds=budget.remaining)
        assert budget.elapsed >= 0.05
    finally:
        environment.close()
