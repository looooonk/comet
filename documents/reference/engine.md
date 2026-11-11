# Native Mini-SGLang integration

This guide describes the retained Qwen3 Mini-SGLang implementation. The active
Qwen3.5-9B study uses the separate [hybrid backend](../hybrid-backend.md).

COMET uses the proposal's Mini-SGLang revision
`254c57bc84e4a7895159ba1062bd46c83626f511`, with
`patches/minisgl-comet.patch`. The AgentKV reference repository is pinned at
`b5280b7c42bd90962712c19f8e0047c89ca40d6d`. Model and tokenizer both use
`Qwen/Qwen3-8B` revision `b968826d9c46dd6066d109eabc6255188de91218` in BF16.
Pass the local Hugging Face snapshot directory, whose basename is that revision.
The legacy 4B and 14B profiles use their own pinned revisions in this engine.
Their pilot-only guards remain in code for historical reproduction; the
[new model decision](../research-direction.md) supersedes the old final-model scope.
No candidate architecture inherits support from these profiles.
The adapter verifies the checkout revision and exact patched-file hashes and rejects
unrecorded tracked upstream changes. It does not use the HTTP serving API.

`MiniSGLangEngine(EngineSettings(...))` loads one model. `start(seed)` resets all
session allocation, query observations, transcript, and random state for a fresh
attempt. `generate(append_token_ids, max_new_tokens, temperature, top_p, deadline)`
accepts only new raw tokens. `set_policy(method, retention)` changes the condition
between attempts while keeping the model loaded. Use one engine per process and
call `close()` when all conditions have finished.

Call the idempotent `warmup()` once as model initialization, before starting any
task budget. It runs every method and retention, including full cache, on the same
synthetic repeated token with `min(max_context-2, max(128, prefill_chunk_tokens))`
prompt tokens and two greedy outputs with EOS ignored. It uses no task data and
has a 600-second setup deadline by default. It restores the original policy and
leaves no live session. Provenance records the shapes, conditions, and actual
elapsed setup time. Later shape-dependent compilation remains charged to the
task budget. The same warmup runs regardless of the conditions selected for a run.

## State and recovery

The native scheduler retains its parked request and physical KV pages between
turns. Its next forward processes the newly appended suffix and, when necessary,
the final sampled token from the preceding turn. Sampled EOS tokens remain in the
raw transcript. A separate CPU transcript records every input and sampled token;
detokenization and subsequent retokenization cannot replace its historical prefix.
Generated token IDs include EOS, while `finished` indicates an EOS termination.
Logical positions remain the original positions for RoPE after compaction.

`recover(raw_token_ids + pending_observation_tokens, deadline)` checks the exact
historical transcript prefix, the one-rebuild limit, pool capacity for the full
transcript, and transient workspace admission. Denied recovery returns its reason
without changing the cache, consuming pending tokens, or spending the rebuild
allowance. An admitted recovery appends pending tokens to the raw transcript,
discards old KV, prefills the complete raw transcript without sampling, and applies the
selected retention policy after all history has been prefetched. It preserves
the sampling RNG. It has no reference to AppWorld and cannot execute or undo tool
actions. A failed admitted rebuild fails the attempt and consumes its allowance.
The final prefill logits are retained. `generate([])` samples the next output
from them once, then continues ordinary decoding; no suffix is duplicated and
no token is unnecessarily re-prefilled. These pending logits are checkpointed.

`checkpoint(path)` writes occupied K/V tensors, request state, logical/per-head
positions, raw tokens, phase labels, all query rings, Python and CPU/CUDA torch RNG,
recovery count, retention decisions, and memory counters. A neighboring JSON
manifest contains compatibility fields and the checkpoint SHA-256. Restore does
not re-prefill. The runner separately saves AppWorld state and remaining budget.
Snapshots are trusted local artifacts and use torch's restricted `weights_only`
reader. Save/restore time is charged by the runner.

`restore(path, branch=True)` allows a policy change only from a checkpoint with
full KV. It first restores identical KV and query observations, then applies the
requested compression. Ordinary resume requires the complete settings fingerprint
to match. All methods maintain the same four eight-entry phase query rings so a
full-cache diagnostic checkpoint can seed AgentKV or R-KV without reconstructing
queries. This auxiliary allocation applies to every control. R-KV still selects
its eight most recent queries; AgentKV uses its upstream four-stage observations.

## Retention accounting

The denominator is `logical_cached_tokens`: the number of token positions a
full-cache request would currently have prefetched. The final sampled token is
excluded until it has been fed through the model. Every layer and KV head uses
that same denominator. An entry includes its K and V vectors. For logical length
`D` and requested retention `r`, the target is `ceil(D*r)`, computed with exact
decimal rational arithmetic, including mandatory entries inside that target.

