"""Overlay a corrective cohort on the original grid without replacing observations."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from comet.aggressivity_plots import aggressivity_series

METHODS = {
    "streamingllm": ("StreamingLLM", "#4477aa", "o"),
    "rkv": ("R-KV", "#cc6677", "s"),
    "agentkv": ("AgentKV", "#228833", "^"),
}


def plot_comparison(original_path, corrective_path, output, y_max=50):
    original = json.loads(original_path.read_text())
    corrective = json.loads(corrective_path.read_text())
    for field in ("tasks", "replicate_seeds", "stage", "integration_smoke"):
        if original[field] != corrective[field]:
            raise ValueError(f"The cohorts must match on {field}")
    for name, row in corrective["conditions"].items():
        if row["condition"] != original["conditions"][name]["condition"]:
            raise ValueError(f"Changed condition settings for {name}")

    cohorts = [aggressivity_series(data) for data in (original, corrective)]
    if cohorts[0][2] != cohorts[1][2]:
        raise ValueError("The cohorts must share the same attempt ceiling")
    if any(policy != "never" for _, series, _ in cohorts for policy, _ in series):
        raise ValueError("This comparison shows the no-recovery grid only")

    metrics = [
        ("single_attempt_success_rate", "First-attempt success"),
        ("oracle_success_rate", "Oracle best-of-N success"),
    ]
    ticks = sorted(
        {0, *(x for _, series, _ in cohorts for points in series.values() for x, _ in points)}
    )
    with plt.rc_context({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False}):
        figure, axes = plt.subplots(1, 2, figsize=(13, 6.8), sharey=True)
        for axis, (metric, title) in zip(axes, metrics, strict=True):
            for cohort_index, (control, series, _) in enumerate(cohorts):
                repaired = cohort_index == 1
                alpha = 1.0 if repaired else 0.48
                for method, (_, color, marker) in METHODS.items():
                    if ("never", method) not in series:
                        continue
                    points = [(0, control), *series["never", method]]
                    axis.plot(
                        [x for x, _ in points],
                        [100 * row[metric]["value"] for _, row in points],
                        color=color,
                        linestyle="-" if repaired else "--",
                        linewidth=2.2 if repaired else 1.4,
                        alpha=alpha,
                        marker=marker,
                        markersize=8 if method == "rkv" else 7,
                        markerfacecolor=color if repaired else "white",
                        markeredgewidth=1.2,
                        zorder=4 if repaired else 2,
                    )
                    for x, row in points[1:]:
                        low, high = row[metric]["ci95"]
                        axis.vlines(
                            x,
                            100 * low,
                            100 * high,
                            color=color,
                            alpha=0.38 if repaired else 0.13,
                            linewidth=1.8,
                        )
                estimate = control[metric]
                axis.plot(
                    0,
                    100 * estimate["value"],
                    marker="D",
                    markersize=8,
                    color="#333333",
                    markerfacecolor="#333333" if repaired else "white",
                    alpha=alpha,
                    zorder=5,
                )
                axis.vlines(
                    0,
                    *(100 * value for value in estimate["ci95"]),
                    color="#333333",
                    alpha=0.38 if repaired else 0.13,
                )

            # Preserve the separately measured original N=1 control as an unconnected point.
            single_controls = [
                row
                for row in original["conditions"].values()
                if row["condition"]["method"] == "full" and row["condition"]["max_attempts"] == 1
            ]
            for row in single_controls:
                axis.plot(
                    0,
                    100 * row[metric]["value"],
                    marker="x",
                    color="#777777",
                    markersize=8,
                    markeredgewidth=1.6,
                    zorder=6,
                )
                axis.vlines(
                    0, *(100 * value for value in row[metric]["ci95"]), color="#777777", alpha=0.13
                )

            axis.set(
                title=title,
                xlabel="Eligible attention KV removed (%)",
                xlim=(-3, max(ticks) + 3),
                ylim=(0, y_max),
                xticks=ticks,
            )
            axis.grid(axis="y", alpha=0.18)
            upper = axis.secondary_xaxis("top", functions=(lambda x: 100 - x, lambda x: 100 - x))
            upper.set_xticks([100 - x for x in ticks])
            upper.set_xlabel("KV retention (%)", labelpad=8)
            upper.spines["top"].set_visible(False)
            axis.set_title(title, pad=65, fontsize=13)
        axes[0].set_ylabel("Tasks solved (%)")

        old = original["conditions"]["agentkv_90_never"]["oracle_success_rate"]["value"] * 100
        new = corrective["conditions"]["agentkv_90_never"]["oracle_success_rate"]["value"] * 100
        axes[1].annotate(
            f"AgentKV at 90% retention: {old:g}% → {new:g}%",
            xy=(10, new),
            xytext=(31, y_max * 0.84),
            fontsize=10,
            color="#176b29",
            arrowprops={"arrowstyle": "->", "color": "#176b29", "lw": 1.2},
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.88},
        )
        method_handles = [
            Line2D([], [], color=color, marker=marker, label=name)
            for name, color, marker in METHODS.values()
        ]
        method_handles.extend(
            [
                Line2D(
                    [], [], color="#333333", marker="D", linestyle="none", label="Full cache N=2"
                ),
                Line2D(
                    [],
                    [],
                    color="#777777",
                    marker="x",
                    linestyle="none",
                    label="Full cache N=1 (original)",
                ),
            ]
        )
        cohort_handles = [
            Line2D(
                [],
                [],
                color="#666666",
                marker="o",
                markerfacecolor="white",
                linestyle="--",
                alpha=0.6,
                label="Original grid",
            ),
            Line2D(
                [],
                [],
                color="#333333",
                marker="o",
                linewidth=2.2,
                label="Corrective replication (five points)",
            ),
        ]
        figure.legend(
            handles=method_handles,
            loc="lower center",
            ncol=5,
            bbox_to_anchor=(0.5, 0.17),
            frameon=False,
            fontsize=10,
        )
        figure.legend(
            handles=cohort_handles,
            loc="lower center",
            ncol=2,
            bbox_to_anchor=(0.5, 0.115),
            frameon=False,
            fontsize=10,
        )
        figure.suptitle(
            "Compression and task success: full grid with corrective results", fontsize=17, y=0.99
        )
        figure.text(
            0.5,
            0.025,
            "50 tasks per condition per cohort · seed 17 · 120-second shared budget · no recovery\n"
            "Pointwise paired-task bootstrap 95% intervals. All failures retained; cohorts are not pooled or spliced.\n"
            "Storage timing differs across runs. Oracle selection is an upper bound; zero-width intervals do not establish certainty.",
            ha="center",
            fontsize=9,
            linespacing=1.45,
        )
        figure.subplots_adjust(left=0.07, right=0.985, top=0.75, bottom=0.30, wspace=0.13)
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=220, bbox_inches="tight")
        plt.close(figure)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("corrective", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--y-max", type=int, choices=(50, 100), default=50)
    args = parser.parse_args()
    plot_comparison(args.original, args.corrective, args.output, args.y_max)
