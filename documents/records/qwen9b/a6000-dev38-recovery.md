# Qwen3.5-9B on the RTX A6000: 38-task confirmation of recovery at 50% retention

On 38 dev tasks the first study did not use, all five declared hypotheses are
confirmed on the RTX A6000 cohort, before and after the Holm adjustment. Over
seeds 17, 29 and 31, AgentKV at 50% retention solves 18 of 114 task-seed cells
without a rebuild, 31 with one rebuild after four tool calls and 32 with the
context and tool-count trigger; full cache with two attempts solves 42. Fixed
minus never is +11.4 points [3.5, 20.2] and dynamic minus never +12.3
[4.4, 21.1] in oracle success. Both mechanism hypotheses are confirmed as
well: after a rebuild a login is rejected in 14% and 10% of first attempts,
against 41% and 36% of their never-rebuild twins over the same turns.

The recovery arms stay about nine points below full cache, with intervals
that include zero. The 38 tasks are new variants of the first study's 19 task
families, not new families.

[Compact evidence](a6000-dev38-recovery.json) |
[Declared design](dev38-recovery-design.md) |
[Cohort design](a6000-cohort-design.md) |
[Reference arms on the first 19 tasks](a6000-dev19-core.md)

## Outcomes

The [declared configuration](../../../configs/qwen9b/a6000/dev38-recovery-v1.json)
ran unchanged: four conditions, 38 tasks, three seeds, 456 cells and 885
attempts, each cell allowing two attempts in 120 seconds. Counts are task-seed
cells out of 114.

| Condition | Oracle | First attempt | Oracle by seed | Attempts | Passing attempts |
| --- | ---: | ---: | --- | ---: | ---: |
| Full cache, two attempts | 42 | 35 | 17, 12, 13 | 226 | 67 |
| AgentKV 50% never | 18 | 12 | 7, 5, 6 | 216 | 20 |
| AgentKV 50% fixed | 31 | 24 | 14, 7, 10 | 221 | 43 |
| AgentKV 50% dynamic | 32 | 23 | 12, 7, 13 | 222 | 40 |

Oracle success is an upper bound that assumes perfect selection among the
attempts; it is not an online policy.

## Declared hypotheses

Differences are in percentage points, paired by task and seed. The task
interval is the shared analysis's paired task bootstrap and the family
interval resamples whole task families, both with 10,000 draws. A hypothesis
is confirmed when both intervals exclude zero in the expected direction. The
p-value is the two-sided family resampling p-value, which cannot fall below
0.0001, adjusted by Holm across the five.

| | Comparison | Metric | Difference | Task interval | Family interval | Holm p | Confirmed |
| --- | --- | --- | ---: | --- | --- | ---: | --- |
| H1 | Fixed minus never | Oracle | +11.4 | [3.5, 20.2] | [3.5, 20.2] | 0.0056 | Yes |
| H2 | Dynamic minus never | Oracle | +12.3 | [4.4, 21.1] | [5.3, 21.1] | 0.0005 | Yes |
| H3 | Fixed minus never | First attempt | +10.5 | [3.5, 18.4] | [3.5, 18.4] | 0.0066 | Yes |
| H4 | Dynamic minus never | First attempt | +9.6 | [4.4, 15.8] | [4.4, 15.8] | 0.0005 | Yes |
| H5 | Never minus full cache | Oracle | -21.1 | [-31.6, -11.4] | [-33.3, -9.6] | 0.0005 | Yes |

The fixed trigger gained 11 tasks in 9 families over never and lost 3; the
dynamic trigger gained 12 in 9 families and lost 1. The 19-task estimates
these hypotheses came from were +14.0, +14.0, +15.8, +21.1 and -17.5 points.
The design expected the oracle intervals to be about 15 points either side;
they came out near 8.5.

Two of the 38 tasks, `396c5a2_1` and `4ec8de5_1`, were used by an earlier
two-task check and stayed in the sample as declared. Without them, which was
not a declared analysis, the five differences are +9.3 [0.9, 18.9], +12.0
[4.4, 21.1], +9.3 [1.9, 17.6], +10.2 [4.6, 16.2] and -19.4 [-31.5, -8.3] with
family intervals.

## Mechanism hypotheses

Among first attempts that were rebuilt and their never-rebuild twins over the
same turns, the share with a rejected login after the rebuild point. Intervals
resample task families (`comet.instruction_errors`, 10,000 draws), with a Holm
adjustment across the two.

| | Trigger | Twin pairs | Rebuilt | Never-rebuild twin | Difference | Holm p | Confirmed |
| --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| M1 | Fixed | 95 | 13.7% | 41.1% | -27.4 points [-41.6, -11.8] | 0.0016 | Yes |
| M2 | Dynamic | 97 | 10.3% | 36.1% | -25.8 points [-37.6, -13.3] | 0.0002 | Yes |

The pairs cover 36 of the 38 tasks and all 19 families. The 19-task estimates
were -38 and -33 points. Calls with wrong arguments fall in the same pairs,
from 36% to 17% for the fixed trigger and from 38% to 15% for the dynamic
trigger, which was not a declared hypothesis. Over whole attempts a login is
rejected in 82 of 216 never-rebuild attempts, 30 of 221 with the fixed
trigger, 32 of 222 with the dynamic trigger and 12 of 226 under full cache.

## Against full cache

