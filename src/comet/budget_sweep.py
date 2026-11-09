"""Paired pilot endpoints from independently executed wall-clock budgets."""

from __future__ import annotations

import hashlib
import math
import random
import textwrap
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from comet.analysis import (
    _estimate,
    environment_initialization_summary,
    read_scored_run,
    reserved_seconds,
)
from comet.artifacts import read_json, write_json
from comet.comparison import _validated_cells
from comet.config import digest


def _endpoint(cells, tasks, seeds, draws):
    by_identity = {(cell["task_id"], cell["seed"]): cell for cell in cells}
    values = {key: [] for key in ("oracle_success_rate", "single_attempt_success_rate",
                                 "actual_attempts", "budget_accounted_seconds", "reserved_budget_seconds")}
    observations = []
    for task in tasks:
        paired = [by_identity[(task, seed)] for seed in seeds]
        values["oracle_success_rate"].append(mean(
            any(attempt["success"] for attempt in cell["attempts"]) for cell in paired))
        values["single_attempt_success_rate"].append(mean(
            bool(cell["attempts"] and cell["attempts"][0]["success"]) for cell in paired))
        values["actual_attempts"].append(mean(len(cell["attempts"]) for cell in paired))
        values["budget_accounted_seconds"].append(mean(cell["elapsed_seconds"] for cell in paired))
        values["reserved_budget_seconds"].append(mean(reserved_seconds(cell) for cell in paired))
        for cell in paired:
            observations.append({
                "task_id": task, "seed": cell["seed"], "run_id": cell["run_id"],
                "oracle_success": any(attempt["success"] for attempt in cell["attempts"]),
                "budget_accounted_seconds": cell["elapsed_seconds"],
                "reserved_budget_seconds": reserved_seconds(cell),
                "attempts": [{key: attempt[key] for key in ("attempt_index", "status", "success")}
                             for attempt in cell["attempts"]],
            })
    attempts = [attempt for cell in cells for attempt in cell["attempts"]]
    return {
        **{key: _estimate(observed, [mean(observed[index] for index in draw) for draw in draws],
                          bounds=(0, 1) if key.endswith("success_rate") else None)
           for key, observed in values.items()},
        "coverage": {"complete_cells": len(cells), "expected_cells": len(tasks) * len(seeds),
                     "scored_attempts": len(attempts), "started_attempts": len(attempts)},
        "attempt_status_counts": dict(Counter(attempt["status"] for attempt in attempts)),
        "zero_attempt_cells": sum(not cell["attempts"] for cell in cells),
        "infeasible_cells": sum(bool(cell.get("infeasible")) or
                                any(attempt["status"] == "infeasible" for attempt in cell["attempts"])
                                for cell in cells),
        "observations": observations,
    }


