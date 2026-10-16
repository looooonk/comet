"""Exercise the real CUDA engine; this is infrastructure validation, not a task score."""

import argparse
import dataclasses
import json
import time
from pathlib import Path

from comet.engine import EngineSettings, MiniSGLangEngine
from comet.engine.contracts import MODEL_REVISION


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    settings = EngineSettings(
        model_path=args.model_path,
        model_revision=MODEL_REVISION,
        tokenizer_revision=MODEL_REVISION,
        method="full",
        retention=1.0,
        max_context_tokens=1024,
        peak_vram_bytes=40 * 2**30,
        workspace_reserve_bytes=4 * 2**30,
        prefill_chunk_tokens=256,
        require_a100=False,
    )
    engine = MiniSGLangEngine(settings)
    records = {"integration_smoke": True, "settings": dataclasses.asdict(settings),
               "device_name": engine.device_name, "checks": []}

    def record(name, value):
        item = {"check": name, "result": value}
        records["checks"].append(item)
        print(json.dumps(item), flush=True)
        (args.output / "result.json").write_text(json.dumps(records, indent=2) + "\n")

    def generate(text, count=8):
        return engine.generate(engine.tokenizer.encode(text, add_special_tokens=False), count, 0.0, 1.0,
                               time.monotonic() + 300)

    try:
        engine.start(42)
        initial = generate("A research notebook contains observations about a garden. " * 24)
        assert initial.memory["physical_cached_tokens"] == initial.memory["logical_cached_tokens"]
        checkpoint = args.output / "full.pt"
        engine.checkpoint(checkpoint)
        continuation = generate("\nThe next observation is")
        assert continuation.prompt_tokens < len(engine.raw_token_ids)
        engine.restore(checkpoint)
        repeated = generate("\nThe next observation is")
        assert continuation.token_ids == repeated.token_ids
        record("full_cache_and_roundtrip", dataclasses.asdict(repeated))
        for method in ("streamingllm", "rkv", "agentkv"):
            for retention in (0.8, 0.5, 0.25):
                engine.set_policy(method, retention)
                engine.restore(checkpoint, branch=True)
                state = engine.memory_stats()
                assert state["physical_cached_tokens"] <= state["retention_target_tokens"]
                first = generate("\nA new observation is")
                compressed = args.output / f"{method}-{retention}.pt"
                engine.checkpoint(compressed)
                expected = generate("\nContinue:", 4)
                engine.restore(compressed)
                actual = generate("\nContinue:", 4)
                assert actual.token_ids == expected.token_ids
                assert first.prompt_tokens < len(engine.raw_token_ids)
                history = engine.raw_token_ids
                recovered = engine.recover(history, time.monotonic() + 300)
                assert recovered.admitted, recovered.reason
                assert engine.raw_token_ids == history
                assert engine.recovery_count == 1
                second = engine.recover(history, time.monotonic() + 300)
                assert not second.admitted and second.reason == "recovery_limit"
                state = engine.memory_stats()
                assert state["physical_cached_tokens"] <= state["retention_target_tokens"]
                record(f"{method}_{retention}", {
                    "generation": dataclasses.asdict(actual),
                    "recovery": dataclasses.asdict(recovered),
                    "second_recovery": dataclasses.asdict(second),
                })
        records["passed"] = True
        record("completed", True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
