# Paired retention pilot plan

This exploratory pilot compares full KV against AgentKV at 80%, 50%, and 25%
retention. Recovery is disabled and each task/condition receives one fresh
attempt. Its purpose is to measure task success, latency, occupied KV memory,
and their uncertainty before planning a larger comparison.

The user authorized a stronger model if Qwen3-8B was inadequate. The earlier
[completion record](validation-2026-10-16-followup.json) contains unsuccessful
8B attempts that completed by declaring inability to finish. The ordinary
trajectories show that they stopped after API summaries without inspecting the
relevant API signatures. This pilot uses Qwen3-14B in BF16 through the same
pinned Mini-SGLang engine. It is separate from the proposal's main 8B/A100
matrix; see [experimental models](../experimental-models.md).

[The versioned configuration](../../configs/pilot-retention-qwen14b.json) fixes
the model/tokenizer revision, prompt, task IDs, seed, and all four conditions.
The eight task families were sampled from the 19 dev families with
`random.Random(20261017).sample(sorted(families), 8)`, taking variant `_1` in
each family. Sampling did not inspect task scores. Seed 17 is paired across
conditions. There are 32 attempts, with a 600-second budget per cell, a
32,768-token context, a 40 GiB total VRAM cap, and a 6 GiB workspace reserve.
Each response may generate up to 4096 tokens with reasoning enabled. The API
prompt is unchanged from the completion-v4 configuration.

All cells run before offline evaluation. Timeout, context-limit, OOM, and other
failed attempts remain failures in the denominator. The budget includes reset,
inference, tools, and outcome saving; initialization and scoring are excluded.
Execution uses one GPU sequentially. Alternative hardware is explicitly marked
as integration mode and cannot qualify the main experiment for freezing.

Analysis treats tasks as the sampling unit and preserves condition pairing.
Report task-level standard errors and pointwise 95% task-bootstrap intervals.
For boundary accuracy results, also report a conservative bounded-mean interval:
an all-zero bootstrap interval is not evidence of zero uncertainty. Plot the
four measured points with error bars; do not fit a curve that imposes smoothness
or monotonicity. Peak occupied KV includes compaction transients. It is distinct
from the preallocated KV pool and peak total VRAM, which must be labeled
separately. Different trajectories may reach different context lengths.

This small sample is for feasibility and variance estimation. Any expansion
must declare its additional tasks, seeds, and precision criterion before scoring
them. Do not repeatedly sample until a preferred trend becomes significant,
discard difficult tasks, or treat repeated seeds as independent tasks.

## Infrastructure repair

The first run encountered compiler-cache disk-quota errors during the third 50%
cell. All 32 outcomes, including 14 infrastructure errors and one timeout, remain
in the [failed-run record](retention-pilot-2026-10-17-quota-failure.json). It is not
a valid four-condition retention comparison. Its full-cache baseline scored 1/8.

After correcting cache placement and checking storage writes, rerun the entire
matrix under a new run ID with the same experimental settings. Keep the two runs
separate, without replacing failed cells or pooling earlier successful cells into
the repaired comparison. Record the new source revision and cache preflight.
