# Broader Qwen3-8B pilot completion

The original [38-rollout pilot](baseline-qwen8b-2026-11-07-plan.md) finished
without intervention at 21:51:24 Eastern on November 7, 2026. Its separate scorer
finished at 21:52:49. Execution job `13832917` and scoring job `13832918` both
exited successfully. All declared task/seed cells have terminal results and
separate evaluator outcomes; see the [completion evidence](baseline-qwen8b-2026-11-08-completion.json).

## Outcomes and interpretation

No rollout solved its task: **0/38**, or 0/19 for each nominal seed. Execution
status and task success are different:

| Execution status | Rollouts | Successful tasks |
| --- | ---: | ---: |
| Normal completion | 14 | 0 |
| Timeout | 19 | 0 |
| Context limit | 5 | 0 |
| Total | 38 | 0 |

Timeout and context-limit failures remain in the denominator and are not given
replacement attempts. The fourteen normal completions received AppWorld
evaluation; none passed all required checks. The run occupied one RTX A6000 for
4h25m38s. Mean cell latency was 415.54 seconds, aggregate decoding throughput
35.63 tokens/second, and maximum recorded total VRAM 20.97 GiB. No attempt had
OOM status. Scoring, analysis, and schema-2 trajectory auditing completed offline.

These outcomes describe the old runtime with the confirmed
[sampling-generator defect](baseline-qwen8b-2026-11-07-trajectory-diagnosis.md).
The two nominal seeds are not validated independent model-sampling replicates.
The result is diagnostic evidence of this configuration's failures, not a sound
estimate of corrected Qwen3-8B performance. It cannot establish the causal effect
of the repair or qualify the A100 research experiment. The earlier 24-attempt
trajectory diagnosis remains a partial snapshot; this report does not extend its
turn-level attribution to the fourteen additional attempts.

## Reproduction and preservation

Artifact identifier: `baseline-broad-qwen8b-20261107`.
Run ID: `8e38480e-61a3-4147-9378-845839dca87e`.
Source: `a457a8bc39c7f31b4c5f84b450fc3a237c536964`.
Resolved configuration digest:
`575d4303ab18b53d9ad9c120431aced9c5385038393bdc3f764c7f31d98e09bf`.

The evidence JSON contains per-attempt status, task success, timing and selected
resource measurements, plus hashes for the immutable manifest, scores, analysis,
and audit. Raw outcomes, trajectories, and evaluator-compatible state remain in
the original run directory. No source, runtime, attempt, or scorer was replaced
to obtain this result. The corrected-sampler paired diagnostic is a separate run.
