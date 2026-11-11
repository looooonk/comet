"""Configuration freezing, runtime inspection and experiment launch commands."""

from __future__ import annotations

import importlib.metadata
import os
import platform
import shutil
import subprocess
from pathlib import Path

from comet.artifacts import read_json, write_json
from comet.clocks import wall_time
from comet.config import Experiment, digest


def freeze(config_path: Path, output: Path, pilot_runs: list[Path]) -> dict:
    config = Experiment.load(config_path, allow_unfrozen=True)
    if config.stage != "final":
        raise ValueError("Freeze an explicitly prepared final-stage configuration")
    if output.exists():
        raise FileExistsError("A frozen configuration is immutable; choose a new versioned path")
    evidence = []
    fields = (
        "budget_seconds",
        "peak_vram_bytes",
        "max_attempts",
        "engine",
        "sampling",
        "triggers",
        "prompt",
        "agent",
    )
    proposed = config.to_dict()
    for run in pilot_runs:
        manifest = read_json(run / "manifest.json")
        if (
            manifest["stage"] != "pilot"
            or manifest["status"] != "completed"
            or manifest.get("integration_smoke", True)
        ):
            raise ValueError("Freeze requires completed qualified-hardware train/dev pilot runs")
        if manifest["config"]["split"] not in {"train", "dev"}:
            raise ValueError("Test outcomes cannot be freeze evidence")
        pilot = Experiment.from_dict(manifest["config"], allow_unfrozen=True).to_dict()
        if any(proposed[key] != pilot[key] for key in fields):
            raise ValueError("Frozen numerical settings must match the supplied measured pilot")
        expected_device = config.engine.device_name
        if expected_device and manifest.get("engine", {}).get("device_name") != expected_device:
            raise ValueError("Pilot GPU does not match the explicitly selected device_name")
        cells = [read_json(run / c["path"]) for c in manifest["cells"]]
        if not cells or any(not cell["completed"] for cell in cells):
            raise ValueError("Pilot evidence is incomplete")
        if not any(a["status"] == "completed" for cell in cells for a in cell["attempts"]):
            raise ValueError("Pilot evidence contains no completed attempts")
        evidence.append(
            {
                "run_id": manifest["run_id"],
                "artifact_id": f"comet-run:{manifest['run_id']}",
                "manifest_digest": digest(manifest),
                "config_digest": manifest["config_digest"],
            }
        )
    if not evidence:
        raise ValueError("At least one measured train/dev pilot is required")
    proposed["frozen"] = {
        "settings_digest": config.settings_digest,
        "frozen_at_unix": wall_time(),
        "pilot_evidence": evidence,
    }
    Experiment.from_dict(proposed)
    write_json(output, proposed)
    return proposed["frozen"]


def doctor(gpu: bool = False) -> dict:
    result = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "commands": {name: shutil.which(name) for name in ("git", "uv", "sbatch", "gcloud")},
        "appworld_root": os.environ.get("APPWORLD_ROOT"),
        "slurm_config": os.environ.get("SLURM_CONF"),
        "packages": {},
    }
    for package in ("comet-research", "appworld", "torch", "transformers", "flashinfer-python"):
        try:
            result["packages"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result["packages"][package] = None
    if gpu:
        command = shutil.which("nvidia-smi")
        if command:
            probe = subprocess.run(
                [command, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
                capture_output=True,
                text=True,
            )
            result["gpu"] = probe.stdout.strip() if probe.returncode == 0 else probe.stderr.strip()
        else:
            result["gpu"] = "nvidia-smi unavailable"
    return result


def run_experiment(args, parser):
    from comet.appworld import AppWorldAdapter, validate_tasks
    from comet.engine import EngineSettings, create_engine
    from comet.runner import Runner

    config = Experiment.load(args.config)
    if args.max_cells is not None:
        if args.max_cells <= 0:
            parser.error("--max-cells must be a positive integer")
    os.environ["APPWORLD_ROOT"] = str(args.appworld_root.resolve())
    validate_tasks(config.split, config.task_ids)
    if config.environment_warmup is not None:
        validate_tasks("train", [config.environment_warmup.task_id])

    def make_engine(condition):
        return create_engine(
            EngineSettings(
                backend=config.engine.backend,
                model=config.engine.model,
                model_path=str(args.model_path.resolve()),
                model_revision=config.engine.model_revision,
                tokenizer_revision=config.engine.tokenizer_revision,
                method=condition.method,
                retention=condition.retention,
                max_context_tokens=config.engine.max_context_tokens,
                peak_vram_bytes=config.peak_vram_bytes,
                workspace_reserve_bytes=config.engine.workspace_reserve_bytes,
                prefill_chunk_tokens=config.engine.prefill_chunk_tokens,
                require_a100=not args.integration_smoke,
                device_name=config.engine.device_name,
            )
        )

    result = Runner(
        config,
        args.output,
        make_engine,
        lambda: AppWorldAdapter(args.appworld_root),
        integration_smoke=args.integration_smoke,
    ).run(resume=args.resume, max_cells=args.max_cells)
    return {"run_id": result["run_id"], "status": result["status"], "output": str(args.output)}
