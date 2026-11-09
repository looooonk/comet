# Qwen hybrid implementation decision

The November 8 execution request authorizes implementation, Insomnia/GCP jobs,
and autonomous routine choices toward the November 9, 11 AM ET target. The user
subsequently requested smaller models first and removed the nonexistent 14B
candidate. Cleanup-only prohibitions no longer describe this execution phase.

## Verified candidates and selection

Official Hugging Face metadata and configuration files were checked on November
8. All five available candidates use Apache-2.0 and safetensors. Qwen3.5 files
include small FP32 recurrent parameters alongside BF16 weights; this is the
official format, not quantization. Thinking can be enabled or disabled through
the official chat template. Qwen3.8 additionally exposes reasoning effort.

| Official repository | Pinned revision | Architecture | Stored parameters |
| --- | --- | --- | ---: |
| [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) | `c202236235762e1c871ad0ccb60c8ee5ba337b9a` | Dense hybrid | 9,653,104,368 |
| [Qwen3.5-27B](https://huggingface.co/Qwen/Qwen3.5-27B) | `fc05daec18b0a78c049392ed2e771dde82bdf654` | Dense hybrid | 27,781,427,952 |
| [Qwen3.5-35B-A3B](https://huggingface.co/Qwen/Qwen3.5-35B-A3B) | `59d61f3ce65a6d9863b86d2e96597125219dc754` | Hybrid MoE | 35,951,822,704 |
| [Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B) | `345d467b117d1fd5eda9b879a5988de9ae5f47a7` | Hybrid MoE | 35,951,822,704 |
| [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B) | `37561816e66b5b9153b1b64c10968c18c1e6f4a0` | Dense hybrid | 27,781,427,952 |

Implement **Qwen3.5-9B first**. It has 32 text layers: eight full-attention
layers and 24 gated-delta recurrent layers. Each attention layer has four KV
heads of dimension 256. Full BF16 KV therefore grows by 32 KiB per token;
16,384 tokens occupy 512 MiB, independently of recurrent state and weights.
The approximately 19.3 GB stored weights fit a 48 GB GPU with substantial
headroom. Larger models remain candidates, not parallel implementation work.
MoE's active parameter count does not reduce the resident expert weight size.

Use one Transformers 5.22.2 backend for every method, with the existing pinned
AgentKV selectors. This implements the user-authorized new backend phase; it
does not claim Mini-SGLang supports Qwen3.5. The selector packaging step changes
imports and removes unused factory entries only; selection algorithms and their
defaults remain upstream code at `254c57bc84e4a7895159ba1062bd46c83626f511`.
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
miscounted as non-PyTorch memory. Retain the sampled device peak separately from
the conservative allocator-plus-external peak estimate.

AgentKV retains the upstream four phase rings with eight queries per phase;
R-KV uses recent queries. Eviction takes place after each prefill chunk and each
generated token. A generated terminal token is included in the raw history and
processed cache so turn boundaries cannot silently lose or duplicate state.

## Hardware and time plan

Prefer an available 48 GB Insomnia device for 9B; request the exact device model
and keep comparisons on that model. H100 queue time does not block this route.
Check queue delays during setup and execution and switch pending requests when
an adequate alternative is available. Initial context/output limits and caps
remain provisional until live checks and dev costs establish useful headroom.

An L4 leaves less headroom for 9B and requires its own measured memory cap and
qualification. Check current quota and availability before provisioning; do not
assume access to a larger GPU. Keep comparisons on the same device model and
cap. Run IDs, available quota and the spending ledger belong in the
[execution record](records/qwen9b-study-2026-11-09.md). Revise runtime and cost
estimates from pilot measurements; deadlines do not relax task-budget accounting.

Judge validation by meaningful output agreement, state correctness and task
behavior, not bitwise equality. Preserve material discrepancies and failures.
Do not freeze settings or mark live qualification complete from CPU tests.

The user also authorized lowering task difficulty and other reasonable research
adjustments when needed to expose the intended compaction/success phenomenon.
Prefer the outlined AppWorld study; declare departures as new exploratory
versions, select difficulty on train/dev, retain every measured condition and
freeze before test. This flexibility does not permit manufactured results or
unreported selection using test outcomes.
