from dataclasses import replace
from types import SimpleNamespace

import pytest

from comet.engine import retention_target

torch = pytest.importorskip("torch")
eviction = pytest.importorskip("minisgl.eviction")
relative_budget = pytest.importorskip("minisgl.eviction.relative").relative_budget
LayerEvictionView, create_eviction_plan = eviction.LayerEvictionView, eviction.create_eviction_plan


@pytest.mark.parametrize("method", ["streamingllm", "rkv", "agentkv"])
@pytest.mark.parametrize("retention", [0.8, 0.5, 0.25])
def test_existing_algorithms_select_exact_relative_budgets_per_head(method, retention):
    torch.manual_seed(21)
    plan = create_eviction_plan(method)
    target = relative_budget(plan, 101, retention)
    assert target == retention_target(101, retention, method)
    plan = (replace(plan, window_tokens=target - plan.sink_tokens)
            if method == "streamingllm" else replace(plan, budget=target))
    view = LayerEvictionView(
        layer_id=0, physical_cached_len=101, num_kv_heads=2, device=torch.device("cpu"),
        k=torch.randn(101, 2, 16), v=torch.randn(101, 2, 16),
        q_observation=torch.randn(32, 4, 16),
        q_observation_positions=torch.arange(69, 101, dtype=torch.int32),
    )
    indices = plan.select_layer(view)
    assert indices.shape == (2, target)
    for row in indices:
        assert row.unique().numel() == target
        assert row.min() >= 0 and row.max() < 101
    if method == "streamingllm":
        assert indices[0, :16].tolist() == list(range(16))
        assert indices[0, 16:].tolist() == list(range(101 - target + 16, 101))
    else:
        assert set(range(93, 101)) <= set(indices[0].tolist())


def test_patch_rejects_missing_attention_observations_instead_of_full_cache_fallback():
    from minisgl.eviction.manager import EvictionManager

    manager = object.__new__(EvictionManager)
    manager.base_plan = manager.plan = create_eviction_plan("rkv")
    manager.retention_fraction = 0.5
    manager.retention_events = []
    manager.engine = SimpleNamespace(kv_cache=SimpleNamespace(
        num_layers=1, k_cache=lambda _: torch.zeros(100, 1, 2, 16),
    ))
    manager._make_layer_eviction_view = lambda *args, **kwargs: LayerEvictionView(
        layer_id=0, physical_cached_len=100, num_kv_heads=2, device=torch.device("cpu"),
        k=torch.zeros(100, 2, 16), q_observation=torch.empty(0, 4, 16),
    )
    with pytest.raises(RuntimeError, match="fallback is forbidden"):
        manager._select_compaction_indices(SimpleNamespace(logical_cached_len=100, physical_cached_len=100))


def test_page_high_water_mark_captures_transient_compaction_ownership():
    from minisgl.scheduler.cache import CacheManager

    manager = CacheManager(20, 1, torch.zeros((1, 20), dtype=torch.int32))
    previous = manager.allocate_token_slots(10)
    replacement = manager.allocate_token_slots(5)
    manager.free_token_slots(previous)
    assert manager.available_pages == 15
    assert manager.peak_used_pages == 15
    manager.free_token_slots(replacement)
    assert manager.available_pages == 20
    assert manager.peak_used_pages == 15
