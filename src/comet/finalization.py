"""Finalize interrupted bookkeeping without initializing inference or AppWorld."""

from pathlib import Path

from comet.artifacts import read_json, run_lock, write_json
from comet.clocks import wall_time
from comet.config import Experiment
from comet.runner import Runner


def finalize_run(output: Path) -> dict:
    output = output.resolve()
    saved = read_json(output / "manifest.json")
    config = Experiment.from_dict(saved["config"])

    def unavailable(*args, **kwargs):
        raise RuntimeError("Metadata finalization must never initialize an engine or environment")

    runner = Runner(config, output, unavailable, unavailable,
                    integration_smoke=saved["integration_smoke"])
    with run_lock(output):
        manifest = runner._manifest(resume=True)
        if manifest["status"] == "completed":
            return manifest
        conditions = {condition.id: condition for condition in config.conditions}
        pending = []
        for reference in manifest["cells"]:
            path = output / reference["path"]
            if not path.exists():
                raise ValueError(f"Inference remains eligible for {reference['id']}; use run --resume")
            cell = read_json(path)
            if cell["completed"]:
                continue
            condition = conditions[reference["condition_id"]]
            if not cell.get("inflight") and (
                cell["elapsed_seconds"] < config.budget_seconds
                and len(cell["attempts"]) < condition.max_attempts
            ):
                raise ValueError(f"Inference remains eligible for {reference['id']}; use run --resume")
            pending.append((reference, condition))
        # Validate the entire run before changing any cell.
        for reference, condition in pending:
            runner._run_cell(manifest, reference, condition, None)
        manifest.setdefault("finalizations", []).append({
            "at_unix": wall_time(), "mode": "metadata_only", "inference_performed": False,
            "cells": [reference["id"] for reference, _ in pending],
        })
        manifest.update(status="completed", finished_at_unix=wall_time())
        write_json(output / "manifest.json", manifest)
        return manifest
