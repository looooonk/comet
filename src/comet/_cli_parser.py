"""Argument definitions for the public COMET command line."""

import argparse
from pathlib import Path


def build_parser():
    parser = argparse.ArgumentParser(description="COMET experiment execution, scoring and analysis")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Validate an experiment configuration")
    validate.add_argument("config", type=Path)
    partition = commands.add_parser("partition", help="Split a frozen study by condition")
    partition.add_argument("config", type=Path)
    partition.add_argument("--output", type=Path, required=True)
    partition.add_argument("--count", type=int, required=True)
    matrix = commands.add_parser("matrix", help="Print the proposal's 29 comparison conditions")
    matrix.add_argument("config", type=Path)
    run = commands.add_parser("run", help="Run pilot, checkpoint diagnostic, or frozen evaluation")
    run.add_argument("config", type=Path)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--model-path", type=Path, required=True)
    run.add_argument("--appworld-root", type=Path, required=True)
    run.add_argument("--resume", action="store_true")
    run.add_argument(
        "--max-cells",
        type=int,
        help="Stop after this many newly completed cells; continue with --resume",
    )
    run.add_argument(
        "--integration-smoke",
        action="store_true",
        help="Allow another GPU; outputs are ineligible for final evaluation",
    )
    evaluate = commands.add_parser("evaluate", help="Score a completed run offline")
    evaluate.add_argument("run", type=Path)
    rescore = commands.add_parser(
        "rescore", help="Score a separate copy while preserving original results"
    )
    rescore.add_argument("run", type=Path)
    rescore.add_argument("--output", type=Path, required=True)
    finalize = commands.add_parser(
        "finalize", help="Finalize interrupted cells when no inference remains"
    )
    finalize.add_argument("run", type=Path)
    analyze = commands.add_parser(
        "analyze", help="Compute task-level oracle success and paired intervals"
    )
    analyze.add_argument("runs", type=Path, nargs="+")
    analyze.add_argument("--output", type=Path, required=True)
    analyze.add_argument("--bootstrap-samples", type=int, default=2000)
    analyze.add_argument("--seed", type=int, default=0)
    analyze.add_argument(
        "--study-config",
        type=Path,
        help="Frozen parent configuration for a complete set of condition partitions",
    )
    budget_sweep = commands.add_parser(
        "analyze-budget-sweep", help="Compare independently rerun pilot budgets"
    )
    budget_sweep.add_argument("runs", type=Path, nargs="+")
    budget_sweep.add_argument("--output", type=Path, required=True)
    budget_sweep.add_argument("--bootstrap-samples", type=int, default=2000)
    budget_sweep.add_argument("--seed", type=int, default=0)
    budget_plot = commands.add_parser(
        "plot-budget-sweep", help="Plot independently rerun budget endpoints"
    )
    budget_plot.add_argument("analysis", type=Path)
    budget_plot.add_argument("--output", type=Path, required=True)
    budget_plot.add_argument("--title", default="Success versus independently rerun budget")
    histories = commands.add_parser(
        "analyze-histories", help="Validate and summarize matched-history measurements"
    )
    histories.add_argument("runs", type=Path, nargs="+")
    histories.add_argument("--output", type=Path, required=True)
    history_plot = commands.add_parser(
        "plot-histories", help="Plot one measured history-cost metric by method"
    )
    history_plot.add_argument("analysis", type=Path)
    history_plot.add_argument("--output", type=Path, required=True)
    history_plot.add_argument(
        "--metric",
        required=True,
        choices=(
            "occupied-kv",
            "peak-kv",
            "reserved-pool",
            "total-vram",
            "peak-vram",
            "decode-peak-vram",
            "prefill-throughput",
            "decode-throughput",
            "prefill-time",
            "decode-time",
            "selection",
            "compaction",
            "instrumented-time",
        ),
    )
    history_plot.add_argument("--history", dest="history_id")
    history_plot.add_argument(
        "--retention",
        type=float,
        choices=(0.8, 0.5, 0.25),
        help="Compare methods at one retention on shared axes, including full KV",
    )
    history_plot.add_argument("--title", default="Matched-history cost")
    compare = commands.add_parser(
        "compare-protocol", help="Compare explicitly declared paired protocol arms"
    )
    compare.add_argument("control", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument(
        "--protocol-field", choices=("prompt", "agent"), action="append", required=True
    )
    compare.add_argument("--output", type=Path, required=True)
    compare.add_argument("--bootstrap-samples", type=int, default=2000)
    compare.add_argument("--seed", type=int, default=0)
    baseline = commands.add_parser(
        "plot-baseline", help="Plot protocol success, failure, errors and duration"
    )
    baseline.add_argument("comparison", type=Path)
    baseline.add_argument("--output", type=Path, required=True)
    baseline.add_argument("--title", default="AppWorld baseline diagnostic")
    retention = commands.add_parser(
        "plot-retention-matrix", help="Facet retention by method, recovery and attempt limit"
    )
    retention.add_argument("analysis", type=Path)
    retention.add_argument("--output", type=Path, required=True)
    retention.add_argument("--title", default="Retention comparison")
    resources = commands.add_parser(
        "plot-resources", help="Plot resource costs against measured KV removal"
    )
    resources.add_argument("analysis", type=Path)
    resources.add_argument("--output", type=Path, required=True)
    resources.add_argument("--policy", choices=("never", "fixed", "dynamic"), default="never")
    resources.add_argument("--title", default="Compaction resource costs")
    for command, help_text, title in (
        (
            "plot-aggressivity",
            "Plot measured KV removal against single/oracle task success",
            "Compaction and task success",
        ),
        (
            "plot-recovery",
            "Plot paired recovery effects, cost and admission",
            "Recovery comparison",
        ),
        (
            "plot-triggers",
            "Plot observed trigger decisions and paired effects",
            "Recovery trigger observations",
        ),
        (
            "plot-attempts",
            "Plot first/oracle success, attempts and observed cost",
            "Attempt allocation comparison",
        ),
        (
            "plot-success-time",
            "Plot attained oracle success along executed schedules",
            "Attained oracle success over time",
        ),
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
    return parser
