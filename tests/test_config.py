from dataclasses import replace
from pathlib import Path

import pytest

from comet.config import Condition, Experiment, comparison_matrix
from comet.engine.contracts import MODEL_PROFILES, MODEL_REVISION


@pytest.mark.parametrize("model", ["Qwen/Qwen3-14B", "Qwen/Qwen3-4B-Instruct-2507"])
def test_exploratory_models_are_explicit_pinned_pilot_only(model):
    base = Experiment.load(Path(__file__).resolve().parents[1] / "configs/pilot-smoke.json")
    assert base.engine.model == "Qwen/Qwen3-8B"
    revision = MODEL_PROFILES[model]["revision"]
    exploratory = replace(base, engine=replace(
        base.engine, model=model, model_revision=revision, tokenizer_revision=revision,
    ))
    exploratory.validate()
    for stage, split in (("final", "test_normal"), ("diagnostic", "dev")):
        with pytest.raises(ValueError, match="exploratory pilot"):
            replace(exploratory, stage=stage, split=split).validate(allow_unfrozen=True)
    for changes in ({"model": "Qwen/Qwen3-8B"}, {"model_revision": MODEL_REVISION},
                    {"tokenizer_revision": MODEL_REVISION}, {"model_revision": "a" * 40}):
        with pytest.raises(ValueError, match="model/revision"):
            replace(exploratory, engine=replace(exploratory.engine, **changes)).validate()
    with pytest.raises(ValueError, match="BF16"):
        replace(exploratory, engine=replace(exploratory.engine, dtype="float16")).validate()
    thinking = replace(exploratory, sampling=replace(exploratory.sampling, enable_thinking=True))
    if MODEL_PROFILES[model]["supports_thinking"]:
        thinking.validate()
    else:
        with pytest.raises(ValueError, match="requires enable_thinking=false"):
            thinking.validate()


@pytest.mark.parametrize("suffix", ["", "-qwen14b"])
def test_baseline_prompt_comparison_keeps_settings_paired(suffix):
    root = Path(__file__).resolve().parents[1] / "configs"
    control = Experiment.load(root / f"pilot-baseline-control{suffix}.json")
    repair = Experiment.load(root / f"pilot-baseline-repair{suffix}.json")
    assert replace(repair, experiment_id=control.experiment_id,
                   prompt=control.prompt, notes=control.notes) == control
    original = Experiment.load(root / "pilot-completion.json")
    assert control.prompt == original.prompt
    assert repair.prompt != control.prompt
    assert repair.stage == "pilot" and repair.split == "dev" and repair.frozen is None
    assert all(c.method == "full" and c.recovery == "never" for c in repair.conditions)


@pytest.mark.parametrize("limit", [-1, True, 1.5, float("inf")])
def test_agent_failure_limit_is_explicit_nonnegative_integer(limit):
    base = Experiment.load(Path(__file__).resolve().parents[1] / "configs/pilot-smoke.json")
    assert base.agent.max_consecutive_errors == 0
    raw = base.to_dict()
    raw["agent"] = {"max_consecutive_errors": limit}
    with pytest.raises(ValueError, match="max_consecutive_errors"):
        Experiment.from_dict(raw)


@pytest.mark.parametrize("value", [0, 1, None, "true"])
def test_executable_action_requirement_rejects_nonboolean_values(value):
    base = Experiment.load(Path(__file__).resolve().parents[1] / "configs/pilot-smoke.json")
    assert base.agent.require_executable is False
    raw = base.to_dict()
    raw["agent"] = {"require_executable": value}
    with pytest.raises(ValueError, match="require_executable"):
        Experiment.from_dict(raw)


def test_executable_action_option_preserves_historical_identity_until_enabled():
    base = Experiment.load(Path(__file__).resolve().parents[1] /
                           "configs/pilot-execution-candidate-qwen4b-instruct-v1.json")
    assert base.digest == "31986e7f626c07ba42da89ded3d716b826a3bea8c9f043a377e19f510d420855"
    candidate = replace(base, agent=replace(base.agent, require_executable=True))
    assert candidate.agent.max_consecutive_errors == 0
    assert candidate.digest != base.digest
    assert candidate.settings_digest != base.settings_digest
    assert Experiment.from_dict(candidate.to_dict()) == candidate


def test_action_validation_diagnostic_changes_only_executable_requirement():
    root = Path(__file__).resolve().parents[1] / "configs"
    control = Experiment.load(root / "pilot-action-validation-control-qwen4b-v1.json")
    candidate = Experiment.load(root / "pilot-action-validation-candidate-qwen4b-v1.json")
    assert replace(candidate, experiment_id=control.experiment_id, agent=control.agent) == control
    assert control.agent.require_executable is False
    assert candidate.agent.require_executable is True
    assert candidate.agent.max_consecutive_errors == 0
    assert control.task_ids == ["23cf851_1"] and control.seeds == [17, 18]


def test_corrected_sampler_protocol_comparison_changes_only_agent_policy():
    root = Path(__file__).resolve().parents[1] / "configs"
    control = Experiment.load(root / "pilot-sampling-control-qwen8b.json")
    candidate = Experiment.load(root / "pilot-agent-guard-qwen8b.json")
    assert replace(candidate, experiment_id=control.experiment_id, notes=control.notes,
                   agent=control.agent) == control
    assert control.agent.max_consecutive_errors == 0
    assert candidate.agent.max_consecutive_errors == 5
    assert candidate.seeds == [17, 18] and len(candidate.task_ids) == 3


def test_declared_intermediate_retention_keeps_core_matrix_unchanged():
    base = Experiment.load(Path(__file__).resolve().parents[1] / "configs/pilot-smoke.json")
    conditions = [Condition(f"agentkv_{percent}", "agentkv", percent / 100, "never", 1)
                  for percent in (25, 30, 40, 50, 60, 70, 80, 90)]
    granular = replace(base, experiment_id="declared-granularity-fixture", conditions=conditions)
    granular.validate()
    assert Experiment.from_dict(granular.to_dict()) == granular
    core = comparison_matrix(3)
    assert len(core) == 29
    assert {condition.retention for condition in core if condition.method != "full"} == {0.8, 0.5, 0.25}
