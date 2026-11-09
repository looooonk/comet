import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from comet.engine import EngineSettings, MiniSGLangEngine, retention_target
from comet.engine.contracts import MODEL_PROFILES, model_storage
from comet.errors import BudgetExpired, MemoryCapExceeded


@pytest.mark.gpu
@pytest.mark.skipif(not os.environ.get("COMET_RUN_GPU_TESTS"), reason="explicit GPU integration opt-in required")
@pytest.mark.parametrize("check", ["sampling", "persistence", "memory_cap", pytest.param(
    "capacity", marks=pytest.mark.skipif(not os.environ.get("COMET_TEST_CAPACITY"),
                                        reason="explicit long-context preflight opt-in required"),
)])
def test_native_gpu(check, tmp_path):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), check, str(tmp_path)],
        capture_output=True, text=True, timeout=900,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _sampling_check(tmp_path):
    import torch
    from minisgl.core import SamplingParams
    from minisgl.engine.sample import Sampler

    MiniSGLangEngine._verify_installation()
    device = torch.device("cuda", 0)
    sampler = Sampler(device, 64)
    logits = torch.zeros((64, 64), device=device)
    records = []
    for top_k, top_p in ((-1, 1.0), (8, 1.0), (-1, 0.95), (8, 0.95)):
        params = SamplingParams(temperature=0.6, top_k=top_k, top_p=top_p)
        batch = SimpleNamespace(reqs=[SimpleNamespace(sampling_params=params)] * 64)
        args = sampler.prepare(batch)
        sampler.sample(logits, args)
        torch.cuda.manual_seed_all(17)
        before = torch.cuda.get_rng_state().clone()
        first = sampler.sample(logits, args)
        after = torch.cuda.get_rng_state().clone()
        second = sampler.sample(logits, args)
        torch.cuda.set_rng_state(before)
        replayed = sampler.sample(logits, args)
        torch.cuda.manual_seed_all(18)
        other = sampler.sample(logits, args)
        assert not torch.equal(before, after)
        assert torch.equal(first, replayed)
        assert not torch.equal(first, second)
        assert not torch.equal(first, other)
        records.append({"top_k": top_k, "top_p": top_p, "rng_advanced": True,
                        "replay_equal": True, "successive_samples_differ": True,
                        "seed_controls_samples": True, "first_samples": first.tolist()})
    greedy = sampler.prepare(SimpleNamespace(reqs=[SimpleNamespace(
        sampling_params=SamplingParams(temperature=0.0))] * 64))
    before = torch.cuda.get_rng_state().clone()
    assert torch.equal(sampler.sample(logits, greedy), torch.zeros(64, device=device))
    assert torch.equal(before, torch.cuda.get_rng_state())
    evidence = Path(os.environ.get("COMET_GPU_SAMPLING_EVIDENCE", tmp_path / "sampling.json"))
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps({"device": torch.cuda.get_device_name(),
                                   "checks": records, "greedy_preserves_rng": True}, indent=2) + "\n")


