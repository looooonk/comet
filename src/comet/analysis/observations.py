from __future__ import annotations

import math
from collections import Counter
from statistics import mean
from typing import Any

from .statistics import _estimate


def recovery_summary(cells: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe recorded decisions without treating absent failure records as denials."""
    attempts = [attempt for cell in cells for attempt in cell["attempts"]]
    events = [event for attempt in attempts for event in attempt.get("recovery_events", [])]
    requests = [event for event in events if event.get("triggered")]
    results = [event.get("result", {}) for event in requests]
    admissions = [result["admitted"] for result in results if type(result.get("admitted")) is bool]
    allowances = [
        result["allowance_consumed"]
        for result in results
        if type(result.get("allowance_consumed")) is bool
    ]
    statuses = Counter(
        result.get(
            "status",
            "completed"
            if result.get("admitted") is True
            else "denied"
            if result.get("admitted") is False
            else "unknown",
        )
        for result in results
    )
    durations = [
        result["seconds"] for result in results if isinstance(result.get("seconds"), (int, float))
    ]
    if any(not math.isfinite(value) or value < 0 for value in durations):
        raise ValueError("Invalid recorded recovery seconds")
    fractions = []
    for cell in cells:
        requested = [
            event
            for attempt in cell["attempts"]
            for event in attempt.get("recovery_events", [])
            if event.get("triggered")
        ]
        measured = [event.get("result", {}).get("seconds") for event in requested]
        complete = all(
            "recovery_events" in attempt and attempt["status"] != "interrupted"
            for attempt in cell["attempts"]
        )
        budget = cell.get("budget_seconds")
        if (
            complete
            and isinstance(budget, (int, float))
            and budget > 0
            and all(isinstance(value, (int, float)) for value in measured)
        ):
            fractions.append(sum(measured) / budget)
    return {
        "decision_count": len(events),
        "requested_count": len(requests),
        "admitted_count": sum(admissions),
        "allowance_consumed_count": sum(allowances),
        "admission_rate": {
            "value": mean(admissions) if admissions else None,
            "observed_requests": len(admissions),
            "total_requests": len(requests),
        },
        "result_status_counts": dict(statuses),
        "refusal_reasons": dict(
            Counter(
                result.get("reason", "unspecified")
                for result in results
                if result.get("admitted") is False
            )
        ),
        "failure_reasons": dict(
            Counter(
                result.get("failure_reason", "unspecified")
                for result in results
                if result.get("status") == "failed"
            )
        ),
        "recorded_seconds": {
            "value": sum(durations) if durations else None,
            "observed_requests": len(durations),
            "total_requests": len(requests),
            "includes": "admission checks and admitted rebuilds, including observed failure time",
        },
        "mean_cell_budget_fraction": {
            "value": mean(fractions) if fractions else None,
            "complete_cells": len(fractions),
            "total_cells": len(cells),
        },
        "coverage": {
            "attempts_with_decisions": sum("recovery_events" in attempt for attempt in attempts),
            "interrupted_attempts": sum(attempt["status"] == "interrupted" for attempt in attempts),
            "total_attempts": len(attempts),
            "unknown_admission_requests": len(requests) - len(admissions),
            "requests_with_allowance_state": len(allowances),
        },
    }


def _finite_number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _attempt_times(cell: dict) -> list[dict]:
    records = []
    previous, reserved_prefix, bad_order = 0.0, False, False
    for index, attempt in enumerate(cell["attempts"]):
        seconds = attempt.get("budget_elapsed_seconds")
        reserved = attempt.get("reserved_budget_seconds", 0)
        invalid_reservation = not _finite_number(reserved) or reserved < 0
        if attempt["attempt_index"] != index:
            bad_order = True
        reason = None
        if invalid_reservation:
            reason = "invalid_reservation"
        elif attempt["status"] == "interrupted":
            reason = "interrupted"
        elif _finite_number(reserved) and reserved > 0:
            reason = "interruption_reservation"
        elif reserved_prefix:
            reason = "unobserved_prior_reservation"
        elif seconds is None:
            reason = "missing_timestamp"
        elif not _finite_number(seconds) or seconds < 0:
            reason = "invalid_timestamp"
        elif seconds < previous or bad_order:
            reason = "nonmonotone_schedule"
            bad_order = True
        elif _finite_number(cell.get("elapsed_seconds")) and seconds > cell["elapsed_seconds"]:
            reason = "after_recorded_cell_end"
        elif (
            attempt["success"]
            and _finite_number(cell.get("budget_seconds"))
            and seconds > cell["budget_seconds"]
        ):
            reason = "success_after_declared_budget"
        records.append(
            {
                "task_id": cell["task_id"],
                "seed": cell["seed"],
                "attempt_index": attempt["attempt_index"],
                "status": attempt["status"],
                "success": attempt["success"],
                "budget_elapsed_seconds": seconds if _finite_number(seconds) else None,
                "completion_seconds": seconds if reason is None else None,
                "timing_status": reason or "recorded",
                "reserved_budget_seconds": reserved if _finite_number(reserved) else None,
            }
        )
        if _finite_number(seconds) and reason not in {"interrupted", "interruption_reservation"}:
            previous = max(previous, seconds)
        reserved_prefix |= invalid_reservation or attempt["status"] == "interrupted" or reserved > 0
    return records


def policy_observations(cells: list[dict]) -> dict:
    """Keep paired identities and observed decisions for offline study figures."""
    outcomes, decisions, recorded_attempts = [], [], []
    for cell in sorted(cells, key=lambda item: (item["task_id"], item["seed"])):
        identity = {"task_id": cell["task_id"], "seed": cell["seed"]}
        attempts = cell["attempts"]
        times = _attempt_times(cell)
        recorded_attempts.extend(times)
        first_success = next((attempt for attempt in times if attempt["success"]), None)
        success_time = {
            "seconds": first_success["completion_seconds"] if first_success else None,
            "coverage": (
                "recorded" if first_success["completion_seconds"] is not None else "unavailable"
            )
            if first_success
            else "no_success",
            "attempt_index": first_success["attempt_index"] if first_success else None,
            "reason": first_success["timing_status"]
            if first_success and first_success["completion_seconds"] is None
            else None,
        }
        outcomes.append(
            {
                **identity,
                "actual_attempts": len(attempts),
                "first_attempt_success": bool(attempts and attempts[0]["success"]),
                "oracle_success": any(attempt["success"] for attempt in attempts),
                "budget_accounted_seconds": cell["elapsed_seconds"],
                "reserved_budget_seconds": reserved_seconds(cell),
                "budget_seconds": cell.get("budget_seconds")
                if _finite_number(cell.get("budget_seconds"))
                else None,
                "first_success_time": success_time,
            }
        )
        for attempt in attempts:
            for index, event in enumerate(attempt.get("recovery_events", [])):
                decisions.append(
                    {
                        **identity,
                        "attempt_index": attempt["attempt_index"],
                        "decision_index": index,
                        **event,
                    }
                )
    return {
        "cells": outcomes,
        "decisions": decisions,
        "attempts": recorded_attempts,
        "actual_attempt_distribution": dict(
            sorted(Counter(len(cell["attempts"]) for cell in cells).items())
        ),
        "latency_scope": "Total observed cell budget accounting, including interruption reservations; "
        "not time to first success or a replay at smaller budgets.",
    }


def _attained_oracle_curve(
    observations: dict,
    tasks: list[str],
    task_seeds: dict,
    draws: list[list[int]],
    event_times: set[float],
) -> dict:
    cells = observations["cells"]
    valid_budgets = [
        cell["budget_seconds"]
        for cell in cells
        if _finite_number(cell["budget_seconds"]) and cell["budget_seconds"] > 0
    ]
    budget = (
        valid_budgets[0]
        if len(valid_budgets) == len(cells) and len(set(valid_budgets)) == 1
        else None
    )
    missing = []
    for cell in cells:
        reasons = []
        if not _finite_number(cell["budget_seconds"]) or cell["budget_seconds"] <= 0:
            reasons.append("missing_or_invalid_budget")
        elif len(set(valid_budgets)) > 1:
            reasons.append("inconsistent_cell_budgets")
        if cell["first_success_time"]["coverage"] == "unavailable":
            reasons.append(cell["first_success_time"]["reason"])
        if reasons:
            missing.append({"task_id": cell["task_id"], "seed": cell["seed"], "reasons": reasons})
    result = {
        "status": "unavailable" if missing else "available",
        "budget_seconds": budget,
        "coverage": {
            "total_cells": len(cells),
            "complete_cells": len(cells) - len(missing),
            "success_cells": sum(cell["oracle_success"] for cell in cells),
            "timed_success_cells": sum(
                cell["first_success_time"]["coverage"] == "recorded" for cell in cells
            ),
            "unavailable_cells": missing,
        },
        "scope": "Success available by cumulative budget-accounted attempt completion time along executed "
        "schedules; perfect-selection upper bound, not smaller-budget reruns or an online selector.",
        "points": [],
    }
    if missing:
        return result
    by_identity = {
        (cell["task_id"], cell["seed"]): cell["first_success_time"]["seconds"] for cell in cells
    }
    previous_values, estimate = None, None
    for seconds in sorted({0.0, budget} | {time for time in event_times if time <= budget}):
        values = [
            mean(
                float(
                    by_identity[(task, seed)] is not None and by_identity[(task, seed)] <= seconds
                )
                for seed in task_seeds[task]
            )
            for task in tasks
        ]
        if values != previous_values:
            samples = [sum(values[index] for index in draw) / len(tasks) for draw in draws]
            estimate = _estimate(values, samples, bounds=(0, 1))
            previous_values = values
        result["points"].append({"seconds": seconds, **estimate})
    return result


def reserved_seconds(cell: dict) -> float:
    values = [cell.get("reserved_budget_seconds", 0)] + [
        attempt.get("reserved_budget_seconds", 0) for attempt in cell["attempts"]
    ]
    if any(not _finite_number(value) or value < 0 for value in values):
        raise ValueError("Invalid recorded reserved_budget_seconds")
    return sum(values)
