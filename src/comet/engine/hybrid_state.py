"""Portable hybrid checkpoints and original AgentKV query observations."""

from __future__ import annotations

import copy
import random
from pathlib import Path

from comet.artifacts import read_json, write_json
from comet.errors import UnsupportedPath

PHASE_MARKERS = (
    ("<|im_start|>system", 0), ("<|im_start|>user", 0),
    ("<|im_start|>assistant", 1), ("<think>", 1), ("</think>", 2),
    ("<tool_call>", 2), ("</tool_call>", 2),
    ("<tool_response>", 3), ("</tool_response>", 3), ("<|im_end|>", 0),
)


def phases(tokenizer, tokens, tail="", phase=0):
    result = []
    for token in tokens:
        tail = (tail + tokenizer.decode([token], skip_special_tokens=False))[-128:]
        position = -1
        for marker, candidate in PHASE_MARKERS:
            index = tail.rfind(marker)
            if index > position:
                position, phase = index, candidate
        result.append(phase)
    return result, tail, phase


def tensor_tree(value, torch, device):
    if isinstance(value, torch.Tensor):
        return value.detach().to(device).clone()
    if isinstance(value, torch.device):
        return torch.device(device)
    if isinstance(value, dict):
        return {key: tensor_tree(item, torch, device) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return type(value)(tensor_tree(item, torch, device) for item in value)
    return copy.deepcopy(value)


def save(engine, path):
    path = Path(path)
    engine.synchronize()
    payload = {
        "layers": [tensor_tree(vars(layer), engine.torch, "cpu") for layer in engine.cache.layers],
        "observations": tensor_tree(engine._observations, engine.torch, "cpu"),
        "positions": tensor_tree(engine._positions, engine.torch, "cpu"),
        "next_logits": tensor_tree(engine._next_logits, engine.torch, "cpu"),
        "raw": engine._raw, "tail": engine._tail, "phase": engine._phase,
        "recoveries": engine._recoveries, "events": engine._events,
        "python_rng": random.getstate(), "torch_rng": engine.torch.get_rng_state(),
        "cuda_rng": engine.torch.cuda.get_rng_state_all(), "memory": engine.memory_stats(),
    }
    metadata = {
        "schema": "hybrid_v1", "backend": engine.settings.backend,
        "settings_fingerprint": engine.settings.fingerprint(),
        "base_fingerprint": engine.settings.fingerprint(policy=False),
        "full_cache": engine.settings.method == "full", "raw_tokens": len(engine._raw),
        "physical_cached_tokens": engine.cache.get_seq_length(),
        "transformers": engine.TRANSFORMERS_VERSION,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    engine.torch.save(payload, temporary)
    temporary.replace(path)
    write_json(path.with_suffix(path.suffix + ".json"), metadata)
    return metadata


def restore(engine, path, branch):
    path = Path(path)
    metadata = read_json(path.with_suffix(path.suffix + ".json"))
    fingerprint = "base_fingerprint" if branch else "settings_fingerprint"
    if (metadata.get("schema") != "hybrid_v1"
            or metadata.get("transformers") != engine.TRANSFORMERS_VERSION
            or metadata.get(fingerprint) != engine.settings.fingerprint(policy=not branch)):
        raise UnsupportedPath("hybrid checkpoint settings or runtime mismatch")
    if branch and not metadata["full_cache"]:
        raise UnsupportedPath("diagnostic branches require a full-cache source")
    payload = engine.torch.load(path, map_location="cpu", weights_only=True)
    engine._clear()
    for layer, state in zip(engine.cache.layers, payload["layers"], strict=True):
        vars(layer).update(tensor_tree(state, engine.torch, "cuda"))
    for attribute, key in (("_observations", "observations"), ("_positions", "positions"),
                           ("_next_logits", "next_logits")):
        setattr(engine, attribute, tensor_tree(payload[key], engine.torch, "cuda"))
    engine._raw = payload["raw"]
    engine._tail, engine._phase = payload["tail"], payload["phase"]
    engine._recoveries, engine._events = payload["recoveries"], payload["events"]
    engine._check_memory()
    if branch:
        engine._compact()
    else:
        engine._peak_kv = max(engine._peak_kv, payload["memory"]["peak_kv_cache_bytes"])
        engine._peak_total = max(engine._peak_total, payload["memory"]["peak_total_vram_bytes"])
    random.setstate(payload["python_rng"])
    engine.torch.set_rng_state(payload["torch_rng"])
    engine.torch.cuda.set_rng_state_all(payload["cuda_rng"])
    return metadata