Short contexts retain at least the original algorithm's mandatory entries:
StreamingLLM has 16 sinks; R-KV has 8 recent tokens; AgentKV has 16 sinks plus
8 recent tokens. Therefore the effective target is
`min(D, max(ceil(D*r), mandatory))`; the requested fraction and actual lengths
are both recorded. StreamingLLM's upstream command-line budget means recent-window
length, so COMET subtracts its 16 sinks when setting the window. R-KV and AgentKV
already accept total entry budgets. No method's scoring or selection algorithm is
replaced.

Compaction occurs after the completed prefill and after every sampled decode
step, before a session is parked. Intermediate prefill chunks materialize the new
suffix without intervening eviction. Full recovery materializes all history
before compaction. These transient occupancies are included in peak KV and total
memory measurements. The full-cache control uses `none`, which explicitly disables
eviction. Missing attention observations in a compressed method raise an error;
the upstream silent identity fallback is forbidden in COMET.

## Memory and time accounting

The engine preallocates a common KV pool from the explicit total VRAM cap, exact
BF16 parameter storage, and the configured workspace reserve. Its capacity is
bounded by the configured maximum context. Retention changes occupied entries;
it does not resize this reservation. Report occupied peak KV bytes, reserved KV
pool bytes, and peak total VRAM separately. This implementation can deny a
rebuild when full history exceeds the pool even though compressed continuation
still fits. Pool reservation can make total VRAM similar across retention
conditions; it must not be reported as the compressed occupied-cache size.
The patched page allocator records its exact high-water mark, including temporary
old-plus-new page ownership during compaction; this KV measurement does not rely
on polling and is distinct from the sampled total-device measurement.

PyTorch's allocator ceiling is set to the experimental cap minus observed
non-PyTorch device use and tightened whenever its observed external high-water
mark grows during initialization or execution. Total-device use is sampled every 10 ms and checked at
forward boundaries. The reported conservative total peak is the larger of sampled
device use and peak allocator reservation plus maximum observed external use.
Allocator rejection or a detected cap excess fails the attempt. Device-wide
sampling also counts other workloads, so use an exclusively allocated GPU.
Sampling is not a measurement of arbitrarily short non-PyTorch allocation peaks;
record this limitation with the run and validate the workspace reserve in the pilot.

Recovery admission reserves the configured transient workspace, increased to a
conservative quadratic R-KV redundancy-workspace estimate where needed. This
uses the pinned R-KV head-chunk rule
`h = max(1, min(kv_heads, similarity_limit // (11*tokens**2)))`, with the upstream
1 GiB similarity limit, and reserves `24*h*tokens**2` plus eight per-layer K/V
arrays of linear workspace. The bound covers simultaneously processed heads,
BF16 similarities, boolean masks, and temporary int64 index tensors. The
allocator ceiling remains active during recovery. CUDA kernels cannot be
preempted by the adapter; deadlines are checked before and after each forward,
and the runner calls `synchronize()` during attempt cleanup and charges actual
elapsed time, including outstanding device work after a deadline signal and
overshoot. Real monotonic
clock calls remain valid under AppWorld's frozen simulated clock.

`prefill_seconds` and `decode_seconds` are synchronized host elapsed times for
their respective forward and compaction paths. Prompt token counts are tokens
actually forwarded, including the preceding uncached output token. The first
generated token comes from prefill. `decode_tokens` counts only outputs from
decode forwards, and `generated_tokens` counts all outputs including prefill's
first output. `estimated_flops` is the dense approximation
`2*parameters*forward_tokens + 4*layers*query_heads*head_dim*attention_pairs`,
where causal attention pairs use the actual retained prefix and each chunk's
query count. It excludes eviction scoring, elementwise kernels, and sampling,
and is an estimate rather than a hardware FLOP measurement. Rebuild estimates
are returned separately for the runner to add.

Each native operation also exposes `last_generation` or `last_recovery`, including
partial counters when it raises. Only completed scheduler batches contribute to
forward-token counts and `estimated_flops`. A failed batch's scheduled tokens and
estimated full-batch work are recorded as `incomplete_forward_tokens` and
`incomplete_forward_estimated_flops`; these are excluded from the completed-work
totals because the amount actually executed is unknown. Sampled tokens already
delivered to the adapter remain in the raw transcript and the failed generation
record. Forward timing includes elapsed host time until an exception; outstanding
GPU work is synchronized and charged separately as cleanup.

Attempt `metrics.metric_coverage` distinguishes `complete` counters, `lower_bound`
work totals, `partial` timings, and `unavailable` measurements. A failed operation
makes its work estimate a lower bound even when earlier batches completed. The
observed generated-token count remains exact for tokens delivered to the adapter.
These distinctions describe accounting coverage, not FLOPs estimation accuracy.
Memory-probe errors are retained separately and cannot erase the primary failure
or the last available memory measurements.

