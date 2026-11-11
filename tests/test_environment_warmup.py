import os
from dataclasses import replace

import pytest
from test_pipeline import Clock, FakeEngine, FakeEnvironment
from test_pipeline import config as config

from comet.analysis import environment_initialization_summary
from comet.appworld import AppWorldAdapter
from comet.artifacts import read_json
from comet.config import Condition, EnvironmentWarmup, attempt_seed
from comet.runner import Runner


def test_environment_setup_is_separate_and_each_resume_starts_fresh(config, tmp_path, monkeypatch):
    config = replace(config, environment_warmup=EnvironmentWarmup("train_1", 0),
                     task_ids=["fixture_1", "fixture_2"], max_attempts=1,
                     conditions=[Condition("full", "full", 1.0, "never", 1)])
    validated, environments = [], []
    monkeypatch.setattr("comet.appworld.validate_tasks", lambda split, ids: validated.append((split, ids)))
    clock = Clock()
    engine = FakeEngine(clock)

    class Environment(FakeEnvironment):
        closed = False

        def reset(self, task_id, seed, directory):
            assert all(e.closed for e in environments if e is not self)
            super().reset(task_id, seed, directory)
            self.task_id, self.seed, self.directory = task_id, seed, directory
            if task_id == "train_1":
                clock.advance(200)

        def initial_prompt(self):
            assert self.task_id != "train_1"
            return super().initial_prompt()

        def execute(self, action, **kwargs):
            assert self.task_id != "train_1"
            return super().execute(action, **kwargs)

        def close(self):
            self.closed = True

    runner = Runner(config, tmp_path, lambda _: engine,
                    lambda: Environment(clock, environments), clock=clock)
    manifest = runner.run(max_cells=1)
    first_cell = tmp_path / manifest["cells"][0]["path"]
    preserved = first_cell.read_bytes()
    manifest = runner.run(resume=True, max_cells=1)
    assert manifest["status"] == "completed"
    assert first_cell.read_bytes() == preserved
    assert validated == [("train", ["train_1"])] * 2
    assert len(environments) == 4 and all(e.closed for e in environments)
    assert len({e.directory for e in environments}) == 4
    assert [e.task_id for e in environments] == ["train_1", "fixture_1", "train_1", "fixture_2"]
    assert [e.count for e in environments] == [0, 2, 0, 2]
    assert engine.starts == [attempt_seed(7, 0)] * 2
    assert [e.seed for e in environments] == [0, attempt_seed(7, 0)] * 2
    for launch in manifest["launches"]:
        setup = launch["environment_initialization"]
        assert setup["status"] == "completed" and setup["seconds"] == 201
        assert setup["charged_to_task_budget"] is False
        assert setup["tool_calls"] == setup["model_observations"] == 0
    for reference in manifest["cells"]:
        cell = read_json(tmp_path / reference["path"])
        assert len(cell["attempts"]) == 1 and cell["elapsed_seconds"] < config.budget_seconds
        assert cell["attempts"][0]["timings"]["reset"] == 2
        assert cell["attempts"][0]["timings"]["tool"] == 6
    runner.run(resume=True)
    assert len(environments) == 4
    setup = environment_initialization_summary(manifest)
    assert setup["measured_seconds"] == 402 and setup["measured_launches"] == 2
    assert setup["status_counts"] == {"completed": 2}


@pytest.mark.parametrize("failure", ["membership", "reset", "close"])
def test_environment_setup_failure_is_recorded_before_any_attempt(config, tmp_path, monkeypatch, failure):
    config = replace(config, environment_warmup=EnvironmentWarmup("train_1", 0))
    clock, environments = Clock(), []
    engine = FakeEngine(clock)

    def validate(split, tasks):
        assert split == "train" and tasks == ["train_1"]
        if failure == "membership":
            raise ValueError("warmup task is not in train")

    monkeypatch.setattr("comet.appworld.validate_tasks", validate)

    class Environment(FakeEnvironment):
        closed = False

        def reset(self, *args):
            clock.advance(4)
            if failure == "reset":
                raise ValueError("warmup reset failed")

        def close(self):
            self.closed = True
            if failure == "close":
                raise ValueError("warmup close failed")

    runner = Runner(config, tmp_path, lambda _: engine,
                    lambda: Environment(clock, environments), clock=clock)
    with pytest.raises(ValueError, match="warmup"):
        runner.run()
    manifest = read_json(tmp_path / "manifest.json")
    setup = manifest["launches"][0]["environment_initialization"]
    assert setup["status"] == "failed" and "warmup" in setup["failure_reason"]
    assert setup["seconds"] == (0 if failure == "membership" else 4)
    assert engine.starts == [] and all(e.closed for e in environments)
    assert not list((tmp_path / "cells").glob("*/cell.json"))


def test_setup_reporting_preserves_failed_and_missing_measurements():
    manifest = {"config": {"environment_warmup": {"task_id": "train_1", "seed": 0}},
                "launches": [{"environment_initialization": {"status": "failed", "seconds": 4}},
                             {"environment_initialization": {"status": "running"}}, {}]}
    summary = environment_initialization_summary(manifest)
    assert summary["measured_seconds"] == 4
    assert summary["measured_launches"] == 1 and summary["recorded_launches"] == 2
    assert summary["total_launches"] == 3
    assert summary["status_counts"] == {"failed": 1, "running": 1}
    assert environment_initialization_summary({"config": {}})["measured_seconds"] is None
    manifest["launches"][0]["environment_initialization"]["seconds"] = float("nan")
    with pytest.raises(ValueError, match="initialization duration"):
        environment_initialization_summary(manifest)


@pytest.mark.appworld
def test_live_environment_setup_closes_train_world_without_tools(config, tmp_path):
    root = os.environ.get("COMET_APPWORLD_ROOT")
    if not root:
        pytest.skip("Set COMET_APPWORLD_ROOT to use the pinned AppWorld data")
    config = replace(config, environment_warmup=EnvironmentWarmup("82e2fac_1", 0))
    environments = []

    class Environment(AppWorldAdapter):
        def reset(self, *args):
            super().reset(*args)
            assert self.world.task.ground_truth is None and self.world.num_interactions == 0
            self.world.shell.user_ns["warmup_isolation_marker"] = True

        def initial_prompt(self):
            pytest.fail("Environment setup must not expose a prompt to the model")

        def execute(self, *args, **kwargs):
            pytest.fail("Environment setup must not execute tools")

    def factory():
        environment = Environment(root)
        environments.append(environment)
        return environment

    runner = Runner(config, tmp_path, lambda _: pytest.fail("Model was invoked"), factory)
    launch = {}
    runner._warmup_environment({"launches": [launch]}, launch)
    assert launch["environment_initialization"]["status"] == "completed"
    assert len(environments) == 1 and environments[0].world is None
    fresh = AppWorldAdapter(root)
    try:
        fresh.reset("82e2fac_1", 0, tmp_path / "fresh")
        assert "warmup_isolation_marker" not in fresh.world.shell.user_ns
        assert fresh.world.num_interactions == 0 and fresh.world.task.ground_truth is None
    finally:
        fresh.close()
