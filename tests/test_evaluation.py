import json

import pytest

from comet.evaluation import evaluate_run, execution_digest, rescore_run


def make_run(tmp_path):
    cells = []
    for task in ("task1", "task2"):
        directory = tmp_path / "cells" / task
        directory.mkdir(parents=True)
        cell = {
            "schema_version": 1, "run_id": "run1", "stage": "pilot", "config_digest": "digest",
            "task_id": task, "seed": 1, "completed": True,
            "condition": {"id": "full", "max_attempts": 3}, "elapsed_seconds": 2,
            "attempts": [{"attempt_index": index, "seed": index, "status": status,
                          "artifact_dir": f"cells/{task}/attempt-{index}", "metrics": {}}
                         for index, status in enumerate(("completed", "timeout", "oom"))],
        }
        (directory / "cell.json").write_text(json.dumps(cell))
        cells.append({"id": task, "path": f"cells/{task}/cell.json", "task_id": task,
                      "condition_id": "full", "seed": 1})
    manifest = {"schema_version": 1, "run_id": "run1", "stage": "pilot", "status": "completed",
                "config_digest": "digest", "cells": cells,
                "config": {"task_ids": ["task1", "task2"], "seeds": [1],
                           "conditions": [{"id": "full", "max_attempts": 3}]}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return manifest


def test_scoring_waits_for_every_cell_before_any_evaluator_call(tmp_path):
    make_run(tmp_path)
    cell_path = tmp_path / "cells/task2/cell.json"
    cell = json.loads(cell_path.read_text())
    cell["completed"] = False
    cell_path.write_text(json.dumps(cell))
    calls = []
    with pytest.raises(ValueError, match="Incomplete"):
        evaluate_run(tmp_path, scorer=lambda path: calls.append(path))
    assert calls == []


def test_execution_failures_remain_failures_and_scores_resume(tmp_path):
    make_run(tmp_path)
    calls = []

    def scorer(path):
        calls.append(path)
        return {"success": True}

    scores = evaluate_run(tmp_path, scorer=scorer)
    assert len(calls) == 2
    assert scores["status"] == "completed"
    for cell in scores["cells"]:
        assert [attempt["success"] for attempt in cell["attempts"]] == [True, False, False]
        assert cell["oracle_success"] is True
        assert cell["actual_attempts"] == 3
    assert evaluate_run(tmp_path, scorer=scorer) == scores
    assert len(calls) == 2


def test_empty_attempt_cell_counts_as_failed_task(tmp_path):
    make_run(tmp_path)
    cell_path = tmp_path / "cells/task2/cell.json"
    cell = json.loads(cell_path.read_text())
    cell["attempts"] = []
    cell_path.write_text(json.dumps(cell))
    scores = evaluate_run(tmp_path, scorer=lambda _: {"success": True})
    assert not scores["cells"][1]["oracle_success"]
    assert not scores["cells"][1]["single_attempt_success"]


def test_scoring_refuses_changed_execution_and_unknown_boolean(tmp_path):
    make_run(tmp_path)
    with pytest.raises(ValueError, match="boolean"):
        evaluate_run(tmp_path, scorer=lambda _: {"success": "yes"})
    evaluate_run(tmp_path, scorer=lambda _: {"success": False})
    cell_path = tmp_path / "cells/task2/cell.json"
    cell = json.loads(cell_path.read_text())
    cell["elapsed_seconds"] = 3
    cell_path.write_text(json.dumps(cell))
    with pytest.raises(ValueError, match="changed since scoring"):
        evaluate_run(tmp_path, scorer=lambda _: {"success": False})


def test_manifest_must_be_complete_and_paths_stay_within_run(tmp_path):
    manifest = make_run(tmp_path)
    manifest["status"] = "running"
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="completed"):
        evaluate_run(tmp_path)
    manifest["status"] = "completed"
    manifest["cells"][0]["path"] = "../outside.json"
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="escapes"):
        evaluate_run(tmp_path)


