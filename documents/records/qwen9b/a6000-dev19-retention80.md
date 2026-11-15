# Qwen3.5-9B on the RTX A6000: AgentKV at 80% retention

At 80% retention there is little for a rebuild to repair and little for a
rebuild-or-not choice to gain. AgentKV with no rebuild solves 18 of 57
task-seed cells against 20 for the full cache, opens every attempt on
protocol and keeps 73% of the system prompt. The fixed rebuild solves 22 and
the symptom-triggered rebuild 19. A rebuilt first attempt and its
never-rebuilt twin end differently in 5 of 56 pairs: the rebuild helped in 3
and hurt in 2. The design expected about 11 such pairs and said in advance
that the study could not establish a predictor. It found fewer, and a perfect
choice between rebuilding and not would add 2 first attempts to always
rebuilding.

The study is exploratory, covers the 19 tasks every earlier reading used, and
is compared only within the RTX A6000 cohort.

[Compact evidence](a6000-dev19-retention80.json) |
[Declared design](a6000-controls-design.md) |
[Reference arms](a6000-dev19-core.md) |
[Controls on the same tasks](a6000-dev19-controls.md)

## Outcomes

The [declared configuration](../../../configs/qwen9b/a6000/dev19-retention80-v1.json)
ran unchanged: three conditions, 19 tasks, seeds 17, 29 and 31, 171 cells and
338 attempts. Reference rows come from the cohort's
[reference arms](a6000-dev19-core.md) and the 50% symptom row from the
[first controls study](a6000-dev19-controls.md). Counts are cells out of 57.

| Condition | Oracle | First attempt | Attempts | Passing attempts | Attempts rebuilt |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full cache, two attempts (reference) | 20 | 16 | 113 | 31 | 0 |
| AgentKV 50% never (reference) | 10 | 7 | 104 | 13 | 0 |
| AgentKV 50% fixed (reference) | 17 | 12 | 111 | 23 | 93 |
| AgentKV 50% symptom (controls study) | 18 | 13 | 110 | 23 | 73 |
| AgentKV 80% never | 18 | 17 | 112 | 30 | 0 |
| AgentKV 80% fixed | 22 | 18 | 113 | 35 | 112 |
| AgentKV 80% symptom | 19 | 18 | 113 | 31 | 31 |

By seed 17, 29 and 31 the 80% arms solve 8, 6 and 4 cells with no rebuild, 7,
7 and 8 with the fixed rebuild and 8, 6 and 5 with the symptom trigger.

## The three declared comparisons

Differences are in percentage points, paired by task and seed, with the
paired task bootstrap (10,000 draws). The 19 tasks are 19 families, so the
family interval equals the task interval in every row. The design set no
confirmation criterion for this study.

| Comparison | Oracle difference | Interval | First-attempt difference | Interval |
| --- | ---: | --- | ---: | --- |
| Fixed minus never | +7.0 | [0.0, 15.8] | +1.8 | [-5.3, 8.8] |
| Symptom minus never | +1.8 | [0.0, 5.3] | +1.8 | [0.0, 5.3] |
| Symptom minus fixed | -5.3 | [-14.0, 3.5] | 0.0 | [-7.0, 7.0] |

The fixed rebuild's lead in oracle success comes through second attempts. A
second attempt alone solves 4 cells with the fixed rebuild and with the full
cache, and 1 cell with no rebuild and with the symptom trigger.

Comparisons with the reference arms were not declared for this study and
cross two source pins and two run times. No rebuild at 80% minus full cache
is -3.5 points [-14.0, 7.0] in oracle success and +1.8 [-10.5, 14.0] on the
first attempt. The fixed rebuild at 80% minus full cache is +3.5
[-7.0, 14.0]. No rebuild at 80% minus no rebuild at 50% is +14.0
[1.8, 28.1].

## What a rebuild changed in first attempts

