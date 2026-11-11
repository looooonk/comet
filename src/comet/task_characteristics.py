"""Offline task-characteristic summaries from saved trajectories and scores.

Post-hoc description only: nothing here runs a model, a tool or the evaluator,
and none of it may feed execution, triggers or attempt selection.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from statistics import mean

API_CALL = re.compile(r"apis\.(\w+)\.(\w+)\s*\(")
IMPORT = re.compile(r"^\s*(?:import|from)\s+\w", re.MULTILINE)
HTTP = re.compile(r"\brequests\.|https?://")
TOLERANCE_ARMS = ("rkv_80_never", "agentkv_80_never", "rkv_50_never", "agentkv_50_never")
RECOVERY_ARMS = ("agentkv_50", "rkv_50")


def _first_api(action: str) -> str | None:
    match = API_CALL.search(action or "")
    return f"{match.group(1)}.{match.group(2)}" if match else None


def action_kind(action: str) -> str:
    """Classify one submitted code block by the first AppWorld API it calls."""
    if not action:
        return "none"
    api = _first_api(action)
    if api is None:
        return "other"
    app = api.split(".")[0]
    if app == "api_docs":
        return "documentation"
    return "supervisor" if app == "supervisor" else "task_api"


def prohibited_patterns(action: str) -> list[str]:
    """Constructs the v4 prompt forbids outright: imports, and requests or HTTP URLs."""
    found = []
    if IMPORT.search(action or ""):
        found.append("import")
    if HTTP.search(action or ""):
        found.append("http")
    return found


def attempt_profile(attempt: dict) -> dict:
    """Observation volume by action kind, repeats and the largest single turn."""
    turns = attempt.get("turns") or []
    chars_by_kind: Counter = Counter()
    actions = []
    error_turns = 0
    largest = None
    for index, turn in enumerate(turns):
        action = turn.get("action") or ""
        kind = action_kind(action)
        chars = turn.get("obs_chars") or 0
        chars_by_kind[kind] += chars
        if action:
            actions.append(action)
        head = turn.get("obs_head") or ""
        if "Execution failed" in head or "Invalid action" in head:
            error_turns += 1
        if largest is None or chars > largest["chars"]:
            largest = {"index": index, "chars": chars, "kind": kind, "api": _first_api(action)}
    return {
        "status": attempt.get("status"),
        "turns": len(turns),
        "tool_calls": attempt.get("tool_calls"),
        "context_tokens": attempt.get("logical_cached_tokens"),
        "observation_chars": sum(chars_by_kind.values()),
        "chars_by_kind": {kind: count for kind, count in chars_by_kind.items() if count},
        "repeated_actions": len(actions) - len(set(actions)),
        "error_turns": error_turns,
        "largest_turn": largest,
    }


def flood_summary(attempts: list[dict]) -> dict:
    """What the largest observation was in attempts that reached the context limit."""
    flooded = [attempt_profile(a) for a in attempts if a.get("status") == "context_limit"]
    kinds = Counter(p["largest_turn"]["kind"] for p in flooded if p["largest_turn"])
    apis = Counter(p["largest_turn"]["api"] or "none" for p in flooded if p["largest_turn"])
    return {
        "attempts": len(attempts),
        "context_limit_attempts": len(flooded),
        "largest_turn_kind": dict(kinds),
        "largest_turn_api": dict(apis),
        "median_largest_turn_chars": _median([p["largest_turn"]["chars"] for p in flooded if p["largest_turn"]]),
        "median_tool_calls": _median([p["tool_calls"] or 0 for p in flooded]),
        "with_repeated_actions": sum(p["repeated_actions"] > 0 for p in flooded),
    }


def opening_api(attempt: dict) -> str | None:
    """The first AppWorld API named in the attempt's first submitted action."""
    turns = attempt.get("turns") or []
    return _first_api(turns[0].get("action") or "") if turns else None


def opening_summary(attempts: list[dict]) -> dict:
    """How attempts ended, grouped by the API their first action called."""
    summary: dict = {}
    for attempt in attempts:
        entry = summary.setdefault(opening_api(attempt) or "none", {"attempts": 0, "status": Counter()})
        entry["attempts"] += 1
        entry["status"][attempt.get("status")] += 1
    return {api: {"attempts": e["attempts"], "status": dict(e["status"])} for api, e in summary.items()}


def documentation_calls(attempts: list[dict]) -> dict:
    """Number and observation size of documentation calls, by api_docs method."""
    sizes: dict[str, list[int]] = {}
    for attempt in attempts:
        for turn in attempt.get("turns") or []:
            api = _first_api(turn.get("action") or "")
            if api and api.startswith("api_docs."):
                sizes.setdefault(api.split(".", 1)[1], []).append(turn.get("obs_chars") or 0)
    return {name: {"calls": len(values), "median_chars": _median(values), "max_chars": max(values)}
            for name, values in sizes.items()}


