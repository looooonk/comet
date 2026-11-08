import runpy
from pathlib import Path

import pytest

from comet.artifacts import write_json
from comet.engine.contracts import MODEL_PROFILES

calibration = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/calibrate_reference_cpu.py"))


def write_source(root, identity):
    for name in ("native-logits.pt", "reference-logits.pt"):
        (root / name).write_bytes(name.encode())
    records = [{"id": f"case{index}", "generated_token_ids": [1, 2, 3, 4]} for index in range(6)]
    native = {"identity": identity, "records": records,
              "logits_sha256": calibration["sha256"](root / "native-logits.pt")}
    write_json(root / "native.json", native)
    comparison = {"identity": identity, "records": records, "artifacts_sha256": {
        name: calibration["sha256"](root / name)
        for name in ("native.json", "native-logits.pt", "reference-logits.pt")}}
    write_json(root / "comparison.json", comparison)
    return native, comparison


@pytest.mark.parametrize("model", ["Qwen/Qwen3-8B", "Qwen/Qwen3-14B"])
def test_calibration_source_accepts_registered_pinned_identity(tmp_path, model):
    revision = MODEL_PROFILES[model]["revision"]
    expected = write_source(tmp_path, {"model": model, "model_revision": revision,
                                       "tokenizer_revision": revision})
    native, comparison, hashes = calibration["read_source"](tmp_path)
    assert (native, comparison) == expected
    assert hashes == {name: calibration["sha256"](tmp_path / name)
                      for name in calibration["SOURCE_FILES"]}


@pytest.mark.parametrize("changes", [
    {"model": "Qwen/Qwen3.5-9B"},
    {"model_revision": MODEL_PROFILES["Qwen/Qwen3-8B"]["revision"]},
    {"tokenizer_revision": MODEL_PROFILES["Qwen/Qwen3-8B"]["revision"]},
    {"model_revision": "main", "tokenizer_revision": "main"},
])
def test_calibration_source_rejects_unsupported_or_mismatched_pins(tmp_path, changes):
    revision = MODEL_PROFILES["Qwen/Qwen3-14B"]["revision"]
    write_source(tmp_path, {"model": "Qwen/Qwen3-14B", "model_revision": revision,
                            "tokenizer_revision": revision, **changes})
    with pytest.raises(ValueError, match="recorded model/revision pair"):
        calibration["read_source"](tmp_path)


@pytest.mark.parametrize("corruption", ["identity", "artifact_hash", "native_hash"])
def test_calibration_source_keeps_identity_and_artifact_checks(tmp_path, corruption):
    revision = MODEL_PROFILES["Qwen/Qwen3-14B"]["revision"]
    native, comparison = write_source(tmp_path, {
        "model": "Qwen/Qwen3-14B", "model_revision": revision, "tokenizer_revision": revision})
    if corruption == "identity":
        comparison["identity"] = {**comparison["identity"], "model": "Qwen/Qwen3-8B"}
    elif corruption == "artifact_hash":
        comparison["artifacts_sha256"]["reference-logits.pt"] = "invalid"
    else:
        native["logits_sha256"] = "invalid"
        write_json(tmp_path / "native.json", native)
        comparison["artifacts_sha256"]["native.json"] = calibration["sha256"](tmp_path / "native.json")
    write_json(tmp_path / "comparison.json", comparison)
    with pytest.raises(ValueError, match="inconsistent identities|artifact hash differs|native logits hash differs"):
        calibration["read_source"](tmp_path)
