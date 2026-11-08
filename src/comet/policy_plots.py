"""Recovery, trigger and attempt figures from the shared offline analysis."""

from __future__ import annotations

import json
import textwrap
from collections import defaultdict
from pathlib import Path

NAMES = {"full": "Full KV", "streamingllm": "StreamingLLM", "rkv": "R-KV", "agentkv": "AgentKV"}
COLORS = {"never": "#4477aa", "fixed": "#ee7733", "dynamic": "#228833"}


def _load(path):
    analysis = json.loads(Path(path).read_text())
    rows = list(analysis["conditions"].values())
    signatures = [(row["condition"]["method"], row["condition"]["retention"],
                   row["condition"]["recovery"], row["condition"]["max_attempts"]) for row in rows]
    if len(set(signatures)) != len(signatures):
        raise ValueError("Ambiguous duplicate study conditions")
    if any(row["condition"]["method"] not in NAMES
           or row["condition"]["recovery"] not in COLORS for row in rows):
        raise ValueError("Unknown method or recovery policy")
    return analysis, rows


def _plotting():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _label(row):
    condition = row["condition"]
    return (f"{NAMES[condition['method']]} {condition['retention']:.0%} | "
            f"{condition['recovery']} | N={condition['max_attempts']}")


def _difference(analysis, left, right):
    for comparison in analysis["paired_comparisons"]:
        if {comparison["left"], comparison["right"]} == {left, right}:
            estimate = comparison["oracle_success_rate"]
            sign = 1 if comparison["right"] == right else -1
            return {"value": sign * estimate["value"],
                    **{key: sorted(sign * bound for bound in estimate[key])
                       for key in ("ci95", "bounded_mean_ci95")}}
    raise ValueError(f"Missing paired success comparison: {left}, {right}")


def _groups(rows):
    groups = {}
    for row in rows:
        condition = row["condition"]
        if condition["method"] != "full":
            key = (condition["method"], condition["retention"], condition["max_attempts"])
            groups.setdefault(key, {})[condition["recovery"]] = row
    return sorted(groups.items())


def _save(fig, analysis, output, title, caption, *, top=0.9, bottom=0.16, left=0.07):
    mode = "Integration diagnostic" if analysis.get("integration_smoke") else analysis.get("stage", "Run")
    height = fig.get_figheight()
    fig.suptitle(title, x=0.07, y=1 - 0.12 / height, ha="left", fontsize=15, fontweight="bold")
    fig.text(0.07, 1 - 0.65 / height, f"{mode} | {analysis['task_count']} paired tasks | "
             f"{len(analysis['replicate_seeds'])} paired seed(s)", color="#555555", fontsize=9)
    fig.text(0.07, 0.15 / height, caption, fontsize=8, color="#555555", linespacing=1.5)
    fig.subplots_adjust(left=left, right=0.97, bottom=bottom, top=top, wspace=0.35, hspace=0.6)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180, metadata={"Creator": "COMET"})
    _plotting().close(fig)


def _horizontal_interval(ax, y, estimate, color):
    for key, width, alpha in (("bounded_mean_ci95", 5, 0.18), ("ci95", 1.5, 1)):
        low, high = [100 * value for value in estimate[key]]
        ax.hlines(y, low, high, color=color, linewidth=width, alpha=alpha)
    ax.plot(100 * estimate["value"], y, "o", color=color, markersize=5)


