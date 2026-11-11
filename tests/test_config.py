from dataclasses import replace
from pathlib import Path

import pytest

from comet.config import Condition, EnvironmentWarmup, Experiment, comparison_matrix
from comet.engine.contracts import MODEL_PROFILES, MODEL_REVISION


@pytest.mark.parametrize("model", ["Qwen/Qwen3-14B", "Qwen/Qwen3-4B-Instruct-2507"])
def test_exploratory_models_are_explicit_pinned_pilot_only(model):
    base = Experiment.load(Path(__file__).resolve().parents[1] / "configs/examples/pilot-smoke.json")
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


@pytest.mark.parametrize("limit", [-1, True, 1.5, float("inf")])
def test_agent_failure_limit_is_explicit_nonnegative_integer(limit):
    base = Experiment.load(Path(__file__).resolve().parents[1] / "configs/examples/pilot-smoke.json")
    assert base.agent.max_consecutive_errors == 0
    raw = base.to_dict()
    raw["agent"] = {"max_consecutive_errors": limit}
    with pytest.raises(ValueError, match="max_consecutive_errors"):
        Experiment.from_dict(raw)


@pytest.mark.parametrize("value", [0, 1, None, "true"])
def test_executable_action_requirement_rejects_nonboolean_values(value):
    base = Experiment.load(Path(__file__).resolve().parents[1] / "configs/examples/pilot-smoke.json")
    assert base.agent.require_executable is False
    raw = base.to_dict()
    raw["agent"] = {"require_executable": value}
    with pytest.raises(ValueError, match="require_executable"):
        Experiment.from_dict(raw)


def test_executable_action_option_preserves_historical_identity_until_enabled():
    base = Experiment.load(Path(__file__).resolve().parents[1] /
                           "tests/fixtures/legacy-qwen4b.json")
    assert base.digest == "31986e7f626c07ba42da89ded3d716b826a3bea8c9f043a377e19f510d420855"
    candidate = replace(base, agent=replace(base.agent, require_executable=True))
    assert candidate.agent.max_consecutive_errors == 0
    assert candidate.digest != base.digest
    assert candidate.settings_digest != base.settings_digest
    assert Experiment.from_dict(candidate.to_dict()) == candidate


@pytest.mark.parametrize("settings", [EnvironmentWarmup("", 0), EnvironmentWarmup("../task", 0),
                                      EnvironmentWarmup("train_1", True), EnvironmentWarmup("train_1", -1),
                                      EnvironmentWarmup("train_1", 1.5)])
def test_environment_warmup_requires_explicit_valid_identity(settings):
    base = Experiment.load(Path(__file__).resolve().parents[1] / "configs/examples/pilot-smoke.json")
    with pytest.raises(ValueError, match="environment_warmup"):
        replace(base, environment_warmup=settings).validate()


def test_environment_warmup_participates_in_frozen_settings():
    base = Experiment.load(Path(__file__).resolve().parents[1] / "configs/examples/pilot-smoke.json")
    assert "environment_warmup" not in base.to_dict()
    warmed = replace(base, environment_warmup=EnvironmentWarmup("82e2fac_1", 0))
    assert warmed.digest != base.digest and warmed.settings_digest != base.settings_digest
    assert Experiment.from_dict(warmed.to_dict()) == warmed


def test_declared_intermediate_retention_keeps_core_matrix_unchanged():
    base = Experiment.load(Path(__file__).resolve().parents[1] / "configs/examples/pilot-smoke.json")
    conditions = [Condition(f"agentkv_{percent}", "agentkv", percent / 100, "never", 1)
                  for percent in (25, 30, 40, 50, 60, 70, 80, 90)]
    granular = replace(base, experiment_id="declared-granularity-fixture", conditions=conditions)
    granular.validate()
    assert Experiment.from_dict(granular.to_dict()) == granular
    core = comparison_matrix(3)
    assert len(core) == 29
    assert {condition.retention for condition in core if condition.method != "full"} == {0.8, 0.5, 0.25}
