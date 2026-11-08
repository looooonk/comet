"""Opt-in numerical cross-check; Transformers is never an experiment backend."""

import hashlib
import importlib.metadata
import inspect
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import pytest

from comet.artifacts import read_json, write_json
from comet.engine import EngineSettings, MiniSGLangEngine
from comet.engine.contracts import MODEL_PROFILES, model_storage

TOLERANCES = {
    "centered_rmse": 0.20,
    "centered_relative_rmse": 0.02,
    "jensen_shannon_nats": 0.002,
    "greedy_regret": 0.125,
    "minimum_exact_greedy_agreement": 0.90,
}
CASES = [
    {"id": "python_no_thinking", "thinking": False, "messages": [
        {"role": "user", "content": "Return exactly this statement in a fenced python block: print(7)"},
    ]},
    {"id": "arithmetic_thinking", "thinking": True, "messages": [
        {"role": "user", "content": "What is 17 times 19?"},
    ]},
    {"id": "tool_history_chunked", "thinking": False, "messages": [
        {"role": "user", "content": "Remember that the project color is cobalt. "
         + "Notes: one two three four. " * 16},
        {"role": "assistant", "content": "The project color is cobalt."},
        {"role": "user", "content": '<tool_response>\n{"project": "COMET", "color": "cobalt"}'
         '\n</tool_response>\nReturn the color.'},
    ]},
]


@pytest.mark.gpu
@pytest.mark.skipif(
    os.environ.get("COMET_RUN_GPU_TESTS") != "1" or os.environ.get("COMET_TEST_REFERENCE") != "1",
    reason="set COMET_TEST_REFERENCE=1 with the managed GPU checks",
)
def test_full_cache_against_transformers(tmp_path):
    root = Path(os.environ.get("COMET_CHECK_OUTPUT", tmp_path)).resolve() / "reference"
    root.mkdir(parents=True, exist_ok=False)
    status = {"status": "running", "phases": []}
    try:
        for phase in ("native", "reference"):
            with (root / f"{phase}.log").open("w") as log:
                result = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), phase, str(root)],
                    stdout=log, stderr=subprocess.STDOUT, timeout=900,
                )
            status["phases"].append({"phase": phase, "returncode": result.returncode})
            assert result.returncode == 0, (root / f"{phase}.log").read_text()[-12000:]
        assert read_json(root / "comparison.json")["passed"]
        status["status"] = "passed"
    except BaseException as error:
        status.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        write_json(root / "status.json", status)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _identity():
    model = os.environ.get("COMET_TEST_MODEL", "Qwen/Qwen3-8B")
    revision = MODEL_PROFILES[model]["revision"]
    path = Path(os.environ["COMET_MODEL_PATH"]).resolve()
    _, parameters = model_storage(str(path), revision, model)
    lock = Path(__file__).resolve().parents[1] / "infra/requirements/gpu.lock"
    pins = dict(line.split("==") for line in lock.read_text().splitlines()
                if "==" in line and not line.startswith((" ", "#")))
    packages = {name: importlib.metadata.version(name) for name in
                ("torch", "transformers", "safetensors", "accelerate", "flashinfer-python")}
    for name, version in packages.items():
        assert version.split("+")[0] == pins[name], (name, version, pins[name])
    files = {name: _sha256(path / name) for name in
             ("config.json", "tokenizer.json", "tokenizer_config.json", "model.safetensors.index.json")}
    weights = []
    for weight in sorted(path.glob("*.safetensors")):
        with weight.open("rb") as stream:
            length = int.from_bytes(stream.read(8), "little")
            header_hash = hashlib.sha256(stream.read(length)).hexdigest()
        weights.append({"file": weight.name, "bytes": weight.stat().st_size,
                        "storage_blob": weight.resolve().name, "header_sha256": header_hash})
    return path, {
        "model": model, "model_revision": revision, "tokenizer_revision": revision,
        "parameters": parameters, "dtype": "bfloat16", "packages": packages,
        "gpu_lock_sha256": _sha256(lock), "small_file_sha256": files,
        "weight_files": weights,
        "weight_identity_scope": "snapshot, size, blob names and headers; not a new full-weight checksum",
        "test_sha256": _sha256(__file__),
    }


