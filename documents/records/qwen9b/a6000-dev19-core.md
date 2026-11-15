# Qwen3.5-9B on the RTX A6000: reference arms of the 19-task recovery study

On the RTX A6000 cohort the recovery result of the first 19 dev tasks appears
again. Over seeds 17, 29 and 31, AgentKV at 50% retention solves 10 of 57
task-seed cells without a rebuild, 17 with one rebuild after four tool calls
and 20 with the context and tool-count trigger; full cache with two attempts
solves 20. Fixed minus never is +12.3 points [1.8, 22.8] and dynamic minus
never +17.5 [5.3, 31.6] in oracle success. The never-rebuild arms of R-KV 50%,
StreamingLLM 50% and AgentKV 25% solve nothing.

These are the tasks that produced the hypothesis, run on a second device, so
this is a repeat and not a confirmation; the
[38-task study](dev38-recovery-design.md) on this cohort is the confirmation.
No hypothesis was declared for this study, and the intervals below are not
adjusted for the number of comparisons.

[Compact evidence](a6000-dev19-core.json) |
[Cohort design](a6000-cohort-design.md) |
[First study](dev19-recovery.md) |
[Instruction-error reading](dev19-instruction-errors.md)

## Outcomes

The [declared configuration](../../../configs/qwen9b/a6000/dev19-core-v1.json)
ran unchanged: seven conditions, 19 tasks, three seeds, 399 cells and 714
attempts, each cell allowing two attempts in 120 seconds. Counts are task-seed
cells out of 57.

| Condition | Oracle | First attempt | Oracle by seed | Attempts | Passing attempts |
| --- | ---: | ---: | --- | ---: | ---: |
| Full cache, two attempts | 20 | 16 | 6, 7, 7 | 113 | 31 |
| AgentKV 50% never | 10 | 7 | 2, 5, 3 | 104 | 13 |
| AgentKV 50% fixed | 17 | 12 | 4, 9, 4 | 111 | 23 |
| AgentKV 50% dynamic | 20 | 15 | 8, 7, 5 | 111 | 25 |
| R-KV 50% never | 0 | 0 | 0, 0, 0 | 91 | 0 |
| StreamingLLM 50% never | 0 | 0 | 0, 0, 0 | 86 | 0 |
| AgentKV 25% never | 0 | 0 | 0, 0, 0 | 98 | 0 |

Oracle success is an upper bound that assumes perfect selection among the
attempts; it is not an online policy. One arm moves by up to five cells
between seeds.

## Paired differences

Differences are in percentage points over the three seeds, paired by task and
seed. The first interval is the shared analysis's paired task bootstrap
(10,000 draws); the second resamples whole task families.

| Comparison | Metric | Difference | Task interval | Family interval |
| --- | --- | ---: | --- | --- |
| Fixed minus never | Oracle | +12.3 | [1.8, 22.8] | [1.8, 24.6] |
| Fixed minus never | First attempt | +8.8 | [1.8, 17.5] | [1.8, 17.5] |
| Dynamic minus never | Oracle | +17.5 | [5.3, 31.6] | [5.3, 31.6] |
| Dynamic minus never | First attempt | +14.0 | [3.5, 28.1] | [3.5, 28.1] |
| Never minus full cache | Oracle | -17.5 | [-31.6, -3.5] | [-31.6, -3.5] |
| Never minus full cache | First attempt | -15.8 | [-31.6, -0.0] | [-31.6, -1.8] |
| Fixed minus full cache | Oracle | -5.3 | [-14.0, 5.3] | [-14.0, 5.3] |
| Dynamic minus full cache | Oracle | 0.0 | [-14.0, 15.8] | [-15.8, 15.8] |
| Dynamic minus fixed | Oracle | +5.3 | [-8.8, 19.3] | [-8.8, 19.3] |

The fixed trigger gained six tasks over never and lost one; the dynamic
trigger gained six and lost none. Neither recovery arm is distinguishable from
full cache or from the other at this size. An interval that includes zero
does not show equivalence.

## What the rebuild changes

The [instruction-error reading](dev19-instruction-errors.md) of the Blackwell
runs predicted fewer rejected logins after a rebuild. Read the same way here,
among first attempts that were rebuilt and their never-rebuild twins over the
same turns:

| Trigger | Twin pairs | Rejected login after the rebuild point, rebuilt | Never-rebuild twin | Difference |
| --- | ---: | ---: | ---: | --- |
| Fixed | 47 | 12.8% | 40.4% | -27.7 points [-39.6, -15.6] |
| Dynamic | 48 | 10.4% | 43.8% | -33.3 points [-46.9, -20.0] |

Intervals resample task families (`comet.instruction_errors`, 10,000 draws).
Over whole attempts, a login is rejected in 36% of never-rebuild attempts,
17% with the fixed trigger, 11% with the dynamic trigger and 9% under full
cache. These tasks informed the reading, so this is the same pattern on
another device, not an independent test of it.

## Attempts and failures

| Condition | Completed | Context limit | Timeout | Protocol error |
| --- | ---: | ---: | ---: | ---: |
| Full cache, two attempts | 94 | 7 | 8 | 4 |
| AgentKV 50% never | 33 | 44 | 22 | 5 |
| AgentKV 50% fixed | 55 | 37 | 17 | 2 |
| AgentKV 50% dynamic | 55 | 40 | 15 | 1 |
| R-KV 50% never | 7 | 0 | 45 | 39 |
| StreamingLLM 50% never | 0 | 6 | 49 | 31 |
| AgentKV 25% never | 2 | 3 | 31 | 62 |

A completed attempt ran to the agent's own stop and need not pass. AgentKV at
50% reaches the 16,384-token transcript limit in 37 to 44 attempts against 7
under full cache, with or without a rebuild. All failures stay in the
denominators. The fixed trigger rebuilt 93 of its 111 attempts and the dynamic
trigger 91 of 111.

## Execution

Four condition groups ran on November 14, 2026 from source `6164ba9` on
node-local storage, were scored offline and analyzed together. The guard did
not trip: the largest rolling ten-cell medians were 1.21 seconds of reset,
1.20 of tool time and 0.19 of trajectory save, against limits of 5, 8 and 8.
One cell spent 95.9 seconds in a single tool call and timed out there. The
compact evidence holds the export and analysis hashes, configuration and
execution digests, attempt statuses and per-condition counts.

## Limits

- Nineteen tasks from 19 families at three seeds, one model and one device.
- The 120-second budget makes outcomes depend on device speed, so nothing here
  is pooled or paired with the Blackwell cohort.
- No hypothesis was declared for this study and nine comparisons are shown
  unadjusted.
- The system prompt is not protected in any arm. The
  [controls](a6000-controls-design.md) test whether that explains the result.
