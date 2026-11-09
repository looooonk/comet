"""Synthetic accounting fixtures; their timings are not experiment measurements."""
import hashlib
from copy import deepcopy

import pytest
from test_history_benchmark import Engine
from test_history_benchmark import inputs as inputs

from comet.artifacts import read_json, write_json
from comet.cli import main
from comet.history_analysis import analyze_histories
from comet.history_benchmark import run_benchmark
from comet.history_plots import plot_histories


class AnalysisEngine(Engine):
    def provenance(self):
        return {**super().provenance(), "backend": "native_minisgl", "dtype": "bfloat16",
                "device_total_bytes": 1000, "patch_file_sha256": {"fixture": "fixture"},
                "packages": {"torch": "fixture"}, "cuda_runtime": "fixture", "driver_version": "fixture",
                **{key: getattr(self.settings, key) for key in ("model", "model_revision", "tokenizer_revision")}}

    def memory_stats(self):
        memory = super().memory_stats()
        return {**memory, "peak_kv_cache_bytes": memory["peak_kv_bytes"],
                "reserved_kv_pool_bytes": memory["reserved_kv_bytes"]}


@pytest.fixture
def history_runs(inputs):
    spec, source, model, output = inputs
    spec["repetitions"] = 2
    spec["logical_lengths"] = [24]
    run_benchmark(spec, source, model, output, engine_factory=AnalysisEngine)
    second = output.parent / "second"
    spec = {**spec, "benchmark_id": "second-fixture", "logical_lengths": [40], "cell_timeout_seconds": 20}
    run_benchmark(spec, source, model, second, engine_factory=AnalysisEngine)
    return output, second, output.parent / "analysis.json"


def _change_pass(run, name, change, *, condition="full", retention=1.0, repetition=0):
    manifest = read_json(run / "manifest.json")
    reference = next(item for item in manifest["cells"] if item["method"] == condition
                     and item["retention"] == retention and item["repetition"] == repetition)
    directory = run / "cells" / reference["id"]
    path = directory / f"{name}.json"
    record = read_json(path)
    change(record)
    write_json(path, record)
    cell_path = directory / "cell.json"
    cell = read_json(cell_path)
    entry = next(item for item in cell["passes"] if item["pass"] == name)
    entry.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), status=record["status"])
    write_json(cell_path, cell)
    return directory, record


def test_analysis_pairs_lengths_preserves_repetitions_and_measured_phase_roles(history_runs):
    first, second, output = history_runs
    # Changing only instrumented throughput must not affect the ordinary decode summary.
    def slow_profile(record):
        record["generation"]["decode_seconds"] = 100
        record["decode_tokens_per_second"] = 0.02
    _change_pass(first, "instrumented", slow_profile)
    result = analyze_histories([first, second], output)
    assert result["summary"]["expected_cells"] == 40
    assert result["summary"]["logical_lengths"] == [24, 40]
    assert len({cell["run_identity"] for cell in result["cells"]}) == 2
    assert {cell["repetition"] for cell in result["cells"]} == {0, 1}
    point = next(point for point in result["points"] if point["method"] == "full" and point["logical_length"] == 24)
    assert point["metrics"]["decode_tokens_per_second"] == {
        "median": 2.0, "minimum": 2.0, "maximum": 2.0, "values": [2.0, 2.0], "observed": 2, "expected": 2,
    }
    assert point["metrics"]["occupied_kv_bytes"]["median"] == 24 * 4
    assert point["metrics"]["reserved_kv_pool_bytes"]["median"] == 256
    assert point["metrics"]["total_vram_bytes"]["median"] == 200
    assert point["metrics"]["selection_seconds"]["median"] == 0
    assert read_json(output) == result


