import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from comet.config import Experiment
from comet.engine import EngineSettings
from comet.engine.contracts import MODEL_PROFILES
from comet.engine.hybrid_state import phases

MODEL = "Qwen/Qwen3.5-9B"
REVISION = MODEL_PROFILES[MODEL]["revision"]


def test_hybrid_registration_requires_its_own_backend():
    config = Experiment.load(Path(__file__).parents[1] / "configs/examples/pilot-smoke.json")
    engine = replace(config.engine, model=MODEL, model_revision=REVISION, tokenizer_revision=REVISION)
    with pytest.raises(ValueError, match="backend"):
        replace(config, engine=engine).validate()
    replace(config, engine=replace(engine, backend="transformers_hybrid")).validate()


def test_phase_markers_survive_split_tokens_and_tool_turns():
    tokenizer = SimpleNamespace(decode=lambda tokens, **kwargs: "".join(tokens))
    first, tail, phase = phases(tokenizer, ["<|im_start|>assistant", "<thi", "nk>", "reason"])
    second, _, _ = phases(tokenizer, ["</think>", "code", "<tool_response>", "data"], tail, phase)
    assert first == [1, 1, 1, 1]
    assert second == [2, 2, 3, 3]


def test_delta_kernel_forwards_state_without_transformer_only_keywords():
    from comet.engine.hybrid import delta_kernel

    calls = []
    delta_kernel(lambda *args, **kwargs: calls.append((args, kwargs)),
                 "q", "k", "v", g="decay", beta="rate", initial_state="state",
                 output_final_state=True, use_cache=True, output_attentions=False)
    args, kwargs = calls[0]
    assert args == ("q", "k", "v")
    assert kwargs["initial_state"] == "state" and kwargs["output_final_state"]
    assert "use_cache" not in kwargs and "output_attentions" not in kwargs


def test_external_memory_does_not_count_a_concurrent_allocator_release():
    from comet.engine.hybrid import HybridEngine

    engine = HybridEngine.__new__(HybridEngine)
    engine._peak_total, engine._peak_external = 0, 10
    reserved = iter([80, 20, 20, 20])
    free = iter([10, 65])
    engine.torch = SimpleNamespace(cuda=SimpleNamespace(
        memory_reserved=lambda: next(reserved), mem_get_info=lambda: (next(free), 100)))
    engine._sample_memory()
    assert engine._peak_total == 90 and engine._peak_external == 10
    engine._sample_memory()
    assert engine._peak_total == 90 and engine._peak_external == 15


def test_device_peak_is_distinct_from_noncoincident_upper_bound():
    from comet.engine.hybrid import HybridEngine

    engine = HybridEngine.__new__(HybridEngine)
    engine._peak_total, engine._peak_external = 90, 15
    engine._peak_kv = engine._peak_recurrent = 0
    engine._raw = []
    engine._state_bytes = lambda: (0, 0)
    engine.cache = SimpleNamespace(get_seq_length=lambda: 0)
    engine.settings = SimpleNamespace(retention=1.0, method="full")
    engine.torch = SimpleNamespace(cuda=SimpleNamespace(
        memory_reserved=lambda: 20, mem_get_info=lambda: (65, 100),
        max_memory_reserved=lambda: 80, max_memory_allocated=lambda: 70))
    memory = engine.memory_stats()
    assert memory["peak_total_vram_bytes"] == 90
    assert memory["estimated_peak_total_vram_upper_bytes"] == 95


