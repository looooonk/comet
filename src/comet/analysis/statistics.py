from __future__ import annotations

import math
import random
from statistics import mean, stdev
from typing import Any


def _quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    left = math.floor(index)
    right = math.ceil(index)
    return ordered[left] + (ordered[right] - ordered[left]) * (index - left)


def _estimate(
    values: list[float], bootstrap: list[float], *, bounds: tuple[float, float] | None = None
) -> dict[str, Any]:
    count = len(values)
    degenerate = bool(bootstrap) and min(bootstrap) == max(bootstrap)
    notes = []
    if count < 2:
        notes.append("Fewer than two observed tasks; task-level standard error is unavailable.")
    if degenerate:
        notes.append(
            "A degenerate bootstrap interval does not establish zero population uncertainty."
        )
    result = {
        "value": mean(values) if values else None,
        "ci95": [_quantile(bootstrap, 0.025), _quantile(bootstrap, 0.975)] if bootstrap else None,
        "standard_error": stdev(values) / math.sqrt(count) if count > 1 else None,
        "task_count": count,
        "bootstrap_degenerate": degenerate,
        "uncertainty_notes": notes,
    }
    if bounds is not None:
        radius = (bounds[1] - bounds[0]) * math.sqrt(math.log(40) / (2 * count)) if count else 0
        result["bounded_mean_ci95"] = (
            [max(bounds[0], mean(values) - radius), min(bounds[1], mean(values) + radius)]
            if count
            else None
        )
    return result


def _bootstrap(values: list[float], rng: random.Random, samples: int) -> list[float]:
    return [mean(rng.choices(values, k=len(values))) for _ in range(samples)] if values else []
