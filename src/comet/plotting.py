"""Plot measured retention points from the shared task-level analysis."""

from __future__ import annotations

import json
from pathlib import Path


def plot_retention(analysis_path: Path, output: Path, *, title: str = "AppWorld retention pilot") -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    analysis = json.loads(analysis_path.read_text())
    rows = sorted(analysis["conditions"].values(), key=lambda row: -row["condition"]["retention"])
    conditions = [row["condition"] for row in rows]
    methods = {condition["method"] for condition in conditions if condition["method"] != "full"}
    if (len(methods) != 1 or not any(condition["method"] == "full" for condition in conditions)
            or len({condition["retention"] for condition in conditions}) != len(conditions)
            or len({condition["max_attempts"] for condition in conditions}) != 1
            or any(condition["recovery"] != "never" for condition in conditions)):
        raise ValueError("Plot one eviction method with unique retentions, a full control, equal N and no recovery")
    if any("bounded_mean_ci95" not in row["oracle_success_rate"] for row in rows):
        raise ValueError("Reanalyze with task-level standard errors and bounded accuracy intervals first")

    aggression = [100 * (1 - condition["retention"]) for condition in conditions]
    success_label = "Task success (%)" if conditions[0]["max_attempts"] == 1 else "Oracle success upper bound (%)"
    interrupted = any(row.get("attempt_status_counts", {}).get("interrupted", 0) for row in rows)
    latency_label = "Mean budget-accounted time (s)" if interrupted else "Mean end-to-end latency (s)"
    panels = [
        ("oracle_success_rate", success_label, 100, "bounded_mean_ci95"),
        ("latency_seconds", latency_label, 1, "ci95"),
        ("mean_peak_kv_bytes", "Mean peak occupied KV (GiB)", 1 / 2**30, "ci95"),
    ]
    with plt.rc_context({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "svg.fonttype": "none", "savefig.dpi": 180}):
        fig, axes = plt.subplots(1, 3, figsize=(12, 4.8))
        for ax, (metric, label, scale, interval) in zip(axes, panels, strict=True):
            points = [(x, row[metric]) for x, row in zip(aggression, rows, strict=True)
                      if row[metric]["value"] is not None]
            xs = [x for x, _ in points]
            ys = [estimate["value"] * scale for _, estimate in points]
            ax.plot(xs, ys, "o-", color="#246b9b", linewidth=1.6, markersize=6, zorder=3)
            for x, estimate in points:
                bounds = estimate[interval]
                if bounds is not None:
                    low, high = [bound * scale for bound in bounds]
                    ax.vlines(x, low, high, color="#246b9b", linewidth=1.3)
                    ax.hlines([low, high], x - 1.5, x + 1.5, color="#246b9b", linewidth=1.3)
            ax.set(xlabel="KV eviction target (%)", ylabel=label,
                   xticks=aggression, xlim=(-5, max(aggression) + 5))
            ax.grid(axis="y", alpha=0.18)
            ax.set_axisbelow(True)
            ax.set_ylim(bottom=-2 if metric == "oracle_success_rate" else 0)
            if metric == "oracle_success_rate":
                ax.set_ylim(top=102)
            if metric == "mean_peak_kv_bytes":
                missing = [row for row in rows if row[metric]["task_count"] != analysis["task_count"]]
                if missing:
                    coverage = "; ".join(
                        f"{row[metric]['task_count']}/{analysis['task_count']} at "
                        f"{row['condition']['retention']:.0%} retained" for row in missing
                    )
                    ax.text(0.02, 1.02, f"Memory coverage: {coverage}", transform=ax.transAxes,
                            va="bottom", fontsize=8, color="#a04a20")
        mode = "Integration pilot" if analysis.get("integration_smoke") else analysis.get("stage", "Run")
        method = {"agentkv": "AgentKV", "rkv": "R-KV", "streamingllm": "StreamingLLM"}[next(iter(methods))]
        fig.suptitle(title, x=0.07, ha="left", fontsize=15, fontweight="bold")
        fig.text(0.07, 0.88,
                 f"{mode} | Full KV / {method} | {analysis['task_count']} paired tasks | "
                 f"{len(analysis['replicate_seeds'])} seed(s) per task | "
                 f"N={conditions[0]['max_attempts']} | no recovery", color="#555555")
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
