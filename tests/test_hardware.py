from dataclasses import replace
from pathlib import Path

import pytest

from comet.artifacts import read_json, write_json
from comet.cli import freeze
from comet.config import Experiment
from comet.engine.contracts import MODEL_REVISION, EngineSettings
from comet.errors import MemoryCapExceeded, UnsupportedPath


def test_device_selection_preserves_legacy_config_and_fingerprints():
    config = Experiment.load(Path(__file__).parents[1] / "configs/pilot-smoke.json")
    assert "device_name" not in config.to_dict()["engine"]
    selected = replace(config, engine=replace(config.engine, device_name="NVIDIA L40S"))
    selected.validate()
    assert selected.digest != config.digest
    assert Experiment.from_dict(selected.to_dict()) == selected
    for name in ("", "   ", 123, True):
        with pytest.raises(ValueError, match="device_name"):
            replace(config, engine=replace(config.engine, device_name=name)).validate()


def test_explicit_device_requires_exact_match_and_sufficient_capacity():
    settings = EngineSettings(
        model_path="/unused", model_revision=MODEL_REVISION, tokenizer_revision=MODEL_REVISION,
        method="full", retention=1, max_context_tokens=32768, peak_vram_bytes=40 << 30,
        workspace_reserve_bytes=6 << 30, prefill_chunk_tokens=256,
    )
    settings.validate_device("NVIDIA A100-SXM4-80GB", 80 << 30)
    with pytest.raises(UnsupportedPath, match="Legacy configs"):
        settings.validate_device("NVIDIA L40S", 48 << 30)
    selected = replace(settings, device_name="NVIDIA L40S")
    selected.validate_device("NVIDIA L40S", 48 << 30)
    assert selected.fingerprint() != settings.fingerprint()
    with pytest.raises(UnsupportedPath, match="Configured GPU"):
        selected.validate_device("NVIDIA H100 80GB HBM3", 80 << 30)
    with pytest.raises(MemoryCapExceeded, match="device capacity"):
        selected.validate_device("NVIDIA L40S", 24 << 30)
    with pytest.raises(UnsupportedPath, match="Configured GPU"):
        replace(selected, require_a100=False).validate_device("NVIDIA L4", 24 << 30)


def test_freeze_requires_observed_selected_device(tmp_path):
    base = Experiment.load(Path(__file__).parents[1] / "configs/pilot-smoke.json")
    pilot = replace(base, engine=replace(base.engine, device_name="NVIDIA L40S"))
    candidate = replace(pilot, experiment_id="fixture-final", stage="final", split="test_normal")
    candidate_path = tmp_path / "candidate.json"
    write_json(candidate_path, candidate.to_dict())
    run = tmp_path / "run"
    manifest = {
        "run_id": "fixture", "stage": "pilot", "status": "completed",
        "integration_smoke": False, "config": pilot.to_dict(), "config_digest": pilot.digest,
        "engine": {"device_name": "NVIDIA H100 80GB HBM3"},
        "cells": [{"path": "cell.json"}],
    }
    write_json(run / "manifest.json", manifest)
    write_json(run / "cell.json", {"completed": True, "attempts": [{"status": "completed"}]})
    with pytest.raises(ValueError, match="Pilot GPU"):
        freeze(candidate_path, tmp_path / "frozen.json", [run])
    manifest["engine"]["device_name"] = "NVIDIA L40S"
    write_json(run / "manifest.json", manifest)
    freeze(candidate_path, tmp_path / "frozen.json", [run])
    assert read_json(tmp_path / "frozen.json")["engine"]["device_name"] == "NVIDIA L40S"
