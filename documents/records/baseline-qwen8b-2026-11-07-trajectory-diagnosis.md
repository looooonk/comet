# Qwen3-8B timeout and context-limit diagnosis

The immediate failure mechanism is repeated, unproductive generation: malformed
responses, unchanged authentication failures, and unchanged data-shape errors.
The first implementation issue to fix is the sampling RNG connection. The pinned
Mini-SGLang sampler does not pass a generator to FlashInfer 0.5.3, whose default
path constructs a fresh generator on every call. COMET's attempt seed therefore
does not control that generator. Treat this run as diagnostic evidence, not a
validated stochastic replication of seeds 17 and 18.

## Inspected evidence

This is a snapshot of the first 24 terminal attempts in the ongoing
[38-rollout pilot](baseline-qwen8b-2026-11-07-plan.md), taken at 20:22 ET on
November 7. It covers the first 12 task families in the declared order, with both
seeds. The remaining 14 attempts are outside this snapshot. No evaluator scores
or ground-truth solutions were read. Ordinary task instructions, responses,
actions, observations, execution metrics, and installed dependency source were
inspected. [Evidence JSON](baseline-qwen8b-2026-11-07-trajectory-diagnosis.json)
records every inspected trajectory's hash and the source identities.

The run uses clean source `a457a8bc39c7f31b4c5f84b450fc3a237c536964`, pinned
Qwen3-8B BF16, Mini-SGLang, and an RTX A6000. Each attempt has a 600-second
budget, 32768-token context limit, 4096-token generation limit, and 40 GiB total
VRAM cap. Full cache remains enabled without eviction or recovery.

| Execution status | Attempts | Response turns | Error turns |
| --- | ---: | ---: | ---: |
| Timeout | 11 | 950 | 763 |
| Context limit | 3 | 530 | 513 |
| Normal completion, unscored | 10 | 84 | 37 |

A response turn is not necessarily an executed tool call: rejected responses
still consume time and transcript space. This distinction explains why the
earlier status check's tool-call counts understated the loop lengths.

## What fills the budgets

- **Authentication loops:** `57c3486_1`, seed 17, makes 62 calls that produce
  HTTP 401. Its generated comments describe logging in, but the executable
  action keeps calling `show_following_artists()` without a token. Seed 18 has
  63 such errors. `6171bbc_1` repeats an unauthenticated `show_account()` call;
  `4ec8de5_1` repeatedly retrieves a password but assumes the API object handles
  authentication implicitly. The candidate prompt explicitly forbids these
  behaviors, but the 8B trajectories do not follow it.
- **Data-shape loops:** `3ab5b8b_1`, seed 17, replaces playlist objects with a
  list of integers and then indexes each integer with `"song_ids"`. The same
  `int is not subscriptable` observation occurs 52 times. Seed 18 repeats a
  download loop after receiving `The song is already downloaded` 19 times,
  eventually exhausting context. Earlier actions in a failing block can already
  have changed the environment; repeating the whole block does not undo them.
- **Malformed reasoning and non-actions:** `0d8a4ee_1`, seed 17, generates 87
  responses with an unclosed reasoning block and executes 43 comment-only
  Python blocks. It makes no AppWorld API call. `383cbac_1`, seed 17, has 132
  such rejected responses and repeatedly prints `38` without consulting the
  transaction feed or completing the task. Its paired run produces the same
  response sequence.
- **Accumulated context:** `530b157_1` reaches 252 and 250 response turns. Of
  those, 212 and 209 are rejected for unfinished reasoning; the remaining
  failures include repeatedly logging in without passing the returned token to
  the next API. All three context-limit attempts end at exactly 32768 raw
  tokens. Generated text accounts for 54.5-54.7% of those tokens, with initial
  prompts and accumulated observations accounting for the remainder. This is
  persistent loop growth, not evidence that a single unusually large API result
  caused the failure.

Only two of the 14 failed attempts issue a specific API-signature lookup. Most
read an API-name catalog and then guess parameters or authentication behavior.
These counts describe this partial snapshot, not all dev tasks or final scores.

