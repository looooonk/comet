# Qwen3.5-9B on the RTX A6000: controls on the first 19 tasks

This is the first of the two controls studies. The declared primary analysis
covers 57 tasks and waits for the second study; the design reports the
19-task part descriptively, and that is what follows.

Pinning the system prompt stopped the rule-breaking and lowered success.
AgentKV at 50% retention with the prompt pinned and no rebuild solves 4 of 57
task-seed cells against 10 without pinning, the reverse of the declared
expectation. Its agents open on protocol, log in correctly, finish, report
success and fail: 84 of 105 attempts complete and 4 pass. The cause, found
after the run, is in the design: the pinned prompt is counted inside the 50%
budget, so while the first turn is read the task statement that follows the
prompt is left almost no room. This arm therefore does not test whether a
pinned prompt is enough.

The other controls read more simply on these tasks. A rebuild on top of the
pinned prompt solves 19 of 57. Re-sending the prompt as text solves 10, the
same as doing nothing, and the fixed rebuild beats it by +12.3 points
[3.5, 21.1]. A rebuild triggered by an error in a tool observation solves 18,
level with the fixed trigger's 17, with 73 rebuilds against 93.

[Compact evidence](a6000-dev19-controls.json) |
[Declared design](a6000-controls-design.md) |
[Definition of the controls](../../exploratory-controls.md) |
[Reference arms](a6000-dev19-core.md)

## Outcomes

The [declared configuration](../../../configs/qwen9b/a6000/dev19-controls-v1.json)
ran unchanged: six conditions, 19 tasks, seeds 17, 29 and 31, 342 cells and
657 attempts. Reference rows come from the cohort's
[reference arms](a6000-dev19-core.md). Counts are cells out of 57.

| Condition | Oracle | First attempt | Attempts | Passing attempts | Attempts rebuilt |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full cache, two attempts (reference) | 20 | 16 | 113 | 31 | 0 |
| AgentKV 50% never (reference) | 10 | 7 | 104 | 13 | 0 |
| AgentKV 50% fixed (reference) | 17 | 12 | 111 | 23 | 93 |
| AgentKV 50% dynamic (reference) | 20 | 15 | 111 | 25 | 91 |
| AgentKV 50% pinned prompt, never | 4 | 3 | 105 | 4 | 0 |
| AgentKV 50% pinned prompt, fixed | 19 | 15 | 112 | 25 | 112 |
| AgentKV 50% text reminder | 10 | 8 | 111 | 15 | 0 |
| AgentKV 50% symptom trigger | 18 | 13 | 110 | 23 | 73 |
| StreamingLLM 50% pinned prompt, never | 0 | 0 | 112 | 0 | 0 |
| R-KV 50% pinned prompt, never | 1 | 0 | 107 | 1 | 0 |

The reminder was sent in 96 of 111 attempts, once each, as 682 tokens.

## The six comparisons on these 19 tasks

Differences are in percentage points, paired by task and seed, with the
paired task bootstrap and the family interval (10,000 draws). The Holm
p-values adjust across the six within this part only; the declared adjustment
belongs to the 57-task analysis.

| | Comparison | Oracle difference | Task interval | Family interval | Holm p | First-attempt difference |
| --- | --- | ---: | --- | --- | ---: | --- |
| C1 | Pinned never minus never | -10.5 | [-24.6, 0.0] | [-24.6, 0.0] | 0.212 | -7.0 [-21.1, 3.5] |
| C2 | Fixed minus pinned never | +22.8 | [7.0, 40.4] | [8.8, 40.4] | 0.009 | +15.8 [0.0, 33.3] |
| C3 | Pinned fixed minus pinned never | +26.3 | [8.8, 45.6] | [8.8, 45.6] | 0.007 | +21.1 [8.8, 35.1] |
| C4 | Fixed minus reminder | +12.3 | [5.3, 21.1] | [3.5, 21.1] | 0.007 | +7.0 [0.0, 15.8] |
| C5 | Symptom minus never | +14.0 | [3.5, 26.3] | [3.5, 26.3] | 0.039 | +10.5 [3.5, 19.3] |
| C6 | Symptom minus fixed | +1.8 | [-7.0, 10.5] | [-7.0, 10.5] | 0.844 | +1.8 [-5.3, 8.8] |

C1 expected a positive difference and found a negative one whose interval
reaches zero. C5 expected a positive difference and found one. The other
declared descriptive comparisons, in oracle success: pinned fixed minus fixed
+3.5 [-12.3, 21.1], pinned fixed minus full cache -1.8 [-14.0, 12.3], pinned
never minus full cache -28.1 [-43.9, -14.0], reminder minus never 0.0
[-10.5, 10.5], symptom minus full cache -3.5 [-14.0, 7.0] and symptom minus
dynamic -3.5 [-19.3, 10.5]. Pinning changes StreamingLLM by 0.0 and R-KV by
+1.8 [0.0, 5.3].

## What pinning changed

Counts are attempts.

