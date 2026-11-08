# Matched-history retention diagnostic

This diagnostic measures the cost of full KV and StreamingLLM, R-KV, and AgentKV
at 80%, 50%, and 25% retention on identical recorded token histories. It is
separate from task execution, recovery evaluation, and task-success analysis.
It never constructs AppWorld, executes saved actions, or reads evaluator scores.

## Declare the workload

Use a completed train/dev run with its manifest, cell records, and trajectories.
A failed task can supply a history: its status and source protocol remain recorded.
Choose source trajectories and logical lengths before inspecting comparative
measurements. Each selected history must contain at least
`max(logical_lengths) + decode_tokens + 1` raw token IDs. No padding, truncation of
the declared prefix, or regenerated substitute history is allowed.

Write a versioned JSON specification containing all the fields below. There are
no default experiment sizes, memory caps, or time limits.

| Field | Meaning |
| --- | --- |
| `schema_version` | `1` |
| `benchmark_id` | Descriptive identifier for this diagnostic version |
| `histories` | List of objects with `trajectory` (path relative to the source run) and `sha256` (SHA-256 of the complete trajectory file) |
| `logical_lengths` | Increasing, unique positive prefix lengths |
| `decode_tokens` | Positive number of actual decode forwards per decode pass |
| `repetitions` | Positive number of independently reset measurements for each cell |
| `seed` | Explicit nonnegative reset seed; paired across every condition and repetition |
| `cell_timeout_seconds` | Shared timeout for reset, measurement, profiling, verification, and journals in each diagnostic cell |
| `warmup_timeout_seconds` | Separate bounded allowance for the engine's standard synthetic warmup |
| `engine.max_context_tokens` | Declared context capacity, including the forced continuation |
| `engine.peak_vram_bytes` | Explicit cap on total device memory |
| `engine.workspace_reserve_bytes` | Explicit allocator/workspace reserve |
| `engine.prefill_chunk_tokens` | Native prefill chunk size |
| `engine.device_name` | Exact GPU model reported by the runtime |

The model and tokenizer identifiers come from the source manifest and must match
its recorded engine metadata and a supported pinned model. The diagnostic loads
that same model in BF16. A 14B source therefore remains exploratory; it cannot
silently supply an 8B comparison. Source trajectories must belong to attempts in
the source manifest, and their bytes must match the declared hashes.

Activate the managed GPU environment, then run the thin entry point:

```sh
source "$COMET_REPO/scripts/activate_runtime.sh" gpu
python "$COMET_REPO/scripts/benchmark_histories.py" \
  --spec "$COMET_HISTORY_SPEC" \
  --source-run "$COMET_HISTORY_SOURCE" \
  --model-path "$COMET_MODEL_PATH" \
  --output "$COMET_HISTORY_OUTPUT"
```

Use a fresh output directory. Slurm or GCP can run this command after the same
managed setup and GPU checks used by the main runner. No live benchmark has been
validated merely by adding this command; record its hardware, results, and
failures after an actual run.

## What each cell measures

A cell identifies one history, logical length, method, retention, and repetition.
There are ten conditions per history/length/repetition. Each cell has three
separately saved passes, resetting the native engine and seed before each:

1. **Prefill:** ingest the recorded prefix and emit one forced recorded token.
   Record parked occupancy at exactly the declared logical length, transient
   peak occupied KV, reserved pool size, total VRAM, peak total VRAM, and prefill
   throughput.
2. **Decode:** ingest the same prefix and emit `decode_tokens + 1` recorded tokens.
   The first output comes from prefill; the remaining outputs require the declared
   number of decode forwards. Record prefill/decode timings and throughput, final
   occupancy, peaks, estimated FLOPs, and retention events.
3. **Instrumented replay:** repeat the decode pass with explicit selection and
   compaction timers. This pass verifies the same raw tokens but is excluded from
   ordinary throughput comparisons because the timers introduce synchronization.

A temporary, diagnostic-only sampler hook returns preallocated recorded token
IDs on the native sampler's device. The model still runs each forward, updates
its phase/query state, and applies the configured eviction policy. The original
sampler is restored even on exceptions. EOS does not stop replay. Exact output
count and final raw-token equality are checked; disagreement is an explicit
infeasible result. This is forced replay, not greedy or sampled task execution,
and its output sequence cannot establish model accuracy or task success.

The pinned COMET engine patch skips sampling for intermediate prefill-only
chunks. The replay hook counts only sampler calls that should produce actual
outputs; live validation must confirm the expected call count at the chosen
chunk sizes. The pinned [sampler interface](https://github.com/LiuTaowen-Tony/kv-management-minisgl/blob/254c57bc84e4a7895159ba1062bd46c83626f511/python/minisgl/engine/sample.py)
returns one output per batch row.

Profiling wraps the pinned eviction manager's
[`_select_compaction_indices` and `compact_session_req` methods](https://github.com/LiuTaowen-Tony/kv-management-minisgl/blob/254c57bc84e4a7895159ba1062bd46c83626f511/python/minisgl/eviction/manager.py).
Selection includes view construction, scoring, and index validation. Compaction
includes cache movement, allocation, and request/position updates. Their host
elapsed times include synchronization after each operation and are disjoint.
They exclude the surrounding `maybe_compact` guards/dispatch and other scheduler
work. Calls, completed calls, partial timings, and missing interfaces remain
explicit. These are instrumented method costs, not GPU-only kernel timings.

Actual retention is physical cached tokens divided by logical cached tokens.
The final sampled token is excluded from that denominator until it is forwarded.
Current occupied KV bytes are calculated from physical occupancy and the pinned
model's KV bytes per token. This differs from reserved pool bytes and transient
peak occupancy. Throughput is token count divided by the corresponding native
synchronized elapsed time; failed-pass throughput is left unavailable. FLOPs
remain estimates with the native exclusions documented in [engine.md](engine.md).

## Evidence and resume

The manifest preserves the specification, original source manifest and hash,
model/tokenizer identity, current code/dependency provenance, hardware, input
prefix hashes, and every expected cell. `inputs/` preserves the required recorded
tokens. Each attempted pass is saved as `prefill.json`, `decode.json`, or
`instrumented.json`, with its hash in a small `cell.json` journal. Failed passes retain the native partial counters;
completed passes remain available even when a later pass fails.

Add `--resume` only with the unchanged specification and source history. Resume
checks source hashes, code, packages, numerical settings, and live runtime/device
identity when more inference is needed. Completed and failed cells are skipped.
An interrupted cell is marked interrupted and charged its entire diagnostic
allowance; it is not retried with extra time. Use a new version/output directory
for a repaired rerun. A pass saved just before its cell journal update is recovered
with its identity, hash, and observed cumulative budget. Completed pass files
remain unchanged; unfinished pass files become explicit interrupted records.
Missing artifacts from a completed benchmark are treated as
corruption, not permission to rerun its cells. A benchmark with only terminal
cells can be finalized without loading a GPU model.

Model loading and synthetic warmup are recorded separately from diagnostic cell
time. Later shape-dependent compilation remains part of measured passes; inspect
repetitions and compilation effects before attributing a speed difference solely
to eviction. These diagnostic timeouts are not the task-level wall-clock budgets
used for Q1 or Q2.

CPU fixtures in `tests/test_history_benchmark.py` check input identity, forced
sequence equality, hook restoration, retention accounting, failure preservation,
and strict resume. Run them through the managed `scripts/run_checks.sh cpu` path.
Those fixtures do not validate the pinned CUDA scheduler or long-context R-KV
workspace feasibility; a small live run is required before a larger diagnostic.
