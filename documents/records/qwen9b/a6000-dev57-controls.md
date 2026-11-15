# Qwen3.5-9B on the RTX A6000: the declared controls analysis on 57 tasks

The second controls study finished, so the declared analysis over the 57 dev
tasks of both studies can be reported. Four of the six comparisons are
supported after the Holm adjustment, one is unresolved, and the one that
expected pinning to help found the reverse.

- A rebuild beats re-sending the prompt as text by +10.5 points
  [4.7, 17.5]. The reminder solves 30 of 171 task-seed cells, the same as
  doing nothing (28).
- A rebuild triggered by an error in a tool observation beats no rebuild by
  +12.3 points [6.4, 18.7] and is level with the fixed trigger, 49 cells
  against 48, with 213 rebuilds against 275. On the 38 tasks that did not
  inform its markers it is +11.4 [6.1, 16.7] above no rebuild.
- Pinning the system prompt without a rebuild solves 9 cells against 28
  unpinned, -11.1 points [-23.4, -1.8]. The confound the
  [first study](a6000-dev19-controls.md) identified repeats on the new
  tasks, so this arm still does not test whether a pinned prompt is enough.
- Pinning the prompt and rebuilding once solves 60 cells against 62 for the
  full cache, a difference of -1.2 points [-9.9, 7.6] that is unresolved,
  not shown to be equal.

[Compact evidence](a6000-dev57-controls.json) |
[Declared design](a6000-controls-design.md) |
[First controls study](a6000-dev19-controls.md) |
[Reference arms on the 38 tasks](a6000-dev38-recovery.md)

## Outcomes

The [second configuration](../../../configs/qwen9b/a6000/dev38-controls-v1.json)
ran unchanged: four AgentKV conditions at 50% retention on the 38 tasks of
the cohort's confirmation, seeds 17, 29 and 31, 456 cells and 872 attempts.
Reference rows come from the cohort's reference arms on the 19 and the 38
tasks. Counts are cells, out of 171 for all 57 tasks and out of 114 for the
38 new ones.

| Condition | Oracle of 171 | First attempt of 171 | Oracle of 114 | First attempt of 114 | Attempts | Passing attempts | Attempts rebuilt |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full cache, two attempts (reference) | 62 | 51 | 42 | 35 | 339 | 98 | 0 |
| AgentKV 50% never (reference) | 28 | 19 | 18 | 12 | 320 | 33 | 0 |
| AgentKV 50% fixed (reference) | 48 | 36 | 31 | 24 | 332 | 66 | 275 |
| AgentKV 50% dynamic (reference) | 52 | 38 | 32 | 23 | 333 | 65 | 277 |
| AgentKV 50% pinned prompt, never | 9 | 6 | 5 | 3 | 316 | 10 | 0 |
| AgentKV 50% pinned prompt, fixed | 60 | 49 | 41 | 34 | 334 | 88 | 331 |
| AgentKV 50% text reminder | 30 | 23 | 20 | 15 | 337 | 41 | 0 |
| AgentKV 50% symptom trigger | 49 | 33 | 31 | 20 | 323 | 61 | 213 |

The reminder was sent in 288 of 337 attempts, once each, as 682 tokens.

## The six declared comparisons

Differences are in oracle success, in percentage points, paired by task and
seed over the 57 tasks, with the paired task bootstrap and the family
interval (10,000 draws). The Holm p-values adjust across the six. A
comparison is supported when both intervals exclude zero, and C1 and C5 only
in the expected positive direction. A p-value of 0.0006 is the floor of
10,000 draws times six.

| | Comparison | Difference | Task interval | Family interval | Holm p | Outcome |
| --- | --- | ---: | --- | --- | ---: | --- |
| C1 | Pinned never minus never | -11.1 | [-18.7, -4.7] | [-23.4, -1.8] | 0.025 | Not supported: negative |
| C2 | Fixed minus pinned never | +22.8 | [14.6, 31.6] | [10.5, 36.8] | 0.0006 | Supported |
| C3 | Pinned fixed minus pinned never | +29.8 | [19.3, 40.4] | [14.6, 46.8] | 0.0006 | Supported |
| C4 | Fixed minus reminder | +10.5 | [4.1, 17.5] | [4.7, 17.5] | 0.0006 | Supported |
| C5 | Symptom minus never | +12.3 | [7.0, 18.1] | [6.4, 18.7] | 0.0006 | Supported |
| C6 | Symptom minus fixed | +0.6 | [-6.4, 7.6] | [-7.6, 8.2] | 0.919 | Unresolved |