def analyze_budget_sweep(run_dirs, output, *, bootstrap_samples=2000, seed=0):
    """Allow budget changes only; retain strict pairing and completed saved cells."""
    if not run_dirs or bootstrap_samples < 1:
        raise ValueError("A budget sweep needs scored runs and at least one bootstrap draw")
    directories = [Path(directory).resolve() for directory in run_dirs]
    output = Path(output).resolve()
    if output.exists() or any(output.is_relative_to(directory) for directory in directories):
        raise ValueError("Save the budget sweep to a new output outside immutable run directories")
    groups, sources = defaultdict(dict), []
    seen_runs, seen_executions, experiments = set(), set(), {}
    contract = runtime_contract = dependencies = smoke = None
    allowed = {"budget_seconds", "experiment_id", "notes", "conditions"}
    for directory in directories:
        manifest, scores, runtime = read_scored_run(directory)
        config = manifest["config"]
        if (manifest["stage"] != "pilot" or config["stage"] != "pilot"
                or config["split"] not in {"train", "dev"}):
            raise ValueError("Budget sweeps require ordinary train/dev pilot runs")
        if manifest["run_id"] in seen_runs or scores["execution_digest"] in seen_executions:
            raise ValueError("Duplicate execution or scoring revision in budget sweep")
        seen_runs.add(manifest["run_id"])
        seen_executions.add(scores["execution_digest"])
        current = {key: value for key, value in config.items() if key not in allowed}
        if contract is not None and current != contract:
            raise ValueError("Budget runs differ outside budget_seconds, experiment_id and notes")
        if (runtime_contract is not None and runtime != runtime_contract
                or dependencies is not None and manifest.get("dependencies") != dependencies):
            raise ValueError("Budget runs require identical source, evaluator, runtime, hardware and dependencies")
        if (not manifest.get("dependencies")
                or not all(runtime["engine"].get(key) for key in ("model", "device_name"))
                or any(not runtime[label][key] for label in ("execution", "evaluation")
                       for key in ("source_hashes", "installed_packages"))):
            raise ValueError("Budget runs require recorded model, hardware, source and package identities")
        current_smoke = manifest.get("integration_smoke", False)
        if smoke is not None and smoke != current_smoke:
            raise ValueError("Budget sweeps cannot mix integration and research runs")
        contract, runtime_contract, dependencies, smoke = current, runtime, manifest["dependencies"], current_smoke
        cells = _validated_cells(directory, manifest, scores)
        budget = config["budget_seconds"]
        if budget in experiments and experiments[budget] != config["experiment_id"]:
            raise ValueError("Condition shards at one budget must share an experiment_id")
        experiments[budget] = config["experiment_id"]
        for condition in config["conditions"]:
            if condition["id"] in groups[budget]:
                raise ValueError("Duplicate condition shard at one budget")
            selected = [cell for cell in cells if cell["condition"] == condition]
            for cell in selected:
                if cell.get("budget_seconds") != budget:
                    raise ValueError("Saved cell budget differs from its declared run budget")
                elapsed = cell.get("elapsed_seconds")
                if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
                    raise ValueError("Invalid recorded cell elapsed time")
                for attempt in cell["attempts"]:
                    if type(attempt.get("success")) is not bool:
                        raise ValueError("Budget endpoints require separately scored attempts")
                    if attempt["status"] != "completed" and attempt["success"]:
                        raise ValueError("Execution failures cannot count as successful attempts")
            groups[budget][condition["id"]] = (condition, selected)
        sources.append({
            "run_directory": str(directory), "run_id": manifest["run_id"],
            "experiment_id": config["experiment_id"], "budget_seconds": budget,
            "environment_initialization": environment_initialization_summary(manifest),
            "condition_ids": [condition["id"] for condition in config["conditions"]],
            "config_digest": manifest["config_digest"], "execution_digest": scores["execution_digest"],
            "manifest_sha256": hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest(),
            "scores_sha256": hashlib.sha256((directory / "scores.json").read_bytes()).hexdigest(),
        })
    budgets = sorted(groups)
    if len(budgets) < 2:
        raise ValueError("A budget sweep needs at least two independently executed budgets")
    conditions = {key: row[0] for key, row in groups[budgets[0]].items()}
    if any({key: row[0] for key, row in group.items()} != conditions for group in groups.values()):
        raise ValueError("Every budget must contain exactly the same condition definitions")
    tasks, seeds = sorted(contract["task_ids"]), sorted(contract["seeds"])
    rng = random.Random(seed)
    draws = [[rng.randrange(len(tasks)) for _ in tasks] for _ in range(bootstrap_samples)]
    result = {
        "schema_version": 1, "kind": "independent_budget_sweep", "stage": "pilot",
        "integration_smoke": smoke, "declared_varying_fields": ["budget_seconds", "experiment_id", "notes"],
        "scope": "Independently executed budget endpoints; oracle assumes perfect outcome selection. "
                 "Not attained-success timestamps or counterfactual truncations of a longer run.",
        "task_count": len(tasks), "tasks": tasks, "replicate_seeds": seeds, "budgets_seconds": budgets,
        "runtime_contract_digest": digest(runtime_contract), "dependencies_digest": digest(dependencies),
        "shared_config": contract, "engine": runtime_contract["engine"], "source_runs": sources,
        "uncertainty": {"method": "paired task bootstrap, percentile 95% CI", "samples": bootstrap_samples,
                        "seed": seed, "resampling_unit": "task, retaining every seed and budget/condition",
                        "task_draws_sha256": digest(draws),
                        "bounded_mean_method": "Hoeffding, clipped to [0,1] for task success means",
                        "interval_scope": "pointwise 95%; not simultaneous across budgets or conditions",
                        "assumption": "independent sampled tasks; seeds do not increase task count"},
        "conditions": {},
    }
    for key, condition in sorted(conditions.items()):
        result["conditions"][key] = {"condition": condition, "points": [
            {"budget_seconds": budget, **_endpoint(groups[budget][key][1], tasks, seeds, draws)}
            for budget in budgets]}
    write_json(output, result)
    return result


