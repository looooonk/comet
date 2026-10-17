import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import pytest

from comet.engine import EngineSettings, MiniSGLangEngine, retention_target
from comet.engine.contracts import MODEL_REVISION, model_storage
from comet.errors import MemoryCapExceeded


@pytest.mark.gpu
@pytest.mark.skipif(not os.environ.get("COMET_RUN_GPU_TESTS"), reason="explicit GPU integration opt-in required")
@pytest.mark.parametrize("check", ["persistence", "memory_cap"])
def test_native_gpu(check, tmp_path):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), check, str(tmp_path)],
        capture_output=True, text=True, timeout=900,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _persistence_check(tmp_path):
    import torch

    engine = MiniSGLangEngine(EngineSettings(
        model_path=os.environ["COMET_MODEL_PATH"], model_revision=MODEL_REVISION,
        tokenizer_revision=MODEL_REVISION, method="full", retention=1.0,
        max_context_tokens=1024, peak_vram_bytes=40 << 30, workspace_reserve_bytes=4 << 30,
        prefill_chunk_tokens=128, require_a100=False,
    ))
    records = []
    try:
        engine.start(21)
        prompt = engine.tokenizer.apply_chat_template(
            [{"role": "user", "content": "Keep this sequence in mind: " + "one two three four. " * 48}],
            tokenize=True, add_generation_prompt=True, enable_thinking=False,
        )
        first = engine.generate(prompt, 4, 0.0, 1.0, time.monotonic() + 600)
        assert engine.raw_token_ids == prompt + first.token_ids
        assert first.memory["physical_cached_tokens"] == first.memory["logical_cached_tokens"]
        checkpoint = tmp_path / "full.pt"
        engine.checkpoint(checkpoint)
        suffix = engine.tokenizer.encode("\n<|im_start|>user\nContinue.<|im_end|>\n<|im_start|>assistant\n", add_special_tokens=False)
        full_prompt = engine.raw_token_ids + suffix
        second = engine.generate(suffix, 4, 0.0, 1.0, time.monotonic() + 600)
        assert second.prompt_tokens == len(suffix) + 1
        engine.start(21)
        fresh = engine.generate(full_prompt, 4, 0.0, 1.0, time.monotonic() + 600)
        assert fresh.prompt_tokens == len(full_prompt)
        assert fresh.token_ids == second.token_ids
        records.append({
            "method": "full", "cached_vs_fresh_tokens_equal": True,
            "cached_prompt_tokens": second.prompt_tokens, "fresh_prompt_tokens": fresh.prompt_tokens,
            "token_ids": second.token_ids,
        })
        engine.restore(checkpoint)
        repeated = engine.generate(suffix, 4, 0.0, 1.0, time.monotonic() + 600)
        assert repeated.token_ids == second.token_ids
        engine.restore(checkpoint)
        sampled = engine.generate(suffix, 8, 0.6, 0.9, time.monotonic() + 600)
        sampled_rng = torch.cuda.get_rng_state().clone()
        engine.restore(checkpoint)
        sampled_again = engine.generate(suffix, 8, 0.6, 0.9, time.monotonic() + 600)
        assert sampled.token_ids == sampled_again.token_ids
        assert torch.equal(sampled_rng, torch.cuda.get_rng_state())
        for method in ("streamingllm", "rkv", "agentkv"):
            engine.set_policy(method, 0.5)
            engine.restore(checkpoint, branch=True)
            raw = engine.raw_token_ids
            before = engine.memory_stats()
            assert before["physical_cached_tokens"] == retention_target(before["logical_cached_tokens"], 0.5, method)
            compressed_checkpoint = tmp_path / f"{method}.pt"
            engine.checkpoint(compressed_checkpoint)
            continuation = engine.generate(suffix, 4, 0.0, 1.0, time.monotonic() + 600)
            engine.restore(compressed_checkpoint)
            repeat = engine.generate(suffix, 4, 0.0, 1.0, time.monotonic() + 600)
            assert continuation.token_ids == repeat.token_ids
            assert engine.raw_token_ids[:len(raw)] == raw
            raw = engine.raw_token_ids
            rng = torch.cuda.get_rng_state().clone()
            recovered = engine.recover(raw + suffix, time.monotonic() + 600)
            assert recovered.admitted, recovered.reason
            assert torch.equal(rng, torch.cuda.get_rng_state())
            raw = raw + suffix
            assert engine.raw_token_ids == raw
            assert not engine.recover(raw, time.monotonic() + 600).admitted
            memory = engine.memory_stats()
            assert memory["physical_cached_tokens"] == retention_target(len(raw), 0.5, method)
            assert memory["peak_total_vram_bytes"] <= 40 << 30
            after_recovery = tmp_path / f"{method}-recovered.pt"
            engine.checkpoint(after_recovery)
            next_output = engine.generate([], 4, 0.0, 1.0, time.monotonic() + 600)
            assert next_output.prompt_tokens == 0
            assert engine.raw_token_ids == raw + next_output.token_ids
            engine.restore(after_recovery)
            same_output = engine.generate([], 4, 0.0, 1.0, time.monotonic() + 600)
            assert next_output.token_ids == same_output.token_ids
            records.append({"method": method, "memory": memory, "recovered": recovered.admitted})
        evidence = Path(os.environ.get("COMET_GPU_EVIDENCE", tmp_path / "gpu-evidence.json"))
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps({"device": engine.device_name, "integration_only": True, "checks": records}, indent=2) + "\n")
    finally:
        engine.close()


