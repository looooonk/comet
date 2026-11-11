# Qwen3.5-9B hybrid backend

The selected model is [Qwen/Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B),
pinned at `c202236235762e1c871ad0ccb60c8ee5ba337b9a` for model and tokenizer.
The official snapshot uses safetensors under Apache-2.0, with BF16 weights and
small FP32 recurrent parameters. Its chat template controls thinking mode.

The text model has 32 layers: eight full-attention layers and 24 gated-delta
recurrent layers. Four KV heads of dimension 256 per attention layer give
32 KiB of BF16 KV per token, or 512 MiB at 16,384 tokens, independently of
recurrent state and weights. Stored parameters total 9,653,104,368 (about
19.3 GB of weights). Larger architectures are unsupported; their former candidate
inventory remains in Git history. See the [research contract](research-direction.md)
for model and hardware qualification boundaries.

## Shared implementation

Use one Transformers 5.22.2 backend for every method, with the existing pinned
AgentKV selectors. This implements the user-authorized new backend phase; it
does not claim Mini-SGLang supports Qwen3.5. The selector packaging step changes
imports and removes unused factory entries only; selection algorithms and their
defaults remain upstream code at `254c57bc84e4a7895159ba1062bd46c83626f511`.
The hybrid integration evaluates R-KV redundancy in query-row tiles with a
256 MiB workspace target. Its original full quadratic integer temporary exceeded
the L4 allocator cap during a 16,384-token rebuild. Row tiling preserves the
similarity, threshold and retained-index rules; FP32 accumulation can change
BF16 rounding slightly. This local implementation is recorded in engine
provenance and checked against the pinned selector on repeated and random keys.
AppWorld, the shared runner, recovery policies, budgets and offline evaluator
remain shared. Model registration and live qualification are separate steps.

Linux runtime setup needs a C compiler and the matching Python development
headers for Triton's driver extension (for system Python on Ubuntu, install
`gcc`, `g++` and `python3-dev`). Probe
`triton.runtime.driver.active.get_current_target()` in the activated hybrid
runtime before downloading weights or launching checks. The engine also checks
this before importing the model so FLA cannot hide a driver setup failure behind
its CPU fallback. The required target is CUDA.

## State and compaction contract

Retention applies to KV entries in the eight full-attention layers, separately
per head, against the full raw processed-token count at the same step. It does
not claim to compress every model state or the text transcript. Decimal ceiling
and mandatory floors remain StreamingLLM 16, R-KV 8 and AgentKV 24 entries.
Gather selected K/V without changing their original rotary positions. The
query uses its original absolute token position; causal masks distinguish
already cached history from the new chunk. Record realized counts.

All recurrent matrices and convolution windows persist across every suffix and
are left unchanged by KV eviction. They are counted separately from occupied KV.
Checkpoint all KV, original positions, recurrent/convolution state, query
observations, raw tokens, saved next-token logits and RNG state. Independent
branches restore these values without aliasing. Full-history recovery discards
the current cache, recomputes *all* hybrid state from the raw transcript once,
then reapplies retention. It neither reruns tools nor restores environment state.
Admission includes full-cache rebuild and workspace peaks under the same cap.
The PyTorch pool leaves 1 GiB of additional headroom for lazy CUDA runtime/kernel
allocations. This is separate from the rebuild workspace estimate and does not
raise the experimental cap. Device-wide peak use remains measured and enforced.
External usage samples are accepted only when the PyTorch pool is unchanged
across the device-memory query; otherwise a concurrent pool release could be
miscounted as non-PyTorch memory. The enforced total-VRAM metric is the measured
device-wide peak, sampled every 10 ms and at forward boundaries. Retain exact
PyTorch allocation/pool peaks and the conservative allocator-plus-external upper
estimate separately; noncoincident maxima are not a measured device peak. Very
short external allocations can fall between samples, so the sampling interval
and allocator headroom remain explicit limitations rather than an exact bound.

AgentKV retains the upstream four phase rings with eight queries per phase;
R-KV uses recent queries. Eviction takes place after each prefill chunk and each
generated token. A generated terminal token is included in the raw history and
processed cache so turn boundaries cannot silently lose or duplicate state.

## Qualification

[Live records](records/README.md) establish the scope of the A6000, L4 and
Blackwell checks. Every new device/cap combination requires its own validation.
Use meaningful output agreement, state correctness and task behavior; preserve
material numerical discrepancies. CPU tests do not establish live qualification.
