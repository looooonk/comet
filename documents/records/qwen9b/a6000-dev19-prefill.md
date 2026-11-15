# Qwen3.5-9B on the RTX A6000: one compaction after the whole first turn

Compacting the first turn once, after all of it has been read, instead of
after every 128-token chunk, removes most of the damage of 50% retention. On
the RTX A6000 cohort over seeds 17, 29 and 31, AgentKV at 50% then opens every
one of its 112 attempts with the prescribed listing call, against 52 of 104
without it, has a login rejected in 2 attempts against 37, and solves 21 of
57 task-seed cells against 10. Full cache with two attempts solves 20. AgentKV
at 25% goes from 0 to 7 cells and R-KV at 50% from 0 to 6. StreamingLLM still
solves nothing and never opens with the listing.

The only change is when the single allowed rebuild happens: at the first
trigger check, before any action. Later turns are compacted chunk by chunk as
usual. The expectations were
[recorded before execution](dev19-recovery-design.md#rebuild-before-the-first-action).
These are the 19 tasks that produced the hypothesis, so this is train/dev
evidence on in-sample tasks, and the intervals are unadjusted.

[Compact evidence](a6000-dev19-prefill.json) |
[Reference arms](a6000-dev19-core.md) |
[Cohort design](a6000-cohort-design.md) |
[Instruction-error reading](dev19-instruction-errors.md)

## Outcomes

The [declared configuration](../../../configs/qwen9b/a6000/dev19-prefill-v1.json)
ran unchanged: four conditions, 19 tasks, three seeds, 228 cells and 420
attempts. Never-rebuild rows are the cohort's
[reference arms](a6000-dev19-core.md) for the same tasks and seeds. Counts are
task-seed cells out of 57.

| Condition | Oracle | First attempt | Oracle by seed | Attempts opening with the listing | Attempts with a rejected login |
| --- | ---: | ---: | --- | --- | ---: |
| AgentKV 50%, compacted once first | 21 | 15 | 7, 6, 8 | 112 of 112 | 2 |
| AgentKV 50%, never rebuilt | 10 | 7 | 2, 5, 3 | 52 of 104 | 37 |
| R-KV 50%, compacted once first | 6 | 6 | 2, 2, 2 | 94 of 99 | 4 |
| R-KV 50%, never rebuilt | 0 | 0 | 0, 0, 0 | 25 of 89 | 5 |
| StreamingLLM 50%, compacted once first | 0 | 0 | 0, 0, 0 | 0 of 99 | 7 |
| StreamingLLM 50%, never rebuilt | 0 | 0 | 0, 0, 0 | 0 of 85 | 0 |
| AgentKV 25%, compacted once first | 7 | 5 | 1, 3, 3 | 107 of 107 | 16 |
| AgentKV 25%, never rebuilt | 0 | 0 | 0, 0, 0 | 0 of 95 | 12 |

For reference on the same cells: AgentKV 50% with the fixed trigger solves 17
and with the dynamic trigger 20, and both open with the listing in about half
of their attempts, as the never arm does, because their rebuild comes after
the first action.

## Paired differences

Percentage points over three seeds, paired by task and seed. The arms come
from two studies, so the task interval applies the shared analysis's bootstrap
to per-task differences (10,000 draws); the second interval resamples task
families.

| Comparison | Metric | Difference | Task interval | Family interval |
| --- | --- | ---: | --- | --- |
| AgentKV 50%: once first minus never | Oracle | +19.3 | [7.0, 33.3] | [7.0, 33.3] |
| AgentKV 50%: once first minus never | First attempt | +14.0 | [1.8, 28.1] | [1.8, 29.8] |
| R-KV 50%: once first minus never | Oracle | +10.5 | [1.8, 22.8] | [1.8, 22.8] |
| AgentKV 25%: once first minus never | Oracle | +12.3 | [1.8, 24.6] | [1.8, 24.6] |
| AgentKV 50%: once first minus fixed | Oracle | +7.0 | [-3.5, 21.1] | [-3.5, 21.1] |
| AgentKV 50%: once first minus dynamic | Oracle | +1.8 | [-14.0, 17.5] | [-14.0, 17.5] |
| AgentKV 50%: once first minus full cache | Oracle | +1.8 | [-10.5, 17.5] | [-10.5, 17.5] |

Compacting once first is not distinguishable from the later rebuilds or from
full cache at this size. An interval that includes zero does not show
equivalence.

## Against the recorded expectations

- **Listing and logins.** Expected: AgentKV 50% and R-KV 50% open with the
  listing in clearly more attempts than their never arms, and AgentKV 50% has
  fewer rejected logins. Observed: 112 of 112 against 52 of 104, 94 of 99
  against 25 of 89, and 2 attempts against 37.
- **StreamingLLM.** It keeps the same positions either way. It still never
  opens with the listing and solves nothing, so for this method what matters
  is which entries are kept, not what they had seen when computed.
- **AgentKV 25%.** A single selection is enough for every attempt to open with
  the listing at a retention where none did, and 7 cells are solved.
- **Tasks solved.** Expected: at least as well as a later rebuild. Observed:
  21 against 17 and 20, within the intervals above.

## Attempts and failures

| Condition | Completed | Context limit | Timeout | Protocol error |
| --- | ---: | ---: | ---: | ---: |
| AgentKV 50%, compacted once first | 95 | 5 | 9 | 3 |
| AgentKV 50%, never rebuilt | 33 | 44 | 22 | 5 |
| R-KV 50%, compacted once first | 37 | 15 | 44 | 3 |
| StreamingLLM 50%, compacted once first | 15 | 1 | 37 | 49 |
| AgentKV 25%, compacted once first | 36 | 18 | 14 | 39 |

AgentKV at 50% reaches the transcript limit in 5 attempts instead of 44. Every
attempt was rebuilt at the first check, before any tool call, and none was
rebuilt again. The median rebuild time charged to a cell is 3.0 seconds.

## Execution

Four condition groups ran on November 14, 2026 from source `6164ba9` on
node-local storage, after a two-cell smoke run, and were scored offline. The
guard did not trip: the largest rolling ten-cell medians were 1.31 seconds of
reset, 1.25 of tool time and 0.14 of trajectory save. One cell spent 101.9
seconds in a single tool call. The compact evidence holds hashes, digests,
attempt statuses and per-arm counts.

## What this does and does not show

- Evicting chunk by chunk while the first turn is read is what removes the
  prompt's rules for AgentKV and R-KV here. Selecting once, with the whole
  turn visible, keeps what the agent needs at the same retention.
- It does not show that a rebuild is needed. The repair is a change in when
  the first compaction happens, not a recovery from a later failure.
- It does not separate a protected prompt from a better first selection. The
  [controls](a6000-controls-design.md) do.
- Nineteen in-sample tasks, three seeds, one model, one device.
