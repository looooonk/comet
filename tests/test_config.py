from dataclasses import replace
from pathlib import Path

import pytest

from comet.config import Experiment
from comet.engine.contracts import MODEL_PROFILES, MODEL_REVISION


def test_qwen14b_is_explicit_pinned_pilot_only():
    base = Experiment.load(Path(__file__).resolve().parents[1] / "configs/pilot-smoke.json")
    assert base.engine.model == "Qwen/Qwen3-8B"
    revision = MODEL_PROFILES["Qwen/Qwen3-14B"]["revision"]
    exploratory = replace(base, engine=replace(
        base.engine, model="Qwen/Qwen3-14B", model_revision=revision, tokenizer_revision=revision,
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
