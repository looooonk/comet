# Numerical screening and FP32 calibration

The L40S validation at source `f838a9b` passed 165 checks, skipped three, and
failed the new independent numerical screen. All 24 greedy tokens agreed with
Transformers BF16. Nineteen positions exceeded the provisional relative-RMSE
limit of 0.02; the largest value was 0.03988. Absolute RMSE, Jensen-Shannon
divergence and greedy regret remained within their original limits.

This was a numerical screening failure, not an OOM, timeout, or missing model
artifact. The original failed status, raw logits and full test evidence are
preserved. The other checks covered AppWorld, cache persistence, recovery,
failure accounting, sampling, memory caps, and the existing full/AgentKV 80%
32K capacity diagnostic. They do not establish the longer R-KV operating range
or task success.

## Independent higher-precision diagnosis

At source `5060c8f`, the CPU calibration loaded the same pinned Qwen3-8B weights
as FP32 using Transformers 4.57.3 eager attention. It replayed the six exact
histories, including the native continuation tokens, without a KV cache. The
run used 12 CPU threads and a 64 GiB host-memory allocation; measured peak RSS
was 34,631,864,320 bytes and the helper took 67.44 seconds. No GPU, new model
download, or FP32 task experiment was involved.

| Comparison against FP32 | Pooled centered RMSE | Maximum relative RMSE | Greedy agreement |
| --- | ---: | ---: | ---: |
| Native Mini-SGLang BF16 | 0.05548 | 0.02442 | 24/24 |
| Transformers BF16 | 0.08512 | 0.03640 | 24/24 |

The native error was smaller at 23 of 24 positions; its pooled error was 65.2%
of the Transformers BF16 error. The original 0.02 relative limit would reject
three native positions and thirteen Transformers BF16 positions when each is
compared with FP32. This supports ordinary BF16 arithmetic differences as the
explanation for the failed screen on these histories. It does not prove every
engine path correct or explain the unsuccessful AppWorld trajectories.

## Revised screen and separate validation

Screen `bf16-fp32-calibrated-v2` raises only the relative-RMSE limit from 0.02 to
0.05. The absolute 0.20 RMSE, 0.002-nat divergence, 0.125 regret and 90% exact
greedy-agreement requirements remain unchanged. The revised value is an
engineering screening bound informed by the independent calibration, not a
guaranteed error bound or an unchanged preregistered threshold. No experimental
model, precision, prompt, task subset, sampling, budget or cap changes here.

Three additional synthetic prompts and their continuations were declared before
the FP32 results arrived. Their exact corpus is
`configs/diagnostics/reference-heldout-v1.json`, SHA-256
`5df22c2a5e0a738fd77052aa4766f3c6250db8d6bbe8917a4e5939caa35b2308`.
These include open-ended generation, a scheduling choice and a fictional tool
observation. The revised screen must pass both the ordinary suite and this
separate corpus on the allocated GPU before the next task pilot. Those checks
remain pending; the original failure has not been relabeled a pass.

The [machine-readable record](reference-calibration-2026-11-08.json) includes
source identities, numerical summaries and 15 artifact hashes. Large raw tensors
remain outside tracked source. Reproduce the original failed screen at `f838a9b`
and its CPU calibration at `5060c8f`, following
[the numerical validation guide](../reference-validation.md). The calibration
helper checks its metric-source tolerances against the recorded run, so use its
recorded source when reproducing the original 0.02-screen evidence.
