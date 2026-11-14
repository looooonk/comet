from pathlib import Path

from comet.config import Experiment

CONFIGS = Path(__file__).resolve().parents[1] / "configs/qwen9b"
DEVICE = "NVIDIA RTX A6000"


def differing(left: Experiment, right: Experiment) -> set[str]:
    return {name for name, value in left.to_dict().items() if right.to_dict()[name] != value}


def assert_only_the_device_differs(left: Experiment, right: Experiment) -> None:
    assert left.engine.device_name == DEVICE
    engine = {k: v for k, v in left.to_dict()["engine"].items() if k != "device_name"}
    assert engine == {k: v for k, v in right.to_dict()["engine"].items() if k != "device_name"}


def test_a6000_qualification_inputs_change_only_the_device():
    for mine, theirs in (("a6000/smoke-v1.json", "blackwell/test50-smoke-v1.json"),
                         ("a6000/resume-check-v1.json", "checks/resume-blackwell-v2.json")):
        left, right = Experiment.load(CONFIGS / mine), Experiment.load(CONFIGS / theirs)
        assert differing(left, right) == {"engine", "experiment_id", "notes"}
        assert_only_the_device_differs(left, right)


def test_a6000_confirmation_and_prefill_studies_change_only_the_device():
    for name in ("dev38-recovery-v1", "dev19-prefill-v1"):
        left, right = Experiment.load(CONFIGS / f"a6000/{name}.json"), Experiment.load(CONFIGS / f"blackwell/{name}.json")
        assert differing(left, right) == {"engine", "experiment_id", "notes"}
        assert_only_the_device_differs(left, right)


def test_a6000_core_study_reruns_first_study_arms_on_the_same_tasks():
    first = Experiment.load(CONFIGS / "blackwell/dev19-recovery-v1.json")
    core = Experiment.load(CONFIGS / "a6000/dev19-core-v1.json")
    reference = {condition.id: condition for condition in first.conditions}
    expected = {"full_best_of_n", "agentkv_50_never", "agentkv_50_fixed", "agentkv_50_dynamic",
                "rkv_50_never", "streamingllm_50_never", "agentkv_25_never"}
    assert {condition.id for condition in core.conditions} == expected
    assert all(condition == reference[condition.id] for condition in core.conditions)
    assert core.task_ids == first.task_ids and core.seeds == [17, 29, 31]
    assert differing(core, first) == {"engine", "experiment_id", "notes", "seeds", "conditions"}
    assert_only_the_device_differs(core, first)


def test_a6000_parts_cover_every_condition_once_without_changing_settings():
    for name in ("dev19-core-v1", "dev19-prefill-v1", "dev38-recovery-v1", "dev19-retry-v1"):
        study = Experiment.load(CONFIGS / f"a6000/{name}.json")
        parent = {k: v for k, v in study.to_dict().items() if k not in ("conditions", "notes")}
        seen = []
        paths = sorted((CONFIGS / f"a6000/{name}-parts").glob("part-*.json"))
        assert len(paths) == 4
        for path in paths:
            part = Experiment.load(path)
            assert {k: v for k, v in part.to_dict().items() if k not in ("conditions", "notes")} == parent
            seen += [condition.id for condition in part.conditions]
        assert sorted(seen) == sorted(condition.id for condition in study.conditions)


def test_a6000_retry_study_runs_single_attempts_of_the_core_arms_at_new_seeds():
    core = Experiment.load(CONFIGS / "a6000/dev19-core-v1.json")
    retry = Experiment.load(CONFIGS / "a6000/dev19-retry-v1.json")
    reference = {condition.id: condition for condition in core.conditions}
    assert retry.task_ids == core.task_ids
    assert retry.seeds == [37, 41, 43, 47, 53] and not set(retry.seeds) & set(core.seeds)
    twins = {"full_once": "full_best_of_n", "agentkv_50_never_once": "agentkv_50_never",
             "agentkv_50_fixed_once": "agentkv_50_fixed", "agentkv_50_dynamic_once": "agentkv_50_dynamic"}
    assert [condition.id for condition in retry.conditions] == list(twins)
    for condition in retry.conditions:
        twin = reference[twins[condition.id]]
        # Same arm as the core study, limited to its first attempt.
        assert (condition.method, condition.retention, condition.recovery) == (twin.method, twin.retention, twin.recovery)
        assert condition.max_attempts == 1 and twin.max_attempts == 2
    assert differing(retry, core) == {"experiment_id", "notes", "seeds", "conditions"}
