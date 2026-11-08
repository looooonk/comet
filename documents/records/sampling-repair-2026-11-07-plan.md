# Corrected sampling and bounded-agent diagnostic

Declared November 7, 2026, following the user's request to implement the
[trajectory diagnosis](baseline-qwen8b-2026-11-07-trajectory-diagnosis.md) and
submit another Insomnia test while leaving the original run going.

## Changes and comparison

The shared Mini-SGLang patch passes PyTorch's attempt-seeded CUDA generator to
all FlashInfer sampling paths. Package and upstream revisions are unchanged.
GPU checks must demonstrate advancing random state, seed-controlled samples,
exact state replay, unchanged greedy behavior, and model checkpoint/recovery
semantics before the new task runs become eligible to start.

Compare [the corrected-sampler control](../../configs/pilot-sampling-control-qwen8b.json)
with [the bounded-agent candidate](../../configs/pilot-agent-guard-qwen8b.json).
Both inherit the same baseline candidate prompt. The second enables the shared
[agent protocol](../agent-protocol.md) with a provisional five-error limit.
This isolates the bundled protocol intervention on a corrected runtime; it does
not isolate each feedback instruction or estimate the sampling fix's causal
effect relative to the original run.

The targeted dev tasks are `0d8a4ee_1` (malformed and comment-only actions),
`3ab5b8b_1` (data shape and repeated download errors), and `57c3486_1`
(authentication). They were chosen from ordinary traces, without reading scores
or reference solutions. Each configuration runs seeds 17 and 18, for six fresh
attempts each and twelve total. All failures remain in the denominator.

Both use pinned Qwen3-8B BF16, full cache with no eviction or recovery, one attempt
per task/seed, a 600-second budget, 40 GiB VRAM cap, 32768-token context, and 4096
generation tokens per turn. Temperature 0.6, top-p 0.95, and reasoning enabled
are unchanged. Maximum task budgets total two hours, plus validation, loading,
and offline scoring. The two seeds are N=1 replicates, not budget-matched
best-of-2. The five-error threshold is provisional dev tuning.

## Isolation and execution

Use a new checkout and separately owned managed GPU environment. Do not update,
resynchronize, patch, cancel, or otherwise change the original run's checkout,
environment, task directory, or queued scorer. Share persistent model weights
and caches; avoid duplicating model snapshots. Audit storage before and after
creating the temporary concurrent environment. Use copy-on-write or copied
package files so package setup cannot change files used by the original run.

Run managed GPU checks under Slurm. Only a successful check job may release the
new experiment job. Both configurations execute sequentially on one GPU in the
same allocation through the common experiment launcher, with fresh output
directories. Use integration mode for alternative hardware, and record the
actual device. The required A100 research qualification remains separate.

Offline scoring, schema-2 trajectory auditing, and per-configuration analysis run
only after both executions finish. Keep the configurations separate and report
matched task/seed outcomes descriptively. Report error counts, stopped attempts,
time, context use, actual seed variation, and task success; fewer timeout labels
alone do not demonstrate better task performance. In particular, an earlier
`AgentProtocolError` remains a failure, not a solved task.
