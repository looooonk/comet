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


@pytest.fixture
def live_world():
    root = os.environ.get("COMET_APPWORLD_ROOT")
    if not root:
        pytest.skip("Set COMET_APPWORLD_ROOT to use the pinned AppWorld data")
    environment = AppWorldAdapter(root)
    try:
        yield environment
    finally:
        environment.close()


@pytest.mark.appworld
def test_live_explicit_authentication_and_parsed_responses(live_world, tmp_path):
    live_world.reset("3ab5b8b_1", 17, tmp_path / "authentication")
    assert live_world.world.task.ground_truth is None
    missing = live_world.execute("print(apis.spotify.show_liked_playlists())")
    assert "Response status code is 401" in missing
    live_world.execute("""profile = apis.supervisor.show_profile()
password = next(p['password'] for p in apis.supervisor.show_account_passwords()
                if p['account_name'] == 'spotify')""")
    wrong_argument = live_world.execute(
        "print(apis.spotify.login(email=profile['email'], password=password))"
    )
    assert "Unexpected parameter 'email'" in wrong_argument
    wrong_token = live_world.execute("print(apis.spotify.show_liked_playlists(access_token=password))")
    assert "Response status code is 401" in wrong_token
    result = live_world.execute("""login = apis.spotify.login(username=profile['email'], password=password)
token = login['access_token']
playlists = apis.spotify.show_liked_playlists(access_token=token)
print({'login_type': type(login).__name__, 'playlists_type': type(playlists).__name__})""")
    assert json.loads(result) == {"login_type": "dict", "playlists_type": "list"}
    assert "Response status code is 401" in live_world.execute(
        "print(apis.spotify.show_liked_playlists())"
    )
    assert not live_world.completed()


@pytest.mark.appworld
def test_live_pagination_requires_explicit_coverage(live_world, tmp_path):
    live_world.reset("23cf851_1", 17, tmp_path / "pagination")
    result = live_world.execute("""profile = apis.supervisor.show_profile()
password = next(p['password'] for p in apis.supervisor.show_account_passwords()
                if p['account_name'] == 'venmo')
token = apis.venmo.login(username=profile['email'], password=password)['access_token']
first = apis.venmo.show_transactions(access_token=token)
transactions = []
for page in range(100):
    batch = apis.venmo.show_transactions(access_token=token, page_index=page, page_limit=5)
    transactions.extend(batch)
    if not batch:
        break
else:
    raise RuntimeError('Pagination probe exceeded its bound')
print({'default_count': len(first), 'all_count': len(transactions),
       'first_page_matches': first == transactions[:len(first)]})""")
    result = json.loads(result)
    assert result["first_page_matches"]
    assert result["all_count"] > result["default_count"] > 0
    assert not live_world.completed()