@pytest.mark.parametrize("change,match", [
    (lambda value: value["provenance"].update(code_commit="other"), "Incompatible source"),
    (lambda value: value["provenance"]["installed_packages"].update(torch="other"), "Incompatible source"),
    (lambda value: value["engine"].update(driver_version="other"), "Incompatible runtime"),
    (lambda value: value["engine"].update(device_total_bytes=2000), "Incompatible runtime"),
    (lambda value: value["measurement_contract"].update(tokens="regenerated"), "Incompatible source"),
    (lambda value: value["source"]["manifest"].update(run_id="other"), "Incompatible source"),
])
def test_incompatible_history_evidence_is_rejected(history_runs, change, match):
    first, second, output = history_runs
    path = second / "manifest.json"
    manifest = read_json(path)
    change(manifest)
    write_json(path, manifest)
    with pytest.raises(ValueError, match=match):
        analyze_histories([first, second], output)
    assert not output.exists()


def test_identity_duplicate_hash_corruption_and_retention_are_rejected(history_runs):
    first, _, output = history_runs
    with pytest.raises(ValueError, match="Duplicate benchmark identity"):
        analyze_histories([first, first], output)
    directory, record = _change_pass(first, "decode", lambda value: value["memory"].update(physical_cached_tokens=1))
    with pytest.raises(ValueError, match="retention accounting"):
        analyze_histories([first], output)
    (directory / "decode.json").write_text("{}")
    with pytest.raises(ValueError, match="SHA-256"):
        analyze_histories([first], output)


@pytest.mark.parametrize("change,match", [
    (lambda value: value["generation"]["token_ids"].__setitem__(0, 79), "exact forced history"),
    (lambda value: value.update(decode_tokens_per_second=999), "throughput disagrees"),
    (lambda value: value["memory"].update(peak_total_vram_bytes=1001), "VRAM cap"),
    (lambda value: value.update(throughput_comparable=False), "pass roles"),
])
def test_completed_pass_accounting_is_checked_even_with_updated_hash(history_runs, change, match):
    first, _, output = history_runs
    _change_pass(first, "decode", change)
    with pytest.raises(ValueError, match=match):
        analyze_histories([first], output)


def test_failure_and_missing_coverage_preserve_good_earlier_passes(history_runs):
    first, _, output = history_runs
    directory, _ = _change_pass(first, "instrumented", lambda value: value.update(
        status="oom", metric_coverage="partial", failure_reason="fixture workspace cap"))
    cell_path = directory / "cell.json"
    cell = read_json(cell_path)
    cell.update(status="oom", failure_reason="fixture workspace cap")
    write_json(cell_path, cell)
    manifest_path = first / "manifest.json"
    manifest = read_json(manifest_path)
    manifest["cell_status_counts"] = {"completed": 19, "oom": 1}
    write_json(manifest_path, manifest)
    _change_pass(first, "decode", lambda value: value.pop("metric_coverage"), repetition=1)
    result = analyze_histories([first], output)
    point = next(point for point in result["points"] if point["method"] == "full")
    assert point["cell_status_counts"] == {"oom": 1, "completed": 1}
    assert point["metrics"]["decode_tokens_per_second"]["observed"] == 1
    assert point["metrics"]["decode_tokens_per_second"]["expected"] == 2
    assert point["metrics"]["occupied_kv_bytes"]["observed"] == 2
    assert point["metrics"]["selection_seconds"]["observed"] == 1
    failed = next(cell for cell in result["cells"] if cell["status"] == "oom")
    assert failed["passes"]["instrumented"]["failure_reason"] == "fixture workspace cap"
    assert failed["metrics"]["selection_seconds"]["value"] is None
    assert failed["metrics"]["selection_seconds"]["observed_value"] == 0


