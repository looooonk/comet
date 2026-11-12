"""Offline summaries for the supplemental trigger-timing study.

Post-hoc description only: reads exported cells and scores, runs no model,
tool or evaluator, and must not feed execution, triggers or attempt selection.
"""

from __future__ import annotations

from collections import Counter

from comet.task_characteristics import API_CALL, opening_api

LISTING_API = "api_docs.show_api_descriptions"
OPENINGS = {
    LISTING_API: "listing",
    "api_docs.search_api_docs": "search",
}


def _actions(attempt: dict) -> list[str]:
    return [turn.get("action") or "" for turn in attempt.get("turns") or []]


def _cells_by_key(cells: list[dict]) -> dict[tuple, dict]:
    """Index cells by task and seed; a repeated cell would be counted twice."""
    indexed: dict[tuple, dict] = {}
    for cell in cells:
        key = (cell["task_id"], cell["seed"])
        if key in indexed:
            raise ValueError(f"Duplicate cell for task and seed: {key}")
        indexed[key] = cell
    return indexed


def _attempts_by_index(cell: dict) -> dict[int, dict]:
    indexed: dict[int, dict] = {}
    for attempt in cell["attempts"]:
        if attempt["attempt_index"] in indexed:
            raise ValueError(
                f"Duplicate attempt {attempt['attempt_index']} in cell {cell['task_id']}"
            )
        indexed[attempt["attempt_index"]] = attempt
    return indexed


def _require_threshold(threshold: int) -> None:
    if threshold < 1:
        raise ValueError(f"A rebuild threshold counts executed tool calls from 1; got {threshold}")


def shared_prefix(left: list[str], right: list[str]) -> int:
    """Number of identical leading actions."""
    count = 0
    for a, b in zip(left, right):
        if a != b:
            break
        count += 1
    return count


def turns_before_rebuild(actions: list[str], threshold: int) -> int:
    """Leading turns generated before a rebuild after `threshold` executed actions."""
    _require_threshold(threshold)
    executed = 0
    for index, action in enumerate(actions):
        if action:
            executed += 1
        if executed == threshold:
            return index + 1
    return len(actions)


def prefix_report(cells: list[dict], reference: list[dict], *, threshold: int) -> dict:
    """Check that each attempt repeats its reference attempt up to the rebuild.

    The reference is a run of the same tasks, seed, method and retention whose
    rebuild comes no earlier, so the two must agree on every turn generated
    before `threshold` tool calls have executed. An empty action is taken as a
    turn that executed nothing; attempts whose recorded tool-call count
    disagrees with that reading are counted so the assumption stays visible.
    """
    _require_threshold(threshold)
    by_key = _cells_by_key(reference)
    compared, mismatches, divergent = 0, 0, []
    for key, cell in _cells_by_key(cells).items():
        other = by_key.get(key)
        if other is None:
            continue
        theirs = _attempts_by_index(other)
        for index, attempt in _attempts_by_index(cell).items():
            match = theirs.get(index)
            if match is None:
                continue
            mine, base = _actions(attempt), _actions(match)
            expected = min(turns_before_rebuild(mine, threshold), len(base))
            shared = shared_prefix(mine, base)
            compared += 1
            mismatches += int((attempt.get("tool_calls") or 0) != sum(bool(a) for a in mine))
            if shared < expected:
                divergent.append({"task_id": cell["task_id"], "seed": cell["seed"],
                                  "attempt_index": index, "shared": shared, "expected": expected})
    return {"attempts_compared": compared, "consistent": compared - len(divergent),
            "tool_call_mismatches": mismatches, "divergent": divergent}


def _opening(attempt: dict) -> str:
    return OPENINGS.get(opening_api(attempt) or "", "other")


def _rebuilt(attempt: dict) -> bool:
    return (attempt.get("rebuilds") or 0) > 0


def _calls_listing(action: str) -> bool:
    return any(f"{app}.{name}" == LISTING_API for app, name in API_CALL.findall(action))


def _solved(cells: list[dict], field: str) -> int | None:
    """Count of cells solved on `field`; None when any cell is unscored on it."""
    values = [cell.get(field) for cell in cells]
    return None if any(value is None for value in values) else sum(bool(value) for value in values)