| Condition | Attempts | Opens with the listing | Rejected login | Wrong arguments | Completed | Context limit | Passed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full cache, two attempts (reference) | 113 | 113 | 10 | 19 | 94 | 7 | 31 |
| AgentKV 50% never (reference) | 104 | 52 | 37 | 43 | 33 | 44 | 13 |
| AgentKV 50% fixed (reference) | 111 | 58 | 19 | 32 | 55 | 37 | 23 |
| AgentKV 50% pinned prompt, never | 105 | 104 | 1 | 9 | 84 | 5 | 4 |
| AgentKV 50% pinned prompt, fixed | 112 | 112 | 3 | 24 | 89 | 4 | 25 |
| AgentKV 50% text reminder | 111 | 57 | 17 | 36 | 52 | 42 | 15 |
| AgentKV 50% symptom trigger | 110 | 58 | 27 | 42 | 47 | 37 | 23 |
| StreamingLLM 50% pinned prompt, never | 112 | 111 | 0 | 37 | 100 | 7 | 0 |
| R-KV 50% pinned prompt, never | 107 | 106 | 0 | 19 | 87 | 1 | 1 |

With the prompt pinned, every method follows the opening rule and the login
rules, stops overrunning the context and completes. Without it, StreamingLLM
completed none of 86 attempts and R-KV 7 of 91. So prompt eviction explains
the rule-breaking. It does not explain the failures: the pinned arms without
a rebuild complete and still pass 4, 0 and 1 times.

They complete something other than the task. In the saved trajectories a
pinned-prompt agent asked to send $91 on Venmo to a phone number logs in to
the phone app, sends "Hello" to one contact and reports success; asked for a
count of likes it answers with a total amount. A descriptive measure that was
not declared: the share of a task's required app APIs that an attempt calls
is 71% under full cache, 48% for never, 41% for pinned never and 67% for
pinned fixed. An attempt calls every required API in 24 of 113 full-cache
attempts, 14 of 104 never attempts, 17 of 112 pinned fixed attempts and none
of the 105 pinned never, 112 StreamingLLM or 107 R-KV pinned attempts.

## Why the pinned arm loses the task

The first user turn is a JSON object that begins with the task instruction,
followed by the supervisor profile, the date, the app descriptions and two
API documents. The engine compacts after every 128-token chunk while that
turn is read, to `max(ceil(0.5 n), p + 24)` entries at `n` tokens with a
pinned prefix of `p` = 673, and an evicted entry does not return without a
rebuild.

| Tokens read | Entries allowed in all | Left for everything after the prompt | Tokens after the prompt so far |
| ---: | ---: | ---: | ---: |
| 768 | 697 | 24 | 95 |
| 896 | 697 | 24 | 223 |
| 1,024 | 697 | 24 | 351 |
| 1,280 | 697 | 24 | 607 |
| 1,408 | 704 | 31 | 735 |
| 2,048 | 1,024 | 351 | 1,375 |
| 3,343 | 1,672 | 999 | 2,670 |

Until the transcript passes 1,393 tokens the budget is the prompt plus 24
entries, so at most 24 entries survive from the first 607 tokens after the
prompt, where the instruction is. Without pinning the same steps keep half of
everything, prompt and instruction alike. The design noted that the two
targets agree from 1,393 tokens and did not consider that what is evicted
before that point stays evicted. This account follows from the target rule
and matches the behavior; retention of the instruction itself was not
recorded, so it is derived, not measured. A fixed rebuild re-reads the whole
transcript without compaction and then selects once with everything visible,
which is why pinned fixed recovers.

Recorded prompt retention: the pinned arms hold all 673 prompt entries at
every turn. In the unpinned arms of this study the median first attempt holds
39% of them at its first action. In the symptom arm the median is 76% at the
last turn. The reminder block is 98% retained on the turn after it is sent
and 85% eight turns later.

## Cost

| Condition | Seconds per rebuild | Share of cell budget | Mean cell latency | Mean peak KV | Decode tokens per second |
| --- | ---: | ---: | ---: | ---: | ---: |
| AgentKV 50% pinned prompt, never | | | 67.2 s | 156 MiB | 25.9 |
| AgentKV 50% pinned prompt, fixed | 3.2 | 5.2% | 83.1 s | 218 MiB | 25.9 |
| AgentKV 50% text reminder | | | 85.7 s | 212 MiB | 25.2 |
| AgentKV 50% symptom trigger | 3.1 | 3.3% | 96.2 s | 247 MiB | 25.1 |
| StreamingLLM 50% pinned prompt, never | | | 49.7 s | 187 MiB | 26.9 |
| R-KV 50% pinned prompt, never | | | 63.7 s | 153 MiB | 17.5 |

The reference arms decoded at 24.6 to 26.3 tokens per second and the fixed
reference arm spent 5.3% of its cell budget on rebuilds. The shortest initial
transcript is 3,343 tokens, above the 1,393 the design required. Every
requested rebuild was admitted and peak total VRAM stayed at or below
23.06 GiB.

## Execution

Four condition groups ran on November 15, 2026 from source `0dd8ece` on
node-local storage, were scored offline and analyzed together. The guard did
not trip: the largest rolling ten-cell medians were 1.18 seconds of reset,
1.64 of tool time and 0.12 of trajectory save. Of the 657 attempts, 459
completed, 96 reached the context limit, 86 timed out and 16 ended at the
protocol's failure limit. One cell spent 97.8 seconds in a single tool call.
The compact evidence holds the hashes, digests, comparisons and per-arm
measurements.

## Limits

- Nineteen tasks, in-sample for the symptom markers and for every earlier
  reading. The 38 new tasks are running.
- The pinned-prompt arm without a rebuild is confounded as described. A
  control that also keeps the task statement, or that compacts the first turn
  once with the prompt pinned, has not been run.
- Reference and control arms ran from different source pins at different
  times on the same device type.
- The reminder is one design. A null result does not show that no text
  remedy works.
- These controls are outside the main experiment matrix and the team has not
  reviewed them.
