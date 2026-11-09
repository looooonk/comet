"""Focused measured-length figures for validated matched-history analyses."""
from __future__ import annotations

from pathlib import Path

from comet.artifacts import read_json
from comet.history_analysis import METRICS

PLOT_METRICS = {
    "occupied-kv": "occupied_kv_bytes", "peak-kv": "peak_occupied_kv_bytes",
    "reserved-pool": "reserved_kv_pool_bytes", "total-vram": "total_vram_bytes",
    "peak-vram": "peak_total_vram_bytes", "decode-peak-vram": "decode_peak_total_vram_bytes",
    "prefill-throughput": "prefill_tokens_per_second",
    "decode-throughput": "decode_tokens_per_second", "prefill-time": "prefill_pass_seconds",
    "decode-time": "decode_pass_seconds", "selection": "selection_seconds",
    "compaction": "compaction_seconds", "instrumented-time": "instrumented_pass_seconds",
}
_METHODS = {"streamingllm": "StreamingLLM", "rkv": "R-KV", "agentkv": "AgentKV"}
_COLORS = {1.0: "#555555", 0.8: "#4477aa", 0.5: "#228833", 0.25: "#ee7733"}
_METHOD_COLORS = {"full": "#555555", "streamingllm": "#4477aa", "rkv": "#ee7733", "agentkv": "#228833"}


