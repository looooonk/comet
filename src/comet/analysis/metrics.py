from __future__ import annotations

import math
from collections import Counter
from statistics import mean
from typing import Any

from .observations import _finite_number


def _resource_tasks(group: dict, tasks: list[str], task_seeds: dict, key: str) -> tuple[dict, dict]:
    values, cells = {}, {}
    observed_attempts = total_attempts = 0
    for identity, cell in group.items():
        measured = [
            attempt["metrics"][key]
            for attempt in cell["attempts"]
            if isinstance(attempt.get("metrics", {}).get(key), (int, float))
        ]
        total_attempts += len(cell["attempts"])
        observed_attempts += len(measured)
        if measured and len(measured) == len(cell["attempts"]):
            cells[identity] = max(measured)
    for task in tasks:
        if all((task, seed) in cells for seed in task_seeds[task]):
            values[task] = mean(cells[(task, seed)] for seed in task_seeds[task])
    return values, {
        "observed_attempts": observed_attempts,
        "total_attempts": total_attempts,
        "complete_cells": len(cells),
        "total_cells": len(group),
        "complete_tasks": len(values),
        "total_tasks": len(tasks),
    }


def _metric(
    attempts: list[dict[str, Any]], key: str, unit: str, aggregation: str
) -> dict[str, Any]:
    values = [
        attempt["metrics"][key]
        for attempt in attempts
        if isinstance(attempt.get("metrics", {}).get(key), (int, float))
    ]
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError(f"Invalid recorded metric: {key}")
    value = (sum(values) if aggregation == "sum" else max(values)) if values else None
    return {
        "value": value,
        "unit": unit,
        "aggregation": aggregation,
        "observed_attempts": len(values),
        "total_attempts": len(attempts),
        "coverage": dict(
            Counter(
                attempt.get("metrics", {}).get("metric_coverage", {}).get(key, "unspecified")
                if isinstance(attempt.get("metrics", {}).get(key), (int, float))
                else "unavailable"
                for attempt in attempts
            )
        ),
    }


def environment_initialization_summary(manifest: dict) -> dict:
    records = [
        {"launch_index": index, **launch["environment_initialization"]}
        for index, launch in enumerate(manifest.get("launches", []))
        if "environment_initialization" in launch
    ]
    durations = [record["seconds"] for record in records if "seconds" in record]
    if any(not _finite_number(value) or value < 0 for value in durations):
        raise ValueError("Invalid environment initialization duration")
    return {
        "settings": manifest["config"].get("environment_warmup"),
        "launches": records,
        "measured_seconds": sum(durations) if durations else None,
        "measured_launches": len(durations),
        "recorded_launches": len(records),
        "total_launches": len(manifest.get("launches", [])),
        "status_counts": dict(Counter(record["status"] for record in records)),
        "charged_to_task_budget": False,
        "scope": "Separate process setup; never amortized into task latency. Missing durations are not zero.",
    }