def arm_summary(cells: list[dict]) -> dict:
    """Outcomes, endings and rebuild counts for one method at one threshold."""
    attempts = [attempt for cell in cells for attempt in cell["attempts"]]
    openings: dict[str, dict[str, int]] = {}
    for attempt in attempts:
        opening = _opening(attempt)
        previous = openings.get(opening, {"attempts": 0, "passed": 0, "context_limit": 0})
        openings[opening] = {
            "attempts": previous["attempts"] + 1,
            "passed": previous["passed"] + int(bool(attempt.get("success"))),
            "context_limit": previous["context_limit"] + int(attempt.get("status") == "context_limit"),
        }
    return {
        "cells": len(cells),
        "attempts": len(attempts),
        "unscored_cells": sum(cell.get("oracle_success") is None for cell in cells),
        "unscored_attempts": sum(attempt.get("success") is None for attempt in attempts),
        "tasks_solved": _solved(cells, "oracle_success"),
        "first_attempt_solved": _solved(cells, "single_attempt_success"),
        "passing_attempts": sum(bool(attempt.get("success")) for attempt in attempts),
        "context_limit_attempts": sum(attempt.get("status") == "context_limit" for attempt in attempts),
        "context_limit_without_rebuild": sum(
            attempt.get("status") == "context_limit" and not _rebuilt(attempt) for attempt in attempts
        ),
        "rebuilt_attempts": sum(_rebuilt(attempt) for attempt in attempts),
        "rebuilt_passing_attempts": sum(
            _rebuilt(attempt) and bool(attempt.get("success")) for attempt in attempts
        ),
        "status": dict(Counter(attempt.get("status") for attempt in attempts)),
        "by_opening": openings,
    }


def paired_tasks(left: list[dict], right: list[dict]) -> dict:
    """Task-paired oracle outcomes of two arms run on the same tasks and seed.

    Pairs with an unscored side are set aside, never read as a failure.
    """
    theirs = _cells_by_key(right)
    matched = [(key[0], cell.get("oracle_success"), theirs[key].get("oracle_success"))
               for key, cell in _cells_by_key(left).items() if key in theirs]
    pairs = [(task, a, b) for task, a, b in matched if a is not None and b is not None]
    return {
        "pairs": len(pairs),
        "unscored_pairs": len(matched) - len(pairs),
        "both": sum(bool(a and b) for _, a, b in pairs),
        "left_only": sorted(task for task, a, b in pairs if a and not b),
        "right_only": sorted(task for task, a, b in pairs if b and not a),
        "neither": sum(not a and not b for _, a, b in pairs),
    }


def _rebuild_turn(attempt: dict, actions: list[str]) -> int:
    """Index of the first turn generated after the attempt's recorded rebuild.

    The recorded trigger is used, not the configured threshold: a rebuild
    refused at the threshold may be admitted on a later turn.
    """
    calls = (attempt.get("recovery_trigger") or {}).get("tool_calls")
    if calls is None:
        raise ValueError(f"Rebuilt attempt {attempt.get('attempt_index')} has no recovery trigger")
    if sum(bool(action) for action in actions) < calls:
        raise ValueError(
            f"Rebuilt attempt {attempt.get('attempt_index')} has fewer executed actions "
            f"than the {calls} tool calls recorded at its rebuild"
        )
    return turns_before_rebuild(actions, calls)


def after_rebuild(cells: list[dict]) -> dict:
    """What rebuilt attempts did next, grouped by how they had opened.

    `next` classifies the first executed action after the rebuild the same way
    as an opening, or `none` when the attempt ended there; `listing_later`
    counts attempts that called the compact listing at any point after it.
    Attempts without a rebuild are left out, and unscored ones are counted
    apart from failures.
    """
    report: dict[str, dict] = {}
    for cell in cells:
        for attempt in cell["attempts"]:
            if not _rebuilt(attempt):
                continue
            actions = _actions(attempt)
            later = [action for action in actions[_rebuild_turn(attempt, actions):] if action]
            following = "none"
            if later:
                following = OPENINGS.get(opening_api({"turns": [{"action": later[0]}]}) or "", "other")
            opening = _opening(attempt)
            previous = report.get(
                opening, {"rebuilt": 0, "passed": 0, "unscored": 0, "next": {}, "listing_later": 0}
            )
            report[opening] = {
                "rebuilt": previous["rebuilt"] + 1,
                "passed": previous["passed"] + int(bool(attempt.get("success"))),
                "unscored": previous["unscored"] + int(attempt.get("success") is None),
                "next": {**previous["next"], following: previous["next"].get(following, 0) + 1},
                "listing_later": previous["listing_later"] + int(any(_calls_listing(a) for a in later)),
            }
    return report
