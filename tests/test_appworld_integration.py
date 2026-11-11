import hashlib
import json
import os
import random
import shutil

import pytest

from comet.appworld import APPWORLD_DATABASE_PATH_VERSION, AppWorldAdapter, validate_tasks
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
@pytest.mark.parametrize("mutate", [False, True], ids=["unchanged", "phone_mutation"])
def test_live_mutation_counters_survive_checkpoint_and_offline_load(
    live_world, tmp_path, mutate, monkeypatch,
):
    from appworld import AppWorld, evaluator
    from appworld.apps.lib.models.db import CachedDBHandler, ModelHashHandler, get_db_home_path
    from appworld.apps.phone import models as phone
    from appworld.collections.models import ModelCollection, ModelCollectionPair
    from appworld.task import Task

    task_id = "0d8a4ee_1"
    live_world.reset(task_id, 17, tmp_path / "live")
    world = live_world.world
    assert phone.SQLModel.db.home_path == world.models_to_db_home_path
    before = phone.GlobalTextMessage.size()
    if mutate:
        observation = live_world.execute("""profile = apis.supervisor.show_profile()
password = next(row['password'] for row in apis.supervisor.show_account_passwords()
                if row['account_name'] == 'phone')
token = apis.phone.login(username=profile['phone_number'], password=password)['access_token']
print(apis.phone.send_text_message(phone_number=profile['phone_number'],
      message='COMET isolated persistence test', access_token=token))""")
        assert json.loads(observation)["message"] == "Text message sent."
    assert phone.GlobalTextMessage.size() == before + int(mutate)
    live_world.checkpoint(tmp_path / "checkpoint")
    counters = json.loads((tmp_path / "checkpoint/dbs/model_hashes.json").read_text())
    if mutate:
        assert counters["phone"]["GlobalTextMessage"] > 0
        assert counters["phone"]["UserTextMessage"] > 0
    live_world.reset(task_id, 17, tmp_path / "restored")
    assert phone.GlobalTextMessage.size() == before
    live_world.restore(tmp_path / "checkpoint")
    assert phone.GlobalTextMessage.size() == before + int(mutate)
    reference = live_world.save(tmp_path / "restored")
    assert reference["database_path_version"] == APPWORLD_DATABASE_PATH_VERSION
    assert json.loads((tmp_path / "restored/task/dbs/model_hashes.json").read_text()) == counters
    live_world.close()

    # Remove process-global counters so this cannot pass on stale execution state.
    ModelHashHandler.reset()
    try:
        task = Task.load(task_id, load_ground_truth=False)
        start = task.model_collection
        end_home = get_db_home_path(storage_type="memory", type="task_output", task_id=task_id)
        end = ModelCollection.load(
            to_db_home_path=end_home, from_db_home_path=str(tmp_path / "restored/task/dbs"),
            load_apps=task.allowed_apps,
        )
        pair = ModelCollectionPair(
            start_db_home_path=start.from_db_home_path, start_model_collection=start,
            end_db_home_path=end_home, end_model_collection=end,
        )
        assert pair.start.phone.SQLModel.db.home_path == start.to_db_home_path
        assert pair.end.phone.SQLModel.db.home_path == end.to_db_home_path
        assert pair.start.phone.GlobalTextMessage.size() == before
        assert pair.end.phone.GlobalTextMessage.size() == before + int(mutate)
        expected = {"phone.GlobalTextMessage", "phone.UserTextMessage"} if mutate else set()
        assert pair.changed_model_names() == expected
        start_counters = pair.start.model_hashes()
        for name, count in start_counters.items():
            app, model = name.split(".")
            ModelHashHandler.data[end_home][app][model] = count + 1
        assert pair.changed_model_names() == expected
    finally:
        AppWorld.close_all()
        ModelHashHandler.reset()

    legacy = tmp_path / "legacy"
    shutil.copytree(tmp_path / "restored", legacy)
    (legacy / "task/dbs/model_hashes.json").write_text("{}")
    del reference["database_path_version"]
    (legacy / "reference.json").write_text(json.dumps(reference))
    original_bytes = {path.relative_to(legacy): path.read_bytes()
                      for path in legacy.rglob("*") if path.is_file()}
    scoring_namespaces = []
    evaluate_task = evaluator.evaluate_task
    observed_changes = []
    changed_model_names = ModelCollectionPair.changed_model_names

    def observe_changes(pair, *args, **kwargs):
        result = changed_model_names(pair, *args, **kwargs)
        observed_changes.append(result.copy())
        return result

    def observe_scoring(*args, **kwargs):
        namespace = live_world.root / "experiments/outputs" / kwargs["experiment_name"]
        assert namespace.is_dir()
        scoring_namespaces.append(namespace)
        return evaluate_task(*args, **kwargs)

    monkeypatch.setattr(ModelCollectionPair, "changed_model_names", observe_changes)
    monkeypatch.setattr(evaluator, "evaluate_task", observe_scoring)
    outcome = score_environment(legacy)
    assert type(outcome["success"]) is bool
    assert expected in observed_changes
    assert original_bytes == {path.relative_to(legacy): path.read_bytes()
                              for path in legacy.rglob("*") if path.is_file()
                              and path.relative_to(legacy).parts[0] != "evaluation"}
    audit = json.loads((legacy / "evaluation/state-comparison.json").read_text())
    assert audit["policy"] == "exhaustive-model-comparison-v1"
    assert audit["original_counter_sha256"] == hashlib.sha256(b"{}").hexdigest()
    assert audit["models_checked"] == len(start_counters) > 0
    assert all(audit["comparison_counters"][app][model] == count + 1
               for name, count in audit["start_counters"].items()
               for app, model in [name.split(".")])
    assert outcome["state_comparison"]["policy"] == audit["policy"]
    assert CachedDBHandler.is_empty()
    assert not ModelHashHandler.data
    assert len(scoring_namespaces) == 1
    assert not scoring_namespaces[0].exists()


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