A rebuilt first attempt and its never-rebuilt twin share seed and start, so
they take the same actions until the rebuild. A pair counts as twins here
when the first attempt was rebuilt and matches its twin action for action up
to that turn. The design's table counted 48 pairs at 50% by whether the twin
reached four tool calls; this definition gives 47 with the same helped and
hurt counts.

| Twins | Pairs | Never passes | Rebuilt passes | Rebuild helped | Rebuild hurt |
| --- | ---: | ---: | ---: | ---: | ---: |
| 80% fixed against never | 56 | 17 | 18 | 3 | 2 |
| 80% symptom against never | 16 | 2 | 3 | 1 | 0 |
| 50% fixed against never (reference) | 47 | 7 | 12 | 5 | 0 |
| 50% dynamic against never (reference) | 48 | 7 | 15 | 8 | 0 |

At 80% the rebuild hurt in 2 of the 5 pairs whose outcomes differ, with an
exact 95% interval of 5% to 85%. The earlier offline count on the other
device was 4 of 11. Harm at mild compression is neither contradicted nor
established. No pair without a rebuild ended differently from its twin, and
40 of the 41 symptom-arm first attempts that were never rebuilt repeat their
twin action for action to the end.

Not declared and added after reading the outcomes: second attempts start
fresh with the same seed and less time, and all 55 rebuilt second attempts of
the fixed arm match their never-rebuilt counterpart up to the rebuild. There
the rebuild helped in 7 and hurt in 3. Over both attempts that is 10 helped
and 5 hurt, a hurt share of 33% with an exact interval of 12% to 62%.

## Why there is little to repair

Counts are attempts.

| Condition | Attempts | Opens with the listing | Rejected login | Wrong arguments | Completed | Context limit | Passed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full cache, two attempts (reference) | 113 | 113 | 10 | 19 | 94 | 7 | 31 |
| AgentKV 50% never (reference) | 104 | 52 | 37 | 43 | 33 | 44 | 13 |
| AgentKV 80% never | 112 | 112 | 6 | 24 | 91 | 3 | 30 |
| AgentKV 80% fixed | 113 | 113 | 3 | 20 | 90 | 6 | 35 |
| AgentKV 80% symptom | 113 | 113 | 4 | 21 | 92 | 5 | 31 |

The median first attempt at 80% holds 73% of the 673 system-prompt entries at
its first action, against 39% at 50% in the controls study, and no first
attempt falls below 72% at any turn. After the fixed rebuild the median is
98% at the last turn. With the prompt mostly intact the 80% arms follow the opening and
login rules about as the full cache does, so the rule-breaking that a
rebuild repairs at 50% is mostly absent. Among twins, a login is rejected
after the rebuild in 1.8% of fixed-arm attempts against 7.1% of their twins,
a difference of -5.4 points [-16.1, 3.6] over 56 pairs. For the symptom arm
it is 6.3% against 25.0%, -18.8 points [-43.8, 0.0] over 16 pairs in 7
families.

## Rebuilds per attempt

| Trigger | 80% retention | 50% retention |
| --- | --- | --- |
| Fixed, after four tool calls | 112 of 113 attempts | 93 of 111 attempts |
| Symptom, after an error marker | 31 of 113 attempts | 73 of 110 attempts |

The symptom trigger rebuilt 16 of 57 first attempts at 80%, at a median of
five tool calls. It left the other 41 alone and matched the fixed trigger on
the first attempt, 18 cells each.

## Choosing between rebuilding and not

Each rule sees only what the runner has seen by the rebuild point and picks,
for every twin pair, the rebuilt attempt or its twin. Seven rules were
scored, the two constant ones included. The fitted rule is a logistic model
on the opening, marker counts, invalid turns, observation length and context
length, trained on pairs whose outcomes differ, with whole task families
held out. Counts are first attempts solved among the twins.

