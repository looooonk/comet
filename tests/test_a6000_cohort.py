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
    for name in ("dev19-core-v1", "dev19-prefill-v1", "dev38-recovery-v1", "dev19-retry-v1",
                 "dev19-controls-v1", "dev38-controls-v1"):
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


def test_a6000_controls_add_only_conditions_and_symptom_markers_to_their_reference_studies():
    studies = {}
    for name, reference in (("dev19-controls-v1", "dev19-core-v1"), ("dev38-controls-v1", "dev38-recovery-v1")):
        study, base = Experiment.load(CONFIGS / f"a6000/{name}.json"), Experiment.load(CONFIGS / f"a6000/{reference}.json")
        assert study.retention_diagnostic and not base.retention_diagnostic
        plain = Experiment.from_dict({k: v for k, v in study.to_dict().items() if k != "retention_diagnostic"})
        assert differing(plain, base) == {"experiment_id", "notes", "conditions", "triggers"}
        triggers = study.to_dict()["triggers"]
        assert len(triggers.pop("symptom_markers")) == 5 and triggers == base.to_dict()["triggers"]
        assert study.seeds == [17, 29, 31] and study.stage == "pilot" and study.split == "dev"
        assert all(c.retention == 0.5 and c.max_attempts == 2 for c in study.conditions)
        studies[name] = study
    dev19, dev38 = studies["dev19-controls-v1"], studies["dev38-controls-v1"]
    assert [c for c in dev19.conditions if c.method == "agentkv"] == dev38.conditions
    assert {c.id: (c.method, c.recovery, c.protect_prompt, c.reminder) for c in dev19.conditions} == {
        "agentkv_50_protect_never": ("agentkv", "never", True, False),
        "agentkv_50_protect_fixed": ("agentkv", "fixed", True, False),
        "agentkv_50_remind_never": ("agentkv", "never", False, True),
        "agentkv_50_symptom": ("agentkv", "symptom", False, False),
        "streamingllm_50_protect_never": ("streamingllm", "never", True, False),
        "rkv_50_protect_never": ("rkv", "never", True, False),
    }


def test_a6000_controls_smoke_keeps_one_unchanged_arm_for_a_token_comparison():
    core = Experiment.load(CONFIGS / "a6000/dev19-core-v1.json")
    controls = Experiment.load(CONFIGS / "a6000/dev19-controls-v1.json")
    smoke = Experiment.load(CONFIGS / "a6000/controls-smoke-v1.json")
    assert differing(smoke, controls) == {"experiment_id", "notes", "conditions", "task_ids", "seeds"}
    assert smoke.task_ids == core.task_ids[:2] and smoke.seeds == [17]
    unchanged = next(c for c in core.conditions if c.id == "agentkv_50_never")
    assert smoke.conditions == [unchanged, *controls.conditions]


def test_a6000_retention80_study_changes_only_the_conditions_of_the_controls_study():
    controls = Experiment.load(CONFIGS / "a6000/dev19-controls-v1.json")
    study = Experiment.load(CONFIGS / "a6000/dev19-retention80-v1.json")
    assert differing(study, controls) == {"experiment_id", "notes", "conditions"}
    assert [(c.id, c.method, c.retention, c.recovery, c.max_attempts, c.protect_prompt, c.reminder)
            for c in study.conditions] == [
        ("agentkv_80_never", "agentkv", 0.8, "never", 2, False, False),
        ("agentkv_80_fixed", "agentkv", 0.8, "fixed", 2, False, False),
        ("agentkv_80_symptom", "agentkv", 0.8, "symptom", 2, False, False),
    ]
    parent = {k: v for k, v in study.to_dict().items() if k not in ("conditions", "notes")}
    paths = sorted((CONFIGS / "a6000/dev19-retention80-v1-parts").glob("part-*.json"))
    seen = []
    for path in paths:
        part = Experiment.load(path)
        assert {k: v for k, v in part.to_dict().items() if k not in ("conditions", "notes")} == parent
        seen += [condition.id for condition in part.conditions]
    assert len(paths) == 3 and seen == [condition.id for condition in study.conditions]



def test_a6000_prompt_budget_studies_change_only_the_conditions_of_the_controls_studies():
    expected = [
        ("agentkv_50_pinned_extra_never", "never", True, True),
        ("agentkv_50_pinned_extra_fixed", "fixed", True, True),
        ("agentkv_50_extra_never", "never", False, True),
    ]
    for key in ("dev19", "dev38"):
        study = Experiment.load(CONFIGS / f"a6000/{key}-prompt-budget-v1.json")
        controls = Experiment.load(CONFIGS / f"a6000/{key}-controls-v1.json")
        assert differing(study, controls) == {"experiment_id", "notes", "conditions"}
        assert [(c.id, c.recovery, c.protect_prompt, c.prompt_outside_budget)
                for c in study.conditions] == expected
        assert all((c.method, c.retention, c.max_attempts, c.reminder) == ("agentkv", 0.5, 2, False)
                   for c in study.conditions)
        parent = {k: v for k, v in study.to_dict().items() if k not in ("conditions", "notes")}
        paths = sorted((CONFIGS / f"a6000/{key}-prompt-budget-v1-parts").glob("part-*.json"))
        seen = []
        for path in paths:
            part = Experiment.load(path)
            assert {k: v for k, v in part.to_dict().items() if k not in ("conditions", "notes")} == parent
            seen += [condition.id for condition in part.conditions]
        assert len(paths) == 3 and seen == [condition.id for condition in study.conditions]


def test_a6000_prompt_budget_smoke_keeps_the_unchanged_arm_and_the_inside_budget_arm():
    core = Experiment.load(CONFIGS / "a6000/dev19-core-v1.json")
    controls = Experiment.load(CONFIGS / "a6000/dev19-controls-v1.json")
    study = Experiment.load(CONFIGS / "a6000/dev19-prompt-budget-v1.json")
    smoke = Experiment.load(CONFIGS / "a6000/prompt-budget-smoke-v1.json")
    assert differing(smoke, study) == {"experiment_id", "notes", "conditions", "task_ids", "seeds"}
    assert smoke.task_ids == core.task_ids[:2] and smoke.seeds == [17]
    unchanged = next(c for c in core.conditions if c.id == "agentkv_50_never")
    inside = next(c for c in controls.conditions if c.id == "agentkv_50_protect_never")
    assert smoke.conditions == [unchanged, inside, *study.conditions]