Inference consumes 97.9% of elapsed time across the timeout attempts. Recorded
tool execution consumes 29.45 seconds across all eleven, under 0.5% of their
combined elapsed time. Slow tool execution is not the dominant bottleneck here.
The maximum observed total VRAM is 20.97 GiB, below the 40 GiB cap; no inspected
attempt has OOM status. All 24 have zero rebuilds and retention events, and equal
final physical and logical cached-token counts. These checks do not establish
numerical correctness of every inference operation.

## Sampling defect and validation gap

COMET seeds the global PyTorch generators in
[`MiniSGLangEngine.start`](../../src/comet/engine/native.py).
The pinned [Mini-SGLang sampling path](https://github.com/LiuTaowen-Tony/kv-management-minisgl/blob/254c57bc84e4a7895159ba1062bd46c83626f511/python/minisgl/engine/sample.py)
calls FlashInfer without a generator. In
[FlashInfer 0.5.3](https://github.com/flashinfer-ai/flashinfer/blob/v0.5.3/flashinfer/sampling.py),
`get_seed_and_offset` creates a new generator when none is supplied, instead of
advancing the global generator seeded by COMET. The installed implementations
on Insomnia were checked against the pinned source; their hashes are recorded.

All 12 inspected task pairs have identical first responses; six have identical
complete response sequences across seeds. The other pairs' later divergence
does not prove working sampling seeds: changed observations can change subsequent
logits. The source defect makes the nominal two seeds unsuitable as evidence of
independent model-sampling replicates. It may contribute to persistent loops,
but the size of that causal effect needs a corrected, controlled rerun.

A separate live CUDA check in Slurm job `13834366`, on an RTX PRO 6000
Blackwell, reproduced the generator problem without running a model or AppWorld.
After setting the global generators to each actual attempt seed, all default
helper calls returned seed `67280421310721` and offset `32`; the global CUDA RNG
did not advance. Explicit generators used the correct attempt seeds
`403056972` and `2753358715`, with offsets advancing through `32`, `64`, and `96`.
The probe ran on a different GPU from the ongoing pilot and did not alter its
runtime, data, or timing allocation.

The actual top-p sampling kernel was then tested on 64 identical uniform
probability rows over 64 tokens. Its default samples were identical across both
seeds and all three successive calls. Explicit generators produced different
samples across calls and seeds, while reseeding exactly replayed the first
sample. This reproduces the sampling defect, not its effect on model task
success. Successful Slurm steps `13834366.1` and `13834366.2` saved the helper
and kernel evidence before the allocation was released.

An initial standalone probe (`13834355`) reached its five-minute limit without
producing a result. The revised launcher's main process was also still importing
dependencies when the separate successful steps finished, so it was stopped
after collecting their evidence. These diagnostic-launch failures are separate
from the 38-rollout pilot and do not add or replace any experiment attempt.

The existing GPU tests verify that restoring a checkpoint reproduces sampled
output and RNG state. They do not assert that ordinary sampling advances the
intended RNG or that changing the attempt seed controls the samples. A sampler
that resets its own generator can pass the existing replay-equality checks.

## Fix order

1. Pass an advancing, attempt-seeded CUDA generator into every FlashInfer
   sampling path. Ensure checkpoint restore and recovery preserve the same RNG
   semantics. Add a small live sampling test for advancement, seed control, and
   exact replay before rerunning model-quality comparisons.
2. With sampling corrected, test a small declared dev subset for authentication,
   signature lookup, and response-shape inspection. Measure executable actions,
   not statements in generated comments. Preserve the original failed runs.
3. Test bounded handling of repeated identical failures and unclosed reasoning.
   Comment-only blocks should not be treated as useful execution. Any retry or
   corrective observation must remain inside the existing attempt budget and
   use no evaluator feedback. Version changes to the agent protocol and keep
   them shared across retention conditions.
4. Reassess time and context limits only after useful progress is demonstrated.
   More budget alone would currently fund more repetitions.

The active experiment, its prompt, and its runtime were not changed by this
investigation. This record is not the completed 38-rollout result, a measured
prompt improvement, or main A100 qualification.
