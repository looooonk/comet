# Controls for the recovery result: decisions and design

Recorded on November 14, 2026, before any execution and before any outcome of
the RTX A6000 cohort was read. Four follow-ups had been held for a team
decision. One contributor then authorized deciding them on best judgment, and
this record states each decision, its reason and the studies it leads to. The
team has not reviewed them. Everything here is exploratory train/dev work
outside the main experiment matrix, as
[exploratory-controls.md](../../exploratory-controls.md) defines.

## Decisions

| Follow-up | Decision |
| --- | --- |
| Protected-prompt control | Run it, with and without the fixed rebuild |
| Text-reminder baseline | Run it, as one verbatim repeat at the fixed trigger |
| Symptom-triggered rebuild | Run it, as a fourth trigger beside never, fixed and dynamic |
| Pre-registered test-split run | Do not run it now |

**Protected prompt.** The [instruction-error reading](dev19-instruction-errors.md)
found that compressed agents break rules stated only in the system prompt and
that a rebuild largely removes this. The pinned AgentKV selector keeps 16
leading entries and R-KV none, so the system turn is evictable. Pinning the
prompt is established practice in the eviction literature, where pinned
entries are counted inside the budget (arXiv 2510.00231, 2607.10582,
2606.09916). Without this control the recovery result may only show that an
unpinned prompt was evicted. With it, the project learns whether a rebuild
restores anything a pinned prompt does not.

**Text reminder.** A rebuild is worth its cost only if it beats re-sending
the instructions as text. System-prompt repetition is the standard text-level
remedy for instruction drift (arXiv 2402.10962). The repeat is verbatim and
happens once, at the step where the fixed policy rebuilds, so it uses the same
trigger and no more knowledge of the failure than the rebuild does. A
condensed list of the rules agents were seen to break would be tuned on the
tasks it is tested on and is not run.

**Symptom trigger.** The proposal's triggers count tokens and tool calls. An
error in a tool observation is direct evidence that something was lost. The
searches found turn-boundary repair of a compressed cache for agents (ICML
2026, "Cache You Later") and an entropy-gated rebuild for diffusion language
models (arXiv 2603.18489), and none that uses tool errors as the trigger. The
markers are the five observation substrings of `comet.instruction_errors`,
fixed on November 14 from the first 19 dev tasks on the Blackwell cohort.

**Test split.** Not now, for three reasons. The settings a held-out run would
freeze are exactly what these controls may change. Fifty test tasks were
already spent on the compression-only grid, and the remaining held-out tasks
are a shared resource the team has not agreed to spend. And 57 dev tasks at
three seeds, analyzed together here, are a better next step in power than one
seed on held-out tasks. A held-out run becomes appropriate once the dev
results below are reported and the team freezes one configuration.

Paper details above were checked at abstract level only.

## What a symptom trigger would have done

Offline, from the saved Blackwell runs of the first 19 dev tasks at seeds 17,
29 and 31, counting attempts whose saved observation text contains a marker.
Saved observations keep only their head and tail, so these are lower bounds.

| Arm | Attempts | With a symptom | First symptom at turn 1 | Median first turn |
| --- | ---: | ---: | ---: | ---: |
| Full cache, two attempts | 114 | 30 | 0 | 5 |
| AgentKV 50% never | 112 | 82 | 28 | 4 |
| R-KV 50% never | 94 | 75 | 40 | 1 |
| StreamingLLM 50% never | 91 | 53 | 17 | 2 |

In the AgentKV never arm, 70 of 96 failed attempts and 12 of 16 passing
attempts show a symptom. A symptom trigger would therefore rebuild about
three attempts in four, a quarter of them after the first turn, and leave the
rest untouched. These tasks informed the markers, so the 19-task results of
the symptom arm are in-sample for the trigger and the 38-task results are not.

## Declared studies

Both keep Qwen3.5-9B, the v4 prompt, sampling, seeds 17, 29 and 31, the
120-second shared budget, two attempts, the 24 GiB cap and the recovery
thresholds of the cohort's reference studies. Retention is 50% throughout.

