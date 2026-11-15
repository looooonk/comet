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

## Mild compression, where a choice could matter

Added on November 14, 2026, after the [reference arms](a6000-dev19-core.md)
were reported and before any execution of this study or any outcome of a
control arm. The contract's recovery policies decide when to rebuild from
token and tool counts. A policy that decides from the workload whether to
rebuild at all is only worth building where rebuilding is sometimes the wrong
choice, so that was checked first on saved runs.

A rebuilt first attempt and its never-rebuilt twin take the same actions until
the rebuild, which shows what each rebuild changed. Offline, on the first 19
dev tasks at three seeds, counting first attempts out of 57:

| Saved runs | Never | Fixed | Twins reaching the rebuild | Rebuild helped | Rebuild hurt |
| --- | ---: | ---: | ---: | ---: | ---: |
| A6000, AgentKV 50% | 7 | 12 | 48 | 5 | 0 |
| Blackwell, AgentKV 50% | 7 | 16 | 51 | 10 | 1 |
| Blackwell, AgentKV 80% | 17 | 20 | 57 | 7 | 4 |

At 50% retention a perfect choice between the two arms equals always
rebuilding on the A6000 and gains one run on Blackwell, so a predictor has no
room there. At 80% the rebuild hurt in 4 of 11 pairs whose outcomes differ. A
rebuild also changes the rest of the trajectory, so some of those 11 are
chance. This reading is exploratory and used the tasks of every earlier one.

The [declared study](../../../configs/qwen9b/a6000/dev19-retention80-v1.json)
runs AgentKV at 80% retention with no rebuild, the fixed rebuild and the
symptom-triggered rebuild on the same 19 tasks and three seeds, 171 cells,
with the markers, measurement and settings of the controls. It reports, with
the intervals used above and no confirmation criterion:

- Fixed minus never, symptom minus never and symptom minus fixed, in oracle
  and first-attempt success.
- Among first-attempt twins whose outcomes differ, how many the rebuild
  helped and how many it hurt, with an exact binomial interval, beside the
  same counts at 50% from the reference arms.
- Rebuilds per attempt under the fixed and symptom triggers.
- Any rule for choosing between the never and fixed arms from what the runner
  has seen by the rebuild point, scored on these twins with whole task
  families held out.

Expected size, recorded in advance: with 57 pairs a difference near 5 points
has an interval of roughly 12 points either side, and about 11 discordant
pairs cannot separate a 4-to-7 split from an even one. The study can show
whether rebuild harm at mild compression repeats on this device; it cannot
establish a predictor.

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
is void as a whole. The 80% study has three condition groups and runs after
the first controls study, from the same source pin.

## Limitations known in advance

- Reference and control arms run at different times and possibly on different
  nodes. Outcomes depend on wall-clock speed, so decode throughput is reported
  by arm.
- One model, one benchmark, 50% retention, and a prompt of one length.
- The reminder is one design among many. A null result does not show that no
  text remedy works.

## Status

Submitted on November 14, 2026. The runtime for the new source was built from
the same locks: its 118 pinned packages match the reference runtime, and the
staged digests of the cohort's existing studies are unchanged under the new
code. Qualification, the smoke run and the two studies had not finished when
this was written, and no outcome of a control arm exists. The
[reference arms](a6000-dev19-core.md) these controls are compared with were
reported after this design was declared and committed.