def test_missing_manifest_cells_are_rejected_before_scoring(tmp_path):
    manifest = make_run(tmp_path)
    manifest["cells"].pop()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="every configured"):
        evaluate_run(tmp_path)


@pytest.mark.parametrize("field", ["source_hashes", "installed_packages"])
def test_scoring_resume_refuses_changed_evaluator(tmp_path, monkeypatch, field):
    make_run(tmp_path)
    original = {"source_hashes": {"evaluation.py": "first"},
                "installed_packages": {"appworld": "pinned"}, "recorded_at_unix": 1}
    monkeypatch.setattr("comet.evaluation.provenance", lambda: original.copy())
    scores = evaluate_run(tmp_path, scorer=lambda _: {"success": False})
    assert scores["evaluation_provenance"] == original
    changed = {**original, field: {"changed": "revision"}}
    monkeypatch.setattr("comet.evaluation.provenance", lambda: changed)
    with pytest.raises(ValueError, match="original evaluator"):
        evaluate_run(tmp_path, scorer=lambda _: pytest.fail("Must not rescore incompatible evidence"))
    monkeypatch.setattr("comet.evaluation.provenance", lambda: {**original, "recorded_at_unix": 2})
    resumed = evaluate_run(tmp_path, scorer=lambda _: pytest.fail("Completed scores should be reused"))
    assert resumed["evaluation_provenance"] == original