def plot_recovery(analysis_path: Path, output: Path, *, title="Recovery comparison") -> None:
    analysis, rows = _load(analysis_path)
    pairs = []
    for _, group in _groups(rows):
        for policy in ("fixed", "dynamic"):
            if policy in group:
                if "never" not in group:
                    raise ValueError("Every recovery condition needs a matched never-rebuild control")
                row = group[policy]
                pairs.append((row, _difference(analysis, group["never"]["condition"]["id"],
                                                row["condition"]["id"])))
    if not pairs:
        raise ValueError("Recovery figures require completed recovery conditions")
    plt = _plotting()
    height = max(5.5, len(pairs) * 0.5 + 2.6)
    with plt.rc_context({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False,
                         "svg.fonttype": "none"}):
        fig, axes = plt.subplots(1, 5, figsize=(17, height), sharey=True,
                                 gridspec_kw={"width_ratios": [2, 1, 1, 1, 1.8]})
        for index, (row, difference) in enumerate(pairs):
            recovery = row["recovery"]
            color = COLORS[row["condition"]["recovery"]]
            _horizontal_interval(axes[0], index, difference, color)
            seconds = recovery["recorded_seconds"]
            observed = seconds["observed_requests"]
            duration = seconds["value"] / observed if observed else None
            panels = ((axes[1], duration, f"{observed}/{seconds['total_requests']} requests"),
                      (axes[2], recovery["mean_cell_budget_fraction"]["value"],
                       f"{recovery['mean_cell_budget_fraction']['complete_cells']}/"
                       f"{recovery['mean_cell_budget_fraction']['total_cells']} cells"),
                      (axes[3], recovery["admission_rate"]["value"],
                       f"{recovery['admission_rate']['observed_requests']}/"
                       f"{recovery['admission_rate']['total_requests']} requests"))
            for ax, value, coverage in panels:
                if value is not None:
                    ax.barh(index, value * (1 if ax is axes[1] else 100), color=color, height=0.55)
                ax.text(0.02, index + 0.31, coverage if value is not None else "Unavailable: " + coverage,
                        transform=ax.get_yaxis_transform(), fontsize=6.5, color="#555555")
            reasons = recovery["refusal_reasons"]
            text = "; ".join(f"{reason}: {count}" for reason, count in sorted(reasons.items())) or "No recorded refusal"
            unknown = recovery["coverage"]["unknown_admission_requests"]
            if unknown:
                text += f"; unknown admission: {unknown}"
            axes[4].text(0, index, text, va="center", fontsize=7, wrap=True)
        titles = ["Success minus never (pp)", "Recorded time / request (s)",
                  "Mean cell budget share (%)", "Admitted / observed (%)", "Recorded refusal reasons"]
        for ax, label in zip(axes, titles, strict=True):
            ax.set_title(label, fontsize=9)
            ax.grid(axis="x", alpha=0.15)
            ax.set_axisbelow(True)
        axes[0].set(yticks=range(len(pairs)), yticklabels=[_label(row) for row, _ in pairs], xlim=(-102, 102))
        axes[0].axvline(0, color="#999999", linewidth=0.8)
        axes[0].invert_yaxis()
        for ax in axes[1:4]:
            ax.set_xlim(left=0)
        axes[3].set_xlim(0, 105)
        axes[4].set_xlim(0, 1)
        axes[4].axis("off")
        _save(fig, analysis, output, title,
              "Paired oracle-success differences: thin lines show task-bootstrap 95% intervals; broad pale lines show conservative bounded intervals.\n"
              "Recovery time includes admission checks and observed failed rebuild time. Unknown requests are not denials; coverage appears below each bar.\n"
              "Budget share includes zero only for cells with complete decision logs. Descriptive cost/admission bars do not imply independent requests.",
              top=1 - 1.2 / height, bottom=1.2 / height, left=0.24)


def plot_triggers(analysis_path: Path, output: Path, *, title="Recovery trigger observations") -> None:
    analysis, rows = _load(analysis_path)
    groups = [(key, group) for key, group in _groups(rows) if "fixed" in group and "dynamic" in group]
    if not groups:
        raise ValueError("Trigger figures need paired fixed and dynamic conditions")
    if any("observations" not in row for _, group in groups for row in group.values()):
        raise ValueError("Reanalyze the run to retain recorded trigger observations")
    plt = _plotting()
    height = 2.6 * len(groups) + 2.1
    with plt.rc_context({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False,
                         "svg.fonttype": "none"}):
        fig, axes = plt.subplots(len(groups), 3, figsize=(12, height), squeeze=False)
        for index, ((method, retention, attempts), group) in enumerate(groups):
            for column, policy in enumerate(("fixed", "dynamic")):
                ax = axes[index, column]
                recorded = group[policy]["observations"]["decisions"]
                points = [event for event in recorded if all(isinstance(event.get(key), int)
                          for key in ("context_tokens", "tool_calls", "rebuilds"))]
                for requested, color, size in ((False, "#b0b0b0", 8), (True, COLORS[policy], 30)):
                    selected = [event for event in points if event["triggered"] is requested]
                    ax.scatter([event["context_tokens"] for event in selected],
                               [event["tool_calls"] for event in selected], s=size, color=color,
                               alpha=0.6, label="Requested" if requested else "Not requested")
                ax.set(title=f"{policy}: {len(points)}/{len(recorded)} located decisions",
                       xlabel="Full raw context tokens", ylabel="Cumulative Python executions")
                ax.grid(alpha=0.15)
                if index == 0:
                    ax.legend(frameon=False, fontsize=7)
            difference = _difference(analysis, group["fixed"]["condition"]["id"],
                                     group["dynamic"]["condition"]["id"])
            ax = axes[index, 2]
            _horizontal_interval(ax, 0, difference, COLORS["dynamic"])
            ax.axvline(0, color="#999999", linewidth=0.8)
            ax.set(title=f"{NAMES[method]} {retention:.0%} | N={attempts}",
                   xlabel="Dynamic minus fixed oracle success (pp)", xlim=(-102, 102), yticks=[])
        _save(fig, analysis, output, title,
              "All observed decisions are shown, including checks after a rebuild; requests may be admitted, denied or unfinished.\n"
              "Trajectories evolve independently after their common start. The point cloud is not a causal boundary or a density estimate.\n"
              "Differences use paired tasks: thin task-bootstrap and pale bounded 95% intervals. Repeated decisions are not independent samples.",
              top=1 - 1.1 / height, bottom=1.1 / height)


