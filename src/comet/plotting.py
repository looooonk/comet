"""Plot measured retention points from the shared task-level analysis."""

from __future__ import annotations

import json
from pathlib import Path


def plot_baseline(
    comparison_path: Path, output: Path, *, title: str = "Paired full-cache protocol diagnostic"
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    comparison = json.loads(comparison_path.read_text())
    if comparison.get("kind") != "paired_protocol_comparison":
        raise ValueError("Baseline plots require a validated paired protocol comparison")
    conditions = [
        value
        for value in comparison["conditions"].values()
        if value["condition"]["method"] == "full" and value["condition"]["max_attempts"] == 1
    ]
    if len(conditions) != 1:
        raise ValueError("Baseline plots require exactly one paired full-cache N=1 condition")
    rows = [conditions[0][arm] for arm in ("control", "candidate")]
    labels, colors = ["Control", "Candidate"], ["#4477aa", "#228833"]
    status_colors = {
        "completed": "#66aabb",
        "error": "#ee6677",
        "timeout": "#ccbb44",
        "context_limit": "#aa3377",
        "oom": "#ee7733",
        "interrupted": "#999999",
        "infeasible": "#332288",
        "not_started": "#dddddd",
    }
    with plt.rc_context(
        {
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.fonttype": "none",
            "savefig.dpi": 180,
        }
    ):
        fig, axes = plt.subplots(2, 2, figsize=(10, 8))
        panels = [
            (
                axes[0, 0],
                [row["oracle_success_rate"] for row in rows],
                "Task success (%)",
                100,
                "bounded_mean_ci95",
            ),
            (
                axes[1, 0],
                [row["behavior"]["error_rate"] for row in rows],
                "Mean errors per 100 saved turns",
                100,
                "bounded_mean_ci95",
            ),
            (
                axes[1, 1],
                [row["behavior"]["attempt_duration_seconds"] for row in rows],
                "Mean measured attempt duration (s)",
                1,
                "ci95",
            ),
        ]
        for ax, estimates, label, scale, interval in panels:
            for index, (estimate, color) in enumerate(zip(estimates, colors, strict=True)):
                value = estimate["value"]
                if value is None:
                    ax.text(
                        index, 0.05, "Unavailable", ha="center", transform=ax.get_xaxis_transform()
                    )
                    continue
                ax.bar(index, value * scale, color=color, width=0.55, zorder=3)
                bounds = estimate[interval]
                if bounds is not None:
                    lower, upper = [bound * scale for bound in bounds]
                    ax.vlines(index, lower, upper, color="#222222", zorder=4)
                    ax.hlines([lower, upper], index - 0.04, index + 0.04, color="#222222", zorder=4)
                ax.annotate(
                    f"{value * scale:.1f}",
                    (index, value * scale),
                    xytext=(8, 4),
                    textcoords="offset points",
                    fontsize=9,
                )
            ax.set(ylabel=label, xticks=[0, 1], xticklabels=labels, xlim=(-0.6, 1.6))
            ax.set_ylim(bottom=0)
            if scale == 100:
                ax.set_ylim(top=105)
            ax.grid(axis="y", alpha=0.18)
            ax.set_axisbelow(True)
        status_ax = axes[0, 1]
        bottoms = [0.0, 0.0]
        for status, color in status_colors.items():
            counts = [
                {**row["attempt_status_counts"], "not_started": row["zero_attempt_cells"]}
                for row in rows
            ]
            if not any(count.get(status) for count in counts):
                continue
            values = [
                100 * count.get(status, 0) / sum(count.values()) if count else 0 for count in counts
            ]
            status_ax.bar(
                [0, 1],
                values,
                bottom=bottoms,
                width=0.55,
                color=color,
                label=status.replace("_", " "),
            )
            bottoms = [bottom + value for bottom, value in zip(bottoms, values, strict=True)]
        status_ax.set(
            ylabel="Cell execution status (%)",
            xticks=[0, 1],
            xticklabels=labels,
            xlim=(-0.6, 1.6),
            ylim=(0, 105),
        )
        status_ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False, fontsize=8)
        mode = "Integration pilot" if comparison["integration_smoke"] else "Train/dev pilot"
        fig.suptitle(title, x=0.09, ha="left", fontsize=15, fontweight="bold")
        fig.text(
            0.09,
            0.93,
            f"{mode} | {comparison['task_count']} paired tasks | "
            f"{len(comparison['replicate_seeds'])} seed(s) | Full KV, N=1",
            color="#555555",
        )
        duration_coverage = "; ".join(
            f"{label}: {row['behavior']['attempt_duration_seconds']['task_count']}/{comparison['task_count']} tasks"
            for label, row in zip(labels, rows, strict=True)
        )
        error_coverage = "; ".join(
            f"{label}: {row['behavior']['error_rate']['task_count']}/{comparison['task_count']} tasks"
            for label, row in zip(labels, rows, strict=True)
        )
        reservations = [row["behavior"]["reserved_budget_seconds"] for row in rows]
        prefixes = [row["behavior"]["coverage"]["interrupted_prefixes"] for row in rows]
        caption = (
            "Pointwise 95% intervals: bounded task means for success/error rates; task bootstrap for duration.\n"
            "Completed execution can still fail evaluation. Fewer errors or shorter attempts do not establish better task performance.\n"
            f"Error-rate coverage: {error_coverage}. Measured-duration coverage: {duration_coverage}."
        )
        if any(reservations) or any(prefixes):
            caption += (
                f"\nInterrupted prefixes in error rates: {prefixes[0]} control / {prefixes[1]} candidate. "
                f"Unmeasured reserved time: {reservations[0]:.1f}s / {reservations[1]:.1f}s; excluded from duration."
            )
        fig.text(0.09, 0.035, caption, fontsize=8, color="#555555", linespacing=1.6)
        fig.subplots_adjust(left=0.09, right=0.82, bottom=0.22, top=0.88, hspace=0.35, wspace=0.35)
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, metadata={"Creator": "COMET"})
        plt.close(fig)