def test_rescoring_preserves_execution_and_original_scores(tmp_path, monkeypatch):
    source, output = tmp_path / "source", tmp_path / "corrected"
    source.mkdir()
    manifest = make_run(source)
    for task in ("task1", "task2"):
        environment = source / f"cells/{task}/attempt-0/environment"
        (environment / "task/dbs").mkdir(parents=True)
        (environment / "task/dbs/model_hashes.json").write_text("{}")
        (environment / "task/dbs/app.jsonl").write_text('[["INSERT INTO t VALUES (?)", [1]]]\n')
        (environment / "evaluation").mkdir()
        (environment / "evaluation/report.md").write_text("old evaluation")
    before_provenance = {"source_hashes": {"evaluation.py": "old"}, "installed_packages": {}}
    monkeypatch.setattr("comet.evaluation.provenance", lambda: before_provenance)
    evaluate_run(source, scorer=lambda _: {"success": False})
    before = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    original_digest = execution_digest(source, manifest)
    monkeypatch.setattr("comet.evaluation.provenance", lambda: {
        "source_hashes": {"evaluation.py": "corrected"}, "installed_packages": {},
    })
    calls = []

    def scorer(path):
        assert path.is_relative_to(output)
        assert not (path / "evaluation").exists()
        assert (path / "task/dbs/model_hashes.json").read_text() == "{}"
        (path / "evaluation").mkdir()
        (path / "evaluation/report.md").write_text("new evaluation")
        calls.append(path)
        return {"success": True}

    scores = rescore_run(source, output, scorer=scorer)
    assert len(calls) == 2
    assert all(cell["oracle_success"] for cell in scores["cells"])
    assert scores["execution_digest"] == original_digest == execution_digest(output, manifest)
    assert before == {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    assert (output / "rescoring/prior-scores.json").read_bytes() == before["scores.json"]
    assert (output / "manifest.json").read_bytes() == before["manifest.json"]
    derivation = json.loads((output / "rescoring/derivation.json").read_text())
    assert derivation["source_execution_digest"] == original_digest
    assert derivation["execution_repeated"] is derivation["execution_artifacts_changed"] is False
    assert evaluate_run(output, scorer=lambda _: pytest.fail("Must reuse corrected scores")) == scores
    with pytest.raises(FileExistsError, match="already exists"):
        rescore_run(source, output)


def test_rescoring_rejects_nested_destinations_and_unfinished_runs(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    manifest = make_run(source)
    for output in (source, source / "nested", tmp_path):
        with pytest.raises(ValueError, match="separate"):
            rescore_run(source, output)
    manifest["status"] = "running"
    (source / "manifest.json").write_text(json.dumps(manifest))
    output = tmp_path / "corrected"
    with pytest.raises(ValueError, match="completed"):
        rescore_run(source, output)
    assert not output.exists()


def test_incomplete_rescoring_copy_cannot_be_evaluated(tmp_path, monkeypatch):
    import shutil

    source, output = tmp_path / "source", tmp_path / "corrected"
    source.mkdir()
    make_run(source)
    copytree = shutil.copytree

    def interrupted_copy(*args, **kwargs):
        result = copytree(*args, **kwargs)
        if args[0] == source / "cells":
            raise KeyboardInterrupt("Interrupted after copying execution")
        return result

    monkeypatch.setattr(shutil, "copytree", interrupted_copy)
    with pytest.raises(KeyboardInterrupt):
        rescore_run(source, output)
    with pytest.raises(ValueError, match="preparation is incomplete"):
        evaluate_run(output, scorer=lambda _: pytest.fail("Must not score an unprepared copy"))
    assert not (output / "scores.json").exists()


def test_rescoring_refuses_changed_original_before_creating_output(tmp_path):
    source, output = tmp_path / "source", tmp_path / "corrected"
    source.mkdir()
    make_run(source)
    evaluate_run(source, scorer=lambda _: {"success": False})
    cell = source / "cells/task1/cell.json"
    content = json.loads(cell.read_text())
    content["elapsed_seconds"] += 1
    cell.write_text(json.dumps(content))
    with pytest.raises(ValueError, match="changed since scoring"):
        rescore_run(source, output)
    assert not output.exists()


@pytest.mark.parametrize("failure_stage", ["copy", "load"])
def test_scoring_cleanup_preserves_primary_error_and_clears_state(tmp_path, monkeypatch, failure_stage):
    import sys
    from types import SimpleNamespace

    from comet.appworld import APPWORLD_DATA_VERSION, APPWORLD_REVISION
    from comet.evaluation import score_environment

    path, root = tmp_path / "saved", tmp_path / "appworld"
    (path / "task").mkdir(parents=True)
    (path / "reference.json").write_text(json.dumps({
        "appworld_revision": APPWORLD_REVISION, "data_version": APPWORLD_DATA_VERSION,
        "appworld_root": str(root), "task_id": "task", "task_directory": "task",
    }))
    calls = []

    def close_all():
        calls.append("close")
        if calls.count("close") > 1:
            raise RuntimeError("cleanup failure")

    def fail_load(**kwargs):
        raise ValueError("primary load failure")

    monkeypatch.setattr("comet.evaluation.configure_appworld_database_paths", lambda: None)
    for name, module in {
        "appworld": SimpleNamespace(AppWorld=SimpleNamespace(close_all=close_all), update_root=lambda _: None),
        "appworld.apps.lib.models.db": SimpleNamespace(
            ModelHashHandler=SimpleNamespace(reset=lambda: calls.append("reset"))),
        "appworld.evaluator": SimpleNamespace(evaluate_task=lambda **_: pytest.fail("Must not score")),
        "appworld.task": SimpleNamespace(Task=SimpleNamespace(load=fail_load)),
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    if failure_stage == "copy":
        def fail_copy(source, destination):
            destination.mkdir(parents=True)
            raise ValueError("primary copy failure")
        monkeypatch.setattr("comet.evaluation.shutil.copytree", fail_copy)
    with pytest.raises(ValueError, match=f"primary {failure_stage} failure") as error:
        score_environment(path)
    assert calls == ["close", "reset", "close", "reset"]
    assert any("cleanup failure" in note for note in error.value.__notes__)
    assert not list((root / "experiments/outputs/comet-scoring").iterdir())
