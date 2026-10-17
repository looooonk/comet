# Native Mini-SGLang integration

COMET uses the proposal's Mini-SGLang revision
`254c57bc84e4a7895159ba1062bd46c83626f511`, with
`patches/minisgl-comet.patch`. The AgentKV reference repository is pinned at
`b5280b7c42bd90962712c19f8e0047c89ca40d6d`. Model and tokenizer both use
`Qwen/Qwen3-8B` revision `b968826d9c46dd6066d109eabc6255188de91218` in BF16.
Pass the local Hugging Face snapshot directory, whose basename is that revision.
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

## Patch and checks

The patch adds relative budgets and strict query-observation checks, preserves
per-layer/per-head retained positions outside debug mode, permits the memory guard
to initialize CUDA first, decouples the logical context limit from physical pool
size, and skips sampling for batches containing only prefill chunks. CUDA graphs
are disabled consistently across methods. FlashInfer attention, batch size one,
and the pinned Qwen3 model implementation are shared by every method.

Run `pytest tests/test_engine_contracts.py` for CPU accounting checks.
`tests/test_engine_numerical.py` additionally exercises the actual pinned eviction
selectors on CPU when torch and the patched dependency are installed.
For the live persistence, numerical checkpoint, policy-branch, and one-rebuild
checks, set `COMET_RUN_GPU_TESTS=1`, `COMET_MODEL_PATH` to the snapshot directory,
and run `pytest tests/test_engine_gpu.py`. Set `COMET_GPU_EVIDENCE` to preserve the
small JSON report outside pytest's temporary directory. Those checks explicitly
permit non-A100 hardware and label their evidence integration-only; they do not
constitute a train/dev pilot or validate the main experiment matrix.
