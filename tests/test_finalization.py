from pathlib import Path

import pytest

from comet.artifacts import read_json, write_json
from comet.config import Experiment
from comet.finalization import finalize_run
from comet.runner import Runner


@pytest.fixture
def interrupted_run(tmp_path):
    config = Experiment.load(Path(__file__).parents[1] / "configs/pilot-smoke.json")
    runner = Runner(config, tmp_path / "run", None, None, integration_smoke=True)
    manifest = runner._manifest(resume=False)
    for index, reference in enumerate(manifest["cells"]):
        condition = next(c for c in config.conditions if c.id == reference["condition_id"])
        cell = runner._new_cell(manifest, reference, condition)
        attempt_dir = Path(reference["path"]).parent / "attempt-000"
        attempt = {
            "attempt_index": 0, "status": "completed" if index else "running",
            "artifact_dir": str(attempt_dir), "metrics": {"generated_tokens": 12},
            "elapsed_seconds": 4, "recovery_events": [],
        }
        cell.update(attempts=[attempt], elapsed_seconds=4, completed=bool(index),
                    inflight=not index)
        write_json(runner.output / reference["path"], cell)
        write_json(runner.output / attempt_dir / "attempt.json", attempt)
        write_json(runner.output / attempt_dir / "trajectory.json", {"raw_token_ids": [1, 2]})
    return runner.output, config


def test_finalization_preserves_completed_artifacts_and_charges_interruption(interrupted_run):
    run, config = interrupted_run
    manifest = read_json(run / "manifest.json")
    untouched = {
        path: path.read_bytes() for reference in manifest["cells"][1:]
        for path in (run / reference["path"]).parent.rglob("*.json")
    }
    first = run / manifest["cells"][0]["path"]
    trajectory = first.parent / "attempt-000/trajectory.json"
    saved_trajectory = trajectory.read_bytes()
    result = finalize_run(run)
    assert result["status"] == "completed"
    assert result["finalizations"][0]["inference_performed"] is False
    cell = read_json(first)
    assert cell["elapsed_seconds"] == config.budget_seconds
    assert len(cell["attempts"]) == 1
    assert cell["attempts"][0]["status"] == "interrupted"
    assert cell["attempts"][0]["reserved_budget_seconds"] == config.budget_seconds - 4
    assert read_json(first.parent / "attempt-000/attempt.json") == cell["attempts"][0]
    assert trajectory.read_bytes() == saved_trajectory
    assert all(path.read_bytes() == content for path, content in untouched.items())
    saved_manifest = (run / "manifest.json").read_bytes()
    finalize_run(run)
    assert (run / "manifest.json").read_bytes() == saved_manifest


@pytest.mark.parametrize("missing", [False, True])
def test_finalization_refuses_any_eligible_inference_before_mutation(interrupted_run, missing):
    run, _ = interrupted_run
    reference = read_json(run / "manifest.json")["cells"][-1]
    path = run / reference["path"]
    if missing:
        path.unlink()
    else:
        cell = read_json(path)
        cell.update(completed=False, inflight=False, attempts=[])
        write_json(path, cell)
    before = {p: p.read_bytes() for p in run.rglob("*.json")}
    with pytest.raises(ValueError, match="Inference remains eligible"):
        finalize_run(run)
    assert all(p.read_bytes() == content for p, content in before.items())


def test_finalization_retains_source_compatibility_checks(interrupted_run):
    run, _ = interrupted_run
    manifest = read_json(run / "manifest.json")
    manifest["provenance"]["code_commit"] = "different"
    write_json(run / "manifest.json", manifest)
    with pytest.raises(ValueError, match="original code"):
        finalize_run(run)


def test_finalization_closes_attempt_limited_cell_without_extra_work(interrupted_run):
    run, _ = interrupted_run
    first = run / read_json(run / "manifest.json")["cells"][0]["path"]
    cell = read_json(first)
    cell["inflight"] = False
    cell["attempts"][0]["status"] = "error"
    write_json(first, cell)
    finalize_run(run)
    finalized = read_json(first)
    assert finalized["completed"]
    assert finalized["attempts"] == cell["attempts"]
    assert finalized["elapsed_seconds"] < cell["budget_seconds"]
