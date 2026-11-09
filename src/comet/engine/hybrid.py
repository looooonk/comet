"""Sequential Qwen3.5 inference with persistent hybrid state and pinned selectors."""

from __future__ import annotations

import importlib.metadata
import random
import threading
from dataclasses import replace
from functools import partial

from comet.clocks import monotonic
from comet.errors import BudgetExpired, MemoryCapExceeded, UnsupportedPath

from . import hybrid_state
from .contracts import GenerationResult, RecoveryResult, model_storage, retention_target


def hybrid_attention(module, query, key, value, attention_mask, scaling=None, **kwargs):
    import torch

    session = module.comet_session
    session._observe(module.layer_idx, query)
    output = torch.nn.functional.scaled_dot_product_attention(
        query, key, value, attn_mask=attention_mask, dropout_p=0.0,
        is_causal=False, scale=scaling, enable_gqa=True,
    )
    return output.transpose(1, 2).contiguous(), None


def delta_kernel(kernel, query, key, value, *, g, beta, initial_state=None,
                 output_final_state=False, use_qk_l2norm_in_kernel=True,
                 cu_seqlens=None, **kwargs):
    return kernel(query, key, value, g=g, beta=beta, initial_state=initial_state,
                  output_final_state=output_final_state,
                  use_qk_l2norm_in_kernel=use_qk_l2norm_in_kernel, cu_seqlens=cu_seqlens)


