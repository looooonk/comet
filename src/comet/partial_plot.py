"""Plot provisional study coverage without filling missing comparisons."""

import argparse
import json
import math
from pathlib import Path


def plot_partial_study(directory: Path, output: Path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    snapshot = json.loads((directory / "snapshot.json").read_text())
    analysis = json.loads((directory / "analysis.json").read_text())
    if not analysis.get("partial_study", {}).get("provisional"):
        raise ValueError("Use the ordinary plotter for a complete study.")
    declared = snapshot["study"]["conditions"]
    rows = analysis["conditions"]
    methods = {"streamingllm": ("StreamingLLM", "#4477aa", "o"),
               "rkv": ("R-KV", "#cc6677", "s"), "agentkv": ("AgentKV", "#228833", "^")}
    metrics = [("single_attempt_success_rate", "First-attempt success"),
               ("oracle_success_rate", "Oracle best-of-two success")]
    with plt.rc_context({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False}):
        figure, axes = plt.subplots(1, 2, figsize=(11.5, 5.4), sharey=True)
        for axis, (metric, title) in zip(axes, metrics, strict=True):
            for method, (label, color, marker) in methods.items():
                points = sorted((100 * (1 - c["retention"]), c["id"])
                                for c in declared if c["method"] == method)
                xs = [x for x, _ in points]
                ys = [100 * rows[name][metric]["value"] if name in rows else math.nan
                      for _, name in points]
                axis.plot(xs, ys, color=color, marker=marker, label=label, linewidth=1.5)
                for x, name in points:
                    if name in rows:
                        low, high = rows[name][metric]["ci95"]
                        axis.vlines(x, 100 * low, 100 * high, color=color, alpha=0.3, linewidth=2)
            controls = [c for c in declared if c["method"] == "full" and c["id"] in rows
                        and (metric == "single_attempt_success_rate" or c["max_attempts"] == 2)]
            if controls:
                control = min(controls, key=lambda c: c["max_attempts"])
                estimate = rows[control["id"]][metric]
                axis.plot(0, 100 * estimate["value"], "D", color="#333333",
                          label=f"Full cache (N={control['max_attempts']})")
                axis.vlines(0, *(100 * value for value in estimate["ci95"]), color="#333333", alpha=0.3)
            else:
                axis.text(0.03, 0.95, "Full-cache N=2 control pending", transform=axis.transAxes,
                          va="top", fontsize=9, color="#666666")
            axis.set(title=title, xlabel="Eligible KV entries removed (%)", xlim=(-3, 78),
                     xticks=[0, 10, 20, 30, 40, 50, 60, 70, 75], ylim=(-3, 103))
            axis.grid(axis="y", alpha=0.2)
            axis.legend(loc="upper right", fontsize=9, frameon=False)
        axes[0].set_ylabel("Task success (%)")
        figure.suptitle(f"PROVISIONAL: {analysis['task_count']} paired tasks per point", fontsize=15)
        figure.text(
            0.5, 0.035,
            f"{len(rows)} of {len(declared)} conditions fully scored. Missing points are pending, not zero.\n"
            "Only full task sets are plotted; failures stay in the denominator. Pointwise paired-task bootstrap 95% intervals.\n"
            "Oracle assumes perfect attempt selection. Zero-width intervals at 0% or 100% do not establish certainty.",
            ha="center", fontsize=9,
        )
        figure.tight_layout(rect=(0, 0.14, 1, 0.93))
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=180, bbox_inches="tight")
        plt.close(figure)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    plot_partial_study(args.directory, args.output)
