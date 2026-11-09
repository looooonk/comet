"""Recompute midpoint comparisons from pinned COMET records (Python stdlib)."""

import argparse
import csv
import hashlib
import io
import json
import statistics
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

SOURCE = "772b7e8247faf004e92731d4779b06e1368ba8f0"
COST = "history-timing-grid-2026-11-08.json"
ATTEMPTS = "execution-prompt-2026-11-08-attempts.csv"
SCORING = "appworld-corrected-pilot-scoring-2026-11-08.md"
BROAD = "baseline-qwen8b-2026-11-08-completion.json"
GIB = 1024**3


def run(repo):
    commit = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", f"{SOURCE}^{{commit}}"], text=True
    ).strip()
    records = {
        name: subprocess.check_output(
            ["git", "-C", str(repo), "show", f"{commit}:documents/records/{name}"]
        )
        for name in (COST, ATTEMPTS, SCORING, BROAD)
    }

    grid = json.loads(records[COST])
    grouped = defaultdict(dict)
    for point in grid["main_measured_points"]:
        grouped[point["logical_length"]][point["method"]] = point

    cost_rows = []
    for length in grid["logical_lengths"]:
        methods = grouped[length]
        if set(methods) != {"full", "streamingllm", "rkv", "agentkv"}:
            raise ValueError(f"Incomplete cost grid at {length}")
        metrics = {}
        for method, point in methods.items():
            expected_retention = 1.0 if method == "full" else 0.5
            if point["retention"] != expected_retention:
                raise ValueError(f"Unexpected retention for {method} at {length}")
            metrics[method] = {}
            for key in (
                "decode_tokens_per_second",
                "decode_peak_total_vram_bytes",
                "occupied_kv_bytes",
                "selection_seconds",
            ):
                values = point["metrics"][key]["values"]
                if len(values) != grid["repetitions"]:
                    raise ValueError(f"Incomplete repetitions for {method} at {length}")
                metrics[method][key] = statistics.median(values)
        full = metrics["full"]
        for method, item in metrics.items():
            cost_rows.append(
                {
                    "logical_tokens": length,
                    "method": method,
                    "decode_tok_s": item["decode_tokens_per_second"],
                    "throughput_fraction_of_full": item["decode_tokens_per_second"]
                    / full["decode_tokens_per_second"],
                    "occupied_kv_gib": item["occupied_kv_bytes"] / GIB,
                    "peak_total_vram_gib": item["decode_peak_total_vram_bytes"] / GIB,
                    "peak_total_vram_delta_vs_full_gib": (
                        item["decode_peak_total_vram_bytes"] - full["decode_peak_total_vram_bytes"]
                    )
                    / GIB,
                    "selection_seconds": item["selection_seconds"],
                }
            )

    pairs = defaultdict(dict)
    for row in csv.DictReader(io.StringIO(records[ATTEMPTS].decode())):
        key = (row["task_id"], int(row["seed"]))
        if row["arm"] in pairs[key]:
            raise ValueError(f"Duplicate arm for {key}")
        pairs[key][row["arm"]] = row
    if len(pairs) != 6 or any(set(pair) != {"control", "candidate"} for pair in pairs.values()):
        raise ValueError("Incomplete prompt pairs")

    task_deltas = defaultdict(list)
    paired_rows = []
    for (task, seed), pair in sorted(pairs.items()):
        control, candidate = pair["control"], pair["candidate"]
        delta = float(candidate["elapsed_seconds"]) - float(control["elapsed_seconds"])
        task_deltas[task].append(delta)
        paired_rows.append(
            {
                "task": task,
                "seed": seed,
                "candidate_minus_control_seconds": delta,
                "control_status": control["status"],
                "candidate_status": candidate["status"],
            }
        )
    if len(task_deltas) != 3 or any(len(values) != 2 for values in task_deltas.values()):
        raise ValueError("Expected three task clusters with two seeds each")

    task_means = {task: statistics.mean(values) for task, values in task_deltas.items()}
    leave_one_out = {
        omitted: statistics.mean(value for task, value in task_means.items() if task != omitted)
        for omitted in task_means
    }
    broad = json.loads(records[BROAD])
    statuses = Counter(row["status"] for row in broad["attempts"])
    timeout_reasons = Counter(
        row["failure_reason"] for row in broad["attempts"] if row["status"] == "timeout"
    )
    if len(broad["attempts"]) != 38 or statuses != broad["statuses"]:
        raise ValueError("Broad pilot inventory mismatch")

    return {
        "source_commit": commit,
        "input_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in records.items()},
        "cost_scope": "Qwen3-8B BF16, one fixed history, RTX A6000; ordinary throughput and total VRAM",
        "cost_grid": cost_rows,
        "prompt_latency": {
            "scope": "Matched 8B dev pilot; all terminal cells included; CSV success column unused",
            "pairs": paired_rows,
            "task_mean_candidate_minus_control_seconds": task_means,
            "mean_candidate_minus_control_seconds": statistics.mean(task_means.values()),
            "leave_one_task_out_seconds": leave_one_out,
        },
        "historical_broad_pilot": {
            "scope": "Old sampler defect; descriptive terminal outcomes only",
            "terminal_counts": dict(statuses),
            "timeout_reasons": dict(timeout_reasons),
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.repo), indent=2, sort_keys=True))
