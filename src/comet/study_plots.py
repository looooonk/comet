"""Faceted retention figures from the shared paired analysis."""

import json
from pathlib import Path


def plot_retention_matrix(
    analysis_path: Path, output: Path, *, title: str = "Retention comparison"
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    analysis = json.loads(analysis_path.read_text())
    rows = list(analysis["conditions"].values())
    names = {"streamingllm": "StreamingLLM", "rkv": "R-KV", "agentkv": "AgentKV"}
    policies = {"never": ("#4477aa", "o"), "fixed": ("#ee7733", "s"), "dynamic": ("#228833", "^")}
    groups = sorted(
        {
            (row["condition"]["method"], row["condition"]["max_attempts"])
            for row in rows
            if row["condition"]["method"] != "full"
        }
    )
    if not groups or any(method not in names for method, _ in groups):
        raise ValueError("Retention figures need recognized compressed methods and full controls")
    signatures = [
        (
            r["condition"]["method"],
            r["condition"]["retention"],
            r["condition"]["recovery"],
            r["condition"]["max_attempts"],
        )
        for r in rows
        if r["condition"]["method"] != "full"
    ]
    if len(set(signatures)) != len(signatures):
        raise ValueError("Ambiguous duplicate compressed conditions")
    if any(row["condition"]["recovery"] not in policies for row in rows):
        raise ValueError("Unknown recovery policy")
    for _, attempts in groups:
        if not any(
            row["condition"]["method"] == "full" and row["condition"]["max_attempts"] == attempts
            for row in rows
        ):
            raise ValueError(f"Missing full-cache control with attempt ceiling {attempts}")
    reserved = any(
        row.get("reserved_budget_seconds", {}).get("value", 0)
        or row.get("attempt_status_counts", {}).get("interrupted", 0)
        for row in rows
    )
    panels = [
        ("oracle_success_rate", "Oracle success upper bound (%)", 100, "bounded_mean_ci95"),
        (
            "latency_seconds",
            "Budget-accounted time (s)" if reserved else "End-to-end time (s)",
            1,
            "ci95",
        ),
        ("mean_peak_kv_bytes", "Peak occupied KV (GiB)", 1 / 2**30, "ci95"),
        ("mean_peak_total_vram_bytes", "Peak total VRAM (GiB)", 1 / 2**30, "ci95"),
    ]
    with plt.rc_context(
        {
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.fonttype": "none",
            "savefig.dpi": 180,
        }
    ):
        height = 3.1 * len(groups) + 3.0
        fig, axes = plt.subplots(len(groups), len(panels), squeeze=False, figsize=(14, height))
        handles = {}
        for row_index, (method, attempts) in enumerate(groups):
            compressed = [
                row
                for row in rows
                if row["condition"]["method"] == method
                and row["condition"]["max_attempts"] == attempts
            ]
            controls = [
                row
                for row in rows
                if row["condition"]["method"] == "full"
                and row["condition"]["max_attempts"] == attempts
            ]
            ticks = sorted({100 * row["condition"]["retention"] for row in compressed} | {100})
            spacing = min(right - left for left, right in zip(ticks, ticks[1:]))
            offset = min(1, spacing / 5)
            margin = max(1, (100 - ticks[0]) / 12)
            for column, (metric, label, scale, interval) in enumerate(panels):
                ax = axes[row_index, column]
                missing = {}
                multiple_policies = len({row["condition"]["recovery"] for row in compressed}) > 1
                for policy, (color, marker) in policies.items():
                    series = sorted(
                        (row for row in compressed if row["condition"]["recovery"] == policy),
                        key=lambda row: row["condition"]["retention"],
                    )
                    if not series:
                        continue
                    xs, ys = [], []
                    for row in series:
                        estimate = row[metric]
                        x = 100 * row["condition"]["retention"]
                        plotted_x = x + (
                            {"never": -offset, "fixed": 0, "dynamic": offset}[policy]
                            if multiple_policies
                            else 0
                        )
                        xs.append(plotted_x)
                        ys.append(
                            estimate["value"] * scale
                            if estimate["value"] is not None
                            else float("nan")
                        )
                        if estimate["task_count"] != analysis["task_count"]:
                            missing.setdefault(policy, []).append(
                                f"{x:g}%: {estimate['task_count']}/{analysis['task_count']}"
                            )
                        if estimate["value"] is not None:
                            _interval(ax, plotted_x, estimate, interval, scale, color, offset)
                    (line,) = ax.plot(
                        xs, ys, marker=marker, color=color, linewidth=1.3, label=policy
                    )
                    handles.setdefault(policy, line)
                for index, control in enumerate(controls):
                    estimate = control[metric]
                    control_label = f"{control['condition']['id']} (N={attempts})"
                    if estimate["task_count"] != analysis["task_count"]:
                        missing[control_label] = [
                            f"{estimate['task_count']}/{analysis['task_count']}"
                        ]
                    if estimate["value"] is not None:
                        (point,) = ax.plot(
                            [100],
                            [estimate["value"] * scale],
                            marker="D" if index == 0 else "x",
                            color="#333333",
                            linestyle="none",
                        )
                        _interval(ax, 100, estimate, interval, scale, "#333333", offset)
                        handles.setdefault(control_label, point)
                ax.set(
                    title=label,
                    xlabel="KV retained (%)",
                    xticks=ticks,
                    xlim=(ticks[0] - margin, 100 + margin),
                )
                if spacing < 5:
                    ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
                    ax.set_xticks(ticks, minor=True)
                elif len(ticks) > 7:
                    ax.tick_params(axis="x", labelrotation=45)
                ax.set_ylim(bottom=-2 if metric == "oracle_success_rate" else 0)
                if metric == "oracle_success_rate":
                    ax.set_ylim(top=102)
                else:
                    ax.set_ylim(top=max(1e-9, ax.get_ylim()[1] * (1.5 if missing else 1.1)))
                ax.grid(axis="y", alpha=0.18)
                ax.set_axisbelow(True)
                if missing:
                    coverage = "\n".join(
                        f"{name}: {', '.join(values)}" for name, values in missing.items()
                    )
                    ax.text(
                        0.02,
                        0.98,
                        "Task coverage\n" + coverage,
                        transform=ax.transAxes,
                        fontsize=6.5,
                        va="top",
                        color="#7a4423",
                        bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none"},
                    )
            axes[row_index, 0].set_ylabel(f"{names[method]}\nAttempt ceiling N={attempts}")
        fig.suptitle(title, x=0.07, y=1 - 0.12 / height, ha="left", fontsize=15, fontweight="bold")
        mode = (
            "Integration diagnostic"
            if analysis.get("integration_smoke")
            else analysis.get("stage", "Run")
        )
        fig.text(
            0.07,
            1 - 0.65 / height,
            f"{mode} | {analysis['task_count']} paired tasks | "
            f"{len(analysis['replicate_seeds'])} paired seed(s)",
            color="#555555",
        )
        fig.legend(
            handles.values(),
            handles.keys(),
            loc="upper right",
            bbox_to_anchor=(0.98, 1 - 0.18 / height),
            ncol=min(5, len(handles)),
            frameon=False,
            fontsize=8,
        )
        caption = (
            "Pointwise 95% intervals: bounded task means for success; task bootstrap for time and memory.\n"
            "Full controls appear at 100%; lines connect compressed measurements only. No fitted or monotone trend.\n"
            "Policy markers are slightly offset at shared retentions. Memory panels average cell peaks across seeds/tasks.\n"
            "Occupied KV and total VRAM are distinct from reserved pool capacity."
        )
        if reserved:
            caption += "\nBudget-accounted time includes unmeasured interruption reservations; it is not purely measured latency."
        fig.text(0.07, 0.15 / height, caption, fontsize=8, color="#555555", linespacing=1.5)
        fig.subplots_adjust(
            left=0.07,
            right=0.98,
            bottom=1.45 / height,
            top=1 - 1.12 / height,
            hspace=0.42,
            wspace=0.27,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, metadata={"Creator": "COMET"})
        plt.close(fig)


def _interval(ax, x, estimate, interval, scale, color, cap_width):
    bounds = estimate[interval]
    if bounds is not None:
        lower, upper = [value * scale for value in bounds]
        ax.vlines(x, lower, upper, color=color, linewidth=1)
        ax.hlines([lower, upper], x - cap_width, x + cap_width, color=color, linewidth=1)