The runner writes triggered recovery decisions to `recovery_events.json` and
`attempt.json` before calling the engine. Finalized results distinguish
`completed`, `denied`, and `failed`, with admission, refusal or failure reason,
elapsed time, partial prefill work, and `allowance_consumed`. Admission is unknown
when a failure precedes the admission decision. Native admission consumes the
allowance before any rebuild mutation, including a rebuild that then fails.
`rebuild_prefill_tokens` counts completed prefill work, rather than requested
history length; `input_tokens` records the latter in the event. Rebuild elapsed
time includes admission checks and failed work. Interrupted-run finalization
merges the latest matching attempt journal and reserves the remaining cell budget;
it preserves a durable terminal attempt if the cell journal had not caught up.
If the attempt was still running, saved work counters and peaks become lower
bounds and saved operation timings become partial: the interrupted operation may
have done additional work after the last durable journal update.

## Patch and checks

The patch adds relative budgets and strict query-observation checks, preserves
per-layer/per-head retained positions outside debug mode, permits the memory guard
to initialize CUDA first, decouples the logical context limit from physical pool
size, and skips sampling for batches containing only prefill chunks. Sampling
explicitly uses PyTorch's default CUDA generator, which is seeded per attempt
and preserved by the shared checkpoint/recovery implementation. FlashInfer 0.5.3
otherwise creates a fresh generator for each call and ignores the attempt seed.
The local patch covers unfiltered, top-k, top-p, and combined sampling without
changing either dependency revision. CUDA graphs
are disabled consistently across methods. FlashInfer attention, batch size one,
and the pinned Qwen3 model implementation are shared by every method.

Run `pytest tests/test_engine_contracts.py` for CPU accounting checks.
`tests/test_engine_numerical.py` additionally exercises the actual pinned eviction
selectors on CPU when torch and the patched dependency are installed.
For live persistence, numerical checkpoint, policy-branch, one-rebuild, and cap
checks, set `COMET_RUN_GPU_TESTS=1`, `COMET_MODEL_PATH` to the snapshot directory,
and run `pytest tests/test_engine_gpu.py`. Each check runs in a fresh subprocess,
isolating Mini-SGLang's global context and CUDA allocator. The persistence check
also compares full-KV cached suffix generation against a fresh prefill of the
identical raw transcript. Two contrasting new user instructions share the same
checkpoint, close the prior assistant turn, and use the Qwen non-thinking
prefill. Each cached/fresh pair must match, and the two continuations must differ.
Set `COMET_GPU_EVIDENCE` to preserve its JSON report.
The `sampling` check uses fixed high-entropy logits to verify advancement, seed
control, exact RNG-state replay, and unchanged greedy behavior. The model
persistence check also requires sampled generation to advance the CUDA RNG.
`scripts/run_checks.sh gpu` saves the independent sampler evidence in `sampling.json`.
`COMET_TEST_MODEL` defaults to `Qwen/Qwen3-8B`; select `Qwen/Qwen3-14B` explicitly
with its corresponding snapshot for exploratory integration checks. The long
32K capacity case additionally requires `COMET_TEST_CAPACITY=1`; see the
[archived model instructions](https://github.com/looooonk/comet/blob/55fca50bfe3c69dfaa4420585e78850da1b3aaf4/documents/experimental-models.md) for its fixed settings
and evidence output.

The `memory_cap` case fixes its cap before constructing the engine, using the
pinned BF16 parameter bytes, initially observed external device use, a 4 GiB
workspace reserve, and a 512-token KV pool. With AgentKV at 25% retention, it
first rejects a rebuild for transient workspace, then grows the raw history past
the pool and rejects a second rebuild for pool capacity. Both checks compare
complete checkpoint payloads except memory high-water counters and verify the
same stochastic continuation and CUDA RNG from the original checkpoint. Pending
tokens and the one-rebuild allowance must remain unchanged after refusal.

The same fixed-cap process injects one real CUDA allocation at an inference
forward boundary. Its request exceeds the allocator ceiling, is bounded to
6 GiB, and requires at least 1 GiB of spare physical device memory beyond the
request. This distinguishes experimental-cap rejection from physical device
exhaustion. It verifies the real CUDA exception is translated to
`MemoryCapExceeded` and the measured peak remains below the unchanged cap.
This injection is test instrumentation, not an experimental inference path.
The same check verifies that the failed forward's elapsed time and scheduled
work survive the allocator error without claiming its FLOPs completed. The
persistence subprocess additionally injects a timeout after one real completed
batch in generation and recovery, checking partial counters, sampled tokens,
and consumed rebuild allowance. CPU checks in `tests/test_failure_metrics.py`
exercise runner journaling and error propagation; they do not replace these
GPU checks.
Set `COMET_GPU_MEMORY_EVIDENCE` to preserve its JSON report and neighboring
before/after checkpoint files; otherwise they use pytest's temporary directory.
Run just this check with `pytest tests/test_engine_gpu.py -k memory_cap`.
These checks explicitly permit non-A100 hardware and label evidence
integration-only; they do not constitute a train/dev pilot or validate the main
experiment matrix.
