import json
from dataclasses import replace
from threading import Lock
from types import SimpleNamespace

import pytest

from comet.engine import EngineSettings, MiniSGLangEngine, retention_target
from comet.engine.contracts import MODEL_PROFILES, MODEL_REVISION, model_storage


def settings(**changes):
    config = EngineSettings(
        model_path="/unused/snapshot", model_revision=MODEL_REVISION,
        tokenizer_revision=MODEL_REVISION, method="full", retention=1.0,
        max_context_tokens=1024, peak_vram_bytes=40 << 30,
        workspace_reserve_bytes=4 << 30, prefill_chunk_tokens=128,
    )
    return replace(config, **changes)


def test_retention_uses_full_logical_denominator_and_includes_mandatory_entries():
    assert retention_target(101, 0.8, "streamingllm") == 81
    assert retention_target(101, 0.5, "rkv") == 51
    assert retention_target(101, 0.25, "agentkv") == 26
    assert retention_target(20, 0.25, "agentkv") == 20
    assert retention_target(20, 0.25, "streamingllm") == 16
    assert retention_target(20, 0.25, "rkv") == 8
    assert retention_target(101, 1, "full") == 101


@pytest.mark.parametrize("method", ["streamingllm", "rkv", "agentkv"])
@pytest.mark.parametrize("retention", [0.8, 0.5, 0.25])
def test_retention_growth_never_requires_inventing_previously_evicted_entries(method, retention):
    previous = 0
    for tokens in range(1, 1001):
        current = retention_target(tokens, retention, method)
        assert previous <= current <= previous + 1
        assert current <= tokens
        previous = current


def test_settings_reject_unpinned_model_or_invalid_control():
    for changes in ({"retention": 0.5}, {"model_revision": "main"},
                    {"prefill_chunk_tokens": 0}, {"workspace_reserve_bytes": 50 << 30}):
        with pytest.raises(ValueError):
            settings(**changes)


def test_exploratory_model_requires_its_own_matching_model_and_tokenizer_pin():
    revision = MODEL_PROFILES["Qwen/Qwen3-14B"]["revision"]
    exploratory = settings(model="Qwen/Qwen3-14B", model_revision=revision,
                           tokenizer_revision=revision)
    assert exploratory.fingerprint(policy=False) != settings().fingerprint(policy=False)
    for changes in ({"model": "Qwen/Qwen3-8B"}, {"model_revision": MODEL_REVISION},
                    {"tokenizer_revision": MODEL_REVISION}, {"model": "Qwen/Qwen3.5-9B"}):
        with pytest.raises(ValueError, match="model/revision"):
            replace(exploratory, **changes)


def test_model_storage_validates_architecture_precision_and_parameter_count(tmp_path):
    revision = MODEL_PROFILES["Qwen/Qwen3-14B"]["revision"]
    snapshot = tmp_path / revision
    snapshot.mkdir()
    config = {
        "architectures": ["Qwen3ForCausalLM"], "model_type": "qwen3",
        "hidden_size": 5120, "num_hidden_layers": 40, "num_attention_heads": 40,
        "intermediate_size": 17408, "num_key_value_heads": 8, "head_dim": 128,
        "vocab_size": 151936, "hidden_act": "silu", "attention_bias": False,
        "tie_word_embeddings": False, "rope_scaling": None, "rope_theta": 1000000,
        "max_position_embeddings": 40960, "sliding_window": None,
        "use_sliding_window": False, "rms_norm_eps": 1e-6, "torch_dtype": "bfloat16",
    }
    config_path = snapshot / "config.json"
    config_path.write_text(json.dumps(config))

    def weights(dtype="BF16", count=14768307200):
        header = json.dumps({"weight": {"dtype": dtype, "shape": [count]}}).encode()
        (snapshot / "model.safetensors").write_bytes(len(header).to_bytes(8, "little") + header)

    weights()
    assert model_storage(str(snapshot), revision, "Qwen/Qwen3-14B") == (config, 14768307200)
    for key, value in (("hidden_size", 4096), ("num_attention_heads", 32),
                       ("architectures", ["Qwen3_5ForConditionalGeneration"]),
                       ("rope_scaling", {"factor": 4.0})):
        config_path.write_text(json.dumps({**config, key: value}))
        with pytest.raises(ValueError, match="architecture"):
            model_storage(str(snapshot), revision, "Qwen/Qwen3-14B")
    config_path.write_text(json.dumps(config))
    weights(dtype="F16")
    with pytest.raises(ValueError, match="BF16"):
        model_storage(str(snapshot), revision, "Qwen/Qwen3-14B")
    weights(count=8190735360)
    with pytest.raises(ValueError, match="parameter count"):
        model_storage(str(snapshot), revision, "Qwen/Qwen3-14B")


def test_branch_fingerprint_only_excludes_policy_and_local_snapshot_location():
    full = settings()
    compressed = settings(method="rkv", retention=0.5, model_path="/another/snapshot")
    assert full.fingerprint() != compressed.fingerprint()
    assert full.fingerprint(policy=False) == compressed.fingerprint(policy=False)
    assert full.fingerprint(policy=False) != settings(max_context_tokens=2048).fingerprint(policy=False)


