from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

from comet.artifacts import read_json, write_json
from comet.clocks import wall_time
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
                "path": str(run.resolve()),
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
    finalize = commands.add_parser("finalize", help="Finalize interrupted cells when no inference remains")
    finalize.add_argument("run", type=Path)
    analyze = commands.add_parser(
        "analyze", help="Compute task-level oracle success and paired intervals"
    )
    analyze.add_argument("runs", type=Path, nargs="+")
    analyze.add_argument("--output", type=Path, required=True)
    analyze.add_argument("--bootstrap-samples", type=int, default=2000)
    analyze.add_argument("--seed", type=int, default=0)
    histories = commands.add_parser("analyze-histories", help="Validate and summarize matched-history measurements")
    histories.add_argument("runs", type=Path, nargs="+")
    histories.add_argument("--output", type=Path, required=True)
    history_plot = commands.add_parser("plot-histories", help="Plot one measured history-cost metric by method")
    history_plot.add_argument("analysis", type=Path)
    history_plot.add_argument("--output", type=Path, required=True)
    history_plot.add_argument("--metric", required=True, choices=(
        "occupied-kv", "peak-kv", "reserved-pool", "total-vram", "peak-vram",
        "prefill-throughput", "decode-throughput", "prefill-time", "decode-time",
        "selection", "compaction", "instrumented-time",
    ))
    history_plot.add_argument("--history", dest="history_id")
    history_plot.add_argument("--title", default="Matched-history cost")
    compare = commands.add_parser("compare-protocol", help="Compare explicitly declared paired protocol arms")
    compare.add_argument("control", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--protocol-field", choices=("prompt", "agent"), action="append", required=True)
    compare.add_argument("--output", type=Path, required=True)
    compare.add_argument("--bootstrap-samples", type=int, default=2000)
    compare.add_argument("--seed", type=int, default=0)
    baseline = commands.add_parser("plot-baseline", help="Plot protocol success, failure, errors and duration")
    baseline.add_argument("comparison", type=Path)
    baseline.add_argument("--output", type=Path, required=True)
    baseline.add_argument("--title", default="AppWorld baseline diagnostic")
    retention = commands.add_parser("plot-retention-matrix", help="Facet retention by method, recovery and attempt limit")
    retention.add_argument("analysis", type=Path)
    retention.add_argument("--output", type=Path, required=True)
    retention.add_argument("--title", default="Retention comparison")
    for command, help_text, title in (
        ("plot-recovery", "Plot paired recovery effects, cost and admission", "Recovery comparison"),
        ("plot-triggers", "Plot observed trigger decisions and paired effects", "Recovery trigger observations"),
        ("plot-attempts", "Plot first/oracle success, attempts and observed cost", "Attempt allocation comparison"),
        ("plot-success-time", "Plot attained oracle success along executed schedules", "Attained oracle success over time"),
    ):
        figure = commands.add_parser(command, help=help_text)
        figure.add_argument("analysis", type=Path)
        figure.add_argument("--output", type=Path, required=True)
        figure.add_argument("--title", default=title)
    plot = commands.add_parser("plot", help="Plot paired retention means and uncertainty")
    plot.add_argument("analysis", type=Path)
    plot.add_argument("--output", type=Path, required=True)
    plot.add_argument("--title", default="AppWorld retention pilot")
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
    elif args.command == "finalize":
        from comet.finalization import finalize_run

        result = finalize_run(args.run)
        _print({"run_id": result["run_id"], "status": result["status"], "inference_performed": False})
    elif args.command == "analyze":
        from comet.analysis import analyze_runs

        analyze_runs(
            args.runs, args.output, bootstrap_samples=args.bootstrap_samples, seed=args.seed
        )
        _print({"analysis": str(args.output)})
    elif args.command == "plot":
        from comet.plotting import plot_retention

        plot_retention(args.analysis, args.output, title=args.title)
        _print({"figure": str(args.output)})
    elif args.command == "analyze-histories":
        from comet.history_analysis import analyze_histories

        analyze_histories(args.runs, args.output)
        _print({"analysis": str(args.output)})
    elif args.command == "plot-histories":
        from comet.history_plots import plot_histories

        plot_histories(args.analysis, args.output, metric=args.metric,
                       history_id=args.history_id, title=args.title)
        _print({"figure": str(args.output)})
    elif args.command == "compare-protocol":
        from comet.comparison import compare_protocol_runs

        compare_protocol_runs(args.control, args.candidate, args.output,
                              protocol_fields=args.protocol_field,
                              bootstrap_samples=args.bootstrap_samples, seed=args.seed)
        _print({"comparison": str(args.output)})
    elif args.command == "plot-baseline":
        from comet.plotting import plot_baseline

        plot_baseline(args.comparison, args.output, title=args.title)
        _print({"figure": str(args.output)})
    elif args.command == "plot-retention-matrix":
        from comet.study_plots import plot_retention_matrix

        plot_retention_matrix(args.analysis, args.output, title=args.title)
        _print({"figure": str(args.output)})
    elif args.command in {"plot-recovery", "plot-triggers", "plot-attempts", "plot-success-time"}:
        from comet.policy_plots import (
            plot_attained_oracle,
            plot_attempts,
            plot_recovery,
            plot_triggers,
        )

        plotters = {"plot-recovery": plot_recovery, "plot-triggers": plot_triggers,
                    "plot-attempts": plot_attempts, "plot-success-time": plot_attained_oracle}
        plotters[args.command](args.analysis, args.output, title=args.title)
        _print({"figure": str(args.output)})
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
        ).run(resume=args.resume)
        _print({"run_id": result["run_id"], "status": result["status"], "output": str(args.output)})


if __name__ == "__main__":
    main()