def _equal_state(left, right, torch):
    assert type(left) is type(right)
    if isinstance(left, torch.Tensor):
        assert torch.equal(left, right)
    elif isinstance(left, dict):
        assert left.keys() == right.keys()
        for key in left:
            _equal_state(left[key], right[key], torch)
    elif isinstance(left, (list, tuple)):
        assert len(left) == len(right)
        for first, second in zip(left, right, strict=True):
            _equal_state(first, second, torch)
    else:
        assert left == right


def _rejected_recovery(engine, suffix, reason, directory):
    torch = engine.torch
    before_path, after_path = directory / f"{reason}-before.pt", directory / f"{reason}-after.pt"
    before = engine.checkpoint(before_path)
    raw = engine.raw_token_ids
    free, total = torch.cuda.mem_get_info()
    available = engine.settings.peak_vram_bytes - (total - free)
    available += torch.cuda.memory_reserved() - torch.cuda.memory_allocated()
    result = engine.recover(raw + suffix, time.monotonic() + 600)
    assert not result.admitted and result.reason == reason
    assert engine.raw_token_ids == raw and engine.recovery_count == 0
    after = engine.checkpoint(after_path)
    left = torch.load(before_path, weights_only=True, map_location="cpu")
    right = torch.load(after_path, weights_only=True, map_location="cpu")
    left.pop("memory")
    right.pop("memory")
    _equal_state(left, right, torch)
    del left, right
    continued = engine.generate(suffix, 4, 0.6, 0.9, time.monotonic() + 600, ignore_eos=True)
    rng = torch.cuda.get_rng_state().clone()
    engine.restore(before_path)
    replay = engine.generate(suffix, 4, 0.6, 0.9, time.monotonic() + 600, ignore_eos=True)
    assert continued.token_ids == replay.token_ids
    assert torch.equal(rng, torch.cuda.get_rng_state())
    return {
        "reason": result.reason, "admitted": result.admitted, "memory": result.memory,
        "raw_tokens": len(raw), "pending_tokens": len(suffix), "state_equal": True,
        "workspace_bound_bytes": engine._workspace_bound(len(raw) + len(suffix)),
        "workspace_available_bytes": available,
        "continuation_tokens_equal": True, "continuation_cuda_rng_equal": True,
        "before_checkpoint": str(before_path), "before_sha256": before["sha256"],
        "after_checkpoint": str(after_path), "after_sha256": after["sha256"],
    }