def _persistence_check(tmp_path):
    import torch

    model = os.environ.get("COMET_TEST_MODEL", "Qwen/Qwen3-8B")
    revision = MODEL_PROFILES[model]["revision"]
    engine = MiniSGLangEngine(EngineSettings(
        model=model, model_path=os.environ["COMET_MODEL_PATH"], model_revision=revision,
        tokenizer_revision=revision, method="full", retention=1.0,
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
        for word in ("COBALT", "AMBER"):
            engine.restore(checkpoint)
            instruction = f"Reply with exactly the single word {word}."
            turn = engine.tokenizer.apply_chat_template(
                [{"role": "user", "content": instruction}],
                tokenize=False, add_generation_prompt=True, enable_thinking=False,
            )
            closing = "" if engine.raw_token_ids[-1] == engine.tokenizer.eos_token_id else "<|im_end|>"
            suffix = engine.tokenizer.encode(closing + "\n" + turn, add_special_tokens=False)
            full_prompt = engine.raw_token_ids + suffix
            second = engine.generate(suffix, 4, 0.0, 1.0, time.monotonic() + 600)
            assert second.prompt_tokens == len(suffix) + 1
            engine.start(21)
            fresh = engine.generate(full_prompt, 4, 0.0, 1.0, time.monotonic() + 600)
            assert fresh.prompt_tokens == len(full_prompt)
            assert fresh.token_ids == second.token_ids
            records.append({
                "method": "full", "cached_vs_fresh_tokens_equal": True,
                "new_user_instruction": instruction,
                "cached_prompt_tokens": second.prompt_tokens, "fresh_prompt_tokens": fresh.prompt_tokens,
                "token_ids": second.token_ids,
            })
        assert records[0]["token_ids"] != records[1]["token_ids"]
        engine.restore(checkpoint)
        repeated = engine.generate(suffix, 4, 0.0, 1.0, time.monotonic() + 600)
        assert repeated.token_ids == second.token_ids
        engine.restore(checkpoint)
        before_sampling = torch.cuda.get_rng_state().clone()
        sampled = engine.generate(suffix, 8, 0.6, 0.9, time.monotonic() + 600)
        sampled_rng = torch.cuda.get_rng_state().clone()
        assert not torch.equal(before_sampling, sampled_rng)
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
        records.extend(_failure_accounting_check(engine, compressed_checkpoint, suffix))
        if model == "Qwen/Qwen3-4B-Instruct-2507":
            records.append(_nonthinking_phase_check(engine, tmp_path))
        evidence = Path(os.environ.get("COMET_GPU_EVIDENCE", tmp_path / "gpu-evidence.json"))
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps({"device": engine.device_name, "integration_only": True, "checks": records}, indent=2) + "\n")
    finally:
        engine.close()


def _phase_state(engine, name):
    state = engine._state()
    ring = engine.scheduler.engine.query_ring
    slot = state.req.table_idx
    sizes = ring.size[slot].cpu().tolist()
    return {
        "name": name, "method": engine.settings.method,
        "raw_token_ids": engine.raw_token_ids, "phase_ids": list(engine._phase),
        "semantic_phase_ids": list(engine._semantic),
        "session_phase_ids": state.full_phase_ids.cpu().tolist(),
        "occupied_queries_per_phase": sizes,
        "query_positions_per_phase": [
            sorted(ring.positions[slot, phase, :size].cpu().tolist())
            for phase, size in enumerate(sizes)
        ],
        "memory": engine.memory_stats(),
    }


def _nonthinking_phase_check(engine, tmp_path):
    from minisgl.phase import SemanticPhase

    from comet.artifacts import write_json
    from comet.history_benchmark import force_recorded_tokens

    evidence = Path(os.environ.get("COMET_GPU_EVIDENCE", tmp_path / "gpu-evidence.json"))
    path = evidence.with_name("phase-occupancy.json")
    record = {
        "status": "running", "model": engine.settings.model,
        "model_revision": engine.settings.model_revision,
        "tokenizer_revision": engine.settings.tokenizer_revision,
        "chat_template_sha256": hashlib.sha256(engine.tokenizer.chat_template.encode()).hexdigest(),
        "kind": "synthetic_nonthinking_phase_qualification", "tools_executed": False,
        "continuation": "forced tokens; not a model capability or sampling check",
        "ring_capacity_per_phase": 8, "nominal_query_capacity": 32,
        "states": [], "checkpoint_sha256": {},
    }
    write_json(path, record)
    try:
        action = "```python\nmarker = [2, 3, 5, 7]\nprint({'marker': marker})\n```"
        observation = json.dumps({"marker": [2, 3, 5, 7], "note": "synthetic observation " * 20})
        messages = [
            {"role": "system", "content": "Return one fenced Python block using the given tool state."},
            {"role": "user", "content": "Store the four prime numbers in a marker and print its value."},
            {"role": "assistant", "content": action},
            {"role": "user", "content": f"<tool_response>\n{observation}\n</tool_response>"},
        ]
        text = engine.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False,
        )
        encoded = engine.tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
        prompt = engine.tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True, enable_thinking=False,
        )
        continuation = engine.tokenizer.encode("```python\nprint(marker)\n```", add_special_tokens=False)
        assert encoded["input_ids"] == prompt
        assert engine.settings.prefill_chunk_tokens < len(prompt)
        assert len(prompt) + len(continuation) < engine.settings.max_context_tokens
        assert "<think>" not in text and "</think>" not in text
        expected_raw = prompt + continuation
        spans = {}
        for name, content in (("python_action", action), ("tool_observation", observation)):
            start = text.index(content)
            spans[name] = [i for i, (left, right) in enumerate(encoded["offset_mapping"])
                           if start <= left < right <= start + len(content)]
            assert spans[name]
        record.update(messages=messages, rendered_prompt=text, prompt_token_ids=prompt,
                      continuation_token_ids=continuation, content_token_indices=spans)

        def capture(name):
            current = _phase_state(engine, name)
            record["states"].append(current)
            write_json(path, record)
            phases = current["phase_ids"]
            semantics = current["semantic_phase_ids"]
            assert current["raw_token_ids"] == expected_raw
            assert len(phases) == len(semantics) == len(expected_raw)
            assert current["session_phase_ids"] == phases
            assert all(phases[i] == 1 and semantics[i] == int(SemanticPhase.ASSISTANT_TEXT)
                       for i in spans["python_action"] + list(range(len(prompt), len(expected_raw))))
            assert all(phases[i] == 3 and semantics[i] == int(SemanticPhase.TOOL_RESPONSE)
                       for i in spans["tool_observation"])
            assert 2 not in phases
            forwarded = current["memory"]["logical_cached_tokens"]
            expected_positions = [[i for i, phase in enumerate(phases[:forwarded]) if phase == stage][-8:]
                                  for stage in range(4)]
            assert current["query_positions_per_phase"] == expected_positions
            assert current["occupied_queries_per_phase"] == [len(indices) for indices in expected_positions]
            assert current["occupied_queries_per_phase"] == [8, 8, 0, 8]
            return current

        engine.set_policy("full", 1.0)
        engine.start(23)
        with force_recorded_tokens(engine, continuation):
            generated = engine.generate(prompt, len(continuation), 0.0, 1.0,
                                        time.monotonic() + 600, ignore_eos=True)
        assert generated.token_ids == continuation
        initial = capture("full")
        assert initial["memory"]["logical_cached_tokens"] == len(expected_raw) - 1
        full = tmp_path / "nonthinking-phase-full.pt"
        record["checkpoint_sha256"]["full"] = engine.checkpoint(full)["sha256"]
        engine.start(23)
        engine.restore(full)
        restored = capture("full_restored")
        for field in ("phase_ids", "semantic_phase_ids", "query_positions_per_phase"):
            assert restored[field] == initial[field]
        engine.set_policy("agentkv", 0.5)
        engine.restore(full, branch=True)
        capture("agentkv_branch")
        compressed = tmp_path / "nonthinking-phase-compressed.pt"
        record["checkpoint_sha256"]["compressed"] = engine.checkpoint(compressed)["sha256"]
        engine.start(23)
        engine.restore(compressed)
        capture("agentkv_restored")
        recovered = engine.recover(expected_raw, time.monotonic() + 600)
        assert recovered.admitted, recovered.reason
        after = capture("agentkv_recovered")
        assert after["phase_ids"] == initial["phase_ids"]
        assert after["semantic_phase_ids"] == initial["semantic_phase_ids"]
        assert after["memory"]["logical_cached_tokens"] == len(expected_raw)
        assert after["memory"]["physical_cached_tokens"] == retention_target(len(expected_raw), 0.5, "agentkv")
        checkpoint = tmp_path / "nonthinking-phase-recovered.pt"
        record["checkpoint_sha256"]["recovered"] = engine.checkpoint(checkpoint)["sha256"]
        engine.start(23)
        engine.restore(checkpoint)
        restored = capture("agentkv_recovered_restored")
        assert restored["query_positions_per_phase"] == after["query_positions_per_phase"]
        record["status"] = "passed"
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}",
                      partial_raw_token_ids=engine.raw_token_ids,
                      partial_phase_ids=list(engine._phase),
                      partial_semantic_phase_ids=list(engine._semantic),
                      last_generation=engine.last_generation)
        raise
    finally:
        write_json(path, record)
    return {"check": "nonthinking_phase_occupancy", "status": record["status"],
            "evidence": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _failure_accounting_check(engine, checkpoint, suffix):
    records = []
    forward = engine.scheduler._forward
    for operation in ("generate", "recover"):
        engine.restore(checkpoint)
        calls = 0

        def fail_second_batch(batch):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise BudgetExpired("injected second-batch timeout")
            return forward(batch)

        engine.scheduler._forward = fail_second_batch
        try:
            with pytest.raises(BudgetExpired, match="injected"):
                if operation == "generate":
                    engine.generate(suffix, 8, 0.0, 1.0, time.monotonic() + 600, ignore_eos=True)
                else:
                    engine.recover(engine.raw_token_ids + suffix, time.monotonic() + 600)
        finally:
            engine.scheduler._forward = forward
        engine.synchronize()
        progress = engine.last_generation if operation == "generate" else engine.last_recovery
        assert progress["status"] == "failed"
        assert progress["prompt_tokens"] > 0 and progress["estimated_flops"] > 0
        assert progress["incomplete_forward_tokens"] > 0
        assert progress["incomplete_forward_estimated_flops"] > 0
        assert progress["prefill_seconds"] > 0
        if operation == "generate":
            assert progress["generated_tokens"] > 0
            assert engine.raw_token_ids[-len(progress["token_ids"]):] == progress["token_ids"]
        else:
            assert progress["admitted"] and progress["allowance_consumed"]
            assert engine.recovery_count == 1
            assert engine.recover(engine.raw_token_ids, time.monotonic() + 600).reason == "recovery_limit"
        records.append({"check": f"{operation}_timeout_accounting", "progress": progress})
    return records


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
    model = os.environ.get("COMET_TEST_MODEL", "Qwen/Qwen3-8B")
    revision = MODEL_PROFILES[model]["revision"]
    config, parameters = model_storage(model_path, revision, model)
    kv_bytes = 4 * config["num_hidden_layers"] * config["num_key_value_heads"] * config["head_dim"]
    free, total = torch.cuda.mem_get_info()
    initial_external = total - free - torch.cuda.memory_reserved()
    workspace = 4 << 30
    # Fix the cap before engine creation; no live setting or admission bound is patched.
    cap = initial_external + parameters * 2 + workspace + 513 * kv_bytes
    engine = MiniSGLangEngine(EngineSettings(
        model=model, model_path=model_path, model_revision=revision, tokenizer_revision=revision,
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
            progress = engine.last_generation
            assert progress["status"] == "failed"
            assert progress["incomplete_forward_tokens"] > 0
            assert progress["incomplete_forward_estimated_flops"] > 0
            assert progress["estimated_flops"] == 0
            assert progress["prefill_seconds"] > 0
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
            "progress": progress,
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


def _capacity_check(tmp_path):
    import minisgl.eviction.manager as manager

    model = os.environ.get("COMET_TEST_MODEL", "Qwen/Qwen3-8B")
    revision = MODEL_PROFILES[model]["revision"]
    settings = EngineSettings(
        model=model, model_path=os.environ["COMET_MODEL_PATH"], model_revision=revision,
        tokenizer_revision=revision, method="full", retention=1.0,
        max_context_tokens=32768, peak_vram_bytes=40 << 30, workspace_reserve_bytes=6 << 30,
        prefill_chunk_tokens=256, require_a100=False,
    )
    engine = MiniSGLangEngine(settings)
    compact = manager.compact_all_layers_kv_heads_inplace_sorted_triton
    in_place_lengths = []

    def record_compaction(**kwargs):
        in_place_lengths.append(kwargs["physical_cached_len"])
        return compact(**kwargs)

    manager.compact_all_layers_kv_heads_inplace_sorted_triton = record_compaction
    try:
        assert engine.memory_stats()["kv_pool_tokens"] == settings.max_context_tokens
        checks = []
        token = engine.tokenizer.encode(" capacity", add_special_tokens=False)[0]
        for method, retention in (("full", 1.0), ("agentkv", 0.8)):
            engine.set_policy(method, retention)
            engine.start(31)
            in_place_lengths.clear()
            initial = engine.generate([token] * 32700, 4, 0.0, 1.0,
                                      time.monotonic() + 600, ignore_eos=True)
            continued = engine.generate([token] * 32, 4, 0.0, 1.0,
                                        time.monotonic() + 600, ignore_eos=True)
            assert continued.prompt_tokens == 33
            memory = continued.memory
            assert memory["physical_cached_tokens"] == retention_target(
                memory["logical_cached_tokens"], retention, method,
            )
            assert memory["peak_total_vram_bytes"] <= settings.peak_vram_bytes
            assert bool(in_place_lengths) == (method == "agentkv")
            checks.append({
                "method": method, "retention": retention, "memory": memory,
                "prefill_seconds": initial.prefill_seconds,
                "suffix_prompt_tokens": continued.prompt_tokens,
                "raw_tokens": len(engine.raw_token_ids), "recovery_count": engine.recovery_count,
                "in_place_compaction_lengths": list(in_place_lengths),
            })
        evidence = Path(os.environ.get("COMET_GPU_CAPACITY_EVIDENCE", tmp_path / "capacity-evidence.json"))
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps({
            "integration_only": True, "settings": asdict(settings),
            "provenance": engine.provenance(), "checks": checks,
        }, indent=2) + "\n")
    finally:
        manager.compact_all_layers_kv_heads_inplace_sorted_triton = compact
        engine.close()


if __name__ == "__main__":
    {"sampling": _sampling_check, "persistence": _persistence_check, "memory_cap": _memory_cap_check,
     "capacity": _capacity_check}[sys.argv[1]](Path(sys.argv[2]))
