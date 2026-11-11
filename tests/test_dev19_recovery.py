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


def test_dev19_seed_replicate_changes_only_seeds():
    first = Experiment.load(BLACKWELL / "dev19-recovery-v1.json")
    replicate = Experiment.load(BLACKWELL / "dev19-recovery-v2.json")
    assert replicate.seeds == [29, 31] and not set(replicate.seeds) & set(first.seeds)
    changed = {"experiment_id", "seeds", "notes"}
    for name, value in first.to_dict().items():
        if name not in changed:
            assert replicate.to_dict()[name] == value, name
    parent = {k: v for k, v in replicate.to_dict().items() if k not in ("conditions", "notes")}
    seen = []
    for path in sorted((BLACKWELL / "dev19-recovery-v2-parts").glob("part-*.json")):
        part = Experiment.load(path)
        assert {k: v for k, v in part.to_dict().items() if k not in ("conditions", "notes")} == parent
        seen += [condition.id for condition in part.conditions]
    assert sorted(seen) == sorted(condition.id for condition in replicate.conditions)


def test_dev19_frontier_extends_the_first_study_with_a_finer_retention_grid():
    first = Experiment.load(BLACKWELL / "dev19-recovery-v1.json")
    frontier = Experiment.load(BLACKWELL / "dev19-frontier-v1.json")
    changed = {"experiment_id", "conditions", "notes"}
    for name, value in first.to_dict().items():
        if name not in changed:
            assert frontier.to_dict()[name] == value, name
    compressed = [c for c in frontier.conditions if c.method != "full"]
    assert {c.method for c in compressed} == {"rkv", "agentkv"}
    assert {c.retention for c in compressed} == {0.7, 0.6, 0.5, 0.4, 0.3}
    assert {c.recovery for c in compressed} == {"never", "fixed"}
    assert len(compressed) == 20 and all(c.max_attempts == 2 for c in compressed)
    assert [c.id for c in frontier.conditions if c.method == "full"] == ["full_best_of_n"]
    parent = {k: v for k, v in frontier.to_dict().items() if k not in ("conditions", "notes")}
    seen = []
    for path in sorted((BLACKWELL / "dev19-frontier-v1-parts").glob("part-*.json")):
        part = Experiment.load(path)
        assert {k: v for k, v in part.to_dict().items() if k not in ("conditions", "notes")} == parent
        seen += [condition.id for condition in part.conditions]
    assert sorted(seen) == sorted(condition.id for condition in frontier.conditions)


def test_dev19_trigger_timing_changes_only_the_fixed_threshold_at_half_retention():
    first = Experiment.load(BLACKWELL / "dev19-recovery-v1.json")
    reference = {c.id: c for c in first.conditions}
    thresholds = []
    for path in sorted((BLACKWELL / "dev19-trigger-v1").glob("fixed-*.json")):
        study = Experiment.load(path)
        thresholds.append(study.triggers.fixed_tool_calls)
        assert study.experiment_id == f"qwen9b-dev19-trigger-fixed{thresholds[-1]}-blackwell-v1"
        assert [c.id for c in study.conditions] == ["agentkv_50_fixed", "rkv_50_fixed"]
        assert all(c == reference[c.id] for c in study.conditions)
        expected = {**first.to_dict()["triggers"], "fixed_tool_calls": thresholds[-1]}
        assert study.to_dict()["triggers"] == expected
        changed = {"experiment_id", "conditions", "triggers", "notes"}
        for name, value in first.to_dict().items():
            if name not in changed:
                assert study.to_dict()[name] == value, name
    assert sorted(thresholds) == [1, 2, 6, 8] and first.triggers.fixed_tool_calls == 4