The design said C2 and C3 decide the claim: if a rebuild still adds success
with the prompt pinned, the rebuild restores more than instructions. C3 is
supported, so by the declared rule that is the reading. It needs the
qualification below, because the pinned arm lost the task statement to the
pinning itself.

Reported descriptively, as declared, with task and family intervals:

| | First attempt, 57 tasks | Oracle, 38 new tasks |
| --- | --- | --- |
| C1 | -7.6 [-14.0, -1.8] [-18.7, 0.0] | -11.4 [-20.2, -3.5] [-23.7, -2.6] |
| C2 | +17.5 [9.9, 25.7] [7.6, 29.2] | +22.8 [13.2, 33.3] [10.5, 36.8] |
| C3 | +25.1 [15.8, 35.1] [12.9, 38.6] | +31.6 [19.3, 44.7] [15.8, 48.2] |
| C4 | +7.6 [1.2, 14.6] [0.6, 15.2] | +9.6 [0.9, 19.3] [2.6, 16.7] |
| C5 | +8.2 [4.1, 12.9] [3.5, 13.5] | +11.4 [5.3, 17.5] [6.1, 16.7] |
| C6 | -1.8 [-8.2, 4.1] [-8.2, 4.1] | 0.0 [-9.6, 9.6] [-9.6, 9.6] |

The 19-task part is in the [first record](a6000-dev19-controls.md). Other
declared descriptive comparisons in oracle success over the 57 tasks, with
the family interval: pinned fixed minus full cache -1.2 [-9.9, 7.6], pinned
fixed minus fixed +7.0 [-4.1, 18.7], pinned never minus full cache -31.0
[-47.4, -16.4], reminder minus never +1.2 [-4.1, 7.6], reminder minus full
cache -18.7 [-29.2, -8.8], symptom minus full cache -7.6 [-17.5, 1.2] and
symptom minus dynamic -1.8 [-11.1, 7.0].

## The pinned arm on the new tasks

Counts are attempts over the 57 tasks.

| Condition | Attempts | Opens with the listing | Rejected login | Wrong arguments | Completed | Context limit | Passed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full cache, two attempts (reference) | 339 | 339 | 22 | 52 | 289 | 21 | 98 |
| AgentKV 50% never (reference) | 320 | 140 | 119 | 145 | 103 | 132 | 33 |
| AgentKV 50% fixed (reference) | 332 | 147 | 49 | 99 | 160 | 116 | 66 |
| AgentKV 50% pinned prompt, never | 316 | 314 | 1 | 32 | 244 | 16 | 10 |
| AgentKV 50% pinned prompt, fixed | 334 | 332 | 9 | 71 | 265 | 22 | 88 |
| AgentKV 50% text reminder | 337 | 149 | 41 | 117 | 159 | 126 | 41 |
| AgentKV 50% symptom trigger | 323 | 142 | 65 | 138 | 142 | 98 | 61 |

The pattern of the first study repeats. With the prompt pinned and no
rebuild, agents open on protocol, log in correctly and complete 244 of 316
attempts, and 10 pass. On the 38 new tasks alone they complete 160 of 211
and 6 pass. A descriptive measure that was not declared: an attempt calls
every app API the task requires in 2 of 316 pinned never attempts, against
28 of 320 never, 42 of 332 fixed, 54 of 334 pinned fixed and 70 of 339
full-cache attempts. The mean share of required APIs called is 42% for
pinned never, 44% for never, 66% for pinned fixed and 70% for the full
cache.

The [first record](a6000-dev19-controls.md) gives the cause: the pinned
prompt is counted inside the 50% budget and the engine compacts after every
128-token chunk, so until the transcript passes 1,393 tokens the cache holds
the prompt and 24 further entries, and the task statement that follows the
prompt is evicted for good. That account is derived from the target rule;
retention of the task statement was not recorded. C1 therefore shows that
this way of pinning removes the rule-breaking and costs the task. It does
not show that a pinned prompt with an undisturbed task statement would fail,
and C2 and C3 show that a rebuild repairs what compacting the first turn
chunk by chunk destroyed, rules in the unpinned arm and the task statement
in the pinned one.