def plot_attempts(analysis_path: Path, output: Path, *, title="Attempt allocation comparison") -> None:
    analysis, rows = _load(analysis_path)
    if any("observations" not in row for row in rows):
        raise ValueError("Reanalyze the run to retain attempt counts and cell outcomes")
    rows.sort(key=lambda row: (row["condition"]["method"], -row["condition"]["retention"],
                              row["condition"]["max_attempts"], row["condition"]["recovery"]))
    plt = _plotting()
    height = max(5.5, 0.48 * len(rows) + 2.6)
    with plt.rc_context({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False,
                         "svg.fonttype": "none"}):
        fig, axes = plt.subplots(1, 3, figsize=(14, height))
        max_attempts = max(row["condition"]["max_attempts"] for row in rows)
        counts = []
        locations = defaultdict(list)
        for index, row in enumerate(rows):
            color = COLORS[row["condition"]["recovery"]]
            for metric, offset, marker in (("single_attempt_success_rate", -0.12, "o"),
                                           ("oracle_success_rate", 0.12, "D")):
                estimate = row[metric]
                low, high = [100 * value for value in estimate["bounded_mean_ci95"]]
                axes[0].hlines(index + offset, low, high, color=color, alpha=0.4)
                axes[0].plot(100 * estimate["value"], index + offset, marker=marker, color=color,
                             fillstyle="none" if metric.startswith("single") else "full", markersize=5)
            distribution = row["observations"]["actual_attempt_distribution"]
            total = len(row["observations"]["cells"])
            counts.append([100 * distribution.get(str(count), distribution.get(count, 0)) / total
                           for count in range(max_attempts + 1)])
            latency = row["latency_seconds"]
            success = row["oracle_success_rate"]
            axes[2].plot(latency["value"], 100 * success["value"], "o", color=color, markersize=5)
            locations[(latency["value"], 100 * success["value"])].append(str(index + 1))
            axes[2].hlines(100 * success["value"], *latency["ci95"], color=color, alpha=0.35)
            axes[2].vlines(latency["value"], *[100 * value for value in success["bounded_mean_ci95"]],
                           color=color, alpha=0.25)
        axes[0].set(title="First attempt (open) / oracle (filled)", xlabel="Success (%)", xlim=(-2, 102),
                    yticks=range(len(rows)), yticklabels=[f"{i + 1}. {_label(row)}" for i, row in enumerate(rows)])
        axes[0].set_ylim(len(rows) - 0.5, -0.5)
        axes[1].imshow(counts, cmap="Blues", vmin=0, vmax=100, aspect="auto", interpolation="none")
        axes[1].set(title="Actual attempts (% of cells)", xlabel="Attempts executed", yticks=[],
                    xticks=range(max_attempts + 1))
        for y, values in enumerate(counts):
            for x, value in enumerate(values):
                if value:
                    axes[1].text(x, y, f"{value:.0f}%", ha="center", va="center", fontsize=7,
                                 color="white" if value > 55 else "#222222")
        for location, identities in locations.items():
            axes[2].annotate(textwrap.fill(",".join(identities), width=22, break_long_words=False), location,
                             xytext=(-5, 5), textcoords="offset points", fontsize=6, ha="right")
        axes[2].set(title="Observed cost and oracle success", xlabel="Mean budget-accounted time (s)",
                    ylabel="Oracle success upper bound (%)", ylim=(-2, 102))
        axes[2].set_xlim(left=0)
        for ax in (axes[0], axes[2]):
            ax.grid(alpha=0.15)
            ax.set_axisbelow(True)
        reserved = sum(row["reserved_budget_seconds"]["value"] or 0 for row in rows)
        _save(fig, analysis, output, title,
              "Success uses conservative pointwise task-mean 95% intervals; time uses paired task bootstrap. Oracle assumes perfect outcome selection.\n"
              "Heatmap includes zero-attempt cells. Colors identify recovery policy; numbered points correspond to condition rows.\n"
              "Cost points describe completed schedules, not time to first success or performance under a smaller budget. "
              + ("Unobserved interruption reservations are included." if reserved else "No interruption reservations recorded."),
              top=1 - 1.2 / height, bottom=1.2 / height, left=0.29)
