"""Create disjoint condition groups without changing a frozen study."""

from __future__ import annotations

import os
from pathlib import Path

from comet.artifacts import write_json
from comet.config import Experiment


def partition_study(config_path: Path, output: Path, count: int) -> dict:
    study = Experiment.load(config_path)
    if study.stage != "final" or study.frozen.get("condition_partition_of"):
        raise ValueError("Partition a frozen parent study, not another partition")
    if not 1 <= count <= len(study.conditions):
        raise ValueError("Partition count must be between one and the condition count")
    records = []
    for index in range(count):
        data = study.to_dict()
        data["conditions"] = data["conditions"][index::count]
        data["frozen"]["condition_partition_of"] = study.digest
        data["frozen"]["settings_digest"] = Experiment.from_dict(
            data, allow_unfrozen=True
        ).settings_digest
        partition = Experiment.from_dict(data)
        records.append((f"part-{index:02d}.json", partition))
    output.mkdir(parents=True, exist_ok=False)
    parent_path = os.path.relpath(config_path.resolve(), output.resolve())
    for filename, partition in records:
        data = partition.to_dict()
        write_json(output / filename, {
            "extends": parent_path,
            "conditions": data["conditions"],
            "frozen": data["frozen"],
        })
    inventory = {
        "study_config": parent_path,
        "study_digest": study.digest,
        "partitions": [
            {"config": filename, "digest": partition.digest,
             "cells": len(partition.conditions) * len(study.task_ids) * len(study.seeds),
             "budget_seconds": len(partition.conditions) * len(study.task_ids)
             * len(study.seeds) * study.budget_seconds}
            for filename, partition in records
        ],
    }
    write_json(output / "index.json", inventory)
    return inventory
