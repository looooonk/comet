from copy import deepcopy
from dataclasses import replace

import pytest
from test_pipeline import Clock, FakeEngine, FakeEnvironment
from test_pipeline import config as config

from comet.artifacts import read_json, write_json
from comet.cli import main
from comet.config import Condition
from comet.errors import MemoryCapExceeded
from comet.evaluation import evaluate_run
from comet.runner import Runner


def make_runner(config, output, *, interrupt_task=None):
    clock, engines, schedule = Clock(), [], []
    interruptions = []

    def factory(condition):
        engine = FakeEngine(clock)
        engine.set_policy = lambda method, retention: setattr(engine, "policy", (method, retention))
        engines.append(engine)
        return engine

    class Environment(FakeEnvironment):
        def reset(self, task_id, seed, directory):
            super().reset(task_id, seed, directory)
            self.task_id = task_id
            schedule.append((engines[-1].policy, task_id, seed))

        def execute(self, action, **kwargs):
            if self.task_id == interrupt_task and not interruptions:
                clock.advance(3)
                interruptions.append(True)
                raise KeyboardInterrupt("fixture process interruption")
            if self.task_id == "timeout_1":
                clock.advance(config.budget_seconds)
            return super().execute(action, **kwargs)

    runner = Runner(config, output, factory, lambda: Environment(clock, []), clock=clock)
    return runner, clock, engines, schedule


def cell_snapshot(output, manifest):
    return {str(path.relative_to(output)): path.read_bytes()
            for reference in manifest["cells"] if (output / reference["path"]).exists()
            for path in (output / reference["path"]).parent.rglob("*") if path.is_file()}


def comparable_cells(output, manifest):
    cells = [read_json(output / reference["path"]) for reference in manifest["cells"]]
    for cell in cells:
        cell.pop("run_id")
        for attempt in cell["attempts"]:
            attempt.pop("environment", None)
    return cells


@pytest.mark.parametrize("diagnostic", [False, True])
def test_segmented_run_matches_uninterrupted_order_outcomes_and_budgets(config, tmp_path, diagnostic):
    config = replace(config, task_ids=["fixture_1", "timeout_1"], seeds=[7, 8],
                     conditions=[Condition("full", "full", 1.0, "never", 2), *config.conditions])
    if diagnostic:
        config = replace(config, stage="diagnostic", checkpoint_after_tool_calls=1, max_attempts=1,
                         conditions=[replace(c, max_attempts=1) for c in config.conditions])
    whole, _, _, whole_schedule = make_runner(config, tmp_path / "whole")
    expected = whole.run()
    runner, clock, engines, schedule = make_runner(config, tmp_path / "segments")
    manifest = runner.run(max_cells=2)
    assert manifest["status"] == "running" and "finished_at_unix" not in manifest
    assert manifest["config_digest"] == config.digest
    assert manifest["config"] == config.to_dict()
    assert manifest["launches"][-1]["stop_reason"] == "max_cells"
    assert manifest["launches"][-1]["completed_cells"] == 2
    with pytest.raises(ValueError, match="completed.*manifest"):
        evaluate_run(runner.output, scorer=lambda _: pytest.fail("Incomplete run was scored"))
    assert not (runner.output / "scores.json").exists()
    checkpoints = {path: path.read_bytes() for path in (runner.output / "checkpoints").rglob("*")
                   if path.is_file()}
    for limit in (3, 3):
        preserved = cell_snapshot(runner.output, manifest)
        clock.advance(10_000)
        manifest = runner.run(resume=True, max_cells=limit)
        assert all((runner.output / path).read_bytes() == content for path, content in preserved.items())
        assert all(path.read_bytes() == content for path, content in checkpoints.items())
    assert manifest["status"] == "completed"
    assert [launch["completed_cells"] for launch in manifest["launches"]] == [2, 3, 3]
    assert [launch["max_cells"] for launch in manifest["launches"]] == [2, 3, 3]
    assert manifest["launches"][-1]["stop_reason"] == "all_cells_completed"
    assert schedule == whole_schedule
    assert comparable_cells(runner.output, manifest) == comparable_cells(whole.output, expected)
    for run in (whole, runner):
        scores = evaluate_run(run.output, scorer=lambda path: {
            "success": read_json(path / "fixture.json")["count"] == 2})
        assert [cell["oracle_success"] for cell in scores["cells"]] == [True, True, False, False] * 2
        assert [cell["actual_attempts"] for cell in scores["cells"]] == (
            [1] * 8 if diagnostic else [2, 2, 1, 1] * 2)
    saved_manifest = (runner.output / "manifest.json").read_bytes()
    runner.run(resume=True, max_cells=1)
    assert len(engines) == 3
    assert (runner.output / "manifest.json").read_bytes() == saved_manifest