| Rule | 80%: rebuilds of 56 | 80%: solved | 50%: rebuilds of 47 | 50%: solved |
| --- | ---: | ---: | ---: | ---: |
| Never rebuild | 0 | 17 | 0 | 7 |
| Always rebuild | 56 | 18 | 47 | 12 |
| Rebuild if a marker was observed | 5 | 17 | 19 | 10 |
| Rebuild unless the attempt opened with the listing | 0 | 17 | 16 | 9 |
| Rebuild if either of those | 5 | 17 | 25 | 10 |
| Rebuild if no marker was observed | 51 | 18 | 28 | 9 |
| Fitted, families held out | 29 | 19 | 47 | 12 |
| Perfect choice | | 20 | | 12 |

At 80% the fitted rule solves one first attempt more than always rebuilding,
a difference of +1.8 points with a family interval of [0.0, 5.5], from 5
informative pairs. No rule is distinguishable from always or never
rebuilding, and a perfect choice is 2 first attempts above always
rebuilding. At 50% every rule that skips rebuilds loses 2 or 3 first
attempts and the perfect choice equals always rebuilding. On these tasks a
choice rule has nothing to gain in success at 50% and at most 2 of 56 first
attempts at 80%. What a trigger can change is cost.

## Cost

| Condition | Seconds per rebuild | Share of cell budget | Mean cell latency | Seconds per attempt | Mean peak KV | Decode tokens per second | Estimated FLOPs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full cache, two attempts (reference) | | | 71.2 s | 35.9 | 319 MiB | 24.6 | 1.98e16 |
| AgentKV 50% never (reference) | | | 91.7 s | 50.3 | 203 MiB | 25.9 | 2.29e16 |
| AgentKV 50% fixed (reference) | 3.9 | 5.3% | 87.3 s | 44.8 | 277 MiB | 26.3 | 3.62e16 |
| AgentKV 80% never | | | 79.9 s | 40.6 | 249 MiB | 23.0 | 1.92e16 |
| AgentKV 80% fixed | 3.5 | 5.7% | 82.8 s | 41.7 | 268 MiB | 23.5 | 3.34e16 |
| AgentKV 80% symptom | 3.6 | 1.6% | 81.2 s | 41.0 | 254 MiB | 23.3 | 2.34e16 |

FLOPs are the shared analysis's estimate summed over an arm's 57 cells, not a
measurement. Every requested rebuild was admitted, 112 and 31, and peak total
VRAM stayed at or below 23.06 GiB. Against the full cache, 80% retention with
no rebuild lowers mean peak KV by about 70 MiB. The symptom trigger spends
1.6% of the cell budget on rebuilds where the fixed trigger spends 5.7%, and
about 30% fewer estimated FLOPs.

The 80% arms decoded at 23.0 to 23.5 tokens per second and the reference
arms at 24.6 to 26.3. The wall-clock budget therefore bought the 80% arms
slightly less work, which bears on every comparison across the two studies
and not on the three declared ones.

## Execution

Three condition groups ran on November 15, 2026 from source `0dd8ece` on
node-local storage, were scored offline and analyzed together. The guard did
not trip: the largest rolling ten-cell medians were 1.36 seconds of reset,
2.09 of tool time and 0.10 of trajectory save. Of the 338 attempts, 273
completed, 14 reached the context limit, 42 timed out and 9 ended at the
protocol's failure limit. One cell spent 47.4 seconds in a single tool call.
The compact evidence holds the hashes, digests, comparisons, twin counts and
per-arm measurements.

## Limits

- Nineteen tasks and 57 pairs, in-sample for the symptom markers and for
  every earlier reading. Five informative first-attempt pairs cannot
  separate a rule from chance.
- The choice rules were scored on the twins they describe. A rebuild also
  changes the rest of a trajectory, so some helped and hurt pairs are chance
  and the perfect choice overstates what any rule could reach.
- Second-attempt twins were not declared and differ in the time left to
  them.
- One device type, one model and one benchmark. Reference arms ran from
  another source pin at another time and decoded faster.
- This study is outside the main experiment matrix and the team has not
  reviewed it.