A rebuild on top of the pinned prompt is the strongest compressed arm in the
cohort. It solves 60 of 171 cells and 49 on the first attempt, against 62
and 51 for the full cache and 48 and 36 for the fixed rebuild without
pinning. Its differences from both are unresolved.

## The symptom trigger

| | Attempts rebuilt | First attempts rebuilt | Seconds per rebuild | Share of cell budget |
| --- | --- | --- | ---: | ---: |
| Fixed, 57 tasks | 275 of 332 | 142 of 171 | | |
| Symptom, 57 tasks | 213 of 323 | 115 of 171 | | |
| Fixed, 38 new tasks | 182 of 221 | 95 of 114 | 4.1 | 5.5% |
| Symptom, 38 new tasks | 140 of 213 | 74 of 114 | 3.1 | 3.2% |

The markers were fixed from the first 19 tasks on another device, so the 38
tasks are out of sample for the trigger. There the symptom arm solves 31 of
114 cells, as the fixed arm does, and 20 on the first attempt against 24.

## Prompt and reminder retention

The pinned arms hold all 673 prompt entries at every turn. In the unpinned
arms of the two studies the median first attempt holds 39% of them at its
first action. At the last turn the median is 75% in the symptom arm and 37%
in the reminder arm. The reminder block is 98% retained on the turn after it
is sent and 84% eight turns later. The shortest initial transcript is 3,342
tokens, above the 1,393 the design required.

## Cost

From the shared analyses of the two studies on the 38 new tasks. The last
column covers all 57 tasks.

| Condition | Seconds per rebuild | Share of cell budget | Mean cell latency | Mean peak KV | Decode tokens per second | Attempt-seconds per passing attempt |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full cache, two attempts (reference) | | | 65.7 s | 325 MiB | 27.2 | 118 |
| AgentKV 50% never (reference) | | | 90.4 s | 213 MiB | 25.6 | 471 |
| AgentKV 50% fixed (reference) | 4.1 | 5.5% | 88.7 s | 277 MiB | 25.6 | 229 |
| AgentKV 50% pinned prompt, never | | | 75.9 s | 157 MiB | 23.1 | 1,248 |
| AgentKV 50% pinned prompt, fixed | 3.3 | 5.2% | 84.8 s | 223 MiB | 25.3 | 164 |
| AgentKV 50% text reminder | | | 85.6 s | 205 MiB | 23.3 | 357 |
| AgentKV 50% symptom trigger | 3.1 | 3.2% | 98.7 s | 233 MiB | 22.0 | 274 |

Every requested rebuild was admitted, 219 and 140 on the new tasks, and peak
total VRAM stayed at or below 23.06 GiB. The symptom arm decoded at 22.0
tokens per second against 25.6 for the fixed reference arm, so the
wall-clock budget bought it less work. That bears on C5 and C6.

## Execution

Four condition groups ran on November 15, 2026 from source `0dd8ece` on
node-local storage, were scored offline and analyzed together. The guard did
not trip: the largest rolling ten-cell medians were 1.29 seconds of reset,
1.82 of tool time and 0.11 of trajectory save. Of the 872 attempts, 538
completed, 174 reached the context limit, 145 timed out and 15 ended at the
protocol's failure limit. One cell spent 83.4 seconds in a single tool call.
The compact evidence holds the hashes, digests, comparisons and per-arm
measurements.

## Limits

- The 57 tasks belong to 19 families and the 38 new ones are further
  variants of the first 19. One device type, one model, the dev split.
- The pinned arm without a rebuild is confounded as described. A control
  that pins the prompt without taking the task statement's share has not
  been run, so whether pinning alone suffices is still open.
- Reference and control arms ran from different source pins at different
  times and decoded at different speeds.
- The reminder is one design. A null result does not show that no text
  remedy works.
- Unresolved differences are not evidence of equality.
- These controls are outside the main experiment matrix and the team has not
  reviewed them.