Reported descriptively, as declared, without a confirmation criterion.

| Comparison | Metric | Difference | Task interval | Family interval |
| --- | --- | ---: | --- | --- |
| Fixed minus full cache | Oracle | -9.6 | [-20.2, 1.8] | [-21.9, 1.8] |
| Dynamic minus full cache | Oracle | -8.8 | [-19.3, 2.6] | [-21.9, 4.4] |
| Fixed minus full cache | First attempt | -9.6 | [-21.1, 1.8] | [-23.7, 2.6] |
| Dynamic minus full cache | First attempt | -10.5 | [-22.8, 1.8] | [-24.6, 3.5] |
| Never minus full cache | First attempt | -20.2 | [-30.7, -9.6] | [-33.3, -7.9] |
| Dynamic minus fixed | Oracle | +0.9 | [-7.9, 10.5] | [-8.8, 9.6] |

A rebuild closes a little more than half of the gap that compression opens.
The two triggers are not distinguishable. An interval that includes zero does
not show equivalence.

## Openings, endings and failures

Full cache opens every attempt with the API listing the prompt asks for. The
compressed arms do so in about 40% of attempts whether or not they later
rebuild, because both triggers act after the opening.

| Condition | Opens with the listing | With a search | Otherwise | Completed | Context limit | Timeout | Protocol error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full cache, two attempts | 226 | 0 | 0 | 195 | 14 | 14 | 3 |
| AgentKV 50% never | 88 | 79 | 49 | 70 | 88 | 42 | 16 |
| AgentKV 50% fixed | 89 | 81 | 51 | 105 | 79 | 34 | 3 |
| AgentKV 50% dynamic | 91 | 81 | 50 | 98 | 76 | 37 | 11 |

A completed attempt ran to the agent's own stop and need not pass. All
failures stay in the denominators. No cell was infeasible and no attempt ran
out of memory.

## Cost

| Condition | Attempts rebuilt | Seconds per rebuild | Share of cell budget | Mean cell latency | Mean peak KV | Largest peak KV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full cache, two attempts | 0 | | | 65.7 s | 325 MiB | 512 MiB |
| AgentKV 50% never | 0 | | | 90.4 s | 213 MiB | 257 MiB |
| AgentKV 50% fixed | 182 of 221 | 4.1 | 5.5% | 88.7 s | 277 MiB | 508 MiB |
| AgentKV 50% dynamic | 186 of 222 | 4.3 | 5.8% | 91.6 s | 275 MiB | 509 MiB |

Every requested rebuild was admitted under the 24 GiB cap. Peak total VRAM
reached 23.06 GiB in every arm. Mean peak KV is the largest value in a cell,
averaged over seeds and then tasks. A rebuilt attempt reaches the full-cache
KV size during the rebuild, so recovery here trades memory for success and
does not lower the peak. Decode throughput was 27.2, 25.6, 25.6 and 23.2
tokens per second in table order.

## The 57 dev tasks together

As declared, after the confirmation is reported on its own. This combines the
19 tasks that produced the hypotheses, from the
[reference arms](a6000-dev19-core.md), with the 38 confirmation tasks, so it
is not a confirmation. Counts are out of 171 cells; all ran on node-local
storage on this device.

| Condition | Oracle | First attempt |
| --- | ---: | ---: |
| Full cache, two attempts | 62 | 51 |
| AgentKV 50% never | 28 | 19 |
| AgentKV 50% fixed | 48 | 36 |
| AgentKV 50% dynamic | 52 | 38 |

| Comparison | Oracle difference | Task interval | Family interval |
| --- | ---: | --- | --- |
| Fixed minus never | +11.7 | [5.3, 18.7] | [4.7, 19.9] |
| Dynamic minus never | +14.0 | [7.0, 21.6] | [6.4, 22.2] |
| Never minus full cache | -19.9 | [-28.1, -12.3] | [-32.2, -8.2] |
| Fixed minus full cache | -8.2 | [-16.4, 0.0] | [-18.1, 2.3] |
| Dynamic minus full cache | -5.8 | [-15.2, 2.9] | [-18.1, 7.0] |
| Dynamic minus fixed | +2.3 | [-5.3, 9.9] | [-7.0, 10.5] |

## Execution

Four condition groups ran on November 14 and 15, 2026 from source `6164ba9`
on node-local storage, were scored offline and analyzed together. The guard
did not trip: the largest rolling ten-cell medians were 1.26 seconds of
reset, 1.74 of tool time and 0.13 of trajectory save, against limits of 5, 8
and 8. One cell spent 78.4 seconds in a single tool call. Of the 885 attempts,
127 timed out and 33 ended at the agent protocol's limit of four consecutive
failures. The compact evidence holds the export and analysis hashes,
configuration and execution digests, statuses and per-condition counts.

## Limits

- The 38 tasks are the two remaining variants of each of the first study's 19
  families. This confirms the result on new task instances of known
  templates, not on new kinds of task.
- One model, one device, AgentKV at 50% retention, the dev split.
- The system prompt is not protected in any arm. The
  [controls](a6000-controls-design.md) address what the rebuild restores.
- The Blackwell submission of the same study has not run. If it does, it is a
  second attempt at these hypotheses and is reported on its own.
- Outcomes depend on device speed under a 120-second budget, so nothing here
  is pooled or paired with another cohort.