def test_segment_resume_finalizes_interruption_without_new_time_or_attempts(config, tmp_path):
    config = replace(config, task_ids=["first_1", "interrupted_1", "last_1"])
    runner, _, engines, schedule = make_runner(config, tmp_path, interrupt_task="interrupted_1")
    with pytest.raises(KeyboardInterrupt):
        runner.run(max_cells=2)
    manifest = read_json(tmp_path / "manifest.json")
    first, interrupted, later = manifest["cells"]
    first_bytes = (tmp_path / first["path"]).read_bytes()
    trajectory = (tmp_path / interrupted["path"]).parent / "attempt-000/trajectory.json"
    trajectory_bytes = trajectory.read_bytes()
    assert manifest["status"] == "running" and manifest["launches"][-1]["completed_cells"] == 1
    before = list(schedule)
    resumed = runner.run(resume=True, max_cells=1)
    cell = read_json(tmp_path / interrupted["path"])
    assert cell["completed"] and not cell["inflight"]
    assert cell["elapsed_seconds"] == config.budget_seconds
    assert len(cell["attempts"]) == 1 and cell["attempts"][0]["status"] == "interrupted"
    assert cell["attempts"][0]["budget_elapsed_seconds"] == config.budget_seconds
    assert cell["attempts"][0]["reserved_budget_seconds"] == config.budget_seconds
    assert schedule == before and not engines[-1].starts
    assert (tmp_path / first["path"]).read_bytes() == first_bytes
    assert trajectory.read_bytes() == trajectory_bytes
    assert not (trajectory.parent.parent / "attempt-001").exists()
    assert not (tmp_path / later["path"]).exists()
    assert resumed["status"] == "running" and resumed["launches"][-1]["completed_cells"] == 1
    assert runner.run(resume=True)["status"] == "completed"
    assert read_json(tmp_path / interrupted["path"]) == cell


def test_cell_limit_includes_model_loading_infeasibility(config, tmp_path):
    config = replace(config, task_ids=["first_1", "second_1"])

    def unavailable(_condition):
        raise MemoryCapExceeded("fixture model does not fit")

    runner = Runner(config, tmp_path, unavailable, lambda: pytest.fail("Environment created"))
    manifest = runner.run(max_cells=1)
    assert manifest["status"] == "running"
    assert manifest["launches"][-1]["completed_cells"] == 1
    assert not (tmp_path / manifest["cells"][1]["path"]).exists()
    manifest = runner.run(resume=True, max_cells=1)
    assert manifest["status"] == "completed"
    for reference in manifest["cells"]:
        cell = read_json(tmp_path / reference["path"])
        assert cell["completed"] and cell["infeasible"]
        assert cell["attempts"] == [] and cell["elapsed_seconds"] == 0


@pytest.mark.parametrize("load_failure", [False, True])
def test_manifest_progress_is_written_only_at_launch_boundaries(config, tmp_path, monkeypatch, load_failure):
    config = replace(config, task_ids=["first_1", "second_1", "third_1"])
    runner, _, _, _ = make_runner(config, tmp_path)
    writes = []

    def journal(path, value):
        if path.name == "manifest.json" and value.get("launches"):
            writes.append(deepcopy(value["launches"][-1]))
        write_json(path, value)

    monkeypatch.setattr("comet.runner.write_json", journal)
    if load_failure:
        def unavailable(_condition):
            raise MemoryCapExceeded("fixture model does not fit")

        runner.engine_factory = unavailable
    runner.run(max_cells=2)
    assert [launch["completed_cells"] for launch in writes if launch["completed_cells"]] == [2]
    assert writes[-1]["stop_reason"] == "max_cells"


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_cell_limits_fail_before_artifacts_or_engine(config, tmp_path, limit):
    runner = Runner(config, tmp_path / "run", lambda _: pytest.fail("Engine created"), lambda: None)
    with pytest.raises(ValueError, match="positive integer"):
        runner.run(max_cells=limit)
    assert not runner.output.exists()


@pytest.mark.parametrize("diagnostic", [False, True])
def test_run_cli_passes_operational_limit_and_resume(config, tmp_path, monkeypatch, capsys, diagnostic):
    if diagnostic:
        config = replace(config, stage="diagnostic", checkpoint_after_tool_calls=1, max_attempts=1,
                         conditions=[replace(c, max_attempts=1) for c in config.conditions])
    path = tmp_path / "config.json"
    write_json(path, config.to_dict())
    calls = []
    monkeypatch.setattr("comet.appworld.validate_tasks", lambda *args: None)

    def run(self, **kwargs):
        calls.append((self.config.digest, kwargs))
        return {"run_id": "fixture", "status": "running"}

    monkeypatch.setattr(Runner, "run", run)
    main(["run", str(path), "--output", str(tmp_path / "run"), "--model-path", "fixture",
          "--appworld-root", "fixture", "--resume", "--max-cells", "3"])
    assert calls == [(config.digest, {"resume": True, "max_cells": 3})]
    assert '"status": "running"' in capsys.readouterr().out


@pytest.mark.parametrize("diagnostic", [False, True])
def test_run_cli_rejects_invalid_limit_before_appworld(config, tmp_path, monkeypatch, diagnostic):
    raw = deepcopy(config.to_dict())
    if diagnostic:
        raw.update(stage="diagnostic", checkpoint_after_tool_calls=1, max_attempts=1)
        for condition in raw["conditions"]:
            condition["max_attempts"] = 1
    path = tmp_path / "config.json"
    write_json(path, raw)
    monkeypatch.setattr("comet.appworld.validate_tasks", lambda *args: pytest.fail("AppWorld accessed"))
    with pytest.raises(SystemExit) as error:
        main(["run", str(path), "--output", str(tmp_path / "run"), "--model-path", "fixture",
              "--appworld-root", "fixture", "--max-cells", "0"])
    assert error.value.code == 2