def plot_histories(analysis_path: Path, output: Path, *, metric: str,
                   history_id: str | None = None, title: str = "Matched-history cost",
                   retention: float | None = None) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    analysis = read_json(analysis_path)
    if analysis.get("kind") != "matched_history_analysis" or analysis.get("schema_version") != 1:
        raise ValueError("History plots require validated matched-history analysis")
    if metric not in PLOT_METRICS:
        raise ValueError(f"Unknown history metric: {metric}")
    if retention is not None and retention not in {0.8, 0.5, 0.25}:
        raise ValueError("Select compressed retention 0.8, 0.5 or 0.25")
    histories = analysis["summary"]["histories"]
    if history_id is None:
        if len(histories) != 1:
            raise ValueError("Select one --history when analysis contains multiple source histories")
        history_id = histories[0]
    if history_id not in histories:
        raise ValueError("Unknown history identity")
    key = PLOT_METRICS[metric]
    phase, label, scale = METRICS[key]
    points = [point for point in analysis["points"] if point["history_id"] == history_id]
    if any(key not in point["metrics"] for point in points):
        raise ValueError("Re-run analyze-histories to include the requested metric")
    lengths = sorted({point["logical_length"] for point in points})
    if not lengths:
        raise ValueError("History contains no declared measurements")
    by_condition = {(point["method"], point["retention"], point["logical_length"]): point
                    for point in points}
    statuses = {}
    selected_cells = [cell for cell in analysis["cells"] if cell["history_id"] == history_id]
    if retention is not None:
        selected_cells = [cell for cell in selected_cells if
                          (cell["method"] == "full" and cell["retention"] == 1)
                          or cell["retention"] == retention]
    for cell in selected_cells:
        statuses[cell["status"]] = statuses.get(cell["status"], 0) + 1
    coverage = sum(cell["metrics"][key]["value"] is not None for cell in selected_cells)
    if retention is None:
        panels = [(label, [("full" if fraction == 1 else method, fraction, color)
                           for fraction, color in _COLORS.items()])
                  for method, label in _METHODS.items()]
        legend_items = [(color, "Full KV" if fraction == 1 else f"{fraction:.0%} retained")
                        for fraction, color in _COLORS.items()]
    else:
        panels = [(f"Compressed conditions at {retention:.0%} retention",
                   [(method, 1.0 if method == "full" else retention, color)
                    for method, color in _METHOD_COLORS.items()])]
        legend_items = [(color, "Full KV" if method == "full" else _METHODS[method])
                        for method, color in _METHOD_COLORS.items()]
    with plt.rc_context({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "svg.fonttype": "none", "savefig.dpi": 180}):
        fig, grid = plt.subplots(1, len(panels), figsize=(12.4, 5.2), sharex=True, sharey=True, squeeze=False)
        axes = grid[0]
        for ax, (panel_label, series) in zip(axes, panels, strict=True):
            for lane, (selected_method, fraction, color) in enumerate(series):
                values = []
                for length in lengths:
                    point = by_condition.get((selected_method, fraction, length))
                    estimate = point["metrics"][key] if point else None
                    if estimate is None:
                        values.append(float("nan"))
                        ax.plot(length, 0.025 + lane * 0.045, "x", color=color,
                                transform=ax.get_xaxis_transform(), clip_on=False)
                        continue
                    value = estimate["median"]
                    values.append(value * scale if value is not None else float("nan"))
                    if value is not None:
                        raw = [observed * scale for observed in estimate["values"]]
                        ax.scatter([length] * len(raw), raw, s=24, facecolors="none",
                                   edgecolors=color, alpha=0.55, zorder=3)
                        ax.vlines(length, estimate["minimum"] * scale, estimate["maximum"] * scale,
                                  color=color, linewidth=1.4, alpha=0.8, zorder=2)
                    failed = sum(count for status, count in point["cell_status_counts"].items()
                                 if status != "completed")
                    if estimate["observed"] < estimate["expected"] or failed:
                        y = 0.025 + lane * 0.045
                        ax.plot(length, y, "x", color=color, transform=ax.get_xaxis_transform())
                        ax.annotate(f"{estimate['observed']}/{estimate['expected']}",
                                    (length, y), xycoords=ax.get_xaxis_transform(),
                                    xytext=(4, 0), textcoords="offset points", color=color,
                                    fontsize=7, va="center")
                ax.plot(lengths, values, marker="o", markersize=4, color=color,
                        linewidth=1.4, linestyle="-" if len(lengths) > 1 else "none", zorder=4)
            ax.set_title(panel_label, fontsize=11, pad=10)
            ax.set_xlabel("Logical history length (tokens)")
            rotation = 30 if len(panels) > 1 and len(lengths) > 3 else 0
            ax.set_xticks(lengths, [f"{length:,}" for length in lengths], rotation=rotation)
            ax.grid(axis="y", alpha=0.18)
            ax.set_axisbelow(True)
            if len(lengths) == 1:
                ax.set_xlim(lengths[0] * 0.85, lengths[0] * 1.15)
            else:
                margin = (max(lengths) - min(lengths)) * 0.07
                ax.set_xlim(min(lengths) - margin, max(lengths) + margin)
        axes[0].set_ylim(bottom=0)
        axes[0].set_ylabel(label)
        legend = [Line2D([0], [0], color=color, marker="o", markersize=4, label=legend_label)
                  for color, legend_label in legend_items]
        fig.legend(handles=legend, loc="upper right", bbox_to_anchor=(0.98, 0.91),
                   ncol=4, frameon=False, fontsize=9)
        fig.suptitle(title, x=0.07, ha="left", fontsize=15, fontweight="bold")
        runtime = analysis.get("runtime") or {}
        prefix = f"{runtime.get('model', 'Unverified model')} | {runtime.get('device_name', 'Unverified device')}"
        detail = "Single logical length; no length trend" if len(lengths) == 1 else "Lines connect measured medians; no fitted trend"
        fig.text(0.07, 0.91, prefix, fontsize=9, color="#555555")
        fig.text(0.07, 0.86, f"{history_id} | {phase} pass | {detail}", fontsize=9, color="#555555")
        caption = (
            f"Covered observations: {coverage}/{len(selected_cells)}. Cell status: "
            + ", ".join(f"{status.replace('_', ' ')} {count}" for status, count in sorted(statuses.items()))
            + ".\nOpen points: all recorded repetitions; solid points: medians; vertical ranges: observed min-max, not confidence intervals."
            + ("\nFull control is repeated in each facet. " if retention is None else
               f"\nFull control and all three methods at {retention:.0%} retention. ")
            + "Crosses flag incomplete cells or metric coverage; labels show covered/expected observations."
        )
        if phase == "instrumented":
            caption += "\nSelection/compaction sum the whole prefix-plus-continuation replay, not per-token rates; nested costs are not added again."
        elif "throughput" in metric:
            caption += "\nNative loop timing includes eviction/output processing; excludes surrounding scheduling, reset and verification."
        elif metric in {"prefill-time", "decode-time"}:
            caption += "\nWhole-pass elapsed includes reset, inference, verification and cleanup; model setup is recorded separately."
        elif metric == "decode-peak-vram":
            caption += "\nPeak covers the ordinary prefix-plus-continuation pass, including transient and allocator-reserved use; it is not KV occupancy."
        else:
            caption += "\nMemory is measured at the prefill prefix; occupied KV, transient peaks, reserved pool and total VRAM are distinct metrics."
        fig.text(0.07, 0.045, caption, fontsize=8, color="#555555", linespacing=1.5)
        fig.subplots_adjust(left=0.07, right=0.98, bottom=0.32, top=0.76, wspace=0.18)
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, metadata={"Creator": "COMET"})
        plt.close(fig)
