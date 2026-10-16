from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

from comet.artifacts import read_json, write_json
from comet.config import Experiment, comparison_matrix, digest


def _print(value) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


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
    )
    proposed = config.to_dict()
    for run in pilot_runs:
        manifest = read_json(run / "manifest.json")
        if (
            manifest["stage"] != "pilot"
            or manifest["status"] != "completed"
            or manifest.get("integration_smoke", True)
        ):
            raise ValueError("Freeze requires completed A100 train/dev pilot runs")
        pilot = manifest["config"]
        if pilot["split"] not in {"train", "dev"}:
            raise ValueError("Test outcomes cannot be freeze evidence")
        if any(proposed[key] != pilot[key] for key in fields):
            raise ValueError("Frozen numerical settings must match the supplied measured pilot")
        cells = [read_json(run / c["path"]) for c in manifest["cells"]]
        if not cells or any(not cell["completed"] for cell in cells):
            raise ValueError("Pilot evidence is incomplete")
        if not any(a["status"] == "completed" for cell in cells for a in cell["attempts"]):
            raise ValueError("Pilot evidence contains no completed attempts")
        evidence.append(
            {
                "run_id": manifest["run_id"],
                "path": str(run.resolve()),
                "manifest_digest": digest(manifest),
                "config_digest": manifest["config_digest"],
            }
        )
    if not evidence:
        raise ValueError("At least one measured train/dev pilot is required")
    proposed["frozen"] = {
        "settings_digest": config.settings_digest,
        "frozen_at_unix": time.time(),
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="COMET experiment execution, scoring and analysis")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Validate an experiment configuration")
    validate.add_argument("config", type=Path)
    matrix = commands.add_parser("matrix", help="Print the proposal's 29 comparison conditions")
    matrix.add_argument("config", type=Path)
    run = commands.add_parser("run", help="Run pilot, checkpoint diagnostic, or frozen evaluation")
    run.add_argument("config", type=Path)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--model-path", type=Path, required=True)
    run.add_argument("--appworld-root", type=Path, required=True)
    run.add_argument("--resume", action="store_true")
    run.add_argument(
        "--integration-smoke",
        action="store_true",
        help="Allow another GPU; outputs are ineligible for final evaluation",
    )
    evaluate = commands.add_parser("evaluate", help="Score a completed run offline")
    evaluate.add_argument("run", type=Path)
    analyze = commands.add_parser(
        "analyze", help="Compute task-level oracle success and paired intervals"
    )
    analyze.add_argument("runs", type=Path, nargs="+")
    analyze.add_argument("--output", type=Path, required=True)
    analyze.add_argument("--bootstrap-samples", type=int, default=2000)
    analyze.add_argument("--seed", type=int, default=0)
    frozen = commands.add_parser(
        "freeze", help="Freeze final settings with measured train/dev evidence"
    )
    frozen.add_argument("config", type=Path)
    frozen.add_argument("--output", type=Path, required=True)
    frozen.add_argument("--pilot-run", type=Path, action="append", required=True)
    check = commands.add_parser("doctor", help="Inspect installed dependencies and scheduler tools")
    check.add_argument("--gpu", action="store_true")
    args = parser.parse_args(argv)
    if args.command in {"validate", "matrix"}:
        config = Experiment.load(args.config)
        _print(
            {
                "experiment_id": config.experiment_id,
                "digest": config.digest,
                "cells": len(config.conditions) * len(config.task_ids) * len(config.seeds),
            }
            if args.command == "validate"
            else [asdict(c) for c in comparison_matrix(config.max_attempts)]
        )
    elif args.command == "doctor":
        _print(doctor(args.gpu))
    elif args.command == "freeze":
        _print(freeze(args.config, args.output, args.pilot_run))
    elif args.command == "evaluate":
        from comet.evaluation import evaluate_run

        result = evaluate_run(args.run)
        _print({"status": result["status"], "scores": str(args.run / "scores.json")})
    elif args.command == "analyze":
        from comet.analysis import analyze_runs

        analyze_runs(
            args.runs, args.output, bootstrap_samples=args.bootstrap_samples, seed=args.seed
        )
        _print({"analysis": str(args.output)})
    else:
        from comet.appworld import AppWorldAdapter, validate_tasks
        from comet.engine import EngineSettings, MiniSGLangEngine
        from comet.runner import Runner

        config = Experiment.load(args.config)
        os.environ["APPWORLD_ROOT"] = str(args.appworld_root.resolve())
        validate_tasks(config.split, config.task_ids)

        def make_engine(condition):
            return MiniSGLangEngine(
                EngineSettings(
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
                )
            )

        result = Runner(
            config,
            args.output,
            make_engine,
            lambda: AppWorldAdapter(args.appworld_root),
            integration_smoke=args.integration_smoke,
        ).run(resume=args.resume)
        _print({"run_id": result["run_id"], "status": result["status"], "output": str(args.output)})


if __name__ == "__main__":
    main()
