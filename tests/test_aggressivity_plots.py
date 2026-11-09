import pytest

from comet.aggressivity_plots import aggressivity_series


def test_aggressivity_preserves_measured_points_and_selects_matching_control():
    def row(method, retention, attempts):
        return {"condition": {"method": method, "retention": retention,
                              "recovery": "never", "max_attempts": attempts}}

    data = {"conditions": {"single": row("full", 1.0, 1), "oracle": row("full", 1.0, 2),
                           "a": row("agentkv", 0.8, 2), "b": row("agentkv", 0.25, 2)}}
    control, series, ceiling = aggressivity_series(data)
    assert control is data["conditions"]["oracle"] and ceiling == 2
    assert [point[0] for point in series["never", "agentkv"]] == pytest.approx([20, 75])
    data["conditions"]["duplicate"] = row("agentkv", 0.25, 2)
    with pytest.raises(ValueError, match="duplicate"):
        aggressivity_series(data)
