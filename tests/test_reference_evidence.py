import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_reference_gpu as reference

from comet.artifacts import read_json, write_json
from comet.engine.contracts import MODEL_REVISION


@pytest.mark.parametrize("phase", ["native", "reference"])
def test_reference_failure_retains_completed_cases_and_current_case(tmp_path, monkeypatch, phase):
    def save(tensors, path):
        path.write_text(json.dumps(tensors))

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(save=save))

    def fail(root):
        reference._record_progress(root, phase, identity={"model": "fixture"},
                                   current={"stage": "case_completed", "id": "first/fresh"},
                                   records=[{"id": "first/fresh"}], tensors={"first/fresh": [1, 2]})
        reference._record_progress(root, phase, current={"stage": "generation", "id": "second/cached"})
        raise AssertionError("fixture logit mismatch")

    monkeypatch.setattr(reference, f"_{phase}", fail)
    with pytest.raises(AssertionError, match="fixture"):
        reference._run_phase(phase, tmp_path)

    progress = read_json(tmp_path / f"{phase}-partial.json")
    assert progress["status"] == "failed" and progress["complete"] is False
    assert progress["identity"] == {"model": "fixture"}
    assert progress["current"] == {"stage": "generation", "id": "second/cached"}
    assert progress["records"] == [{"id": "first/fresh"}]
    assert progress["error"] == "AssertionError: fixture logit mismatch"
    checkpoint = tmp_path / f"{phase}-partial-logits.pt"
    assert progress["logits_sha256"] == hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    assert json.loads(checkpoint.read_text()) == {"first/fresh": [1, 2]}
    assert not list(tmp_path.glob("*.tmp"))
    assert not (tmp_path / "comparison.json").exists()
    assert not (tmp_path / "native.json").exists()


def test_reference_startup_failure_is_explicit_without_tensor_dependencies(tmp_path, monkeypatch):
    def fail(root):
        raise ImportError("fixture dependency unavailable")

    monkeypatch.setattr(reference, "_native", fail)
    with pytest.raises(ImportError):
        reference._run_phase("native", tmp_path)
    progress = read_json(tmp_path / "native-partial.json")
    assert progress["status"] == "failed"
    assert progress["current"] == {"stage": "startup"}
    assert progress["records"] == [] and "logits_sha256" not in progress


def test_success_keeps_complete_output_schema_and_supersedes_partial_journal(tmp_path, monkeypatch):
    expected = {"passed": True, "records": [{"id": "fixture"}]}

    def success(root):
        write_json(root / "comparison.json", expected)

    monkeypatch.setattr(reference, "_reference", success)
    reference._run_phase("reference", tmp_path)
    assert read_json(tmp_path / "comparison.json") == expected
    progress = read_json(tmp_path / "reference-partial.json")
    assert progress["complete"] is False
    assert progress["status"] == "superseded_by_complete_artifacts"
    assert progress["current"] is None


@pytest.mark.parametrize("generation_raises", [False, True])
def test_first_native_case_saves_actual_capture_before_assertion(tmp_path, monkeypatch, generation_raises):
    class Tensor(list):
        @property
        def shape(self):
            return (len(self), len(self[0])) if self and isinstance(self[0], list) else (len(self),)

        def __getitem__(self, key):
            value = super().__getitem__(key)
            return Tensor(value) if isinstance(value, list) else value

        def detach(self):
            return self

        float = cpu = detach

        def clone(self):
            return Tensor(self)

    sampler = SimpleNamespace(sample=lambda logits, args: [1])
    engine = SimpleNamespace(
        scheduler=SimpleNamespace(engine=SimpleNamespace(sampler=sampler)), raw_token_ids=[],
        tokenizer=SimpleNamespace(apply_chat_template=lambda *args, **kwargs: [3, 4]),
        start=lambda seed: None, close=lambda: None, last_generation={},
    )

    def generate(prompt, *args, **kwargs):
        sampler.sample(Tensor([[0.0, 2.0, 1.0]]), SimpleNamespace(temperatures=None))
        engine.raw_token_ids = prompt + [1]
        engine.last_generation = {"token_ids": [1]}
        if generation_raises:
            raise RuntimeError("failure after first capture")
        return SimpleNamespace(token_ids=[1])

    engine.generate = generate
    monkeypatch.setattr(reference, "MiniSGLangEngine", lambda settings: engine)
    monkeypatch.setattr(reference, "_identity", lambda: (Path("/fixture"), {
        "model": "Qwen/Qwen3-8B", "model_revision": MODEL_REVISION,
        "tokenizer_revision": MODEL_REVISION,
    }))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        stack=lambda tensors: Tensor(tensors),
        save=lambda tensors, path: path.write_text(json.dumps(tensors)),
    ))

    with pytest.raises(RuntimeError if generation_raises else AssertionError):
        reference._run_phase("native", tmp_path)

    progress = read_json(tmp_path / "native-partial.json")
    assert progress["status"] == "failed" and progress["complete"] is False
    assert progress["records"] == []
    pending = progress["unvalidated_current"]
    assert pending["id"] == "python_no_thinking/fresh"
    assert pending["validation_status"] == "unvalidated"
    assert pending["input_token_ids"] == [3, 4]
    assert pending["generated_token_ids"] == [1]
    assert pending["observed_raw_token_ids"] == [3, 4, 1]
    assert pending["generation_returned"] is not generation_raises
    checkpoint = read_json(tmp_path / "native-partial-logits.pt")
    assert checkpoint[pending["logits_key"]] == [[0.0, 2.0, 1.0]]
    assert not (tmp_path / "native.json").exists()
