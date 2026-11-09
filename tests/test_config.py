from dataclasses import replace
from pathlib import Path

import pytest

from comet.config import Experiment
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


def test_corrected_sampler_protocol_comparison_changes_only_agent_policy():
    root = Path(__file__).resolve().parents[1] / "configs"
    control = Experiment.load(root / "pilot-sampling-control-qwen8b.json")
    candidate = Experiment.load(root / "pilot-agent-guard-qwen8b.json")
    assert replace(candidate, experiment_id=control.experiment_id, notes=control.notes,
                   agent=control.agent) == control
    assert control.agent.max_consecutive_errors == 0
    assert candidate.agent.max_consecutive_errors == 5
    assert candidate.seeds == [17, 18] and len(candidate.task_ids) == 3
