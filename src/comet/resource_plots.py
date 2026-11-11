"""Resource costs at the measured compaction points."""

import json
import math
from pathlib import Path

from comet.aggressivity_plots import aggressivity_series


def resource_value(row, metric, cells):
    if metric in {
        "latency_seconds",
        "actual_attempts",
        "mean_peak_kv_bytes",
        "mean_peak_total_vram_bytes",
    }:
        return row[metric]["value"], row[metric]["ci95"]
    if metric == "recovery_seconds":
        recovery = row["recovery"]
        value = 0.0 if recovery["requested_count"] == 0 else recovery["recorded_seconds"]["value"]
    else:
        value = row["metrics"][metric]["value"]
    if value is not None and metric != "decode_throughput":
        value /= cells
    return value, None


def plot_resources(
    analysis_path: Path, output: Path, *, policy="never", title="Compaction resource costs"
):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    analysis = json.loads(analysis_path.read_text())
    control, series, ceiling = aggressivity_series(analysis)
    selected = {
        method: points for (recovery, method), points in series.items() if recovery == policy
    }
    if not selected:
        raise ValueError("No measured conditions for the selected recovery policy")
    cells = analysis["task_count"] * len(analysis["replicate_seeds"])
    panels = [
        ("latency_seconds", "Mean cell latency (s)", 1),
        ("actual_attempts", "Mean attempts per cell", 1),
        ("mean_peak_kv_bytes", "Mean cell peak occupied KV (MiB)", 1 / 2**20),
        ("mean_peak_total_vram_bytes", "Mean cell peak total VRAM (GiB)", 1 / 2**30),
        ("decode_throughput", "Decode throughput (tokens/s)", 1),
        ("estimated_flops", "Estimated TFLOPs per cell", 1 / 1e12),
        ("compaction_seconds", "Compaction seconds per cell", 1),
        ("recovery_seconds", "Recovery seconds per cell", 1),
    ]
    names = {
        "streamingllm": ("StreamingLLM", "#4477aa", "o"),
        "rkv": ("R-KV", "#cc6677", "s"),
        "agentkv": ("AgentKV", "#228833", "^"),
    }
    with plt.rc_context(
        {
            "font.size": 9,
            "svg.fonttype": "none",
            "savefig.dpi": 300,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    ):
        figure, axes = plt.subplots(2, 4, figsize=(15, 7.8))
        handles = {}
        for axis, (metric, label, scale) in zip(axes.flat, panels, strict=True):
            for method, points in selected.items():
                name, color, marker = names[method]
                measured = [(0, control), *points]
                values = [resource_value(row, metric, cells) for _, row in measured]
                xs = [x for x, _ in measured]
                ys = [value * scale if value is not None else math.nan for value, _ in values]
                (line,) = axis.plot(xs, ys, color=color, marker=marker, linewidth=1.3, label=name)
                handles[name] = line
                for x, (value, interval) in zip(xs[1:], values[1:], strict=True):
                    if value is not None and interval is not None:
                        axis.vlines(
                            x, *(bound * scale for bound in interval), color=color, alpha=0.3
                        )
            value, interval = resource_value(control, metric, cells)
            if value is not None:
                (point,) = axis.plot(0, value * scale, "D", color="#333333", label="Full cache")
                handles["Full cache"] = point
                if interval is not None:
                    axis.vlines(
                        0, *(bound * scale for bound in interval), color="#333333", alpha=0.3
                    )
            ticks = sorted({0, *(x for points in selected.values() for x, _ in points)})
            axis.set(title=label, xlabel="Eligible KV entries removed (%)", xticks=ticks)
            axis.set_ylim(bottom=0)
            if len(ticks) > 7:
                axis.tick_params(axis="x", labelrotation=45)
            axis.grid(axis="y", alpha=0.2)
        figure.suptitle(f"{title} | recovery: {policy}", fontsize=14)
        figure.legend(
            handles.values(),
            handles.keys(),
            loc="lower center",
            ncol=4,
            bbox_to_anchor=(0.5, 0.075),
            frameon=False,
        )
        figure.text(
            0.5,
            0.02,
            f"{analysis['task_count']} tasks; {len(analysis['replicate_seeds'])} seed(s); N <= {ceiling}. "
            "Pointwise task-bootstrap intervals for latency, attempts and memory.\n"
            "Throughput is a ratio of sums. FLOPs, compaction and recovery costs use recorded sums per cell; missing data remain missing.\n"
            "FLOPs are estimates; exclusions and measurement coverage are in the analysis. Occupied KV excludes recurrent state; no reserved KV pool.",
            ha="center",
            fontsize=8,
        )
        figure.tight_layout(rect=(0, 0.14, 1, 0.94))
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, bbox_inches="tight")
        plt.close(figure)
