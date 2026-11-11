import json

import pytest
from test_comparison import scored_pair

from comet.comparison import compare_protocol_runs
from comet.plotting import plot_baseline


def test_baseline_plot_labels_failure_reservations_and_nonzero_uncertainty(tmp_path):
    pytest.importorskip("matplotlib")
    control, candidate = scored_pair(tmp_path)
    path = tmp_path / "comparison.json"
    compare_protocol_runs(control, candidate, path, protocol_fields=["agent"], bootstrap_samples=50)
    output = tmp_path / "baseline.svg"
    plot_baseline(path, output)
    svg = output.read_text()
    assert "Task success (%)" in svg
    assert "Cell execution status (%)" in svg
    assert "Mean errors per 100 saved turns" in svg
    assert "Unmeasured reserved time: 0.0s / 600.0s; excluded from duration." in svg
    assert "Measured-duration coverage: Control: 2/2 tasks; Candidate: 1/2 tasks." in svg


def test_baseline_plot_requires_the_paired_comparison_artifact(tmp_path):
    pytest.importorskip("matplotlib")
    path = tmp_path / "ordinary.json"
    path.write_text(json.dumps({"kind": "ordinary_analysis"}))
    with pytest.raises(ValueError, match="validated paired"):
        plot_baseline(path, tmp_path / "baseline.svg")
