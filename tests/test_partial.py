from pathlib import Path

import pytest

from comet.artifacts import read_json, write_json
from comet.config import Experiment
from comet.partial import score_snapshot, snapshot_study
from comet.partitions import partition_study


def live_study(tmp_path):
    data = Experiment.load(Path(__file__).parent / "fixtures/full-cache.json").to_dict()
    conditions = [data["conditions"][0]]
    conditions += [{"id": method, "method": method, "retention": 0.5,
                    "recovery": "never", "max_attempts": 2}
                   for method in ("streamingllm", "rkv", "agentkv")]
    data.update(stage="final", split="test_normal", task_ids=["task1", "task2"],
                max_attempts=2, conditions=conditions)
    data["frozen"] = {"settings_digest": Experiment.from_dict(data, allow_unfrozen=True).settings_digest,
                      "pilot_evidence": [{"run_id": "fixture"}]}
    parent, parts, run = tmp_path / "parent.json", tmp_path / "parts", tmp_path / "run"
    write_json(parent, data)
    index = partition_study(parent, parts, 4)
    for number, statuses in enumerate((("completed", "error"), ("oom", "timeout"),
                                       ("completed", "running"))):
        entry = index["partitions"][number]
        config = Experiment.load(parts / entry["config"])
        directory = run / f"part-{number:02d}"
        refs = []
        for task, status in zip(data["task_ids"], statuses, strict=True):
            relative = f"cells/{task}"
            cell = {"schema_version": 1, "run_id": str(number), "stage": "final",
                    "config_digest": config.digest, "task_id": task, "seed": 17,
                    "condition": config.to_dict()["conditions"][0], "completed": status != "running",
                    "inflight": status == "running", "elapsed_seconds": 5, "budget_seconds": 600,
                    "attempts": [{"attempt_index": 0, "status": status, "metrics": {},
                                  "artifact_dir": f"{relative}/attempt-000"}]}
            write_json(directory / relative / "cell.json", cell)
            if status == "completed":
                write_json(directory / relative / "attempt-000/environment/reference.json", {"saved": True})
            refs.append({"id": task, "path": f"{relative}/cell.json", "task_id": task,
                         "condition_id": cell["condition"]["id"], "seed": 17})
        write_json(directory / "manifest.json", {
            "schema_version": 1, "status": "running", "run_id": str(number), "config_digest": config.digest,
            "engine": {"device_name": "fixture"}, "provenance": {"source_hashes": {}, "installed_packages": {}},
            "config": config.to_dict(), "cells": refs,
        })
    return parts, run


def test_partial_snapshot_keeps_full_pairing_failures_and_live_files_unchanged(tmp_path):
    parts, run = live_study(tmp_path)
    before = {p: p.read_bytes() for p in run.rglob("*") if p.is_file()}
    output = tmp_path / "partial"
    snapshot = snapshot_study(parts, run, output)
    assert snapshot["included_conditions"] == ["full_once", "streamingllm"]
    assert snapshot["coverage"]["rkv"]["completed_cells"] == 1
    assert snapshot["coverage"]["agentkv"]["completed_cells"] == 0
    assert len(snapshot["cells"]) == 4
    calls = []

    def scorer(path):
        assert path.is_relative_to(output)
        write_json(path / "evaluation/report.json", {"scored": True})
        calls.append(path)
        return {"success": True}

    analysis = score_snapshot(output, scorer=scorer, bootstrap_samples=20)
    assert len(calls) == 1
    assert analysis["task_count"] == 2 and analysis["partial_study"]["provisional"]
    assert analysis["conditions"]["full_once"]["oracle_success_rate"]["value"] == 0.5
    assert analysis["conditions"]["streamingllm"]["oracle_success_rate"]["value"] == 0
    score_snapshot(output, scorer=lambda _: pytest.fail("Completed scores should be reused"), bootstrap_samples=20)
    assert before == {p: p.read_bytes() for p in run.rglob("*") if p.is_file()}
    with pytest.raises(FileExistsError):
        snapshot_study(parts, run, output)


def test_partial_snapshot_rejects_live_destination_and_mixed_runtime(tmp_path):
    parts, run = live_study(tmp_path)
    with pytest.raises(ValueError, match="separate"):
        snapshot_study(parts, run, run / "partial")
    path = run / "part-01/manifest.json"
    manifest = read_json(path)
    manifest["engine"]["device_name"] = "different hardware"
    write_json(path, manifest)
    with pytest.raises(ValueError, match="different source, runtime or hardware"):
        snapshot_study(parts, run, tmp_path / "partial")


def test_partial_snapshot_rejects_terminal_cell_with_running_attempt(tmp_path):
    parts, run = live_study(tmp_path)
    path = run / "part-00/cells/task1/cell.json"
    cell = read_json(path)
    cell["attempts"][0]["status"] = "running"
    write_json(path, cell)
    with pytest.raises(ValueError, match="nonterminal"):
        snapshot_study(parts, run, tmp_path / "partial")


def _successful_scorer(path):
    return {"success": True}


def test_parallel_scoring_preserves_failures_and_pairing(tmp_path):
    parts, run = live_study(tmp_path)
    output = tmp_path / "partial"
    snapshot_study(parts, run, output)
    analysis = score_snapshot(output, scorer=_successful_scorer, bootstrap_samples=20, workers=2)
    assert analysis["conditions"]["full_once"]["oracle_success_rate"]["value"] == 0.5
    assert analysis["conditions"]["streamingllm"]["oracle_success_rate"]["value"] == 0
    assert len(list(output.glob("cells/*/*/attempt-*/environment/partial-score.json"))) == 1
