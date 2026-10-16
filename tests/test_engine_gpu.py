import json
import os
import time
from pathlib import Path

import pytest

from comet.engine import EngineSettings, MiniSGLangEngine, retention_target
from comet.engine.contracts import MODEL_REVISION


@pytest.mark.gpu
@pytest.mark.skipif(not os.environ.get("COMET_RUN_GPU_TESTS"), reason="explicit GPU integration opt-in required")
def test_native_persistence_eviction_checkpoint_and_single_rebuild(tmp_path):
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
        second = engine.generate(suffix, 4, 0.0, 1.0, time.monotonic() + 600)
        assert second.prompt_tokens == len(suffix) + 1
        engine.restore(checkpoint)
        repeated = engine.generate(suffix, 4, 0.0, 1.0, time.monotonic() + 600)
        assert repeated.token_ids == second.token_ids
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