def _native(root):
    import torch

    path, identity = _identity()
    cap = int(os.environ.get("COMET_REFERENCE_CAP_BYTES", 40 << 30))
    settings = EngineSettings(
        model=identity["model"], model_path=str(path), model_revision=identity["model_revision"],
        tokenizer_revision=identity["tokenizer_revision"], method="full", retention=1.0,
        max_context_tokens=1024, peak_vram_bytes=cap, workspace_reserve_bytes=4 << 30,
        prefill_chunk_tokens=64, require_a100=False,
    )
    engine = MiniSGLangEngine(settings)
    sampler = engine.scheduler.engine.sampler
    original_sample = sampler.sample
    captured = []

    def capture(logits, arguments):
        # The pinned batch-size-1 engine skips sampling for intermediate prefill_only chunks.
        assert arguments.temperatures is None and logits.shape[0] == 1
        captured.append(logits[0].detach().float().cpu().clone())
        return original_sample(logits, arguments)

    sampler.sample = capture
    records, tensors = [], {}
    try:
        for case in CASES:
            engine.start(17)
            prompt = engine.tokenizer.apply_chat_template(
                case["messages"], tokenize=True, add_generation_prompt=True,
                enable_thinking=case["thinking"],
            )
            if case["id"] == "tool_history_chunked":
                assert len(prompt) > settings.prefill_chunk_tokens
            for phase in ("fresh", "cached"):
                if phase == "cached":
                    closing = ("" if engine.raw_token_ids[-1] == engine.tokenizer.eos_token_id
                               else "<|im_end|>")
                    suffix_text = closing + "\n" + engine.tokenizer.apply_chat_template(
                        [{"role": "user", "content": "Now return exactly the word AMBER."}],
                        tokenize=False, add_generation_prompt=True, enable_thinking=False,
                    )
                    prompt = engine.tokenizer.encode(suffix_text, add_special_tokens=False)
                history = engine.raw_token_ids + prompt
                captured.clear()
                generated = engine.generate(prompt, 4, 0.0, 1.0, time.monotonic() + 600, ignore_eos=True)
                assert len(captured) == len(generated.token_ids) == 4
                assert engine.raw_token_ids == history + generated.token_ids
                assert generated.prompt_tokens == len(prompt) + (phase == "cached")
                assert not engine.retention_events
                assert generated.memory["physical_cached_tokens"] == generated.memory["logical_cached_tokens"]
                key = f"{case['id']}/{phase}"
                tensors[key] = torch.stack(captured)
                assert tensors[key].argmax(dim=-1).tolist() == generated.token_ids
                records.append({"id": key, "case": case, "phase": phase,
                                "input_token_ids": history, "generated_token_ids": generated.token_ids,
                                "suffix_text": suffix_text if phase == "cached" else None,
                                "suffix_token_ids": prompt if phase == "cached" else None,
                                "prefill_tokens": generated.prompt_tokens})
        torch.save(tensors, root / "native-logits.pt")
        write_json(root / "native.json", {
            "identity": identity, "settings": asdict(settings), "engine": engine.provenance(),
            "records": records, "logits_sha256": _sha256(root / "native-logits.pt"),
        })
    finally:
        sampler.sample = original_sample
        engine.close()


def _compare_logits(native, reference, token):
    import torch

    native, reference = native.double(), reference.double()
    if not torch.isfinite(native).all() or not torch.isfinite(reference).all():
        return {"passed": False, "reason": "nonfinite_logits"}
    centered_native, centered_reference = native - native.mean(), reference - reference.mean()
    difference = centered_native - centered_reference
    rmse = difference.square().mean().sqrt().item()
    relative = rmse / max(centered_reference.square().mean().sqrt().item(), 1e-12)
    log_p, log_q = native.log_softmax(-1), reference.log_softmax(-1)
    log_m = torch.logaddexp(log_p, log_q) - torch.log(torch.tensor(2.0, dtype=torch.float64))
    js = 0.5 * (torch.sum(log_p.exp() * (log_p - log_m)) + torch.sum(log_q.exp() * (log_q - log_m)))
    reference_top = reference.topk(2)
    reference_token = reference.argmax().item()
    regret = (reference[reference_token] - reference[token]).item()
    result = {
        "centered_rmse": rmse, "centered_relative_rmse": relative,
        "centered_max_absolute_error": difference.abs().max().item(),
        "jensen_shannon_nats": max(0.0, js.item()),
        "native_token": token, "reference_token": reference_token,
        "exact_greedy_agreement": token == reference_token,
        "reference_top_two_margin": (reference_top.values[0] - reference_top.values[1]).item(),
        "greedy_regret": regret,
    }
    result["passed"] = all(result[key] <= TOLERANCES[key] for key in
                           ("centered_rmse", "centered_relative_rmse", "jensen_shannon_nats", "greedy_regret"))
    return result