def plot_retention(
    analysis_path: Path, output: Path, *, title: str = "AppWorld retention pilot"
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    analysis = json.loads(analysis_path.read_text())
    rows = sorted(analysis["conditions"].values(), key=lambda row: -row["condition"]["retention"])
    conditions = [row["condition"] for row in rows]
    methods = {condition["method"] for condition in conditions if condition["method"] != "full"}
    if (
        len(methods) != 1
        or not any(condition["method"] == "full" for condition in conditions)
        or len({condition["retention"] for condition in conditions}) != len(conditions)
        or len({condition["max_attempts"] for condition in conditions}) != 1
        or any(condition["recovery"] != "never" for condition in conditions)
    ):
        raise ValueError(
            "Plot one eviction method with unique retentions, a full control, equal N and no recovery"
        )
    if any("bounded_mean_ci95" not in row["oracle_success_rate"] for row in rows):
        raise ValueError(
            "Reanalyze with task-level standard errors and bounded accuracy intervals first"
        )

    aggression = [100 * (1 - condition["retention"]) for condition in conditions]
    success_label = (
        "Task success (%)"
        if conditions[0]["max_attempts"] == 1
        else "Oracle success upper bound (%)"
    )
    interrupted = any(
        row.get("attempt_status_counts", {}).get("interrupted", 0)
        or row.get("reserved_budget_seconds", {}).get("value", 0)
        for row in rows
    )
    latency_label = (
        "Mean budget-accounted time (s)" if interrupted else "Mean end-to-end latency (s)"
    )
    panels = [
        ("oracle_success_rate", success_label, 100, "bounded_mean_ci95"),
        ("latency_seconds", latency_label, 1, "ci95"),
        ("mean_peak_kv_bytes", "Mean peak occupied KV (GiB)", 1 / 2**30, "ci95"),
    ]
    with plt.rc_context(
        {
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.fonttype": "none",
            "savefig.dpi": 180,
        }
    ):
        fig, axes = plt.subplots(1, 3, figsize=(12, 4.8))
        for ax, (metric, label, scale, interval) in zip(axes, panels, strict=True):
            points = [
                (x, row[metric])
                for x, row in zip(aggression, rows, strict=True)
                if row[metric]["value"] is not None
            ]
            xs = [x for x, _ in points]
            ys = [estimate["value"] * scale for _, estimate in points]
            ax.plot(xs, ys, "o-", color="#246b9b", linewidth=1.6, markersize=6, zorder=3)
            for x, estimate in points:
                bounds = estimate[interval]
                if bounds is not None:
                    low, high = [bound * scale for bound in bounds]
                    ax.vlines(x, low, high, color="#246b9b", linewidth=1.3)
                    ax.hlines([low, high], x - 1.5, x + 1.5, color="#246b9b", linewidth=1.3)
            ax.set(
                xlabel="KV eviction target (%)",
                ylabel=label,
                xticks=aggression,
                xlim=(-5, max(aggression) + 5),
            )
            ax.grid(axis="y", alpha=0.18)
            ax.set_axisbelow(True)
            ax.set_ylim(bottom=-2 if metric == "oracle_success_rate" else 0)
            if metric == "oracle_success_rate":
                ax.set_ylim(top=102)
            if metric == "mean_peak_kv_bytes":
                missing = [
                    row for row in rows if row[metric]["task_count"] != analysis["task_count"]
                ]
                if missing:
                    coverage = "; ".join(
                        f"{row[metric]['task_count']}/{analysis['task_count']} at "
                        f"{row['condition']['retention']:.0%} retained"
                        for row in missing
                    )
                    ax.text(
                        0.02,
                        1.02,
                        f"Memory coverage: {coverage}",
                        transform=ax.transAxes,
                        va="bottom",
                        fontsize=8,
                        color="#a04a20",
                    )
        mode = (
            "Integration pilot"
            if analysis.get("integration_smoke")
            else analysis.get("stage", "Run")
        )
        method = {"agentkv": "AgentKV", "rkv": "R-KV", "streamingllm": "StreamingLLM"}[
            next(iter(methods))
        ]
        fig.suptitle(title, x=0.07, ha="left", fontsize=15, fontweight="bold")
        fig.text(
            0.07,
            0.88,
            f"{mode} | Full KV / {method} | {analysis['task_count']} paired tasks | "
            f"{len(analysis['replicate_seeds'])} seed(s) per task | "
            f"N={conditions[0]['max_attempts']} | no recovery",
            color="#555555",
        )
        caption = (
            "Pointwise 95% intervals: conservative bounded-mean for accuracy; task bootstrap for time and KV.\n"
            "Lines connect recorded means; no fitted trend. Occupied KV includes compaction transients, not pool capacity."
        )
        if interrupted:
            caption += "\nInterrupted-cell time includes an unobserved reserved budget, not a measured duration."
        fig.text(0.07, 0.06, caption, fontsize=8, color="#555555")
        fig.subplots_adjust(left=0.07, right=0.98, bottom=0.24, top=0.79, wspace=0.33)
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, metadata={"Creator": "COMET"})
        plt.close(fig)
