import json

import pytest

from comet.evaluation import evaluate_run


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