class HybridEngine:
    TRANSFORMERS_VERSION = "5.22.2"

    def __init__(self, settings):
        import torch
        from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration
        from transformers.modeling_utils import ALL_ATTENTION_FUNCTIONS

        if settings.backend != "transformers_hybrid":
            raise UnsupportedPath("hybrid engine requires an explicit hybrid backend")
        if importlib.metadata.version("transformers") != self.TRANSFORMERS_VERSION:
            raise UnsupportedPath("install the pinned hybrid runtime")
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise UnsupportedPath("expose exactly one CUDA GPU")
        self.settings, self.torch = settings, torch
        device = torch.cuda.get_device_properties(0)
        self.device_name, self.device_total_bytes = device.name, device.total_memory
        settings.validate_device(device.name, device.total_memory)
        config, self.parameter_count = model_storage(settings.model_path, settings.model_revision,
                                                     settings.model)
        if settings.max_context_tokens > config["max_position_embeddings"]:
            raise UnsupportedPath("context exceeds model support")
        free, total = torch.cuda.mem_get_info()
        self._external = total - free - torch.cuda.memory_reserved()
        available = settings.peak_vram_bytes - self._external
        if available < 2 * self.parameter_count + settings.workspace_reserve_bytes:
            raise MemoryCapExceeded("weights and workspace do not fit the selected memory cap")
        torch.cuda.set_per_process_memory_fraction(available / total)
        self.tokenizer = AutoTokenizer.from_pretrained(settings.model_path, local_files_only=True)
        self.model = Qwen3_5ForConditionalGeneration.from_pretrained(
            settings.model_path, dtype=torch.bfloat16, device_map="cuda",
            attn_implementation="sdpa", local_files_only=True,
        ).eval()
        self.text_model = self.model.model.language_model
        self.text_config = self.model.config.text_config
        self.attention_layers = [i for i, kind in enumerate(config["layer_types"])
                                 if kind == "full_attention"]
        self.kv_bytes_per_token = 4 * len(self.attention_layers) * config["num_key_value_heads"] * config["head_dim"]
        self._attention_factor = 4 * len(self.attention_layers) * config["num_attention_heads"] * config["head_dim"]
        self._text_parameters = sum(p.numel() for p in self.text_model.parameters()) + self.model.lm_head.weight.numel()
        ALL_ATTENTION_FUNCTIONS.register("comet_hybrid", hybrid_attention)
        self.text_config._attn_implementation = "comet_hybrid"
        for index in self.attention_layers:
            self.text_model.layers[index].self_attn.comet_session = self
        self._install_recurrent_kernels()
        self._warmup_record = None
        self._peak_kv = self._peak_total = self._peak_recurrent = 0
        self._peak_external = self._external
        self._monitor_stop = threading.Event()
        self._monitor_error = None
        self._clear()
        self._monitor = threading.Thread(target=self._monitor_memory, daemon=True)
        self._monitor.start()
        self._check_memory()

    @staticmethod
    def _install_recurrent_kernels():
        from fla.ops.gated_delta_rule import (
            chunk_gated_delta_rule,
            fused_recurrent_gated_delta_rule,
        )
        from transformers.models.qwen3_5 import modeling_qwen3_5

        # Keep the upstream hybrid forward and replace only its equivalent recurrent kernels.
        modeling_qwen3_5.torch_chunk_gated_delta_rule = partial(delta_kernel, chunk_gated_delta_rule)
        modeling_qwen3_5.torch_recurrent_gated_delta_rule = partial(delta_kernel, fused_recurrent_gated_delta_rule)

    def _clear(self):
        from transformers import DynamicCache

        self.cache = DynamicCache(config=self.text_config)
        self._raw, self._events = [], []
        self._observations, self._positions = {}, {}
        self._tail, self._phase, self._recoveries = "", 0, 0
        self._next_logits = None
        self._last_generation, self._last_recovery = {}, {}

    @property
    def raw_token_ids(self):
        return list(self._raw)

    @property
    def recovery_count(self):
        return self._recoveries

    @property
    def last_generation(self):
        return dict(self._last_generation)

    @property
    def last_recovery(self):
        return dict(self._last_recovery)

    @property
    def retention_events(self):
        return list(self._events)

    def _state_bytes(self):
        kv = recurrent = 0
        for layer in self.cache.layers:
            for name in ("keys", "values"):
                tensor = getattr(layer, name, None)
                if tensor is not None:
                    kv += tensor.numel() * tensor.element_size()
            for name in ("conv_states", "recurrent_states"):
                for tensor in getattr(layer, name, {}).values():
                    if tensor is not None:
                        recurrent += tensor.numel() * tensor.element_size()
        return kv, recurrent

    def _sample_memory(self):
        free, total = self.torch.cuda.mem_get_info()
        self._peak_total = max(self._peak_total, total - free)
        self._peak_external = max(self._peak_external, total - free - self.torch.cuda.memory_reserved())

    def _monitor_memory(self):
        while not self._monitor_stop.wait(0.01):
            try:
                self._sample_memory()
            except Exception as error:
                self._monitor_error = error
                return

    def memory_stats(self):
        self._sample_memory()
        kv, recurrent = self._state_bytes()
        self._peak_kv, self._peak_recurrent = max(self._peak_kv, kv), max(self._peak_recurrent, recurrent)
        return {
            "peak_total_vram_bytes": max(self._peak_total, self.torch.cuda.max_memory_reserved() + self._peak_external),
            "peak_total_vram_sampled_bytes": self._peak_total,
            "peak_torch_allocated_bytes": self.torch.cuda.max_memory_allocated(),
            "peak_torch_reserved_bytes": self.torch.cuda.max_memory_reserved(),
            "peak_kv_cache_bytes": self._peak_kv, "peak_kv_bytes": self._peak_kv,
            "occupied_kv_bytes": kv, "recurrent_state_bytes": recurrent,
            "peak_recurrent_state_bytes": self._peak_recurrent,
            "reserved_kv_pool_bytes": 0, "reserved_kv_bytes": 0,
            "physical_cached_tokens": self.cache.get_seq_length(),
            "logical_cached_tokens": len(self._raw),
            "retention_target_tokens": retention_target(len(self._raw), self.settings.retention, self.settings.method),
            "memory_sample_interval_seconds": 0.01,
            "total_peak_kind": "max(sampled device use, allocator peak plus maximum external use)",
        }

    def _check_memory(self):
        if self._monitor_error:
            raise UnsupportedPath(f"memory monitoring failed: {self._monitor_error}")
        memory = self.memory_stats()
        if memory["peak_total_vram_bytes"] > self.settings.peak_vram_bytes:
            raise MemoryCapExceeded("hybrid inference exceeded peak total VRAM cap")
        return memory

    def _check_deadline(self, deadline):
        if monotonic() >= deadline:
            raise BudgetExpired("shared task deadline reached during hybrid inference")
        self._check_memory()

    def start(self, seed):
        self._clear()
        self.torch.cuda.empty_cache()
        self.torch.cuda.reset_peak_memory_stats()
        self._peak_kv = self._peak_total = self._peak_recurrent = 0
        self._peak_external = self._external
        random.seed(seed)
        self.torch.manual_seed(seed)
        self.torch.cuda.manual_seed_all(seed)
        self._check_memory()

    def set_policy(self, method, retention):
        self.settings = replace(self.settings, method=method, retention=retention)
        self._clear()

    def _observe(self, index, query):
        torch = self.torch
        query = query[0].transpose(0, 1).detach()
        positions = torch.arange(self._forward_start, self._forward_start + query.shape[0], device=query.device)
        ring = self._observations.setdefault(index, {})
        phase_indices = {stage: [i for i, phase in enumerate(self._forward_phases) if phase == stage]
                         for stage in range(4)}
        for stage, indices in phase_indices.items():
            if not indices:
                continue
            selected = torch.tensor(indices[-8:], device=query.device)
            q, p = query[selected], positions[selected]
            if stage in ring:
                q, p = torch.cat([ring[stage][0], q]), torch.cat([ring[stage][1], p])
            ring[stage] = (q[-8:].clone(), p[-8:].clone())
        added = positions[None].expand(self.text_config.num_key_value_heads, -1)
        previous = self._positions.get(index)
        self._positions[index] = added.clone() if previous is None else torch.cat([previous, added], dim=1)

    def _compact(self):
        from comet_agentkv import LayerEvictionView, create_eviction_plan

        if self.settings.method == "full":
            return 0.0
        target = retention_target(len(self._raw), self.settings.retention, self.settings.method)
        before = self.cache.get_seq_length()
        if before <= target:
            return 0.0
        self.synchronize()
        started = monotonic()
        plan = create_eviction_plan(self.settings.method)
        plan = (replace(plan, window_tokens=target - min(target, plan.sink_tokens), sink_tokens=min(target, plan.sink_tokens))
                if self.settings.method == "streamingllm" else replace(plan, budget=target))
        torch = self.torch
        for index in self.attention_layers:
            layer = self.cache.layers[index]
            observations = self._observations[index]
            q = torch.cat([observations[s][0] for s in sorted(observations)])
            p = torch.cat([observations[s][1] for s in sorted(observations)])
            view = LayerEvictionView(
                layer_id=index, num_layers=len(self.cache.layers), physical_cached_len=before,
                num_kv_heads=self.text_config.num_key_value_heads, device=layer.keys.device,
                logical_current_position=len(self._raw) - 1,
                logical_positions_by_head=self._positions[index],
                k=layer.keys[0].transpose(0, 1), v=layer.values[0].transpose(0, 1),
                q_observation=q, q_observation_positions=p,
            )
            keep = plan.select_layer(view).sort(dim=1).values
            if keep.shape != (self.text_config.num_key_value_heads, target):
                raise UnsupportedPath("selector did not satisfy relative retention")
            gather = keep[None, :, :, None].expand(1, -1, -1, self.text_config.head_dim)
            layer.keys = layer.keys.gather(2, gather).contiguous()
            layer.values = layer.values.gather(2, gather).contiguous()
            self._positions[index] = self._positions[index].gather(1, keep)
        self._events.append({"logical_cached_tokens": len(self._raw), "physical_before": before,
                             "target_tokens": target})
        self.synchronize()
        return monotonic() - started

    def _forward(self, tokens, deadline, progress, *, prefill, compact=True):
        self._check_deadline(deadline)
        torch = self.torch
        start, count, cached = len(self._raw), len(tokens), self.cache.get_seq_length()
        self._forward_start = start
        self._forward_phases, tail, phase = hybrid_state.phases(self.tokenizer, tokens, self._tail, self._phase)
        positions = torch.arange(start, start + count, device="cuda")[None]
        mask = None
        if count > 1:
            mask = torch.zeros((count, cached + count), dtype=torch.bfloat16, device="cuda")
            future = torch.arange(cached + count, device="cuda")[None] > cached + torch.arange(count, device="cuda")[:, None]
            mask.masked_fill_(future, float("-inf"))
            mask = mask[None, None]
        started = monotonic()
        try:
            with torch.inference_mode():
                output = self.text_model(
                    input_ids=torch.tensor([tokens], device="cuda"), position_ids=positions,
                    attention_mask={"full_attention": mask, "linear_attention": None},
                    past_key_values=self.cache, use_cache=True,
                )
                self._next_logits = self.model.lm_head(output.last_hidden_state[:, -1]).float()
                self._raw.extend(tokens)
                self._tail, self._phase = tail, phase
                self._check_memory()
                if compact:
                    progress["compaction_seconds"] += self._compact()
                self.synchronize()
            progress["estimated_flops"] += (2 * self._text_parameters * count
                + self._attention_factor * (count * cached + count * (count + 1) // 2))
            progress["prompt_tokens" if prefill else "decode_tokens"] += count
        finally:
            progress["prefill_seconds" if prefill else "decode_seconds"] += monotonic() - started
        self._check_deadline(deadline)

    @staticmethod
    def _progress():
        return {"status": "running", "failure_reason": None, "prefill_seconds": 0.0,
                "decode_seconds": 0.0, "prompt_tokens": 0, "decode_tokens": 0,
                "estimated_flops": 0, "generated_tokens": 0, "compaction_seconds": 0.0}

    def _prefill(self, tokens, deadline, progress, *, compact=True):
        chunk = self.settings.prefill_chunk_tokens
        for start in range(0, len(tokens), chunk):
            self._forward(tokens[start:start + chunk], deadline, progress, prefill=True, compact=compact)

    def _sample(self, temperature, top_p):
        torch = self.torch
        if temperature == 0:
            return self._next_logits.argmax(-1).item()
        logits, indices = (self._next_logits[0] / temperature).sort(descending=True)
        probabilities = logits.softmax(-1)
        remove = probabilities.cumsum(-1) - probabilities >= top_p
        probabilities.masked_fill_(remove, 0)
        return indices[torch.multinomial(probabilities, 1)].item()

    def generate(self, append_token_ids, max_new_tokens, temperature, top_p, deadline):
        if len(self._raw) + len(append_token_ids) + max_new_tokens > self.settings.max_context_tokens:
            raise UnsupportedPath("generation exceeds configured context limit")
        progress = self._last_generation = self._progress()
        generated, finished = [], False
        try:
            self._prefill(append_token_ids, deadline, progress)
            if self._next_logits is None:
                raise ValueError("generation requires a nonempty prompt")
            for _ in range(max_new_tokens):
                self._check_deadline(deadline)
                token = self._sample(temperature, top_p)
                generated.append(token)
                progress["generated_tokens"] += 1
                self._forward([token], deadline, progress, prefill=False)
                if token == self.tokenizer.eos_token_id:
                    finished = True
                    break
            progress["status"] = "completed"
        except BaseException as error:
            progress.update(status="failed", failure_reason=f"{type(error).__name__}: {error}")
            raise
        finally:
            progress["memory"] = self.memory_stats()
        return GenerationResult(generated, finished, progress["decode_seconds"],
                                progress["prefill_seconds"], progress["prompt_tokens"],
                                progress["decode_tokens"], progress["memory"],
                                progress["estimated_flops"], len(generated))

    def recover(self, full_token_ids, deadline):
        started = monotonic()
        reason = None
        if self._recoveries:
            reason = "recovery_limit"
        elif full_token_ids[:len(self._raw)] != self._raw or not full_token_ids:
            raise UnsupportedPath("recovery requires the complete append-only transcript")
        elif len(full_token_ids) > self.settings.max_context_tokens:
            reason = "context_limit"
        else:
            kv, _ = self._state_bytes()
            required = (self.torch.cuda.memory_allocated() - kv + self._peak_external
                        + self.kv_bytes_per_token * len(full_token_ids)
                        + self.settings.workspace_reserve_bytes)
            if required > self.settings.peak_vram_bytes:
                reason = "memory_cap"
        if reason:
            result = RecoveryResult(False, reason, monotonic() - started, len(full_token_ids), self.memory_stats())
            self._last_recovery = {"status": "denied", "admitted": False,
                                   "allowance_consumed": False, "reason": reason}
            return result
        self._check_deadline(deadline)
        rng, cpu_rng, python_rng = self.torch.cuda.get_rng_state_all(), self.torch.get_rng_state(), random.getstate()
        progress = self._progress()
        progress.update(admitted=True, allowance_consumed=True)
        old_events = self._events
        self._clear()
        self.torch.cuda.empty_cache()
        self._last_recovery = progress
        self._recoveries = 1
        try:
            self._prefill(full_token_ids, deadline, progress, compact=False)
            with self.torch.inference_mode():
                progress["compaction_seconds"] += self._compact()
            self.synchronize()
            self._check_deadline(deadline)
            progress["status"] = "completed"
        except BaseException as error:
            progress.update(status="failed", failure_reason=f"{type(error).__name__}: {error}")
            raise
        finally:
            self._events = old_events + self._events
            self.torch.cuda.set_rng_state_all(rng)
            self.torch.set_rng_state(cpu_rng)
            random.setstate(python_rng)
            progress["memory"] = self.memory_stats()
            progress["seconds"] = monotonic() - started
        return RecoveryResult(True, None, progress["seconds"], len(full_token_ids),
                              progress["memory"], progress["estimated_flops"])

    def checkpoint(self, path):
        return hybrid_state.save(self, path)

    def restore(self, path, *, branch=False):
        return hybrid_state.restore(self, path, branch)

    def warmup(self, deadline=None):
        if self._warmup_record is not None:
            return self._warmup_record
        started, original = monotonic(), self.settings
        deadline = started + 600 if deadline is None else deadline
        tokens = self.tokenizer.encode("A short warmup sentence. " * 24)
        tokens = tokens[:min(128, self.settings.max_context_tokens - 2)]
        for method in ("full", "streamingllm", "rkv", "agentkv"):
            self.set_policy(method, 1.0 if method == "full" else 0.5)
            self.start(0)
            self.generate(tokens, 2, 0.0, 1.0, deadline)
        self.settings = original
        self._clear()
        self._warmup_record = {"seconds": monotonic() - started, "tokens": len(tokens),
                               "methods": ["full", "streamingllm", "rkv", "agentkv"]}
        return self._warmup_record

    def provenance(self):
        return {"backend": self.settings.backend, "model": self.settings.model,
                "model_revision": self.settings.model_revision,
                "tokenizer_revision": self.settings.tokenizer_revision,
                "device_name": self.device_name, "device_total_bytes": self.device_total_bytes,
                "dtype": "bfloat16", "cuda_runtime": self.torch.version.cuda,
                "model_parameter_count": self.parameter_count,
                "text_parameter_count": self._text_parameters,
                "packages": {name: importlib.metadata.version(name) for name in
                             ("torch", "transformers", "flash-linear-attention", "comet-agentkv-selectors")},
                "attention_backend": "torch_sdpa", "cuda_graphs": False,
                "selector_revision": "254c57bc84e4a7895159ba1062bd46c83626f511",
                "retention_state": "full_attention_kv_only; recurrent_and_conv_state_uncompressed",
                "sampling_rng": "torch_cuda_default_generator_v1",
                "estimated_flops_method": "2P_text_per_token_plus_4LHD_per_full_attention_pair",
                "estimated_flops_exclusions": ["recurrent_state_updates", "eviction", "elementwise", "vision"],
                "memory": self.memory_stats(), "warmup": self._warmup_record}

    def synchronize(self):
        self.torch.cuda.synchronize()

    def close(self):
        self._monitor_stop.set()
        self._monitor.join(timeout=1)
        self._clear()
        for index in self.attention_layers:
            del self.text_model.layers[index].self_attn.comet_session
        del self.text_model, self.model
        self.torch.cuda.empty_cache()
