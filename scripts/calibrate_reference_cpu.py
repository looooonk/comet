#!/usr/bin/env python3
"""Describe BF16 reference errors against FP32 CPU inference without changing gates."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import math
import os
import platform
import resource
import runpy
import sys
from pathlib import Path
from statistics import mean

from comet.artifacts import provenance, read_json, write_json
from comet.budget import Budget
from comet.clocks import monotonic, wall_time
from comet.engine.contracts import model_storage, validate_model

SOURCE_FILES = ("native.json", "comparison.json", "native-logits.pt", "reference-logits.pt")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cpu_memory() -> dict:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result = {
        "peak_rss_bytes": int(usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024)),
        "user_cpu_seconds": usage.ru_utime,
        "system_cpu_seconds": usage.ru_stime,
    }
    status = Path("/proc/self/status")
    if status.exists():
        fields = dict(line.split(":", 1) for line in status.read_text().splitlines() if ":" in line)
        for field in ("VmRSS", "VmHWM", "RssAnon", "RssFile"):
            if field in fields:
                result[field + "_bytes"] = int(fields[field].split()[0]) * 1024
    return result


def read_source(root: Path) -> tuple[dict, dict, dict]:
    native, comparison = read_json(root / "native.json"), read_json(root / "comparison.json")
    hashes = {name: sha256(root / name) for name in SOURCE_FILES}
    if native["identity"] != comparison["identity"]:
        raise ValueError("Source numerical comparison has inconsistent identities")
    for name, expected in comparison["artifacts_sha256"].items():
        if hashes.get(name) != expected:
            raise ValueError(f"Source artifact hash differs: {name}")
    if hashes["native-logits.pt"] != native["logits_sha256"]:
        raise ValueError("Source native logits hash differs")
    identity = native["identity"]
    validate_model(identity["model"], identity["model_revision"], identity["tokenizer_revision"])
    records = native["records"]
    if (
        len(records) != 6
        or len({record["id"] for record in records}) != 6
        or any(len(record["generated_token_ids"]) != 4 for record in records)
        or {record["id"] for record in records}
        != {record["id"] for record in comparison["records"]}
    ):
        raise ValueError("Expected the six original cases with four generated tokens each")
    return native, comparison, hashes


def verify_model(path: Path, identity: dict) -> dict:
    config, parameters = model_storage(str(path), identity["model_revision"], identity["model"])
    if parameters != identity["parameters"]:
        raise ValueError("Model parameter count differs from the source")
    for name, expected in identity["small_file_sha256"].items():
        if sha256(path / name) != expected:
            raise ValueError(f"Model/tokenizer file differs from source: {name}")
    weights = []
    for file in sorted(path.glob("*.safetensors")):
        with file.open("rb") as stream:
            length = int.from_bytes(stream.read(8), "little")
            header = hashlib.sha256(stream.read(length)).hexdigest()
        weights.append(
            {
                "file": file.name,
                "bytes": file.stat().st_size,
                "storage_blob": file.resolve().name,
                "header_sha256": header,
            }
        )
    if weights != identity["weight_files"]:
        raise ValueError("Model weight identity differs from source snapshot/header evidence")
    return config


def descriptive_metrics(compare, values, reference) -> dict:
    result = compare(values, reference, int(values.argmax().item()))
    result.pop("passed", None)
    return result


def error_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator > 0 else None


def summarize(records: list[dict]) -> dict:
    steps = [step for record in records for step in record["steps"]]
    summary = {"vectors": len(steps), "cases": len(records)}
    pooled = {}
    for arm in ("native", "bf16_reference"):
        values = [step[arm + "_vs_fp32"] for step in steps]
        rmse = [value["centered_rmse"] for value in values]
        pooled[arm] = math.sqrt(mean(value * value for value in rmse))
        summary[arm] = {
            "pooled_centered_rmse": pooled[arm],
            "max_centered_rmse": max(rmse),
            "mean_centered_relative_rmse": mean(
                value["centered_relative_rmse"] for value in values
            ),
            "max_centered_relative_rmse": max(value["centered_relative_rmse"] for value in values),
            "mean_jensen_shannon_nats": mean(value["jensen_shannon_nats"] for value in values),
            "max_jensen_shannon_nats": max(value["jensen_shannon_nats"] for value in values),
            "exact_greedy_agreements": sum(value["exact_greedy_agreement"] for value in values),
            "exact_greedy_agreement_fraction": mean(
                value["exact_greedy_agreement"] for value in values
            ),
            "max_greedy_regret": max(value["greedy_regret"] for value in values),
        }
    summary["native_to_bf16_pooled_centered_rmse_ratio"] = error_ratio(
        pooled["native"], pooled["bf16_reference"]
    )
    return summary


def checkpoint(output: Path, progress: dict, tensors: dict, torch) -> None:
    temporary = output / "fp32-partial-logits.pt.tmp"
    torch.save(tensors, temporary)
    os.replace(temporary, output / "fp32-partial-logits.pt")
    progress["partial_logits_sha256"] = sha256(output / "fp32-partial-logits.pt")
    progress["cpu_memory"] = cpu_memory()
    write_json(output / "progress.json", progress)


def calibrate(
    reference_run: Path, model_path: Path, output: Path, threads: int, timeout_seconds: float
) -> None:
    if threads <= 0 or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("Provide positive thread count and finite timeout")
    output.mkdir(parents=True, exist_ok=False)
    progress = {
        "schema_version": 1,
        "status": "running",
        "complete": False,
        "current": "source_validation",
        "records": [],
        "started_at_unix": wall_time(),
    }
    write_json(output / "progress.json", progress)
    budget = Budget(timeout_seconds)
    tensors = {}
    try:
        native, comparison, hashes = read_source(reference_run)
        identity = native["identity"]
        config = verify_model(model_path.resolve(), identity)
        packages = {name: importlib.metadata.version(name) for name in identity["packages"]}
        if any(
            packages[name].split("+")[0] != version.split("+")[0]
            for name, version in identity["packages"].items()
        ):
            raise ValueError("Use the same pinned runtime package versions as the BF16 source")
        if packages["transformers"] != "4.57.3":
            raise ValueError("Calibration requires Transformers 4.57.3")
        repo = Path(__file__).resolve().parents[1]
        metric_file = repo / "tests/test_reference_gpu.py"
        metric_module = runpy.run_path(str(metric_file), run_name="reference_metric_definitions")
        compare = metric_module["_compare_logits"]
        metric_source = inspect.getsource(compare)
        if metric_module["TOLERANCES"] != comparison["tolerances"]:
            raise ValueError(
                "Metric source gates differ from the recorded comparison; do not retune here"
            )
        source = provenance()
        source["source_hashes"][str(Path(__file__).resolve().relative_to(repo))] = sha256(
            Path(__file__)
        )
        source["source_hashes"]["tests/test_reference_gpu.py"] = sha256(metric_file)
        metadata = {
            "purpose": "FP32 CPU calibration of two BF16 implementations; descriptive errors only",
            "source_artifacts_sha256": hashes,
            "source_identity": identity,
            "source_device_name": comparison["device_name"],
            "packages": packages,
            "metrics_function_sha256": hashlib.sha256(metric_source.encode()).hexdigest(),
            "metrics_function_source": metric_source,
            "source": source,
            "original_tolerances": comparison["tolerances"],
            "tolerances_modified": False,
            "cpu": {
                "platform": platform.platform(),
                "processor": platform.processor(),
                "affinity": sorted(os.sched_getaffinity(0))
                if hasattr(os, "sched_getaffinity")
                else None,
                "threads_requested": threads,
                "interop_threads_requested": 1,
            },
            "timeout_seconds": timeout_seconds,
            "cpu_memory_before_load": cpu_memory(),
        }
        write_json(output / "provenance.json", metadata)
        os.environ.update(
            CUDA_VISIBLE_DEVICES="", OMP_NUM_THREADS=str(threads), MKL_NUM_THREADS=str(threads)
        )
        import torch
        from transformers import Qwen3ForCausalLM

        torch.set_num_threads(threads)
        torch.set_num_interop_threads(1)
        metadata["cpu"].update(
            threads_actual=torch.get_num_threads(),
            interop_threads_actual=torch.get_num_interop_threads(),
        )
        native_logits = torch.load(
            reference_run / "native-logits.pt", weights_only=True, map_location="cpu"
        )
        bf16_logits = torch.load(
            reference_run / "reference-logits.pt", weights_only=True, map_location="cpu"
        )
        expected_keys = {record["id"] for record in native["records"]}
        if native_logits.keys() != expected_keys or bf16_logits.keys() != expected_keys:
            raise ValueError("Saved logits do not cover exactly the six source histories")
        for record in native["records"]:
            for values in (native_logits[record["id"]], bf16_logits[record["id"]]):
                if (
                    tuple(values.shape) != (4, config["vocab_size"])
                    or not torch.isfinite(values).all()
                ):
                    raise ValueError("Saved BF16 logits have the wrong shape or nonfinite values")
            if native_logits[record["id"]].argmax(-1).tolist() != record["generated_token_ids"]:
                raise ValueError("Saved native logits disagree with recorded greedy outputs")
        progress["current"] = "load_fp32_model"
        write_json(output / "progress.json", progress)
        with budget.charge("model_load"):
            model, loading = Qwen3ForCausalLM.from_pretrained(
                model_path,
                dtype=torch.float32,
                device_map={"": "cpu"},
                low_cpu_mem_usage=True,
                attn_implementation="eager",
                local_files_only=True,
                trust_remote_code=False,
                output_loading_info=True,
            )
        metadata["loading_info"] = loading
        metadata["cpu_memory_after_load"] = cpu_memory()
        metadata["reference_source_sha256"] = sha256(Path(inspect.getfile(Qwen3ForCausalLM)))
        write_json(output / "provenance.json", metadata)
        if any(
            loading.get(key)
            for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")
        ):
            raise ValueError("FP32 model did not load the complete pinned checkpoint")
        model.eval()
        if model.config._attn_implementation != "eager" or any(
            parameter.dtype != torch.float32 or parameter.device.type != "cpu"
            for parameter in model.parameters()
        ):
            raise ValueError(
                "Calibration requires eager attention and all model parameters in FP32 on CPU"
            )
        with torch.inference_mode():
            for original in native["records"]:
                key = original["id"]
                history, generated = original["input_token_ids"], original["generated_token_ids"]
                inputs = history + generated[:-1]
                progress["current"] = {"id": key, "stage": "forward", "input_token_ids": inputs}
                write_json(output / "progress.json", progress)
                print(f"Calibrating {key}: {len(inputs)} input tokens", flush=True)
                started = monotonic()
                values = None
                try:
                    with budget.charge("forward"):
                        values = (
                            model(
                                input_ids=torch.tensor([inputs], dtype=torch.long, device="cpu"),
                                use_cache=False,
                                logits_to_keep=4,
                            )
                            .logits[0]
                            .float()
                            .cpu()
                        )
                finally:
                    seconds = monotonic() - started
                    progress["current"]["forward_seconds"] = seconds
                    if values is not None:
                        tensors[key] = values
                        progress["current"]["stage"] = "unvalidated_logits"
                        checkpoint(output, progress, tensors, torch)
                if values.shape != native_logits[key].shape or not torch.isfinite(values).all():
                    raise ValueError(f"FP32 reference has invalid logits for {key}")
                steps = []
                with budget.charge("comparison"):
                    for index, fp32 in enumerate(values):
                        native_metrics = descriptive_metrics(
                            compare, native_logits[key][index], fp32
                        )
                        bf16_metrics = descriptive_metrics(compare, bf16_logits[key][index], fp32)
                        steps.append(
                            {
                                "step": index,
                                "native_vs_fp32": native_metrics,
                                "bf16_reference_vs_fp32": bf16_metrics,
                                "native_to_bf16_centered_rmse_ratio": error_ratio(
                                    native_metrics["centered_rmse"], bf16_metrics["centered_rmse"]
                                ),
                            }
                        )
                progress["records"].append(
                    {
                        "id": key,
                        "input_token_ids": inputs,
                        "history_tokens": len(history),
                        "generated_token_ids": generated,
                        "forward_seconds": seconds,
                        "steps": steps,
                        "cpu_memory": cpu_memory(),
                    }
                )
                progress["current"] = {"id": key, "stage": "recorded"}
                checkpoint(output, progress, tensors, torch)
                budget.check()
        torch.save(tensors, output / "fp32-logits.pt")
        budget.check()
        report = {
            "schema_version": 1,
            "status": "completed",
            "purpose": metadata["purpose"],
            "dtype": "float32",
            "device": "cpu",
            "attention": "eager",
            "use_cache": False,
            "tolerances_modified": False,
            "records": progress["records"],
            "summary": summarize(progress["records"]),
            "timings": budget.timings,
            "elapsed_seconds": budget.elapsed,
            "cpu_memory": cpu_memory(),
            "artifacts_sha256": {
                name: sha256(output / name) for name in ("provenance.json", "fp32-logits.pt")
            },
        }
        write_json(output / "calibration.json", report)
        progress.update(status="completed", complete=True, current=None)
    except BaseException as error:
        progress.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        progress.update(
            elapsed_seconds=budget.elapsed, timings=budget.timings, cpu_memory=cpu_memory()
        )
        write_json(output / "progress.json", progress)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-run", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    args = parser.parse_args()
    calibrate(args.reference_run, args.model_path, args.output, args.threads, args.timeout_seconds)


if __name__ == "__main__":
    main()
