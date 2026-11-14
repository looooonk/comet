"""Paired differences with task families as the resampling unit.

AppWorld variants of one family share a template, so they are not independent
tasks. This offline summary resamples whole families, keeping each family's
tasks and their paired seeds together. It reads scored outcomes only and is a
stricter companion to the shared task bootstrap, not a replacement for it.
"""

from __future__ import annotations

import random

Outcomes = dict[tuple[str, int], bool]
MINIMUM_DRAWS = 40


def family_of(task_id: str) -> str:
    """AppWorld task identifiers are a family and a variant joined by an underscore."""
    return task_id.rsplit("_", 1)[0]


def _task_differences(left: Outcomes, right: Outcomes) -> tuple[dict[str, float], list[int]]:
    if set(left) != set(right):
        raise ValueError("Both arms need the same tasks and seeds")
    values = (*left.values(), *right.values())
    if any(value is None for value in values):
        raise ValueError("Unscored cells cannot be compared")
    if any(not isinstance(value, bool) for value in values):
        raise ValueError("Outcomes must be true or false")
    tasks = sorted({task for task, _ in left})
    seeds = sorted({seed for _, seed in left})
    if len(left) != len(tasks) * len(seeds):
        raise ValueError("Each task needs every seed")
    differences = {
        task: sum(int(left[(task, seed)]) - int(right[(task, seed)]) for seed in seeds) / len(seeds)
        for task in tasks
    }
    return differences, seeds


def paired_family_difference(
    left: Outcomes, right: Outcomes, *, draws: int = 10000, seed: int = 0
) -> dict:
    """Left-minus-right success difference with a family-resampled percentile interval.

    Seeds are averaged within a task and tasks weigh equally. Each draw samples
    families with replacement and takes the mean difference over their tasks.
    The bounds leave the same number of draws outside on each side.
    """
    if draws < MINIMUM_DRAWS:
        raise ValueError(f"At least {MINIMUM_DRAWS} draws are needed for a 95% interval")
    differences, seeds = _task_differences(left, right)
    by_family: dict[str, list[float]] = {}
    for task, value in differences.items():
        by_family.setdefault(family_of(task), []).append(value)
    families = sorted(by_family)
    if len(families) < 2:
        raise ValueError("A family interval needs at least two families")
    rng = random.Random(seed)
    samples = []
    for _ in range(draws):
        total, count = 0.0, 0
        for _ in families:
            values = by_family[rng.choice(families)]
            total += sum(values)
            count += len(values)
        samples.append(total / count)
    samples.sort()
    tail = round(0.025 * draws)
    return {
        "difference": sum(differences.values()) / len(differences),
        "ci95": [samples[tail - 1], samples[draws - tail]],
        "draws_at_or_below_zero": sum(value <= 0 for value in samples),
        "draws_at_or_above_zero": sum(value >= 0 for value in samples),
        "families": len(families),
        "tasks": len(differences),
        "seeds": seeds,
        "tasks_gained": sorted(task for task, value in differences.items() if value > 0),
        "tasks_lost": sorted(task for task, value in differences.items() if value < 0),
        "resampling_unit": "task family, retaining its tasks and their paired seeds",
        "draws": draws,
        "bootstrap_seed": seed,
    }
