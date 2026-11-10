import hashlib
import json
from pathlib import Path

from comet.config import Experiment, comparison_matrix

BLACKWELL = Path(__file__).resolve().parents[1] / "configs/qwen9b/blackwell"
RECORDS = Path(__file__).resolve().parents[1] / "documents/records/qwen9b"


def test_dev19_recovery_matches_qualified_dev_settings_and_core_matrix():
    study = Experiment.load(BLACKWELL / "dev19-recovery-v1.json")
    reference = Experiment.load(BLACKWELL / "dev-v1.json")
    assert (study.stage, study.split, study.seeds) == ("pilot", "dev", [17])
    changed = {"experiment_id", "task_ids", "conditions", "notes"}
    for name, value in reference.to_dict().items():
        if name not in changed:
            assert study.to_dict()[name] == value, name
    assert study.conditions == comparison_matrix(study.max_attempts)
    assert len(study.conditions) == 29 and study.max_attempts == 2


def test_dev19_task_selection_follows_the_recorded_rule():
    study = Experiment.load(BLACKWELL / "dev19-recovery-v1.json")
    record = json.loads((RECORDS / "dev19-recovery-selection.json").read_text())
    namespace = record["namespace"]

    def rank(task_id):
        return hashlib.sha256(f"{namespace}:variant:{task_id}".encode()).hexdigest()

    families = record["families"]
    assert len(families) == 19 and sorted(families) == families
    expected = [min((f"{family}_{v}" for v in (1, 2, 3)), key=rank) for family in families]
    assert study.task_ids == expected == record["task_ids"]


def test_dev19_parts_cover_every_condition_once_without_changing_settings():
    study = Experiment.load(BLACKWELL / "dev19-recovery-v1.json")
    parent = {k: v for k, v in study.to_dict().items() if k not in ("conditions", "notes")}
    seen = []
    for path in sorted((BLACKWELL / "dev19-recovery-v1-parts").glob("part-*.json")):
        part = Experiment.load(path)
        assert {k: v for k, v in part.to_dict().items() if k not in ("conditions", "notes")} == parent
        assert all(condition in study.conditions for condition in part.conditions)
        seen += [condition.id for condition in part.conditions]
    assert sorted(seen) == sorted(condition.id for condition in study.conditions)
