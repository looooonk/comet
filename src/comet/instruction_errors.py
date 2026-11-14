"""Offline counts of turns that break an explicit rule of the system prompt.

The v4 prompt tells the agent how to obtain credentials, to return one fenced
code block, to use only documented API names and arguments, and not to import
modules or call URLs. These summaries read which of those rules a saved turn
broke from its action and its observation. They are post-hoc description:
nothing here runs a model, a tool or the evaluator, and none of it may feed
execution, triggers or attempt selection.
"""

from __future__ import annotations

import random
import re

from comet.family_bootstrap import MINIMUM_DRAWS, family_of
from comet.trigger_timing import _cells_by_key, _rebuild_turn

# Observation text that identifies the broken rule. Task-level refusals, such
# as an expired payment card, match none of these and are not violations.
OBSERVATION_MARKERS = {
    "format": ("Invalid action",),
    "credentials": ("Invalid credentials",),
    "unknown_api": ("No API named", "No APIs with name"),
    "wrong_arguments": ("Unexpected parameter",),
}
# The prompt forbids importing the API objects and using requests or HTTP URLs;
# standard-library imports are allowed and do not count. A variable may be
# named requests, so the library is recognised by its import or its calls.
FORBIDDEN_MODULES = r"(?:apis|api_docs|supervisor|requests)\b"
PROHIBITED = re.compile(
    rf"\bfrom\s+{FORBIDDEN_MODULES}|\bimport\s+(?:[\w.]+\s*,\s*)*{FORBIDDEN_MODULES}"
    r"|\brequests\.(?:get|post|put|patch|delete|request|Session)\b|https?://"
)
COMMENT = re.compile(r"#[^\n]*")
VIOLATIONS = (*OBSERVATION_MARKERS, "prohibited")


def turn_violations(turn: dict) -> set[str]:
    """Prompt rules one turn broke, from its action and saved observation text."""
    observation = (turn.get("obs_head") or "") + (turn.get("obs_tail") or "")
    found = {
        name for name, markers in OBSERVATION_MARKERS.items()
        if any(marker in observation for marker in markers)
    }
    if PROHIBITED.search(COMMENT.sub("", turn.get("action") or "")):
        found.add("prohibited")
    return found


def _counts(turns: list[dict]) -> dict[str, int]:
    counts = dict.fromkeys(VIOLATIONS, 0)
    for turn in turns:
        for name in turn_violations(turn):
            counts[name] += 1
    return counts


def arm_summary(cells: list[dict]) -> dict:
    """Attempts with each violation, and turns with it, for one condition."""
    attempts = [attempt for cell in cells for attempt in cell["attempts"]]
    per_attempt = [_counts(attempt.get("turns") or []) for attempt in attempts]
    return {
        "attempts": len(attempts),
        "violations": {
            name: {
                "attempts": sum(counts[name] > 0 for counts in per_attempt),
                "turns": sum(counts[name] for counts in per_attempt),
            }
            for name in VIOLATIONS
        },
    }


def _first_attempt(cell: dict) -> dict | None:
    return next((a for a in cell["attempts"] if a["attempt_index"] == 0), None)


def twin_rows(rebuilt_cells: list[dict], never_cells: list[dict]) -> list[dict]:
    """Violations after the rebuild, beside the never-rebuild twin's same turns.

    A recovery arm and its never arm share seed and start, so a first attempt
    repeats its twin action for action until the rebuild. Only first attempts
    that were rebuilt and match their twin up to that turn are compared; the
    turns before it are identical and left out.
    """
    twins = _cells_by_key(never_cells)
    rows = []
    for key, cell in _cells_by_key(rebuilt_cells).items():
        twin = twins.get(key)
        mine = _first_attempt(cell)
        theirs = _first_attempt(twin) if twin else None
        if not mine or not theirs or not (mine.get("rebuilds") or 0):
            continue
        actions = [turn.get("action") or "" for turn in mine["turns"]]
        cut = _rebuild_turn(mine, actions)
        # A twin that ended before the rebuild, or took another path to it, has no comparable turns.
        if actions[:cut] != [turn.get("action") or "" for turn in theirs["turns"]][:cut]:
            continue
        rows.append({
            "task_id": cell["task_id"], "seed": cell["seed"], "turns_before_rebuild": cut,
            "rebuilt": _counts(mine["turns"][cut:]), "never": _counts(theirs["turns"][cut:]),
            "rebuilt_turns": len(mine["turns"]) - cut, "never_turns": len(theirs["turns"]) - cut,
            "rebuilt_passed": bool(mine.get("success")), "never_passed": bool(theirs.get("success")),
        })
    return rows


def clustered_share_difference(
    rows: list[dict], violation: str, *, draws: int = 10000, seed: int = 0
) -> dict:
    """Share of twin pairs with the violation after the rebuild, rebuilt minus never.

    The interval resamples task families with all of their pairs.
    """
    if draws < MINIMUM_DRAWS:
        raise ValueError(f"At least {MINIMUM_DRAWS} draws are needed for a 95% interval")
    by_family: dict[str, list[tuple[int, int]]] = {}
    for row in rows:
        pair = (int(row["rebuilt"][violation] > 0), int(row["never"][violation] > 0))
        by_family.setdefault(family_of(row["task_id"]), []).append(pair)
    families = sorted(by_family)
    if len(families) < 2:
        raise ValueError("A family interval needs at least two families")

    def shares(pairs: list[tuple[int, int]]) -> tuple[float, float]:
        return sum(p[0] for p in pairs) / len(pairs), sum(p[1] for p in pairs) / len(pairs)

    rng = random.Random(seed)
    samples = []
    for _ in range(draws):
        pairs = [pair for _ in families for pair in by_family[rng.choice(families)]]
        rebuilt, never = shares(pairs)
        samples.append(rebuilt - never)
    samples.sort()
    tail = round(0.025 * draws)
    rebuilt, never = shares([pair for family in families for pair in by_family[family]])
    return {
        "violation": violation, "pairs": len(rows), "families": len(families),
        "rebuilt_share": rebuilt, "never_share": never, "difference": rebuilt - never,
        "ci95": [samples[tail - 1], samples[draws - tail]],
        "resampling_unit": "task family, retaining all of its twin pairs",
        "draws": draws, "bootstrap_seed": seed,
    }
