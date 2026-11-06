"""Offline symptoms from saved trajectories; never reads evaluator feedback."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


CATEGORIES = (
    "HTTP 401", "HTTP 422", "Unexpected parameter", "No API named",
    "Invalid action", "TypeError", "AttributeError", "NameError",
)


def summarize(trajectory: dict) -> dict:
    turns = trajectory["turns"]
    categories = Counter()
    actions = []
    first_error = None
    streak = longest_streak = error_turns = 0
    for index, turn in enumerate(turns, 1):
        observation = turn["observation"]
        text = observation if isinstance(observation, str) else json.dumps(observation)
        action = turn.get("action")
        if isinstance(action, str):
            actions.append(action)
        failed = "Execution failed" in text or "Invalid action" in text
        if failed:
            error_turns += 1
            first_error = index if first_error is None else first_error
            category = next((c for c in CATEGORIES if c in text), "other execution error")
            categories[category] += 1
            streak += 1
            longest_streak = max(longest_streak, streak)
        else:
            streak = 0
    return {
        "turns": len(turns), "error_turns": error_turns,
        "first_error_turn": first_error, "longest_error_streak": longest_streak,
        "repeated_action_strings": len(actions) - len(set(actions)),
        "categories": dict(categories),
    }


def audit(root: Path) -> dict:
    rows = []
    for path in sorted(root.rglob("trajectory.json")):
        raw = path.read_bytes()
        row = summarize(json.loads(raw))
        rows.append({"trajectory": path.relative_to(root).as_posix(),
                     "sha256": hashlib.sha256(raw).hexdigest(), **row})
    if not rows:
        raise ValueError("No saved trajectories found")
    return {"schema_version": 1,
            "scope": "Offline symptoms, not causal attribution or task scores. Missing trajectories are not imputed.",
            "trajectory_count": len(rows),
            "trajectories_with_errors": sum(row["error_turns"] > 0 for row in rows),
            "trajectories": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new audit output")
    result = audit(args.run)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(f"Audited {result['trajectory_count']} trajectories; "
          f"{result['trajectories_with_errors']} contain error turns")


if __name__ == "__main__":
    main()
