"""Measured compaction-success curves from the shared task-paired analysis."""

import json
from pathlib import Path


def aggressivity_series(analysis):
    rows = list(analysis["conditions"].values())
    compressed = [row for row in rows if row["condition"]["method"] != "full"]
    ceilings = {row["condition"]["max_attempts"] for row in compressed}
    if len(ceilings) != 1:
        raise ValueError("Use one shared compressed attempt ceiling per aggressivity figure")
    ceiling = ceilings.pop()
    controls = [row for row in rows if row["condition"]["method"] == "full"
                and row["condition"]["max_attempts"] == ceiling]
    if len(controls) != 1:
        raise ValueError("Require one full-cache control at the shared attempt ceiling")
    series = {}
    for row in compressed:
        condition = row["condition"]
        key = (condition["recovery"], condition["method"])
        points = series.setdefault(key, [])
        x = 100 * (1 - condition["retention"])
        if any(abs(previous[0] - x) < 1e-8 for previous in points):
            raise ValueError("Ambiguous duplicate measured retention condition")
        points.append((x, row))
    return controls[0], {key: sorted(points) for key, points in series.items()}, ceiling


def plot_aggressivity(analysis_path: Path, output: Path, *, title="Compaction and task success"):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    analysis = json.loads(analysis_path.read_text())
    control, series, ceiling = aggressivity_series(analysis)
    policies = [policy for policy in ("never", "fixed", "dynamic")
                if any(key[0] == policy for key in series)]
    labels = {"never": "No recovery", "fixed": "Fixed tool-count recovery",
              "dynamic": "Context/tool-count recovery"}
    methods = {"streamingllm": ("StreamingLLM", "#4477aa", "o"),
               "rkv": ("R-KV", "#cc6677", "s"), "agentkv": ("AgentKV", "#228833", "^")}
    metrics = [("single_attempt_success_rate", "Single-attempt task success (%)"),
               ("oracle_success_rate", "Oracle best-of-N success (%)")]
    with plt.rc_context({"font.size": 10, "svg.fonttype": "none", "savefig.dpi": 300,
                         "axes.spines.top": False, "axes.spines.right": False}):
        figure, axes = plt.subplots(2, len(policies), squeeze=False, sharey=True,
                                   figsize=(4.2 * len(policies), 7.4))
        handles = {}
        for column, policy in enumerate(policies):
            for row_index, (metric, ylabel) in enumerate(metrics):
                axis = axes[row_index, column]
                for method, (name, color, marker) in methods.items():
                    if (policy, method) not in series:
                        continue
                    points = [(0, control), *series[policy, method]]
                    xs = [point[0] for point in points]
                    ys = [100 * point[1][metric]["value"] for point in points]
                    line, = axis.plot(xs, ys, color=color, marker=marker, linewidth=1.5, label=name)
                    handles[name] = line
                    for x, measured in points[1:]:
                        estimate = measured[metric]
                        if estimate["ci95"] is not None:
                            low, high = (100 * value for value in estimate["ci95"])
                            axis.vlines(x, low, high, color=color, alpha=0.3, linewidth=2)
                estimate = control[metric]
                point, = axis.plot(0, 100 * estimate["value"], "D", color="#333333", label="Full cache")
                handles["Full cache"] = point
                if estimate["ci95"] is not None:
                    axis.vlines(0, *(100 * value for value in estimate["ci95"]), color="#333333", alpha=0.35)
                ticks = sorted({0, *(x for key, points in series.items() if key[0] == policy for x, _ in points)})
                axis.set(xlabel="Eligible KV entries removed (%)", ylabel=ylabel if column == 0 else "",
                         xticks=ticks, ylim=(-3, 103), xlim=(-3, max(ticks) + 3))
                if len(ticks) > 7:
                    axis.tick_params(axis="x", labelrotation=45)
                if row_index == 0:
                    axis.set_title(labels[policy])
                axis.grid(axis="y", alpha=0.2)
        figure.suptitle(title, fontsize=14)
        figure.legend(handles.values(), handles.keys(), loc="lower center", ncol=4,
                      bbox_to_anchor=(0.5, 0.075), frameon=False)
        figure.text(0.5, 0.025,
                    f"{analysis['task_count']} paired tasks; N <= {ceiling}. Pointwise task-bootstrap 95% intervals.\n"
                    "Oracle assumes perfect outcome selection. Lines join measured points; all failures are retained.\n"
                    "Degenerate bootstrap intervals at 0% or 100% do not establish population certainty.",
                    ha="center", fontsize=8)
        figure.tight_layout(rect=(0, 0.14, 1, 0.95))
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, bbox_inches="tight")
        plt.close(figure)
