# Qwen3.5-9B on the RTX A6000: retry curve at 50% retention

With eight independent attempts per task, keeping the cache compressed and
retrying does not catch up with rebuilding it. At equal occupied KV, one
attempt with a rebuild solves 25.0% (fixed) and 25.7% (dynamic) of the 19
tasks against 20.9% for the best of two never-rebuild attempts; two rebuilt
attempts solve 35.0% and 36.5% against 27.1% for the best of four; four solve
43.0% and 45.7% against 31.6% for the best of eight. Every one of these
intervals includes zero. One of the two recorded expectations failed: with
perfect selection, five never-rebuild attempts reach the level of one
full-cache attempt.

Compression also bought little to retry with. A never-rebuild attempt holds
about 110 MiB less KV than a full-cache attempt under a 24 GiB cap, and takes
58 seconds on average against 38.

[Compact evidence](a6000-dev19-retry.json) |
[Declared analysis](a6000-cohort-design.md#retry-curve) |
[Reference arms](a6000-dev19-core.md)

## Attempts

The [declared configuration](../../../configs/qwen9b/a6000/dev19-retry-v1.json)
ran unchanged: single attempts of four arms on the 19 first-study tasks at
seeds 37, 41, 43, 47 and 53, 380 cells. With the first attempts of the
reference arms at seeds 17, 29 and 31, each task and arm has eight
independent attempts, each starting from the task's initial state with its
own 120-second budget.

| Arm | Passing attempts of 152 | Tasks never solved | Tasks solved every time | Mean seconds per attempt | Attempt-seconds per passing attempt |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full cache | 42 | 11 | 3 | 38.0 | 137 |
| AgentKV 50% never | 23 | 13 | 1 | 58.5 | 387 |
| AgentKV 50% fixed | 38 | 10 | 1 | 52.0 | 208 |
| AgentKV 50% dynamic | 39 | 9 | 1 | 50.8 | 198 |

Tasks are out of 19. The fixed and dynamic triggers each rebuilt 138 of their
152 attempts.

## Best of k attempts

Success is the share of tasks solved by at least one of k attempts, averaged
over every choice of k of the eight seeds. It assumes the passing attempt can
be picked, so it is an upper bound and favours retrying. Values are
percentages of 19 tasks.

| Arm | k = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full cache | 27.6 | 33.8 | 37.1 | 38.9 | 40.0 | 40.8 | 41.4 | 42.1 |
| AgentKV 50% never | 15.1 | 20.9 | 24.5 | 27.1 | 28.9 | 30.1 | 30.9 | 31.6 |
| AgentKV 50% fixed | 25.0 | 35.0 | 40.1 | 43.0 | 44.7 | 45.9 | 46.7 | 47.4 |
| AgentKV 50% dynamic | 25.7 | 36.5 | 42.3 | 45.7 | 48.0 | 49.8 | 51.3 | 52.6 |

Paired task-bootstrap intervals (10,000 draws) at one attempt are
[11.8, 46.1], [3.9, 28.9], [11.8, 40.1] and [12.5, 40.1] in table order, and
at eight attempts [21.1, 63.2], [10.5, 52.6], [26.3, 68.4] and [31.6, 73.7].

## Equal occupied KV

Declared comparisons, taking two 50% attempts as one full-cache attempt and a
rebuilt attempt at its full-size peak. Differences are in percentage points
with paired task-bootstrap intervals.

| Full, never, rebuilt attempts | Fixed minus never | Dynamic minus never | Never minus full cache | Fixed minus full cache | Dynamic minus full cache |
| --- | --- | --- | --- | --- | --- |
| 1, 2, 1 | +4.1 [-5.4, 14.1] | +4.8 [-2.1, 12.8] | -6.8 [-22.6, 8.2] | -2.6 [-17.1, 9.2] | -2.0 [-15.8, 10.5] |
| 2, 4, 2 | +7.9 [-4.3, 21.8] | +9.4 [-1.1, 21.6] | -6.8 [-26.1, 12.6] | +1.1 [-15.4, 16.7] | +2.6 [-12.8, 18.6] |
| 4, 8, 4 | +11.4 [-1.4, 27.4] | +14.1 [-1.1, 31.2] | -7.4 [-28.6, 13.2] | +4.1 [-14.1, 22.4] | +6.8 [-8.2, 24.3] |

The point estimates favour rebuilding over retrying at every tier and the gap
widens with more attempts, but no interval excludes zero. Nineteen tasks
cannot settle a difference of this size.

The memory side of the comparison, from this study's five seeds:

| Arm | Mean peak KV | Largest peak KV | Mean peak total VRAM |
| --- | ---: | ---: | ---: |
| Full cache | 305 MiB | 500 MiB | 23.03 GiB |
| AgentKV 50% never | 194 MiB | 257 MiB | 22.44 GiB |
| AgentKV 50% fixed | 265 MiB | 500 MiB | 22.92 GiB |
| AgentKV 50% dynamic | 252 MiB | 496 MiB | 22.92 GiB |

Model weights and runtime take most of the 24 GiB cap. Halving the KV cache
frees roughly 110 MiB on average and 240 MiB at the largest peak, which is
not room for a second concurrent attempt on this model. Counting two
compressed attempts as one full-cache attempt is therefore generous to
retrying. Attempts ran one after another, as declared.

## Recorded expectations

- **One rebuilt attempt is at least as good as the best of two never-rebuild
  attempts.** Holds in the point estimates, 25.0% and 25.7% against 20.9%.
  The intervals include zero.
- **The never-rebuild curve stays below one full-cache attempt through eight
  attempts.** Does not hold. The best of five never-rebuild attempts is 28.9%
  against 27.6% for one full-cache attempt, and the best of eight is 31.6%,
  a difference of +3.9 points [-15.1, 24.3].
- **Under the self-report selector the rebuilt arms gain more from retries
  than full cache does.** Holds in the point estimates. From one to eight
  attempts the fixed arm gains 21.1 points, the dynamic arm 10.5 and full
  cache 5.3; the differences from full cache are +15.8 [0.0, 31.6] and +5.3
  [-10.5, 21.1]. The never-rebuild arm also gains 21.1.

## Without perfect selection

The selector takes attempts in seed order and keeps the first one that ends
with a completion call reporting success; if none does, it keeps the last.
With 19 tasks each step is 5.3 points, and only one order of seeds is used.

| Arm | k = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full cache | 26.3 | 26.3 | 31.6 | 31.6 | 31.6 | 31.6 | 31.6 | 31.6 |
| AgentKV 50% never | 5.3 | 21.1 | 21.1 | 21.1 | 21.1 | 26.3 | 26.3 | 26.3 |
| AgentKV 50% fixed | 15.8 | 26.3 | 31.6 | 31.6 | 31.6 | 31.6 | 31.6 | 36.8 |
| AgentKV 50% dynamic | 31.6 | 36.8 | 36.8 | 42.1 | 42.1 | 42.1 | 42.1 | 42.1 |

| Arm | Attempts claiming success | Of which pass | Attempts with no claim |
| --- | ---: | ---: | ---: |
| Full cache | 127 of 152 | 42 (33%) | 25 |
| AgentKV 50% never | 57 of 152 | 23 (40%) | 95 |
| AgentKV 50% fixed | 90 of 152 | 38 (42%) | 62 |
| AgentKV 50% dynamic | 89 of 152 | 39 (44%) | 63 |

No attempt reported failure and none passed without claiming success. Full
cache claims success in five attempts of six and is right a third of the
time, so a selector that trusts the claim rarely lets it retry. The
compressed arms more often end without a claim, at the context limit or the
time limit, which is what lets them retry.

## Execution

Four condition groups ran on November 14 and 15, 2026 from source `6164ba9`
on node-local storage, were scored offline and analyzed together. The guard
did not trip: the largest rolling ten-cell medians were 0.66 seconds of
reset, 1.00 of tool time and 0.07 of trajectory save. Of the 380 attempts,
233 completed, 98 reached the context limit, 28 timed out and 21 ended at the
protocol's failure limit. Every requested rebuild was admitted. The compact
evidence holds the hashes, digests, curves, intervals and per-arm counts.

## Limits

- Nineteen tasks, the ones that produced the recovery hypothesis, with three
  of the eight seeds already read in the reference arms.
- Retries are independent fresh attempts. Attempts did not run concurrently,
  and no attempt used the outcome of another.
- Best of k is an upper bound. The self-report selector is one simple rule,
  read in one seed order.
- One model, one device, AgentKV at 50% retention, the dev split.
