from __future__ import annotations

import json
from dataclasses import asdict

from comet._cli_parser import build_parser
from comet._commands import doctor as doctor
from comet._commands import freeze as freeze
from comet._commands import run_experiment
from comet.config import Experiment, comparison_matrix


def _print(value) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
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
    elif args.command == "partition":
        from comet.partitions import partition_study

        _print(partition_study(args.config, args.output, args.count))
    elif args.command == "evaluate":
        from comet.evaluation import evaluate_run

        result = evaluate_run(args.run)
        _print({"status": result["status"], "scores": str(args.run / "scores.json")})
    elif args.command == "rescore":
        from comet.evaluation import rescore_run

        result = rescore_run(args.run, args.output)
        _print({"status": result["status"], "scores": str(args.output / "scores.json")})
    elif args.command == "finalize":
        from comet.finalization import finalize_run

        result = finalize_run(args.run)
        _print(
            {"run_id": result["run_id"], "status": result["status"], "inference_performed": False}
        )
    elif args.command == "analyze":
        from comet.analysis import analyze_runs

        analyze_runs(
            args.runs,
            args.output,
            bootstrap_samples=args.bootstrap_samples,
            seed=args.seed,
            study_config=args.study_config,
        )
        _print({"analysis": str(args.output)})
    elif args.command == "analyze-budget-sweep":
        from comet.budget_sweep import analyze_budget_sweep

        analyze_budget_sweep(
            args.runs, args.output, bootstrap_samples=args.bootstrap_samples, seed=args.seed
        )
        _print({"analysis": str(args.output)})
    elif args.command == "plot-budget-sweep":
        from comet.budget_sweep import plot_budget_sweep

        plot_budget_sweep(args.analysis, args.output, title=args.title)
        _print({"figure": str(args.output)})
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

        plot_histories(
            args.analysis,
            args.output,
            metric=args.metric,
            history_id=args.history_id,
            title=args.title,
            retention=args.retention,
        )
        _print({"figure": str(args.output)})
    elif args.command == "compare-protocol":
        from comet.comparison import compare_protocol_runs

        compare_protocol_runs(
            args.control,
            args.candidate,
            args.output,
            protocol_fields=args.protocol_field,
            bootstrap_samples=args.bootstrap_samples,
            seed=args.seed,
        )
        _print({"comparison": str(args.output)})
    elif args.command == "plot-baseline":
        from comet.plotting import plot_baseline

        plot_baseline(args.comparison, args.output, title=args.title)
        _print({"figure": str(args.output)})
    elif args.command == "plot-retention-matrix":
        from comet.study_plots import plot_retention_matrix

        plot_retention_matrix(args.analysis, args.output, title=args.title)
        _print({"figure": str(args.output)})
    elif args.command == "plot-resources":
        from comet.resource_plots import plot_resources

        plot_resources(args.analysis, args.output, policy=args.policy, title=args.title)
        _print({"figure": str(args.output)})
    elif args.command == "plot-aggressivity":
        from comet.aggressivity_plots import plot_aggressivity

        plot_aggressivity(args.analysis, args.output, title=args.title)
        _print({"figure": str(args.output)})
    elif args.command in {"plot-recovery", "plot-triggers", "plot-attempts", "plot-success-time"}:
        from comet.policy_plots import (
            plot_attained_oracle,
            plot_attempts,
            plot_recovery,
            plot_triggers,
        )

        plotters = {
            "plot-recovery": plot_recovery,
            "plot-triggers": plot_triggers,
            "plot-attempts": plot_attempts,
            "plot-success-time": plot_attained_oracle,
        }
        plotters[args.command](args.analysis, args.output, title=args.title)
        _print({"figure": str(args.output)})
    else:
        _print(run_experiment(args, parser))


if __name__ == "__main__":
    main()