def task_outcomes(solved: dict[str, bool]) -> dict:
    """Per-task oracle outcomes; every referenced condition must be present."""
    benefit = {}
    for arm in RECOVERY_ARMS:
        # Read both arms before combining them so a success cannot hide missing data.
        fixed, dynamic = solved[f"{arm}_fixed"], solved[f"{arm}_dynamic"]
        recovered = fixed or dynamic
        benefit[arm] = int(recovered) - int(solved[f"{arm}_never"])
    full_once, full_best_of_n = solved["full_once"], solved["full_best_of_n"]
    return {
        "full_cache_solved": bool(full_once or full_best_of_n),
        "tolerance": sum(bool(solved[arm]) for arm in TOLERANCE_ARMS),
        "tolerance_arms": len(TOLERANCE_ARMS),
        "recovery_benefit": benefit,
        "any_recovery_gain": any(value > 0 for value in benefit.values()),
    }


def task_table(export: dict, solved: dict[tuple[str, str, int], bool]) -> list[dict]:
    """One row per task and seed: metadata, full-cache behaviour and outcomes."""
    by_cell = {(c["task_id"], c["condition"]["id"], c["seed"]): c for c in export["cells"]}
    rows = []
    for task_id, seed in sorted({(task, seed) for task, _, seed in solved}):
        meta = export["tasks"][task_id]
        details = meta.get("metadata") or {}
        first = by_cell[(task_id, "full_once", seed)]["attempts"][0]
        profile = attempt_profile(first)
        outcome = task_outcomes({cond: value for (task, cond, s), value in solved.items()
                                 if task == task_id and s == seed})
        rows.append({
            "task_id": task_id, "seed": seed,
            "difficulty": details.get("difficulty"), "num_apps": details.get("num_apps"),
            "num_apis": details.get("num_apis"), "ground_truth_api_calls": meta.get("ground_truth_api_calls"),
            "is_question": bool(meta.get("is_question")), "required_apps": meta.get("required_apps") or [],
            "full_cache_status": first.get("status"), "full_cache_tool_calls": first.get("tool_calls"),
            "full_cache_context_tokens": first.get("logical_cached_tokens"),
            "full_cache_seconds": first.get("elapsed_seconds"),
            "full_cache_observation_chars": profile["observation_chars"],
            "full_cache_documentation_chars": profile["chars_by_kind"].get("documentation", 0),
            **outcome,
        })
    return rows


def _median(values: list) -> float | None:
    ordered = sorted(v for v in values if v is not None)
    if not ordered:
        return None
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for position in range(start, end + 1):
            ranks[order[position]] = (start + end) / 2 + 1
        start = end + 1
    return ranks


def spearman(left: list[float], right: list[float]) -> float | None:
    """Rank correlation with average ranks for ties; None when either side is constant."""
    if len(left) != len(right) or len(left) < 3:
        return None
    x, y = _ranks(left), _ranks(right)
    mean_x, mean_y = mean(x), mean(y)
    spread_x = sum((v - mean_x) ** 2 for v in x)
    spread_y = sum((v - mean_y) ** 2 for v in y)
    if not spread_x or not spread_y:
        return None
    return sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y)) / (spread_x * spread_y) ** 0.5


def permutation_p(left: list[float], right: list[float], *, draws: int = 10000, seed: int = 0) -> float | None:
    """Two-sided permutation p-value for the rank correlation; exploratory only."""
    observed = spearman(left, right)
    if observed is None:
        return None
    rng = random.Random(seed)
    shuffled = list(right)
    extreme = 0
    for _ in range(draws):
        rng.shuffle(shuffled)
        value = spearman(left, shuffled)
        if value is not None and abs(value) >= abs(observed) - 1e-12:
            extreme += 1
    return (extreme + 1) / (draws + 1)


def associations(rows: list[dict], features: list[str], outcomes: dict) -> list[dict]:
    """Rank correlation of each feature with each numeric outcome extractor."""
    results = []
    for feature in features:
        for name, extract in outcomes.items():
            pairs = [(float(row[feature]), float(extract(row))) for row in rows if row.get(feature) is not None]
            left, right = [p[0] for p in pairs], [p[1] for p in pairs]
            results.append({"feature": feature, "outcome": name, "n": len(pairs),
                            "spearman": spearman(left, right), "permutation_p": permutation_p(left, right)})
    return results