def test_unfinished_snapshot_retains_unjournaled_pass_and_reserved_time(history_runs):
    first, _, output = history_runs
    manifest_path = first / "manifest.json"
    manifest = read_json(manifest_path)
    manifest["status"] = "running"
    directory = first / "cells" / manifest["cells"][0]["id"]
    cell_path = directory / "cell.json"
    cell = read_json(cell_path)
    cell.update(status="interrupted", passes=cell["passes"][:2],
                observed_elapsed_seconds=2, reserved_timeout_seconds=8, budget_accounted_seconds=10)
    write_json(cell_path, cell)
    missing = first / "cells" / manifest["cells"][1]["id"] / "cell.json"
    missing.unlink()
    # A never-started cell has no pass artifacts.
    for path in missing.parent.glob("*.json"):
        path.unlink()
    write_json(manifest_path, manifest)
    before = (directory / "instrumented.json").read_bytes()
    result = analyze_histories([first], output)
    assert (directory / "instrumented.json").read_bytes() == before
    interrupted = result["cells"][0]
    assert interrupted["reserved_timeout_seconds"] == 8
    assert interrupted["metrics"]["selection_seconds"]["value"] is None
    assert interrupted["passes"]["instrumented"]["status"] == "completed"
    assert not interrupted["passes"]["instrumented"]["journaled"]
    assert result["summary"]["cell_status_counts"]["not_started"] == 1
    assert all(metric["value"] is None for metric in result["cells"][1]["metrics"].values())


def test_cli_single_point_plot_and_missing_metric_are_explicit(history_runs, tmp_path):
    pytest.importorskip("matplotlib")
    first, _, output = history_runs
    _change_pass(first, "decode", lambda value: value.pop("metric_coverage"))
    main(["analyze-histories", str(first), "--output", str(output)])
    figure = tmp_path / "synthetic-single-point.svg"
    main(["plot-histories", str(output), "--metric", "decode-throughput", "--output", str(figure),
          "--title", "Synthetic fixture: not experimental data"])
    text = figure.read_text()
    assert "Single logical length; no length trend" in text
    assert "Synthetic fixture: not experimental data" in text
    assert "Covered observations: 19/20" in text
    assert "1/2" in text
    assert "Decode loop (tokens/s)" in text
    invalid = deepcopy(read_json(output))
    invalid["summary"]["histories"].append("another-history")
    write_json(output, invalid)
    with pytest.raises(ValueError, match="Select one"):
        plot_histories(output, figure, metric="occupied-kv")


def test_shared_axis_includes_larger_later_method_values(history_runs, tmp_path, monkeypatch):
    pytest.importorskip("matplotlib")
    from matplotlib.figure import Figure

    first, _, output = history_runs
    result = analyze_histories([first], output)
    for point in result["points"]:
        value = {"full": 0, "streamingllm": 1, "rkv": 20, "agentkv": 10}[point["method"]]
        point["metrics"]["selection_seconds"].update(
            median=value, minimum=value, maximum=value, values=[value, value])
    write_json(output, result)
    observed_limits = []

    def inspect(figure, *args, **kwargs):
        observed_limits.extend(ax.get_ylim() for ax in figure.axes)

    monkeypatch.setattr(Figure, "savefig", inspect)
    plot_histories(output, tmp_path / "layout.svg", metric="selection",
                   title="Synthetic layout fixture: not experimental data")
    assert len(observed_limits) == 3
    assert all(lower == 0 and upper >= 20_000 for lower, upper in observed_limits)


def test_cross_method_plot_preserves_selected_failures_and_all_repetitions(history_runs, tmp_path):
    pytest.importorskip("matplotlib")
    first, second, output = history_runs
    _change_pass(first, "decode", lambda value: value.pop("metric_coverage"),
                 condition="rkv", retention=0.5)
    _change_pass(first, "decode", lambda value: value.pop("metric_coverage"),
                 condition="agentkv", retention=0.8)
    analyze_histories([first, second], output)
    figure = tmp_path / "synthetic-cross-method.svg"
    main(["plot-histories", str(output), "--metric", "decode-throughput", "--output", str(figure),
          "--retention", "0.5", "--title", "Synthetic fixture: not experimental data"])
    text = figure.read_text()
    assert "Compressed conditions at 50% retention" in text
    assert "Covered observations: 15/16" in text
    assert "1/2" in text
    assert all(label in text for label in ("Full KV", "StreamingLLM", "R-KV", "AgentKV"))
    assert "80% retained" not in text and "25% retained" not in text
    assert "Open points: all recorded repetitions" in text
    assert "Full control is repeated in each facet" not in text
    with pytest.raises(ValueError, match="compressed retention"):
        plot_histories(output, figure, metric="decode-throughput", retention=1.0)