| Study | Tasks | Conditions | Cells |
| --- | --- | --- | ---: |
| [Controls, first tasks](../../../configs/qwen9b/a6000/dev19-controls-v1.json) | The 19 tasks of the [reference arms](a6000-cohort-design.md) | AgentKV protected never, protected fixed, reminder and symptom; StreamingLLM and R-KV protected never | 342 |
| [Controls, new tasks](../../../configs/qwen9b/a6000/dev38-controls-v1.json) | The 38 tasks of the cohort's confirmation | The four AgentKV conditions | 456 |

The pinned tokenizer gives a system turn of 673 tokens with its delimiters,
identical across tasks, and a reminder block of 682 tokens. At 50% retention
the protected and unprotected targets agree from 1,393 logical tokens for
AgentKV. Initial transcripts in the saved runs are near 3,355 tokens, so every
action should be generated under the same KV count as in the unprotected arm;
the analysis reports the shortest initial transcript to confirm it. Both
studies record `system_prompt_retained` on every turn. Reference outcomes come from the cohort's own never, fixed and
dynamic arms and its full-cache control, produced by source `6164ba9`.

## Hypotheses and analysis

All differences are in oracle success within the 120-second budget, paired by
task and seed within the A6000 cohort, over the 57 dev tasks of both studies.

| | Comparison (AgentKV 50%) | Expectation |
| --- | --- | --- |
| C1 | Protected never minus never | Positive |
| C2 | Fixed minus protected never | None declared |
| C3 | Protected fixed minus protected never | None declared |
| C4 | Fixed minus reminder | None declared |
| C5 | Symptom minus never | Positive |
| C6 | Symptom minus fixed | None declared |

C2 and C3 decide what the project may claim. If protected never matches
fixed and a rebuild adds nothing to it, the recovery result reduces to prompt
eviction and the claim is that pinning suffices. If a rebuild still adds
success with the prompt pinned, the rebuild restores more than instructions.
C4 asks the same of the text remedy.

Each comparison is reported with the shared analysis's paired task bootstrap
and with a 95% interval that resamples whole task families
(`comet.family_bootstrap`, 10,000 draws), unadjusted and with a Holm
adjustment across C1 to C6. A comparison counts as supported only when both
intervals exclude zero, and for C1 and C5 only in the expected direction. An
interval that includes zero is reported as unresolved, not as equivalence.

Reported descriptively, without a criterion:

- The same six comparisons on first-attempt success, and on the 19 and the 38
  tasks separately.
- Protected never minus never for StreamingLLM and R-KV on the 19 tasks.
- Instruction-violation shares by arm with `comet.instruction_errors`.
- `system_prompt_retained` at the first action, at the fixed trigger and at
  the last turn, and `reminder_retained` over the turns after the reminder.
- Rebuilds per attempt, rebuild seconds, reminder tokens, attempts per cell,
  GPU-seconds per solved task, decode throughput and peak KV bytes by arm.
- Every runtime failure and per-cell charged I/O.

Expected size, recorded so it cannot be adjusted afterward: with 57 tasks in
19 families, a difference near 10 points has a family interval of roughly 12
points either side, so several comparisons may stay unresolved.

## Execution

The controls need new code, so they run from a new source pin with its own
managed runtime, qualified with the same live checks as the cohort. The
running and queued studies keep source `6164ba9` and are not touched. A
14-cell smoke run on two tasks precedes the studies and is kept outside them.
It must show that protected arms report `system_prompt_retained` of 1 at every
turn, that the reminder is sent once and only after the fourth tool call, and
that every symptom rebuild follows an observation containing a marker. It also
reruns the unchanged AgentKV never arm and compares its first-attempt token
stream with the reference study's. If the streams differ, comparisons stay
paired by task and seed and any analysis of matched turns is dropped.

Workers, node-local storage, guard limits and the four-worker ceiling are
those of the [cohort design](a6000-cohort-design.md). The two studies run one
after the other, behind the cohort's queued studies. A study the guard stops
is void as a whole.

## Limitations known in advance

- Reference and control arms run at different times and possibly on different
  nodes. Outcomes depend on wall-clock speed, so decode throughput is reported
  by arm.
- One model, one benchmark, 50% retention, and a prompt of one length.
- The reminder is one design among many. A null result does not show that no
  text remedy works.

## Status

Declared. Nothing has run.