def test_empty_recovery_is_explicit_and_never_counts_as_a_rebuild():
    engine = MiniSGLangEngine.__new__(MiniSGLangEngine)
    engine._raw = []
    engine._recoveries = 0
    engine.memory_stats = lambda: {}
    result = engine.recover([], deadline=1.0)
    assert not result.admitted
    assert result.reason == "empty_history"
    assert engine.recovery_count == 0


def test_recovery_refuses_a_different_history_or_second_rebuild():
    engine = MiniSGLangEngine.__new__(MiniSGLangEngine)
    engine._raw = [1, 2, 3]
    engine._recoveries = 1
    engine.memory_stats = lambda: {}
    with pytest.raises(ValueError, match="exact"):
        engine.recover([1, 3], deadline=1.0)
    result = engine.recover([1, 2, 3], deadline=1.0)
    assert not result.admitted
    assert result.reason == "recovery_limit"


@pytest.mark.parametrize("pool,available,reason", [(2, 100, "full_history_exceeds_kv_pool"),
                                                (10, 5, "transient_workspace_exceeds_cap")])
def test_recovery_admission_denial_preserves_transcript_and_allowance(pool, available, reason):
    engine = MiniSGLangEngine.__new__(MiniSGLangEngine)
    engine._raw = [1, 2, 3]
    engine._recoveries = 0
    engine.settings = SimpleNamespace(peak_vram_bytes=100, workspace_reserve_bytes=10, method="agentkv",
                                      max_context_tokens=100)
    engine.scheduler = SimpleNamespace(engine=SimpleNamespace(num_pages=pool))
    engine.torch = SimpleNamespace(cuda=SimpleNamespace(
        mem_get_info=lambda: (available, 100), memory_reserved=lambda: 0, memory_allocated=lambda: 0,
    ))
    engine._check_deadline = lambda deadline: None
    engine.memory_stats = lambda: {}
    result = engine.recover([1, 2, 3, 4], deadline=1.0)
    assert not result.admitted and result.reason == reason
    assert engine.raw_token_ids == [1, 2, 3]
    assert engine.recovery_count == 0


def test_warmup_covers_all_conditions_once_and_restores_selected_policy():
    engine = MiniSGLangEngine.__new__(MiniSGLangEngine)
    engine.settings = settings(method="rkv", retention=0.25)
    engine._warmup_record = None
    engine.tokenizer = SimpleNamespace(encode=lambda *args, **kwargs: [42])
    calls = []

    def set_policy(method, retention):
        engine.settings = replace(engine.settings, method=method, retention=retention)
        engine._session_id = None

    def start(seed):
        engine._session_id = "warmup"

    def generate(tokens, count, temperature, top_p, deadline, **kwargs):
        calls.append((engine.settings.method, engine.settings.retention, tokens, count, kwargs))

    engine.set_policy, engine.start, engine.generate = set_policy, start, generate
    record = engine.warmup()
    assert len(calls) == 10
    assert all(len(call[2]) == 128 and call[3] == 2 and call[4]["ignore_eos"] for call in calls)
    assert (engine.settings.method, engine.settings.retention) == ("rkv", 0.25)
    assert engine._session_id is None
    assert engine.warmup() is record
    assert len(calls) == 10


def test_rkv_recovery_workspace_accounts_for_concurrent_redundancy_heads():
    engine = MiniSGLangEngine.__new__(MiniSGLangEngine)
    engine.settings = SimpleNamespace(method="rkv", workspace_reserve_bytes=1)
    engine._num_kv_heads, engine._num_layers = 8, 32
    engine.kv_bytes_per_token = 2 * 2 * 32 * 8 * 128
    engine.scheduler = SimpleNamespace(eviction_manager=SimpleNamespace(
        base_plan=SimpleNamespace(redundancy_max_similarity_bytes=1 << 30),
    ))
    count = 4096
    expected_heads = 5
    bound = engine._workspace_bound(count)
    assert bound >= 24 * expected_heads * count * count
    assert bound > 2_000_000_000


def test_allocator_ceiling_only_tightens_when_external_device_use_grows():
    engine = MiniSGLangEngine.__new__(MiniSGLangEngine)
    fractions = []
    engine.settings = SimpleNamespace(peak_vram_bytes=1000)
    engine.device_total_bytes = 2000
    engine._peak_total, engine._peak_external, engine._allocator_external_bytes = 600, 200, 100
    engine._monitor_error = None
    engine._memory_lock = Lock()
    engine._sample_memory = lambda: None
    engine.torch = SimpleNamespace(cuda=SimpleNamespace(
        max_memory_reserved=lambda: 100,
        set_per_process_memory_fraction=lambda fraction, **kwargs: fractions.append(fraction),
    ))
    engine._check_memory()
    engine._peak_external = 150
    engine._check_memory()
    engine._peak_external = 300
    engine._check_memory()
    assert fractions == [0.4, 0.35]
