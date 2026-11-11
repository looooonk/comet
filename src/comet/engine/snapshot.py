from __future__ import annotations

import hashlib
import json
import random
import uuid
from dataclasses import asdict, fields
from pathlib import Path

from comet.errors import MemoryCapExceeded, UnsupportedPath

from ._pins import PATCH_FILE_HASHES
from .contracts import MINISGL_REVISION


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_snapshot(engine, path: Path) -> dict:
    torch, scheduler = engine.torch, engine.scheduler
    torch.cuda.synchronize()
    state = engine._state()
    if state is None or state.status != "PARKED" or state.req is None:
        raise UnsupportedPath("checkpoint requires an idle session with materialized KV")
    req = state.req
    req.materialize_full_host()
    req_data = {}
    for field in fields(req):
        value = getattr(req, field.name)
        if field.name == "sampling_params":
            value = asdict(value)
        elif isinstance(value, torch.Tensor):
            value = value.cpu().clone()
        req_data[field.name] = value
    req_data.update(device_len=req.device_len, max_device_len=req.max_device_len)
    slots = scheduler.engine.page_table[req.table_idx, : req.physical_cached_len].long()
    kv = []
    for layer in range(scheduler.engine.kv_cache.num_layers):
        kv.append(
            [
                cache(layer).index_select(0, slots).cpu()
                for cache in (scheduler.engine.kv_cache.k_cache, scheduler.engine.kv_cache.v_cache)
            ]
        )
        engine._check_memory()
    ring = scheduler.engine.query_ring
    payload = {
        "schema": 2,
        "request": req_data,
        "kv": kv,
        "query_ring": {
            name: getattr(ring, name)[req.table_idx].cpu().clone()
            for name in ("q", "positions", "write_pos", "size")
        },
        "raw": engine._raw,
        "phase": engine._phase,
        "semantic": engine._semantic,
        "recoveries": engine._recoveries,
        "uid": engine._uid,
        "python_rng": random.getstate(),
        "torch_rng": torch.get_rng_state(),
        "cuda_rng": torch.cuda.get_rng_state_all(),
        "next_logits": None if engine._next_logits is None else engine._next_logits.cpu(),
        "memory": engine.memory_stats(),
        "retention_events": scheduler.eviction_manager.retention_events,
    }
    manifest = {
        "schema": 2,
        "settings_fingerprint": engine.settings.fingerprint(),
        "base_fingerprint": engine.settings.fingerprint(policy=False),
        "settings": asdict(engine.settings),
        "minisgl_revision": MINISGL_REVISION,
        "patch_file_sha256": PATCH_FILE_HASHES,
        "logical_cached_tokens": req.logical_cached_len,
        "physical_cached_tokens": req.physical_cached_len,
        "raw_tokens": len(engine._raw),
        "recovery_count": engine._recoveries,
        "full_cache": req.physical_cached_len == req.logical_cached_len,
        "device_name": engine.device_name,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    torch.save(payload, temporary)
    manifest["sha256"] = _digest(temporary)
    temporary.replace(path)
    manifest_path = path.with_suffix(path.suffix + ".json")
    temporary_manifest = manifest_path.with_suffix(".tmp")
    temporary_manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary_manifest.replace(manifest_path)
    return manifest


def restore_snapshot(engine, path: Path, *, branch: bool) -> dict:
    from minisgl.core import Req, SamplingParams

    manifest = json.loads(path.with_suffix(path.suffix + ".json").read_text())
    if (
        manifest.get("schema") != 2
        or manifest.get("minisgl_revision") != MINISGL_REVISION
        or manifest.get("patch_file_sha256") != PATCH_FILE_HASHES
    ):
        raise UnsupportedPath("unsupported engine checkpoint schema or dependency revision")
    expected = engine.settings.fingerprint(policy=not branch)
    if manifest["base_fingerprint" if branch else "settings_fingerprint"] != expected:
        raise UnsupportedPath("checkpoint settings do not match this engine")
    if branch and not manifest["full_cache"]:
        raise UnsupportedPath("diagnostic branching requires a saved full-cache checkpoint")
    if _digest(path) != manifest["sha256"]:
        raise UnsupportedPath("engine checkpoint digest mismatch")
    if manifest["physical_cached_tokens"] > engine.scheduler.engine.num_pages:
        raise MemoryCapExceeded("checkpoint KV does not fit the configured pool")
    torch, scheduler = engine.torch, engine.scheduler
    payload = torch.load(path, map_location="cpu", weights_only=True)
    engine._clear_session()
    req = object.__new__(Req)
    for name, value in payload["request"].items():
        setattr(req, name, SamplingParams(**value) if name == "sampling_params" else value)
    req.table_idx = scheduler.table_manager.allocate()
    req.session_id = f"comet-{uuid.uuid4().hex}"
    engine._session_id = req.session_id
    slots = scheduler.cache_manager.allocate_token_slots(req.physical_cached_len).long()
    scheduler.engine.page_table[req.table_idx, : req.physical_cached_len].copy_(slots)
    engine._orphan_req = req
    for layer, (key, value) in enumerate(payload["kv"]):
        scheduler.engine.kv_cache.k_cache(layer).index_copy_(0, slots, key.to(scheduler.device))
        scheduler.engine.kv_cache.v_cache(layer).index_copy_(0, slots, value.to(scheduler.device))
        engine._check_memory()
    scheduler.token_pool[req.table_idx, : req.device_len].copy_(req.input_ids)
    ring = scheduler.engine.query_ring
    for name, tensor in payload["query_ring"].items():
        getattr(ring, name)[req.table_idx].copy_(tensor)
    ring._refresh_unordered_read_indices(req.table_idx)
    engine._raw = list(payload["raw"])
    engine._phase = list(payload["phase"])
    engine._semantic = list(payload["semantic"])
    engine._recoveries = payload["recoveries"]
    engine._uid = payload["uid"]
    engine._next_logits = (
        None if payload["next_logits"] is None else payload["next_logits"].to(scheduler.device)
    )
    scheduler.eviction_manager.retention_events = payload["retention_events"]
    with torch.inference_mode(), scheduler.engine_stream_ctx:
        scheduler.engine.stream.wait_stream(scheduler.stream)
        if branch and not scheduler.eviction_manager.disabled:
            error = scheduler.eviction_manager.maybe_compact(req, finished=True)
            if error:
                raise MemoryCapExceeded(error.error)
        scheduler.session_manager.finish_request(req)
        torch.cuda.synchronize()
    engine._orphan_req = None
    random.setstate(payload["python_rng"])
    torch.set_rng_state(payload["torch_rng"])
    torch.cuda.set_rng_state_all(payload["cuda_rng"])
    saved_memory = payload["memory"]
    if not branch:
        with engine._memory_lock:
            engine._peak_total = max(engine._peak_total, saved_memory["peak_total_vram_bytes"])
            engine._peak_kv = max(engine._peak_kv, saved_memory["peak_kv_cache_bytes"])
    engine._check_memory()
    scheduler.cache_manager.check_integrity(owned_pages=scheduler.session_manager.owned_pages())
    return manifest
