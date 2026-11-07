from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import random
import subprocess
import tempfile
import threading
import uuid
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from comet.clocks import monotonic
from comet.errors import BudgetExpired, MemoryCapExceeded, UnsupportedPath

from ._pins import PATCH_FILE_HASHES
from .contracts import (
    MINISGL_REVISION,
    EngineSettings,
    GenerationResult,
    RecoveryResult,
    model_storage,
    retention_target,
)


class MiniSGLangEngine:
    """One model, one live session, and a separate raw CPU token transcript."""

    def __init__(self, settings: EngineSettings):
        self.settings = settings
        self._verify_installation()
        import torch
        from minisgl.distributed import DistributedInfo
        from minisgl.scheduler import Scheduler, SchedulerConfig

        self.torch = torch
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise UnsupportedPath("expose exactly one NVIDIA GPU with CUDA_VISIBLE_DEVICES")
        properties = torch.cuda.get_device_properties(0)
        if settings.require_a100 and ("A100" not in properties.name or properties.total_memory < 79_000_000_000):
            raise UnsupportedPath("main experiments require one A100 80GB; use integration mode for smoke checks")
        if settings.peak_vram_bytes > properties.total_memory:
            raise MemoryCapExceeded("configured VRAM cap exceeds device capacity")
        model_config, self.parameter_count = model_storage(settings.model_path, settings.model_revision,
                                                           settings.model)
        if settings.max_context_tokens > model_config["max_position_embeddings"]:
            raise UnsupportedPath("configured context exceeds the pinned model's supported positions")
        self._num_layers = model_config["num_hidden_layers"]
        self._num_kv_heads = model_config["num_key_value_heads"]
        self._attention_flop_factor = (4 * model_config["num_hidden_layers"]
                                      * model_config["num_attention_heads"] * model_config["head_dim"])
        self.kv_bytes_per_token = (
            2 * 2 * model_config["num_hidden_layers"] * model_config["num_key_value_heads"]
            * model_config.get("head_dim", model_config["hidden_size"] // model_config["num_attention_heads"])
        )
        free, total = torch.cuda.mem_get_info()
        self._external_bytes = total - free - torch.cuda.memory_reserved()
        self._allocator_external_bytes = self._external_bytes
        allocator_cap = settings.peak_vram_bytes - self._external_bytes
        if allocator_cap <= 0:
            raise MemoryCapExceeded("GPU memory already exceeds configured cap")
        torch.cuda.set_per_process_memory_fraction(allocator_cap / total, device=0)
        pool_bytes = allocator_cap - self.parameter_count * 2 - settings.workspace_reserve_bytes
        pool_tokens = min(settings.max_context_tokens, pool_bytes // self.kv_bytes_per_token - 1)
        if pool_tokens < 2:
            raise MemoryCapExceeded("model and transient workspace leave no feasible KV pool")
        self._distributed_store = tempfile.TemporaryDirectory(prefix="comet-rendezvous-")
        rendezvous_uri = (Path(self._distributed_store.name) / "store").as_uri()

        class SingleGPUConfig(SchedulerConfig):
            @property
            def distributed_addr(self):
                return rendezvous_uri

        config = SingleGPUConfig(
            model_path=settings.model_path,
            tp_info=DistributedInfo(0, 1),
            dtype=torch.bfloat16,
            max_running_req=1,
            page_size=1,
            attention_backend="fi",
            cuda_graph_bs=[],
            max_seq_len_override=settings.max_context_tokens,
            num_page_override=pool_tokens,
            max_extend_tokens=settings.prefill_chunk_tokens,
            prefill_chunk_size=settings.prefill_chunk_tokens,
            offline_mode=True,
            eviction_plan="none" if settings.method == "full" else settings.method,
            comet_retention_fraction=None if settings.method == "full" else settings.retention,
            compact_interval=1,
            compact_after_prefill=True,
            compact_before_park=True,
            compact_aware_kv_reserve=True,
            query_ring_capacity=8,
            query_ring_num_stages=4,
        )
        try:
            self.scheduler = Scheduler(config)
        except BaseException:
            self._distributed_store.cleanup()
            raise
        self.scheduler.send_result = self._receive
        self.tokenizer = self.scheduler.tokenizer
        self.device_name = properties.name
        self.device_total_bytes = properties.total_memory
        self._raw: list[int] = []
        self._phase: list[int] = []
        self._semantic: list[int] = []
        self._session_id: str | None = None
        self._uid = 0
        self._orphan_req = None
        self._next_logits = None
        self._recoveries = 0
        self._replies: list = []
        self._peak_total = 0
        self._peak_kv = 0
        self._peak_external = self._external_bytes
        self._memory_lock = threading.Lock()
        self._monitor_stop = threading.Event()
        self._monitor_error: Exception | None = None
        self._warmup_record: dict | None = None
        self._monitor = threading.Thread(target=self._monitor_memory, daemon=True)
        self._monitor.start()
        self._sample_memory()
        self._check_memory()

    @staticmethod
    def _verify_installation():
        spec = importlib.util.find_spec("minisgl")
        if spec is None or not spec.submodule_search_locations:
            raise UnsupportedPath("install the pinned, patched Mini-SGLang checkout first")
        source = Path(next(iter(spec.submodule_search_locations)))
        result = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True, text=True,
        )
        if result.returncode or result.stdout.strip() != MINISGL_REVISION:
            raise UnsupportedPath("Mini-SGLang checkout does not match the pinned revision")
        for name, expected in PATCH_FILE_HASHES.items():
            file = source / name
            if not file.exists() or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
                raise UnsupportedPath(f"Mini-SGLang patch file mismatch: {name}")
        changes = subprocess.run(
            ["git", "-C", str(source), "diff", "HEAD", "--name-only"], capture_output=True,
            text=True, check=True,
        ).stdout.splitlines()
        if set(changes) - {"python/minisgl/" + name for name in PATCH_FILE_HASHES}:
            raise UnsupportedPath("unrecorded changes in the pinned Mini-SGLang checkout")

    @property
    def raw_token_ids(self) -> list[int]:
        return list(self._raw)

    @property
    def recovery_count(self) -> int:
        return self._recoveries

    @property
    def retention_events(self) -> list[dict]:
        return list(self.scheduler.eviction_manager.retention_events)

    def provenance(self) -> dict:
        versions = {}
        for name in ("torch", "transformers", "flashinfer-python", "sgl-kernel", "triton", "safetensors"):
            try:
                versions[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                versions[name] = None
        try:
            driver = subprocess.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5, check=True,
            ).stdout.splitlines()[0].strip()
        except (OSError, subprocess.SubprocessError, IndexError):
            driver = None
        return {
            "backend": "native_minisgl", "minisgl_revision": MINISGL_REVISION,
            "patch_file_sha256": PATCH_FILE_HASHES,
            "model": self.settings.model,
            "model_scope": "main" if self.settings.model == "Qwen/Qwen3-8B" else "exploratory_pilot",
            "model_revision": self.settings.model_revision,
            "tokenizer_revision": self.settings.tokenizer_revision,
            "model_path": str(Path(self.settings.model_path).resolve()),
            "model_parameter_count": self.parameter_count,
            "dtype": "bfloat16", "device_name": self.device_name,
            "device_total_bytes": self.device_total_bytes, "cuda_runtime": self.torch.version.cuda,
            "driver_version": driver,
            "packages": versions, "attention_backend": "flashinfer_fa2", "cuda_graphs": False,
            "query_ring_stages": 4, "query_ring_capacity_per_stage": 8,
            "estimated_flops_method": "dense_2P_per_forward_token_plus_causal_qk_av_4LHD_per_attention_pair",
            "estimated_flops_exclusions": ["eviction_scoring", "elementwise_operations", "sampling"],
            "memory": self.memory_stats(),
            "warmup": self._warmup_record,
        }

    def warmup(self, deadline: float | None = None) -> dict:
        if self._warmup_record is not None:
            return self._warmup_record
        if self.settings.max_context_tokens < 4:
            raise UnsupportedPath("warmup requires room for a prompt and two generated tokens")
        original = self.settings
        deadline = monotonic() + 600 if deadline is None else deadline
        count = min(original.max_context_tokens - 2, max(128, original.prefill_chunk_tokens))
        token = self.tokenizer.encode("warmup", add_special_tokens=False)[0]
        started = monotonic()
        conditions = [("full", 1.0)] + [(method, retention) for method in ("streamingllm", "rkv", "agentkv")
                                       for retention in (0.8, 0.5, 0.25)]
        try:
            for method, retention in conditions:
                self.set_policy(method, retention)
                self.start(0)
                self.generate([token] * count, 2, 0.0, 1.0, deadline, ignore_eos=True)
            self._warmup_record = {
                "seconds": monotonic() - started, "prompt_tokens": count, "max_new_tokens": 2,
                "conditions": conditions, "task_data_used": False,
                "later_shape_dependent_compilation": "charged_to_task_budget",
            }
            return self._warmup_record
        finally:
            self.set_policy(original.method, original.retention)

    def _receive(self, messages):
        from minisgl.message import DetokenizeMsg

        for message in messages:
            if isinstance(message, DetokenizeMsg):
                self._append_phases([message.next_token])
                self._raw.append(message.next_token)
        self._replies.extend(messages)

    def _state(self):
        return self.scheduler.session_manager.sessions.get(self._session_id)

    def _sample_memory(self):
        with self._memory_lock:
            torch = self.torch
            free, total = torch.cuda.mem_get_info()
            reserved = torch.cuda.memory_reserved()
            self._peak_external = max(self._peak_external, total - free - reserved)
            self._peak_total = max(self._peak_total, total - free)
            occupied = self.scheduler.cache_manager.peak_used_pages
            self._peak_kv = max(self._peak_kv, occupied * self.kv_bytes_per_token)

    def _monitor_memory(self):
        while not self._monitor_stop.wait(0.01):
            try:
                self._sample_memory()
            except Exception as exc:
                self._monitor_error = exc
                return

    def _check_memory(self):
        self._sample_memory()
        if self._monitor_error is not None:
            raise UnsupportedPath(f"total-device memory monitoring failed: {self._monitor_error}")
        peak = max(self._peak_total, self.torch.cuda.max_memory_reserved() + self._peak_external)
        if peak > self.settings.peak_vram_bytes:
            raise MemoryCapExceeded(f"peak total VRAM {peak} exceeds cap {self.settings.peak_vram_bytes}")
        with self._memory_lock:
            if self._peak_external > self._allocator_external_bytes:
                self._allocator_external_bytes = self._peak_external
                ceiling = self.settings.peak_vram_bytes - self._allocator_external_bytes
                self.torch.cuda.set_per_process_memory_fraction(ceiling / self.device_total_bytes, device=0)

    def _check_deadline(self, deadline: float):
        if monotonic() >= deadline:
            raise BudgetExpired("shared task deadline reached during inference")
        self._check_memory()

    def memory_stats(self) -> dict:
        self._sample_memory()
        state = self._state()
        cached = state.req.physical_cached_len if state is not None and state.req is not None else 0
        logical = state.req.logical_cached_len if state is not None and state.req is not None else 0
        return {
            "peak_total_vram_bytes": max(self._peak_total, self.torch.cuda.max_memory_reserved() + self._peak_external),
            "peak_total_vram_sampled_bytes": self._peak_total,
            "peak_torch_allocated_bytes": self.torch.cuda.max_memory_allocated(),
            "peak_torch_reserved_bytes": self.torch.cuda.max_memory_reserved(),
            "peak_kv_cache_bytes": self._peak_kv,
            "peak_kv_bytes": self._peak_kv,
            "reserved_kv_pool_bytes": self.scheduler.engine.kv_cache._kv_buffer.numel() * 2,
            "reserved_kv_bytes": self.scheduler.engine.kv_cache._kv_buffer.numel() * 2,
            "kv_pool_tokens": self.scheduler.engine.num_pages,
            "physical_cached_tokens": cached,
            "logical_cached_tokens": logical,
            "retention_target_tokens": retention_target(logical, self.settings.retention, self.settings.method),
            "memory_sample_interval_seconds": 0.01,
            "total_peak_kind": "max(sampled device use, allocator peak plus maximum external use)",
        }

    def _clear_session(self):
        scheduler = self.scheduler
        self.torch.cuda.synchronize()
        # Batch size one permits a complete allocator reset after an interrupted forward.
        scheduler.cache_manager.free_slots = self.torch.arange(
            scheduler.engine.num_pages, dtype=self.torch.int32, device=scheduler.device,
        )
        scheduler.cache_manager.peak_used_pages = 0
        scheduler.table_manager._free_slots = [0]
        scheduler.engine.page_table[0].zero_()
        scheduler.token_pool[0].zero_()
        scheduler.engine.query_ring.reset(0)
        scheduler.decode_manager.running_reqs.clear()
        scheduler.session_manager.sessions.clear()
        scheduler.session_manager.closed_sessions.clear()
        scheduler.finished_reqs.clear()
        scheduler.prefill_manager.pending_list.clear()
        scheduler.prefill_manager.inflight_partials.clear()
        scheduler.cache_manager.check_integrity(owned_pages=0)
        self._session_id = None
        self._orphan_req = None
        self._next_logits = None
        scheduler.engine.comet_last_prefill_logits = None

    def set_policy(self, method: str, retention: float):
        from minisgl.eviction import create_eviction_plan

        settings = replace(self.settings, method=method, retention=retention)
        self._clear_session()
        manager = self.scheduler.eviction_manager
        manager.plan = manager.base_plan = create_eviction_plan("none" if method == "full" else method)
        manager.disabled = method == "full"
        manager.retention_fraction = None if method == "full" else retention
        manager.retention_events.clear()
        self.settings = settings

    def _forward_flops(self, batch) -> int:
        tokens = sum(req.extend_len for req in batch.reqs)
        pairs = sum(req.extend_len * req.physical_cached_len + req.extend_len * (req.extend_len + 1) // 2
                    for req in batch.reqs)
        return 2 * self.parameter_count * tokens + self._attention_flop_factor * pairs

    def start(self, seed: int):
        self._clear_session()
        self._session_id = f"comet-{uuid.uuid4().hex}"
        self._raw, self._phase, self._semantic = [], [], []
        self._recoveries = 0
        self.scheduler.eviction_manager.retention_events.clear()
        self.torch.cuda.empty_cache()
        with self._memory_lock:
            self.torch.cuda.reset_peak_memory_stats()
            self._peak_kv = self._peak_total = 0
            self._peak_external = self._external_bytes
        random.seed(seed)
        self.torch.manual_seed(seed)
        self.torch.cuda.manual_seed_all(seed)
        self._check_memory()

    def _append_phases(self, token_ids):
        from minisgl.scheduler.scheduler import _phase_from_tail, _semantic_phase_from_tail

        tail = self.tokenizer.decode(self._raw[-128:], skip_special_tokens=False)[-128:]
        phase = self._phase[-1] if self._phase else 0
        semantic = self._semantic[-1] if self._semantic else -1
        for token in token_ids:
            tail = (tail + self.tokenizer.decode([token], skip_special_tokens=False))[-128:]
            phase = _phase_from_tail(tail, phase)
            semantic = _semantic_phase_from_tail(tail, semantic)
            self._phase.append(phase)
            self._semantic.append(semantic)

    def _sample_saved_logits(self, sampling_params) -> float:
        from minisgl.core import Batch
        from minisgl.engine.engine import ForwardOutput

        scheduler, torch = self.scheduler, self.torch
        state = self._state()
        if state is None or state.req is None:
            raise UnsupportedPath("saved recovery logits require a parked session")
        req = state.req
        req.uid = self._uid
        req.sampling_params = sampling_params
        req.output_len, req.generated_len = sampling_params.max_tokens, 0
        req.max_device_len = req.device_len + sampling_params.max_tokens
        req.session_prompt_len = len(self._raw)
        req.prefill_only = False
        req.phase_text_tail = self.tokenizer.decode(self._raw[-128:], skip_special_tokens=False)[-128:]
        state.status = "RUNNING"
        batch = Batch([req], "prefill")
        batch.padded_reqs = [req]
        started = monotonic()
        with torch.inference_mode(), scheduler.engine_stream_ctx:
            scheduler.engine.stream.wait_stream(scheduler.stream)
            args = scheduler.engine.sampler.prepare(batch)
            begin = torch.cuda.Event(enable_timing=True)
            ready = torch.cuda.Event(enable_timing=True)
            copied = torch.cuda.Event(enable_timing=True)
            begin.record()
            token = scheduler.engine.sampler.sample(self._next_logits, args).to(torch.int32)
            ready.record()
            host = token.to("cpu", non_blocking=True)
            copied.record()
            req.complete_one()
            scheduler.token_pool[req.table_idx, req.physical_cached_len] = token[0]
            scheduler.decode_manager.filter_reqs([req])
            output = ForwardOutput(token, host, copied, begin, ready, False)
            scheduler._process_last_data((SimpleNamespace(batch=batch), output))
            torch.cuda.synchronize()
        self._next_logits = None
        scheduler.engine.comet_last_prefill_logits = None
        return monotonic() - started

    def generate(self, append_token_ids: list[int], max_new_tokens: int, temperature: float,
                 top_p: float, deadline: float, *, ignore_eos: bool = False) -> GenerationResult:
        from minisgl.core import SamplingParams
        from minisgl.message import TokenizerErrorMsg, UserMsg

        if self._session_id is None:
            raise RuntimeError("call start(seed) before generate")
        if max_new_tokens <= 0 or not 0 < top_p <= 1 or temperature < 0:
            raise ValueError("invalid sampling settings")
        if len(self._raw) + len(append_token_ids) + max_new_tokens > self.settings.max_context_tokens:
            raise UnsupportedPath("generation would exceed the frozen maximum context; truncation is forbidden")
        self._check_deadline(deadline)
        self._append_phases(append_token_ids)
        self._raw.extend(append_token_ids)
        self._uid += 1
        self._replies = []
        prefill_seconds = decode_seconds = 0.0
        prompt_tokens = estimated_flops = decode_outputs = 0
        sampling = SamplingParams(temperature=temperature, top_p=top_p, max_tokens=max_new_tokens,
                                  ignore_eos=ignore_eos)
        try:
            if self._next_logits is not None and not append_token_ids:
                prefill_seconds = self._sample_saved_logits(sampling)
            else:
                self._next_logits = None
                self.scheduler.engine.comet_last_prefill_logits = None
                self.scheduler._process_one_msg(UserMsg(
                    uid=self._uid,
                    input_ids=self.torch.tensor(self._raw, dtype=self.torch.int32),
                    phase_ids=self.torch.tensor(self._phase, dtype=self.torch.int32),
                    semantic_phase_ids=self.torch.tensor(self._semantic, dtype=self.torch.int32),
                    sampling_params=sampling,
                    session_id=self._session_id,
                ))
            while self.scheduler.prefill_manager.runnable or self.scheduler.decode_manager.runnable:
                self._check_deadline(deadline)
                with self.torch.inference_mode(), self.scheduler.engine_stream_ctx:
                    self.scheduler.engine.stream.wait_stream(self.scheduler.stream)
                    forward = self.scheduler._schedule_next_batch()
                    if forward is None:
                        raise MemoryCapExceeded("insufficient KV pool for the pending suffix and generation")
                    tokens = sum(req.extend_len for req in forward.batch.reqs)
                    estimated_flops += self._forward_flops(forward.batch)
                    self._sample_memory()
                    started = monotonic()
                    output = self.scheduler._forward(forward)
                    self.scheduler._process_last_data((forward, output))
                    self.torch.cuda.synchronize()
                    elapsed = monotonic() - started
                    if forward.batch.is_prefill:
                        prefill_seconds += elapsed
                        prompt_tokens += tokens
                    else:
                        decode_seconds += elapsed
                        decode_outputs += forward.batch.size
                self._check_deadline(deadline)
            self._check_deadline(deadline)
            errors = [reply.error for reply in self._replies if isinstance(reply, TokenizerErrorMsg)]
            if errors:
                raise UnsupportedPath("; ".join(errors))
            result = [reply.next_token for reply in self._replies]
            state = self._state()
            if state is None or state.req is None:
                raise UnsupportedPath("native session did not park its KV state")
            state.req.materialize_full_host()
            state.full_token_ids = self.torch.tensor(self._raw, dtype=self.torch.int32)
            state.full_phase_ids = self.torch.tensor(self._phase, dtype=self.torch.int32)
            if state.req.full_input_ids.tolist() != self._raw:
                raise UnsupportedPath("native session and raw token transcript diverged")
            return GenerationResult(result, bool(result and result[-1] == self.tokenizer.eos_token_id),
                                    decode_seconds, prefill_seconds, prompt_tokens, decode_outputs,
                                    self.memory_stats(), estimated_flops, len(result))
        except self.torch.cuda.OutOfMemoryError as exc:
            raise MemoryCapExceeded("CUDA allocator refused memory under the experimental cap") from exc

    def recover(self, full_token_ids: list[int], deadline: float) -> RecoveryResult:
        started = monotonic()
        full_token_ids = list(full_token_ids)
        if full_token_ids[:len(self._raw)] != self._raw:
            raise ValueError("recovery must preserve the exact current raw token transcript prefix")
        if self._recoveries:
            return RecoveryResult(False, "recovery_limit", 0.0, len(self._raw), self.memory_stats())
        if not full_token_ids:
            return RecoveryResult(False, "empty_history", 0.0, 0, self.memory_stats())
        self._check_deadline(deadline)
        if len(full_token_ids) > self.settings.max_context_tokens:
            return RecoveryResult(False, "full_history_exceeds_context", monotonic() - started,
                                  len(full_token_ids), self.memory_stats())
        if len(full_token_ids) > self.scheduler.engine.num_pages:
            return RecoveryResult(False, "full_history_exceeds_kv_pool", monotonic() - started,
                                  len(full_token_ids), self.memory_stats())
        free, total = self.torch.cuda.mem_get_info()
        available = self.settings.peak_vram_bytes - (total - free)
        available += self.torch.cuda.memory_reserved() - self.torch.cuda.memory_allocated()
        if self._workspace_bound(len(full_token_ids)) > available:
            return RecoveryResult(False, "transient_workspace_exceeds_cap", monotonic() - started,
                                  len(full_token_ids), self.memory_stats())
        suffix = full_token_ids[len(self._raw):]
        self._append_phases(suffix)
        self._raw.extend(suffix)
        self._recoveries += 1
        estimated_flops = self._prefill_history(deadline)
        return RecoveryResult(True, None, monotonic() - started, len(self._raw), self.memory_stats(), estimated_flops)

    def _workspace_bound(self, tokens: int) -> int:
        if self.settings.method == "rkv":
            limit = self.scheduler.eviction_manager.base_plan.redundancy_max_similarity_bytes
            heads = max(1, min(self._num_kv_heads, limit // max(1, 11 * tokens * tokens)))
            matrix = 24 * heads * tokens * tokens
            linear = 8 * self.kv_bytes_per_token * tokens // self._num_layers
            return max(self.settings.workspace_reserve_bytes, matrix + linear)
        return self.settings.workspace_reserve_bytes

    def _prefill_history(self, deadline: float):
        from minisgl.core import Batch, Req, SamplingParams

        scheduler, torch = self.scheduler, self.torch
        self._clear_session()
        self._session_id = f"comet-{uuid.uuid4().hex}"
        table = scheduler.table_manager.allocate()
        req = None
        estimated_flops = 0
        for end in range(min(len(self._raw), self.settings.prefill_chunk_tokens),
                         len(self._raw) + self.settings.prefill_chunk_tokens, self.settings.prefill_chunk_tokens):
            end = min(end, len(self._raw))
            self._check_deadline(deadline)
            req = Req(
                input_ids=torch.tensor(self._raw[:end], dtype=torch.int32),
                table_idx=table, physical_cached_len=0 if req is None else req.physical_cached_len,
                logical_cached_len=0 if req is None else req.logical_cached_len,
                retained_positions=None if req is None else req.retained_positions,
                output_len=1, uid=self._uid, sampling_params=SamplingParams(max_tokens=1),
                session_id=self._session_id, full_input_ids=torch.tensor(self._raw, dtype=torch.int32),
                phase_ids=torch.tensor(self._phase[:end], dtype=torch.int32),
                full_phase_ids=torch.tensor(self._phase, dtype=torch.int32),
                semantic_phase_ids=torch.tensor(self._semantic[:end], dtype=torch.int32), prefill_only=True,
            )
            scheduler.token_pool[table, :end].copy_(req.input_ids)
            with torch.inference_mode(), scheduler.engine_stream_ctx:
                scheduler.engine.stream.wait_stream(scheduler.stream)
                forward = scheduler._prepare_batch(Batch([req], "prefill"))
                estimated_flops += self._forward_flops(forward.batch)
                self._sample_memory()
                output = scheduler._forward(forward)
                output.copy_done_event.synchronize()
                self._check_deadline(deadline)
        if req is None:
            raise ValueError("cannot recover empty history")
        self._next_logits = scheduler.engine.comet_last_prefill_logits
        with torch.inference_mode(), scheduler.engine_stream_ctx:
            error = scheduler.eviction_manager.maybe_compact(req, finished=True)
            if error:
                raise MemoryCapExceeded(error.error)
            scheduler.session_manager.finish_request(req)
            torch.cuda.synchronize()
        self._check_deadline(deadline)
        return estimated_flops

    def checkpoint(self, path: str | Path) -> dict:
        from .snapshot import save_snapshot
        return save_snapshot(self, Path(path))

    def restore(self, path: str | Path, *, branch: bool = False) -> dict:
        from .snapshot import restore_snapshot
        return restore_snapshot(self, Path(path), branch=branch)

    def close(self):
        self._monitor_stop.set()
        self._monitor.join(timeout=1)
        self._clear_session()
        try:
            self.scheduler.shutdown()
        finally:
            self._distributed_store.cleanup()

    def synchronize(self):
        self.torch.cuda.synchronize()
