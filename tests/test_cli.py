from copy import deepcopy
from pathlib import Path

import pytest

from comet.artifacts import read_json, write_json
from comet.cli import freeze
from comet.config import Experiment, digest


@pytest.fixture
def freeze_files(tmp_path):
    pilot = Experiment.load(Path(__file__).parents[1] / "configs/pilot-smoke.json").to_dict()
    candidate = deepcopy(pilot)
    candidate.update(experiment_id="fixture-final", stage="final", split="test_normal",
                     task_ids=["fixture_test_1"], notes="Unit test fixture; no experiment was run.")
    config_path = tmp_path / "candidate.json"
    write_json(config_path, candidate)
    run = tmp_path / "pilot"
    manifest = {
        "schema_version": 1, "run_id": "fixture-pilot", "stage": "pilot",
        "status": "completed", "integration_smoke": False,
        "config": pilot, "config_digest": digest(pilot), "cells": [],
    }
    for condition in pilot["conditions"]:
        path = f"cells/{condition['id']}/cell.json"
        manifest["cells"].append({"id": condition["id"], "path": path,
                                  "task_id": pilot["task_ids"][0],
                                  "condition_id": condition["id"], "seed": pilot["seeds"][0]})
        write_json(run / path, {
            "schema_version": 1, "run_id": manifest["run_id"], "stage": "pilot",
            "config_digest": manifest["config_digest"], "task_id": pilot["task_ids"][0],
            "split": pilot["split"], "condition": condition, "seed": pilot["seeds"][0],
            "budget_seconds": pilot["budget_seconds"], "elapsed_seconds": 1,
            "completed": True,
            "attempts": [{"attempt_index": 0, "status": "completed", "metrics": {}}],
        })
    write_json(run / "manifest.json", manifest)
    return config_path, run, tmp_path / "frozen.json"


def test_freeze_accepts_matching_pilot_and_preserves_evidence(freeze_files):
    candidate, run, output = freeze_files
    record = freeze(candidate, output, [run])
    frozen = Experiment.load(output)
    assert frozen.frozen == record
    assert record["settings_digest"] == frozen.settings_digest
    assert record["pilot_evidence"] == [{
        "run_id": "fixture-pilot", "path": str(run.resolve()),
        "manifest_digest": digest(read_json(run / "manifest.json")),
        "config_digest": read_json(run / "manifest.json")["config_digest"],
    }]
    assert frozen.stage == "final" and frozen.split == "test_normal"
    assert read_json(candidate)["frozen"] is None


@pytest.mark.parametrize(("keys", "value", "message"), [
    (("integration_smoke",), True, "completed A100"),
    (("status",), "running", "completed A100"),
    (("config", "split"), "test_normal", "Test outcomes"),
    (("config", "budget_seconds"), 121, "numerical settings"),
    (("config", "peak_vram_bytes"), 35_000_000_000, "numerical settings"),
    (("config", "engine", "max_context_tokens"), 8192, "numerical settings"),
    (("config", "sampling", "temperature"), 0.9, "numerical settings"),
    (("config", "triggers", "fixed_tool_calls"), 7, "numerical settings"),
    (("cells",), [], "incomplete"),
])
def test_freeze_rejects_ineligible_or_mismatched_evidence(freeze_files, keys, value, message):
    candidate, run, output = freeze_files
    manifest = read_json(run / "manifest.json")
    target = manifest
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    write_json(run / "manifest.json", manifest)
    with pytest.raises(ValueError, match=message):
        freeze(candidate, output, [run])
    assert not output.exists()


@pytest.mark.parametrize("incomplete", [True, False])
def test_freeze_requires_finished_cells_and_a_completed_attempt(freeze_files, incomplete):
    candidate, run, output = freeze_files
    for reference in read_json(run / "manifest.json")["cells"]:
        path = run / reference["path"]
        cell = read_json(path)
        if incomplete:
            cell["completed"] = False
        else:
            cell["attempts"][0]["status"] = "timeout"
        write_json(path, cell)
    with pytest.raises(ValueError, match="incomplete|no completed attempts"):
        freeze(candidate, output, [run])
    assert not output.exists()


def test_freeze_requires_evidence_and_never_overwrites(freeze_files):
    candidate, run, output = freeze_files
    with pytest.raises(ValueError, match="At least one"):
        freeze(candidate, output, [])
    freeze(candidate, output, [run])
    saved = output.read_bytes()
    with pytest.raises(FileExistsError, match="immutable"):
        freeze(candidate, output, [run])
    assert output.read_bytes() == saved


@pytest.mark.parametrize("split", ["train", "dev"])
def test_final_configuration_rejects_training_splits(freeze_files, split):
    candidate, run, output = freeze_files
    config = read_json(candidate)
    config["split"] = split
    write_json(candidate, config)
    with pytest.raises(ValueError, match="explicit test split"):
        freeze(candidate, output, [run])
    assert not output.exists()
