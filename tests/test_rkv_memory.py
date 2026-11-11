import pytest

torch = pytest.importorskip("torch")
r1kv = pytest.importorskip("comet_agentkv.r1kv")

from comet.engine.rkv_memory import redundancy_scores  # noqa: E402


@pytest.mark.parametrize("direction", ["last", "first", "last_percent", "first_percent"])
def test_tiled_redundancy_preserves_upstream_scores(direction):
    torch.manual_seed(17)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    keys = torch.randn(4, 513, 64, device=device, dtype=torch.bfloat16)
    keys[:, 100:200] = keys[:, :100]
    settings = dict(redundancy_threshold=0.5, retain_ratio=0.1, retain_direction=direction)
    expected = r1kv._r1kv_redundancy_scores_by_head_chunk(keys, **settings)
    actual = redundancy_scores(keys, max_similarity_bytes=4 * 513 * 19 * 31, **settings)
    torch.testing.assert_close(actual, expected, rtol=0.015, atol=0)


def test_single_token_redundancy_is_zero():
    keys = torch.ones(4, 1, 8)
    actual = redundancy_scores(keys, redundancy_threshold=0.5, retain_ratio=0.1,
                               retain_direction="last")
    assert actual.shape == (4, 1)
    assert not actual.count_nonzero()