def plot_budget_sweep(analysis_path, output, *, title="Success versus independently rerun budget"):
    from comet.policy_plots import COLORS, _curve_panels, _plotting, _save

    analysis = read_json(Path(analysis_path))
    if analysis.get("kind") != "independent_budget_sweep":
        raise ValueError("Plot a validated independent budget sweep, not attained-success curves")
    rows = list(analysis["conditions"].values())
    signatures = [tuple(row["condition"][key] for key in ("method", "retention", "recovery", "max_attempts"))
                  for row in rows]
    if len(set(signatures)) != len(signatures):
        raise ValueError("Ambiguous duplicate budget-sweep conditions")
    _, panels = _curve_panels(
        rows, missing_control="Each compressed budget panel needs a full-cache control with the same attempt limit")
    if not panels:
        raise ValueError("No supported budget-sweep conditions to plot")
    columns = min(3, len(panels))
    height, width = 3 * math.ceil(len(panels) / columns) + 2.2, max(8, 4.6 * columns)
    plt = _plotting()
    with plt.rc_context({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False,
                         "svg.fonttype": "none"}):
        fig, axes = plt.subplots(math.ceil(len(panels) / columns), columns,
                                 figsize=(width, height), squeeze=False)
        for ax, (label, entries) in zip(axes.flat, panels, strict=False):
            full_only = all(row["condition"]["method"] == "full" for row in entries)
            for index, row in enumerate(entries):
                condition = row["condition"]
                is_full = condition["method"] == "full"
                name = "Full KV" if is_full else condition["recovery"].capitalize()
                color = "#333333" if is_full else COLORS[condition["recovery"]]
                style = "--" if is_full else {"never": "-", "fixed": "-.", "dynamic": ":"}[condition["recovery"]]
                if full_only:
                    name += f" N={condition['max_attempts']}"
                    color = ("#333333", "#aa4499", "#44aa99", "#999933")[index % 4]
                points = row["points"]
                x = [point["budget_seconds"] for point in points]
                y = [100 * point["oracle_success_rate"]["value"] for point in points]
                for field, alpha in (("bounded_mean_ci95", 0.04), ("ci95", 0.12)):
                    low, high = ([100 * point["oracle_success_rate"][field][side] for point in points]
                                 for side in (0, 1))
                    ax.fill_between(x, low, high, color=color, alpha=alpha, linewidth=0)
                    ax.vlines(x, low, high, color=color, alpha=0.35 if field.startswith("bounded") else 1,
                              linewidth=0.7 if field.startswith("bounded") else 1.4)
                ax.plot(x, y, marker="o", markersize=4, linestyle=style, color=color, label=name)
            ax.set(title=label, xlabel="Independently executed budget (s)",
                   ylabel="Oracle task success (%)", ylim=(-2, 102))
            ax.set_xticks(analysis["budgets_seconds"])
            ax.grid(alpha=0.15)
            ax.set_axisbelow(True)
            ax.legend(frameon=False, fontsize=7, ncol=2)
        for ax in list(axes.flat)[len(panels):]:
            ax.set_visible(False)
        caption = "\n".join(textwrap.fill(line, int(width * 14)) for line in (
            "Each point is an independently executed budget endpoint. Lines only guide the eye; no smoothing or monotonicity constraint.",
            "Identical paired tasks, seeds and conditions at every budget. Failures and zero-attempt cells remain; oracle assumes perfect outcome selection.",
            "Pointwise 95% task-bootstrap and pale conservative bounded-mean intervals; not simultaneous. No success timestamps or interruption reservations define the x-axis.",
        ))
        _save(fig, analysis, output, title, caption, top=1 - 1.15 / height,
              bottom=(0.65 + 0.15 * len(caption.splitlines())) / height)
