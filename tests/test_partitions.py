import json
from pathlib import Path

import pytest

from comet.artifacts import write_json
from comet.config import Experiment, comparison_matrix
from comet.partitions import partition_study


def frozen_parent(tmp_path):
    data = Experiment.load(Path(__file__).parent / "fixtures/full-cache.json").to_dict()
    from dataclasses import asdict

    data.update(stage="final", split="test_normal", task_ids=["task1", "task2"],
                conditions=[asdict(c) for c in comparison_matrix(data["max_attempts"])])
    data["frozen"] = {
        "settings_digest": Experiment.from_dict(data, allow_unfrozen=True).settings_digest,
        "pilot_evidence": [{"run_id": "fixture"}],
    }
    path = tmp_path / "parent.json"
    write_json(path, data)
    return path


def test_partitioning_preserves_settings_evidence_and_exact_coverage(tmp_path):
    parent = frozen_parent(tmp_path)
    original = parent.read_bytes()
    output = tmp_path / "partitions"
    index = partition_study(parent, output, 8)
    study = Experiment.load(parent)
    conditions = []
    sizes = []
    for entry in index["partitions"]:
        part = Experiment.load(output / entry["config"])
        assert part.digest == entry["digest"]
        assert part.frozen["condition_partition_of"] == study.digest
        assert part.frozen["pilot_evidence"] == study.frozen["pilot_evidence"]
        settings = part.to_dict()
        settings.update(conditions=study.to_dict()["conditions"], frozen=study.frozen)
        assert settings == study.to_dict()
        conditions.extend(part.conditions)
        sizes.append(len(part.conditions))
    assert sorted(c.id for c in conditions) == sorted(c.id for c in study.conditions)
    assert max(sizes) - min(sizes) <= 1
    assert sum(p["cells"] for p in index["partitions"]) == len(study.conditions) * 2
    assert parent.read_bytes() == original
    assert json.loads((output / "index.json").read_text()) == index
    with pytest.raises(FileExistsError):
        partition_study(parent, output, 8)
    with pytest.raises(ValueError, match="not another partition"):
        partition_study(output / "part-00.json", tmp_path / "nested", 1)


@pytest.mark.parametrize("count", [0, -1, 30])
def test_partition_count_is_bounded(tmp_path, count):
    output = tmp_path / "partitions"
    with pytest.raises(ValueError, match="Partition count"):
        partition_study(frozen_parent(tmp_path), output, count)
    assert not output.exists()


def test_unfrozen_or_pilot_studies_cannot_be_partitioned(tmp_path):
    pilot = Path(__file__).parent / "fixtures/full-cache.json"
    with pytest.raises(ValueError, match="frozen parent"):
        partition_study(pilot, tmp_path / "pilot", 1)
    parent = frozen_parent(tmp_path)
    data = json.loads(parent.read_text())
    data["task_ids"].append("unfrozen_change")
    write_json(parent, data)
    with pytest.raises(ValueError, match="matching frozen"):
        partition_study(parent, tmp_path / "invalid", 1)