def _reference(root):
    import torch
    from transformers import AutoTokenizer, Qwen3ForCausalLM

    path, identity = _identity()
    native = read_json(root / "native.json")
    assert identity == native["identity"]
    assert torch.cuda.device_count() == 1
    assert torch.cuda.get_device_name() == native["engine"]["device_name"]
    assert _sha256(root / "native-logits.pt") == native["logits_sha256"]
    native_logits = torch.load(root / "native-logits.pt", weights_only=True, map_location="cpu")
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    free, total = torch.cuda.mem_get_info()
    external = total - free - torch.cuda.memory_reserved()
    cap = native["settings"]["peak_vram_bytes"]
    assert 0 < cap - external < total
    torch.cuda.set_per_process_memory_fraction((cap - external) / total)
    model, loading = Qwen3ForCausalLM.from_pretrained(
        path, dtype=torch.bfloat16, device_map={"": "cuda:0"}, attn_implementation="eager",
        local_files_only=True, trust_remote_code=False, output_loading_info=True,
    )
    assert not any(loading.get(key) for key in
                   ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")), loading
    model.eval()
    assert all(parameter.dtype == torch.bfloat16 and parameter.device.type == "cuda"
               for parameter in model.parameters())
    assert model.config._attn_implementation == "eager"
    records, tensors = [], {}
    with torch.inference_mode():
        for record in native["records"]:
            history, generated = record["input_token_ids"], record["generated_token_ids"]
            case = record["case"]
            prompt = tokenizer.apply_chat_template(
                case["messages"], tokenize=True, add_generation_prompt=True,
                enable_thinking=case["thinking"],
            )
            assert history[:len(prompt)] == prompt
            if record["phase"] == "cached":
                assert tokenizer.encode(record["suffix_text"], add_special_tokens=False) == \
                    record["suffix_token_ids"]
            inputs = torch.tensor([history + generated[:-1]], device="cuda", dtype=torch.long)
            logits = model(input_ids=inputs, use_cache=False, logits_to_keep=len(generated)).logits
            logits = logits[0].float().cpu()
            assert logits.shape == native_logits[record["id"]].shape
            tensors[record["id"]] = logits
            comparisons = [_compare_logits(left, right, token) for left, right, token in
                           zip(native_logits[record["id"]], logits, generated, strict=True)]
            records.append({"id": record["id"], "input_tokens": len(history), "steps": comparisons})
    torch.save(tensors, root / "reference-logits.pt")
    steps = [step for record in records for step in record["steps"]]
    agreement = sum(step.get("exact_greedy_agreement", False) for step in steps) / len(steps)
    passed = (all(step["passed"] for step in steps)
              and agreement >= TOLERANCES["minimum_exact_greedy_agreement"])
    write_json(root / "comparison.json", {
        "schema_version": 1,
        "purpose": "full-cache numerical validation only; no task-success or serving substitution claim",
        "passed": passed, "identity": identity, "device_name": torch.cuda.get_device_name(),
        "reference": {"class": type(model).__name__, "attention": "eager", "use_cache": False,
                      "source_sha256": _sha256(inspect.getfile(Qwen3ForCausalLM)),
                      "loading_info": loading, "allocator_cap_bytes": cap - external,
                      "peak_allocated_bytes": torch.cuda.max_memory_allocated()},
        "tolerances": TOLERANCES, "exact_greedy_agreement": agreement, "records": records,
        "artifacts_sha256": {name: _sha256(root / name) for name in
                             ("native.json", "native-logits.pt", "reference-logits.pt")},
    })
    assert passed, "Independent reference comparison failed; inspect comparison.json without relaxing tolerances"


if __name__ == "__main__":
    phase, directory = sys.argv[1:]
    {"native": _native, "reference": _reference}[phase](Path(directory))