def _memory_cap_check(tmp_path):
    import torch

    model_path = os.environ["COMET_MODEL_PATH"]
    config, parameters = model_storage(model_path, MODEL_REVISION)
    kv_bytes = 4 * config["num_hidden_layers"] * config["num_key_value_heads"] * config["head_dim"]
    free, total = torch.cuda.mem_get_info()
    initial_external = total - free - torch.cuda.memory_reserved()
    workspace = 4 << 30
    # Fix the cap before engine creation; no live setting or admission bound is patched.
    cap = initial_external + parameters * 2 + workspace + 513 * kv_bytes
    engine = MiniSGLangEngine(EngineSettings(
        model_path=model_path, model_revision=MODEL_REVISION, tokenizer_revision=MODEL_REVISION,
        method="agentkv", retention=0.25, max_context_tokens=2048,
        peak_vram_bytes=cap, workspace_reserve_bytes=workspace,
        prefill_chunk_tokens=64, require_a100=False,
    ))
    try:
        evidence = Path(os.environ.get("COMET_GPU_MEMORY_EVIDENCE", tmp_path / "memory-evidence.json"))
        evidence.parent.mkdir(parents=True, exist_ok=True)
        artifacts = evidence.parent / f"{evidence.stem}-checkpoints"
        artifacts.mkdir(parents=True, exist_ok=True)
        engine.start(29)
        token = engine.tokenizer.encode(" memory", add_special_tokens=False)[0]
        engine.generate([token] * 128, 4, 0.0, 1.0, time.monotonic() + 600, ignore_eos=True)
        pool = engine.memory_stats()["kv_pool_tokens"]
        assert 384 <= pool <= 640
        checks = [_rejected_recovery(engine, [token] * 8, "transient_workspace_exceeds_cap", artifacts)]
        while len(engine.raw_token_ids) <= pool:
            engine.generate([token] * 64, 4, 0.0, 1.0, time.monotonic() + 600, ignore_eos=True)
        checks.append(_rejected_recovery(engine, [token] * 8, "full_history_exceeds_kv_pool", artifacts))

        engine._check_memory()
        allocator_ceiling = cap - engine._allocator_external_bytes
        allocated = torch.cuda.memory_allocated()
        request = allocator_ceiling - allocated + (64 << 20)
        free, _ = torch.cuda.mem_get_info()
        assert 0 < request <= 6 << 30
        assert free > request + (1 << 30)
        forward = engine.scheduler._forward

        def allocate_over_cap(batch):
            torch.empty(request, dtype=torch.uint8, device="cuda")
            raise AssertionError("CUDA allocator admitted a request above its fixed ceiling")

        engine.scheduler._forward = allocate_over_cap
        try:
            with pytest.raises(MemoryCapExceeded, match="CUDA allocator refused") as failure:
                engine.generate([token], 1, 0.0, 1.0, time.monotonic() + 600, ignore_eos=True)
            assert isinstance(failure.value.__cause__, torch.cuda.OutOfMemoryError)
        finally:
            engine.scheduler._forward = forward
        engine.synchronize()
        memory = engine.memory_stats()
        assert memory["peak_total_vram_bytes"] <= cap
        checks.append({
            "reason": "allocator_ceiling", "exception": type(failure.value).__name__,
            "cause": type(failure.value.__cause__).__name__, "request_bytes": request,
            "allocated_before_bytes": allocated, "allocator_ceiling_bytes": allocator_ceiling,
            "physical_free_before_bytes": free, "memory": memory,
        })
        evidence.write_text(json.dumps({
            "integration_only": True, "provenance": engine.provenance(),
            "settings": asdict(engine.settings),
            "cap_bytes": cap, "initial_external_bytes": initial_external,
            "workspace_reserve_bytes": workspace, "kv_pool_tokens": pool,
            "cap_changed_after_initialization": False, "checks": checks,
        }, indent=2) + "\n")
    finally:
        engine.close()


if __name__ == "__main__":
    {"persistence": _persistence_check, "memory_cap": _memory_cap_check}[sys.argv[1]](Path(sys.argv[2]))
