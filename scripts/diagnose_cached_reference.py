#!/usr/bin/env python3
"""Compare saved cached native logits with fresh native replay of identical tokens."""
from __future__ import annotations

import argparse
import hashlib
import inspect
import math
import os
import runpy
from dataclasses import asdict
from pathlib import Path

from comet.artifacts import provenance, read_json, write_json
from comet.budget import Budget
from comet.engine import EngineSettings, MiniSGLangEngine
from comet.history_benchmark import force_recorded_tokens


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def diagnose(reference_run: Path, model_path: Path, cases: Path, output: Path,
             timeout_seconds: float) -> None:
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("Provide a positive finite timeout")
    output.mkdir(parents=True, exist_ok=False)
    repo = Path(__file__).resolve().parents[1]
    helpers = runpy.run_path(str(repo / "tests/test_reference_gpu.py"))
    record_progress, record_current = helpers["_record_progress"], helpers["_record_current"]
    record_progress(output, "fresh", current={"stage": "validate_source"})
    budget = Budget(timeout_seconds)
    engine = None
    try:
        native = read_json(reference_run / "native.json")
        comparison = read_json(reference_run / "comparison.json")
        hashes = {name: sha256(reference_run / name) for name in
                  ("native.json", "comparison.json", "native-logits.pt", "reference-logits.pt")}
        if native["identity"] != comparison["identity"]:
            raise ValueError("Source native/reference identities differ")
        if hashes["native-logits.pt"] != native["logits_sha256"] or any(
                hashes[name] != value for name, value in comparison["artifacts_sha256"].items()):
            raise ValueError("Saved reference artifact hashes differ")
        os.environ.update(COMET_MODEL_PATH=str(model_path.resolve()),
                          COMET_TEST_MODEL=native["identity"]["model"],
                          COMET_REFERENCE_CASES=str(cases.resolve()))
        path, identity = helpers["_identity"]()
        if identity != native["identity"]:
            raise ValueError("Use the original reference source, model, packages and case corpus")
        settings = EngineSettings(**{**native["settings"], "model_path": str(path)})
        if (settings.method != "full" or settings.retention != 1.0
                or settings.prefill_chunk_tokens != 64):
            raise ValueError("This diagnostic requires the recorded full-cache, chunk-64 settings")
        originals = [record for record in native["records"] if record["phase"] == "cached"]
        if len(originals) != 3 or any(len(record["generated_token_ids"]) != 4 for record in originals):
            raise ValueError("Expected the three recorded cached cases with four output tokens")
        source = provenance()
        source["source_hashes"][str(Path(__file__).resolve().relative_to(repo))] = sha256(Path(__file__))
        source["source_hashes"]["tests/test_reference_gpu.py"] = sha256(repo / "tests/test_reference_gpu.py")
        metric_source = inspect.getsource(helpers["_compare_logits"])
        metadata = {
            "purpose": "descriptive native cached-versus-fresh replay; no gate or task-success claim",
            "source_artifacts_sha256": hashes, "source_identity": identity, "source": source,
            "settings": asdict(settings), "seed": 17, "timeout_seconds": timeout_seconds,
            "source_device_name": native["engine"]["device_name"],
            "metric_function_source": metric_source,
            "metric_function_sha256": hashlib.sha256(metric_source.encode()).hexdigest(),
            "sampling": "force recorded cached tokens; report fresh argmax separately",
        }
        write_json(output / "provenance.json", metadata)
        import torch

        if torch.cuda.device_count() != 1 or torch.cuda.get_device_name() != native["engine"]["device_name"]:
            raise ValueError("Use exactly one GPU of the same model as the saved cached run")
        cached_logits = torch.load(reference_run / "native-logits.pt", map_location="cpu", weights_only=True)
        record_progress(output, "fresh", identity=identity, current={"stage": "load_model"})
        with budget.charge("model_load"):
            engine = MiniSGLangEngine(settings)
        metadata["engine"] = engine.provenance()
        if any(metadata["engine"][field] != native["engine"][field] for field in
               ("minisgl_revision", "patch_file_sha256", "dtype", "attention_backend", "cuda_graphs")):
            raise ValueError("Native engine revision, patches or execution settings differ from source")
        write_json(output / "provenance.json", metadata)
        records, tensors = [], {}
        for original in originals:
            key = original["id"]
            history, forced = original["input_token_ids"], original["generated_token_ids"]
            cached = cached_logits[key]
            if cached.shape[0] != 4 or cached.argmax(-1).tolist() != forced:
                raise ValueError("Saved cached logits disagree with the recorded greedy tokens")
            record_progress(output, "fresh", current={"stage": "reset", "id": key})
            with budget.charge("reset"):
                engine.start(17)
            captured, generated = [], None
            print(f"Fresh replay of {key}: {len(history)} input tokens", flush=True)
            record_progress(output, "fresh", current={"stage": "generation", "id": key})
            try:
                with force_recorded_tokens(engine, forced) as replay:
                    sampler = engine.scheduler.engine.sampler
                    forced_sample = sampler.sample

                    def capture(logits, arguments):
                        if arguments.temperatures is not None or logits.shape[0] != 1:
                            raise ValueError("Expected one greedy native sampler row")
                        captured.append(logits[0].detach().float().cpu().clone())
                        return forced_sample(logits, arguments)

                    sampler.sample = capture
                    try:
                        with budget.charge("generation"):
                            generated = engine.generate(history, 4, 0.0, 1.0, budget.deadline, ignore_eos=True)
                    finally:
                        sampler.sample = forced_sample
            finally:
                current_logits = torch.stack(captured) if captured else None
                record_current(output, "fresh", records, tensors, {
                    "id": key, "input_token_ids": history, "forced_token_ids": forced,
                    "conditional_input_token_ids": [history + forced[:step] for step in range(4)],
                    "observed_raw_token_ids": engine.raw_token_ids, "captured_steps": len(captured),
                    "generation": engine.last_generation,
                }, current_logits)
            if (len(captured) != 4 or generated.token_ids != forced
                    or engine.raw_token_ids != history + forced
                    or generated.prompt_tokens != len(history) or generated.decode_tokens != 3
                    or engine.retention_events or current_logits.shape != cached.shape
                    or not torch.isfinite(current_logits).all()
                    or generated.memory["physical_cached_tokens"] != generated.memory["logical_cached_tokens"]):
                raise ValueError("Fresh replay did not preserve the declared full-cache token history")
            steps = []
            for index, (cached_row, fresh_row, token) in enumerate(zip(cached, current_logits, forced, strict=True)):
                metrics = helpers["_compare_logits"](cached_row, fresh_row, token)
                metrics.pop("passed", None)
                steps.append({"step": index, "forced_token": token,
                              "cached_argmax": cached_row.argmax().item(),
                              "fresh_argmax": fresh_row.argmax().item(),
                              "cached_vs_fresh": metrics})
            tensors[key] = current_logits
            records.append({"id": key, "input_token_ids": history, "forced_token_ids": forced,
                            "conditional_input_token_ids": [history + forced[:step] for step in range(4)],
                            "observed_raw_token_ids": engine.raw_token_ids, "replay": replay,
                            "generation": asdict(generated), "steps": steps})
            record_progress(output, "fresh", current={"stage": "case_completed", "id": key},
                            records=records, tensors=tensors)
            budget.check()
        torch.save(tensors, output / "fresh-logits.pt")
        write_json(output / "fresh.json", {
            "schema_version": 1, "status": "completed", "purpose": metadata["purpose"],
            "records": records, "elapsed_seconds": budget.elapsed, "timings": budget.timings,
            "artifacts_sha256": {name: sha256(output / name) for name in ("provenance.json", "fresh-logits.pt")},
        })
        record_progress(output, "fresh", status="superseded_by_complete_artifacts")
    except BaseException as error:
        current = read_json(output / "fresh-partial.json")["current"]
        record_progress(output, "fresh", current=current, status="failed", error=error)
        raise
    finally:
        write_json(output / "timings.json", {"elapsed_seconds": budget.elapsed, "timings": budget.timings})
        if engine is not None:
            engine.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-run", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    args = parser.parse_args()
    diagnose(args.reference_run, args.model_path, args.cases, args.output, args.timeout_seconds)


if __name__ == "__main__":
    main()
