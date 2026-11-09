# Qwen3.5-9B: verified findings, November 9

**Interim result:** the shared hybrid backend supports the required methods at
16,384 tokens on one L4 under a 21 GiB cap, and the corrected full-cache agent
solves 3/4 declared train tasks. The compaction-success curve and Q1/Q2 answers
remain pending. Queued experiments are not counted as completed evidence.

## Capability and cost

The v4 pilot uses one attempt per task, seed 17, a 300-second task budget and
the same four train families declared before execution. Evaluation runs after
execution. The [saved results](qwen9b-protocol-v4.json) contain every outcome:

| Task | Outcome | Time (s) | Tools | Raw tokens |
| --- | --- | ---: | ---: | ---: |
| File organization, `34d9492_1` | Correct | 124.1 | 16 | 11,699 |
| Arithmetic, `76f2c72_1` | Correct | 57.3 | 11 | 8,837 |
| Phone deletion, `771d8fc_1` | Correct | 51.6 | 11 | 10,089 |
| Spotify reviews, `692c77d_1` | API-error stop | 112.8 | 16 | 11,950 |

The 75% success estimate has a task-bootstrap 95% interval of 25-100%; four
families and one seed provide weak population precision. The remaining failure
confuses review IDs with song IDs and repeats authorization/duplicate-review
errors. No task reached the context or memory limit. Aggregate decoding
throughput is 13.34 tokens/s, computed as total decoded tokens divided by total
decode time. Mean task latency is 86.4 seconds, including the failed task.

Earlier pilot versions scored 0/4 and 1/4 and remain in the
[execution record](qwen9b-study-2026-11-09.md). Prompt, context and backend changes
separate those versions from v4; their difference is not a controlled estimate
of any individual change. General API examples use observed credentials and
never supply task answers.

## What the memory saving means

![Synthetic 16K capacity and recovery](../figures/qwen9b/qualification-16k.png)

The [capacity record](qwen9b-l4-context-16384.json) measures the same 16,384-token
synthetic history for each method. At 25% retention, stored full-attention KV
falls from 512 MiB to 128 MiB. Recurrent/convolution state remains 49.5 MiB.
These are different quantities from the approximately 20 GiB total GPU peak,
which also includes weights, allocator reservations and other runtime memory.

Full-history recovery temporarily rebuilds all 512 MiB of attention KV, then
reapplies retention. It takes 21.6 seconds for StreamingLLM, 22.8 for R-KV and
21.6 for AgentKV. The sampled peak including recovery is 20.05 GiB for all three,
below the unchanged 21 GiB cap. A 75% reduction in retained KV therefore does
not imply a 75% reduction in total peak GPU memory. Recovering at this history
length consumes about 18-19% of a 120-second task budget; actual task costs
depend on history length at the trigger.

These are single synthetic observations, not task-quality measurements or a
throughput benchmark. Total VRAM is sampled every 10 ms and at forward
boundaries; shorter external-memory transients can be missed. FLOPs elsewhere
in the analysis are estimates and omit recurrent updates, eviction, elementwise
operations and vision. The bounded R-KV workspace passed five live numerical
checks; the managed local suite passed 339 tests, with GPU checks run separately.

## Remaining comparisons

The matched compression screen, independent 90/120/150-second budgets,
28-arm common-checkpoint diagnostic, all-method eight-level train grid and
separate dev confirmation were queued before local cloud authentication expired.
Only a closed, unscored portion of the first compression screen has been
retrieved. Its traces show no-progress behavior under aggressive compaction,
but they do not yet support a complete success-rate comparison.

The [final candidate](../../configs/qwen9b/final-candidate-l4-v1.json) is declared
but unfrozen and unlaunched: two predeclared test families, one seed, 120 seconds,
N=2, all 29 core conditions plus five intermediate AgentKV points. The full
eight-level grid for all methods is measured separately on train. This scope
reduction preserves the core recovery comparisons within the available time;
unmeasured intermediate test points must not be implied.

Freeze requires completed train/dev evidence, at least one dev success and
both successes and failures in the train grid. Q1 requires the independently
restored checkpoint branches; Q2 requires fresh-start paired final attempts.
All timeouts, errors and flat outcomes remain in their denominators. No test
outcome may select a task or change the frozen settings.

Cloud sign-in expired during execution. The bounded worker and queued plans
continue independently, but retrieval and final submission require renewed
access. Completion, final figures and resource cleanup have not been verified
beyond the last retrieved artifacts.

## Reproduction and exports

Model, dependency and source revisions are recorded in the linked JSON files.
The backend revision for the v4/16K evidence is `0d438bf`; the v4 run identifier
is `comet-run:1fb4b489-1af3-42f1-b754-f998fb6b3aa1`. Large trajectories remain
outside tracked source. The [figure inventory](qwen9b-qualification-figures.json)
records portable source/export paths and hashes.

After activating the managed CPU profile, regenerate the capacity figure with:

```bash
python scripts/plot_hybrid_qualification.py \
  documents/records/qwen9b-l4-context-16384.json \
  --output documents/figures/qwen9b/qualification-16k
```

Exports: [PNG](../figures/qwen9b/qualification-16k.png),
[SVG](../figures/qwen9b/qualification-16k.svg),
[PDF](../figures/qwen9b/qualification-16k.pdf).
