import hashlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from comet.artifacts import read_json, write_json
from comet.config import Experiment, attempt_seed
from comet.evaluation import evaluate_run
from comet.runner import cell_id


def _fingerprints(directory):
    return {
        str(path.relative_to(directory)): {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "mtime_ns": path.stat().st_mtime_ns,
        }
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != ".lock"
    }


def _kill(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=30)


def _run(command, log, deadline):
    with log.open("w") as stream:
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            return process.wait(timeout=max(0.1, deadline - time.monotonic()))
        finally:
            _kill(process)


@pytest.mark.gpu
@pytest.mark.appworld
def test_live_process_interruption_and_resume():
    config_path = os.environ.get("COMET_RESUME_CONFIG")
    if not config_path:
        pytest.skip("Set COMET_RESUME_CONFIG for the real CLI process-kill validation.")
    config = Experiment.load(config_path)
    assert config.stage == "pilot" and config.split in {"train", "dev"}
    assert len(config.task_ids) == len(config.seeds) == 1
    assert len(config.conditions) == 3
    before, target, after = config.conditions
    assert all(c.method == "full" for c in config.conditions)
    assert before.max_attempts == after.max_attempts == 1
    assert target.max_attempts >= 2
    root = Path(os.environ["COMET_RESUME_ARTIFACT_DIR"]).resolve()
    root.mkdir(parents=True, exist_ok=False)
    output = root / "run"
    resolved = root / "config.json"
    write_json(resolved, config.to_dict())
    command = [
        sys.executable, "-m", "comet.cli", "run", str(resolved), "--output", str(output),
        "--model-path", os.environ["COMET_MODEL_PATH"],
        "--appworld-root", os.environ["COMET_APPWORLD_ROOT"], "--integration-smoke",
    ]
    timeout = float(os.environ.get("COMET_RESUME_TIMEOUT_SECONDS", 3 * config.budget_seconds + 600))
    assert 0 < timeout <= 3600, "Bound the validation to at most one hour."
    deadline = time.monotonic() + timeout
    task, seed = config.task_ids[0], config.seeds[0]
    directories = [output / "cells" / cell_id(task, c, seed) for c in config.conditions]
    before_dir, target_dir, after_dir = directories
    target_trajectory = target_dir / "attempt-000" / "trajectory.json"
    report = {"status": "running", "integration_only": True, "command": command,
              "config_digest": config.digest, "timeout_seconds": timeout,
              "interruption_signal": "SIGKILL", "cells": [str(d) for d in directories]}
    write_json(root / "report.json", report)
    try:
        segmented = _run(command + ["--max-cells", "1"], root / "segment.log", deadline)
        assert segmented == 0, "Clean segment failed; inspect segment.log."
        manifest = read_json(output / "manifest.json")
        assert manifest["status"] == "running" and "finished_at_unix" not in manifest
        assert manifest["config_digest"] == config.digest
        assert manifest["config"] == config.to_dict()
        assert len(manifest["launches"]) == 1
        launch = manifest["launches"][0]
        assert launch["max_cells"] == launch["completed_cells"] == 1
        assert launch["stop_reason"] == "max_cells"
        assert read_json(before_dir / "cell.json")["completed"]
        assert not target_dir.exists() and not after_dir.exists()
        preserved = _fingerprints(before_dir)
        snapshot = _fingerprints(output)
        with pytest.raises(ValueError, match="completed.*manifest"):
            evaluate_run(output, scorer=lambda _: pytest.fail("Incomplete execution was scored"))
        assert _fingerprints(output) == snapshot
        report["clean_segment"] = {"returncode": segmented, "launch": launch,
                                   "incomplete_scoring_rejected": True}
        report["completed_cell_before"] = preserved
        write_json(root / "report.json", report)
        with (root / "initial.log").open("w") as stream:
            process = subprocess.Popen(command + ["--resume"], stdout=stream, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            try:
                while True:
                    assert time.monotonic() < deadline, "No interruptible trajectory before timeout."
                    assert process.poll() is None, "Initial CLI exited before the interruption."
                    if target_trajectory.exists():
                        trajectory = read_json(target_trajectory)
                        if trajectory["tool_calls"] >= 1 and any(
                            turn["action"] is not None for turn in trajectory["turns"]
                        ):
                            os.killpg(process.pid, signal.SIGSTOP)
                            target_cell = read_json(target_dir / "cell.json")
                            assert target_cell["inflight"] and not target_cell["completed"]
                            assert len(target_cell["attempts"]) == 1
                            assert target_cell["attempts"][0]["status"] == "running"
                            assert read_json(before_dir / "cell.json")["completed"]
                            assert not (after_dir / "cell.json").exists()
                            break
                    time.sleep(0.02)
            finally:
                _kill(process)
        assert process.returncode == -signal.SIGKILL
        trajectory = read_json(target_trajectory)
        assert _fingerprints(before_dir) == preserved
        interrupted_trajectory = hashlib.sha256(target_trajectory.read_bytes()).hexdigest()
        report["interrupted"] = {
            "pid": process.pid, "returncode": process.returncode,
            "cell": target_cell, "tool_calls": trajectory["tool_calls"],
            "raw_token_count": len(trajectory["raw_token_ids"]),
            "trajectory_sha256": interrupted_trajectory,
        }
        write_json(root / "report.json", report)

        incompatible = config.to_dict()
        incompatible["budget_seconds"] += 1
        changed_path = root / "incompatible-config.json"
        write_json(changed_path, incompatible)
        changed_command = [*command]
        changed_command[4] = str(changed_path)
        snapshot = _fingerprints(output)
        rejected = _run(changed_command + ["--resume"], root / "incompatible.log", deadline)
        assert rejected != 0
        assert "Resume configuration differs" in (root / "incompatible.log").read_text()
        assert _fingerprints(output) == snapshot
        report["incompatible_config"] = {"returncode": rejected, "artifacts_unchanged": True}
        write_json(root / "report.json", report)

        resumed = _run(command + ["--resume"], root / "resume.log", deadline)
        assert resumed == 0, "Resume failed; inspect resume.log."
        manifest = read_json(output / "manifest.json")
        assert manifest["status"] == "completed" and len(manifest["launches"]) == 3
        assert manifest["launches"][0] == report["clean_segment"]["launch"]
        assert manifest["launches"][-1]["completed_cells"] == 2
        assert manifest["launches"][-1]["stop_reason"] == "all_cells_completed"
        assert manifest["config_digest"] == config.digest
        assert _fingerprints(before_dir) == preserved
        target_cell = read_json(target_dir / "cell.json")
        assert target_cell["completed"] and not target_cell["inflight"]
        assert target_cell["elapsed_seconds"] == config.budget_seconds
        assert len(target_cell["attempts"]) == 1
        attempt = target_cell["attempts"][0]
        assert attempt["status"] == "interrupted"
        assert attempt["failure_reason"] == "process_interrupted"
        assert attempt["budget_elapsed_seconds"] == config.budget_seconds
        assert attempt["reserved_budget_seconds"] == config.budget_seconds
        assert read_json(target_dir / "attempt-000" / "attempt.json") == attempt
        assert not (target_dir / "attempt-001").exists()
        assert hashlib.sha256(target_trajectory.read_bytes()).hexdigest() == interrupted_trajectory

        after_cell = read_json(after_dir / "cell.json")
        assert after_cell["completed"] and len(after_cell["attempts"]) == 1
        later = after_cell["attempts"][0]
        assert later["attempt_index"] == 0 and later["seed"] == attempt_seed(seed, 0)
        assert later["status"] in {"completed", "context_limit", "timeout"}
        original = read_json(before_dir / "attempt-000" / "trajectory.json")
        fresh = read_json(after_dir / "attempt-000" / "trajectory.json")
        assert original["turns"][0] == trajectory["turns"][0] == fresh["turns"][0]
        prefix = trajectory["raw_token_ids"]
        assert original["raw_token_ids"][:len(prefix)] == fresh["raw_token_ids"][:len(prefix)] == prefix
        environments = [read_json(d / "attempt-000" / "environment" / "live.json")
                        for d in directories]
        assert len({e["experiment_name"] for e in environments}) == 3
        assert len({e["output_directory"] for e in environments}) == 3
        assert all(e["task_id"] == task and e["seed"] == attempt_seed(seed, 0) for e in environments)
        assert not (output / "scores.json").exists()
        report.update(
            status="passed", run_id=manifest["run_id"], resume_returncode=resumed,
            preserved_completed_cell=True, preserved_interrupted_trajectory=True,
            interrupted_cell=target_cell, remaining_cell=after_cell,
            paired_first_turn_equal=True, paired_raw_prefix_tokens=len(prefix),
            distinct_environments=environments,
        )
    except BaseException as error:
        report.update(status="failed", failure=f"{type(error).__name__}: {error}")
        raise
    finally:
        write_json(root / "report.json", report)