@pytest.mark.gpu
@pytest.mark.skipif(os.environ.get("COMET_RUN_HYBRID_TESTS") != "1", reason="opt-in hybrid GPU check")
def test_live_hybrid_reference_persistence_recovery_and_branches(tmp_path):
    import torch
    from transformers import DynamicCache

    from comet.artifacts import write_json
    from comet.clocks import monotonic
    from comet.engine import create_engine, retention_target

    settings = EngineSettings(
        model=MODEL, model_path=os.environ["COMET_MODEL_PATH"], model_revision=REVISION,
        tokenizer_revision=REVISION, backend="transformers_hybrid", method="full", retention=1.0,
        max_context_tokens=int(os.environ.get("COMET_TEST_CONTEXT_TOKENS", 8192)),
        peak_vram_bytes=int(os.environ.get("COMET_GPU_CAP_BYTES", 40 * 2**30)),
        workspace_reserve_bytes=int(os.environ.get("COMET_GPU_WORKSPACE_BYTES", 4 * 2**30)),
        prefill_chunk_tokens=128, require_a100=False,
    )
    engine = create_engine(settings)
    evidence = {"reference": {}, "conditions": []}
    deadline = monotonic() + 1200
    try:
        engine.warmup(deadline)
        tokens = engine.tokenizer.apply_chat_template(
            [{"role": "user", "content": "Remember: the access code is 7391. " * 20
              + "What is the access code? Reply with the number."}],
            tokenize=True, return_dict=False, add_generation_prompt=True, enable_thinking=False,
        )
        engine.set_policy("full", 1.0)
        engine.start(17)
        engine._prefill(tokens, deadline, engine._progress())
        chunked_logits = engine._next_logits.detach().clone()
        # Independent official full-sequence path checks positions, masks and chunked state.
        engine.text_config._attn_implementation = "sdpa"
        with torch.inference_mode():
            reference = engine.model(
                input_ids=torch.tensor([tokens], device="cuda"),
                past_key_values=DynamicCache(config=engine.text_config), use_cache=True,
                logits_to_keep=1,
            ).logits[:, -1].float()
        engine.text_config._attn_implementation = "comet_hybrid"
        cosine = torch.nn.functional.cosine_similarity(chunked_logits, reference).item()
        overlap = len(set(chunked_logits.topk(10).indices[0].tolist()) & set(reference.topk(10).indices[0].tolist())) / 10
        evidence["reference"] = {"logit_cosine": cosine, "top10_overlap": overlap,
                                  "prompt_tokens": len(tokens)}
        assert cosine > 0.98 and overlap >= 0.7
        del reference, chunked_logits
        source = tmp_path / "source.pt"
        engine.checkpoint(source)
        answer = engine.generate([], 16, 0.0, 1.0, deadline)
        evidence["reference"]["greedy_text"] = engine.tokenizer.decode(answer.token_ids, skip_special_tokens=True)
        engine.restore(source)
        suffix = engine.tokenizer.encode("\nA further observation: continue.\n")
        grid = (0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9) if os.environ.get("COMET_TEST_RETENTION_GRID") == "1" else (0.5,)
        for method in ("streamingllm", "rkv", "agentkv"):
            for retention in grid:
                engine.set_policy(method, retention)
                engine.restore(source, branch=True)
                assert engine.cache.get_seq_length() == retention_target(len(tokens), retention, method)
                checkpoint = tmp_path / "compressed.pt"
                engine.checkpoint(checkpoint)
                first = engine.generate(suffix, 3, 0.7, 0.8, deadline)
                raw = engine.raw_token_ids
                assert raw == tokens + suffix + first.token_ids
                engine.restore(checkpoint)
                replay = engine.generate(suffix, 3, 0.7, 0.8, deadline)
                assert first.token_ids == replay.token_ids
                assert engine.cache.get_seq_length() == retention_target(len(raw), retention, method)
                rng = torch.cuda.get_rng_state().clone()
                recovered = engine.recover(raw, deadline)
                assert recovered.admitted and engine.raw_token_ids == raw
                assert torch.equal(rng, torch.cuda.get_rng_state())
                assert not engine.recover(raw, deadline).admitted
                assert engine.cache.get_seq_length() == retention_target(len(raw), retention, method)
                engine.checkpoint(checkpoint)
                post = engine.generate([], 2, 0.7, 0.8, deadline)
                engine.restore(checkpoint)
                assert engine.generate([], 2, 0.7, 0.8, deadline).token_ids == post.token_ids
                evidence["conditions"].append({"method": method, "retention": retention,
                                                "memory": engine.memory_stats(),
                                                "rebuild_seconds": recovered.seconds})
        engine.set_policy("rkv", 0.5)
        engine.restore(source, branch=True)
        original = engine.settings
        used = torch.cuda.memory_allocated() + engine._peak_external
        engine.settings = replace(original, peak_vram_bytes=int(used + 2**30))
        assert not engine.recover(engine.raw_token_ids, deadline).admitted
        engine.settings = original
        evidence["cap_refusal"] = True
        if os.environ.get("COMET_TEST_CAPACITY") == "1":
            unit = engine.tokenizer.encode("Archive entry: completed routine item. ")
            capacity_tokens = (unit * (settings.max_context_tokens // len(unit) + 1))[
                :settings.max_context_tokens - 2
            ]
            evidence["capacity"] = []
            for method in ("full", "streamingllm", "rkv", "agentkv"):
                engine.set_policy(method, 1.0 if method == "full" else 0.25)
                engine.start(17)
                engine.generate(capacity_tokens, 2, 0.0, 1.0, deadline)
                record = {"method": method, "memory": engine.memory_stats()}
                if method != "full":
                    recovery = engine.recover(engine.raw_token_ids, deadline)
                    assert recovery.admitted
                    record["recovery_seconds"] = recovery.seconds
                    record["post_recovery_memory"] = engine.memory_stats()
                evidence["capacity"].append(record)
    finally:
        evidence["engine"] = engine.provenance()
        destination = os.environ.get("COMET_GPU_EVIDENCE")
        if destination:
            write_json(Path(destination), evidence)
        engine.close()
