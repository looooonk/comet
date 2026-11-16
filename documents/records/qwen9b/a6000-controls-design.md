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

## The protected-prompt control, corrected

Added on November 15, 2026, after the
[57-task analysis](a6000-dev57-controls.md) was reported and before any
execution of the studies below. One contributor authorized it and the team has
not reviewed it.

C1 could not test whether a pinned prompt is enough. The protected arm counted
the prompt inside the budget, so it kept only 24 entries of everything else
until the transcript passed 1,393 tokens, and the task instruction is the
first thing after the prompt. Two additions, defined in
[exploratory-controls.md](../../exploratory-controls.md), address this:

- `prompt_outside_budget` applies the retention fraction to the tokens after
  the system turn and adds the system turn's entries to the target. The later
  tokens then keep half their entries at every length. In the unpinned 50%
  arms the prompt holds a median 39% of its entries at the first action,
  which leaves the later tokens about 53% of theirs.
- The measurement also records `task_statement_retained`, the share of the
  task instruction's entries still cached when each action is generated.

An arm with the option holds more entries than a 50% arm: about 337 more per
layer and head, which is 60% of a 3,355-token transcript. A gain over the 50%
arms could therefore come from the extra entries and not from pinning. A
third arm stores the same number of entries with nothing pinned and separates
the two.

| Study | Tasks | Conditions | Cells |
| --- | --- | --- | ---: |
| [Prompt budget, first tasks](../../../configs/qwen9b/a6000/dev19-prompt-budget-v1.json) | The 19 tasks of the reference arms | Prompt pinned outside the budget with no rebuild and with the fixed rebuild; the same entry count with nothing pinned and no rebuild | 171 |
| [Prompt budget, new tasks](../../../configs/qwen9b/a6000/dev38-prompt-budget-v1.json) | The 38 tasks of the confirmation | The same three conditions | 342 |

Model, prompt, sampling, seeds, budget, attempts, cap, thresholds, markers and
measurement are those of the controls studies. Reference outcomes are the
cohort's never, fixed and full-cache arms from source `6164ba9` and the two
protected arms from source `0dd8ece`.

All differences are in oracle success within the 120-second budget, paired by
task and seed within the A6000 cohort, over the 57 dev tasks.

| | Comparison (AgentKV, 50% of the tokens after the prompt) | Expectation |
| --- | --- | --- |
| D1 | Pinned outside the budget, no rebuild, minus the same entry count unpinned | Positive |
| D2 | Pinned outside the budget, no rebuild, minus never | Positive |
| D3 | Pinned outside the budget, fixed rebuild minus no rebuild | None declared |
| D4 | Fixed minus pinned outside the budget, no rebuild | None declared |
| D5 | Same entry count unpinned minus never | None declared |
| D6 | Pinned outside the budget, no rebuild, minus full cache | None declared |

D1 and D3 decide the reading. If D1 is supported and D3 is not, a prompt that
stays cached does most of what the rebuild does and the recovery result is
largely prompt eviction. If D3 is supported, a rebuild restores more than a
pinned prompt and an intact share of the later tokens. D5 shows what the
extra entries alone buy. A positive D2 without a positive D1 is attributable
to them and not to pinning.

Intervals and criteria are those of C1 to C6: the paired task bootstrap and
the family bootstrap at 10,000 draws, a Holm adjustment across D1 to D6,
support only when both intervals exclude zero, and for D1 and D2 only in the
expected direction. An interval that includes zero is unresolved, not
equivalence. In particular, an unresolved D3 does not show that a rebuild adds
nothing.

Reported descriptively, without a criterion:

- The six comparisons on first-attempt success, and on the 19 and the 38
  tasks separately.
- Each new pinned arm against its inside-budget counterpart, which solved 9
  and 60 of 171 cells.
- `task_statement_retained` and `system_prompt_retained` at the first action,
  at the fixed trigger and at the last turn, by arm.
- Entries held against the nominal 50% at the end of each attempt, and peak
  KV bytes by arm.
- How attempts open, rejected logins, completed attempts and required-API
  coverage, as in the 57-task record.
- Rebuilds per attempt, rebuild seconds, attempts per cell, decode throughput,
  every runtime failure and per-cell charged I/O.

Expected size, recorded so it cannot be adjusted afterward: family intervals
in the 57-task analysis were 6 to 16 points either side, so a difference
under about 8 points is likely to stay unresolved.

The new code runs from a third source pin with its own managed runtime,
qualified with the same live checks. A 10-cell
[smoke run](../../../configs/qwen9b/a6000/prompt-budget-smoke-v1.json) on two
tasks precedes the studies and is kept outside them. It runs the unchanged
never arm, the inside-budget protected arm and the three new arms, and must
show that:

- both pinned accountings report `system_prompt_retained` of 1 at every turn;
- the retention target recorded at the end of every attempt is
  $p + \lceil (n - p) / 2 \rceil$ in the three new arms, for a transcript
  of $n$ tokens and the prompt's $p$, and $\lceil n / 2 \rceil$ in the
  other two;
- every turn records `task_statement_retained`, and the measured span decodes
  to the task's instruction to within one token at each end.

It also compares the unchanged arm's first-attempt token stream with the
reference study and reports `task_statement_retained` at the first action in
all five arms, neither as a gate. That is the only measurement of the
confound on the two earlier arms: two tasks, a check of the mechanism and not
a result. The two studies run one after the other with three workers each,
node-local storage and the cohort's guard limits. A study the guard stops is
void as a whole.

Known in advance:

- The new arms hold more entries than every 50% arm they are compared with.
  Only D1 is free of that difference.
- They run from a later source and at a later time than the reference arms,
  so decode throughput is reported by arm.
- The reference arms carry no statement measurement.
- The 38 tasks are variants of the 19 task families.

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
code. Qualification passed the same day: 55 in-process checks, which include
the control checks against the installed selectors, and the
process-interruption check. The [reference arms](a6000-dev19-core.md) these
controls are compared with were reported after this design was declared and
committed.

The 14-cell smoke run met the three declared conditions. All 15 attempts of
protected arms report `system_prompt_retained` of 1 at every turn, with a
protected prefix of 673 tokens. Each of the three reminder attempts received
one reminder of 682 tokens, on the turn of its fourth tool call. Each of the
four symptom rebuilds was decided at the check after the first observation
containing a marker.

The smoke check job still exited with a failure, which cancelled the queued
studies before any cell started. Its script also failed on any attempt that
ended in an error, and one StreamingLLM attempt ended at the agent protocol's
limit of four consecutive failures. That is an ordinary attempt outcome the
declared conditions do not cover. The script now fails only on infeasible
attempts and on errors other than that limit. The first report is kept beside
the run, the corrected check passed when read against the saved run, and the
check and the studies were resubmitted. The resubmitted job passed. It also
scored the 14 cells, ran the shared analysis on control arms and exported all
287 turns with their retention measurement.

Of the two unchanged cells, one matched the reference study token for token
through 11,322 tokens. The other matched through 6,855 tokens and twelve turns
of identical model responses, then differed in a tool observation that
printed the same eight values in another order. The new source reproduced the
model's behavior in both. Tool output order is therefore a source of
divergence between twins that does not come from the model. As declared, no
analysis of matched turns across the two sources is used.

The first controls study ran on November 15, 2026 without a guard trip and
its 19-task part is [reported](a6000-dev19-controls.md). That record also
identifies a confound this design did not foresee. The pinned prompt is
counted inside the budget and the engine compacts after every 128-token
chunk, so until the transcript passes 1,393 tokens the pinned arm keeps the
prompt and 24 further entries. The task instruction is the first thing after
the prompt and what is evicted there does not return without a rebuild. The
statement above that the targets agree from 1,393 tokens is correct and does
not cover this. C1 as run therefore does not test whether a pinned prompt is
enough, and the second study carries the same arm. Smoke outcomes are not
results.

The 80% study ran on November 15, 2026 without a guard trip and is
[reported](a6000-dev19-retention80.md). It found 5 first-attempt twin pairs
with different outcomes where about 11 were expected, 3 helped and 2 hurt by
the rebuild, and no choice rule distinguishable from always or never
rebuilding.

The second controls study ran on November 15, 2026 without a guard trip, and
the declared analysis over the 57 tasks is
[reported](a6000-dev57-controls.md). C2, C3, C4 and C5 are supported after
the Holm adjustment and C6 is unresolved. C1 found a negative difference
where a positive one was expected, with the confound above repeating on the
new tasks, so whether a pinned prompt alone suffices is still open.

The corrected protected-prompt control was submitted on November 15, 2026
from source `c49fb91`. Before submission the statement lookup was checked
with the pinned tokenizer and chat template on the saved first transcripts of
the 19 first tasks, without a GPU. Every span starts ten tokens after the
673-token system turn, covers 12 to 60 tokens and decodes to the task's
instruction less its closing punctuation, and a lookup takes 7 ms. Each
instruction therefore ends by token 743, inside the stretch where the
inside-budget arm kept 24 entries of all later tokens. No cell of the smoke
run or the studies had started when this was recorded.

Setup, qualification and the smoke run passed the same evening. The runtime's
118 pinned packages match the reference runtime, and the staged digests of
the seven earlier A6000 studies are unchanged under the new source.
Qualification ran 69 in-process checks, which include the new target and
measurement checks against the installed selectors, and the
process-interruption check.

The 10-cell smoke run met the three declared conditions on all 18 attempts.
Both pinned accountings report `system_prompt_retained` of 1 at every turn.
Every recorded target equals the declared rule and every completed attempt
holds exactly its target, which for the new arms is 53% to 55% of the final
transcript. Every turn records `task_statement_retained`, and each span
decodes to its task's instruction.

Share of the task instruction still cached at the first action, on the two
smoke tasks:

| Arm | First task | Second task |
| --- | ---: | ---: |
| Unpinned, 50% | 67% | 86% |
| Pinned inside the budget | 6% | 19% |
| Pinned outside the budget | 52% | 79% |
| Same entry count, unpinned | 78% | 96% |

This is the first measurement of the confound. The inside-budget arm had
lost most of the instruction before its first action, and the share did not
change afterward. Counting the prompt outside the budget keeps most of the
instruction, though less than the unpinned arms keep. It is two tasks, a
check of the mechanism and not a result.

Of the two unchanged cells, one matched the reference study token for token
through 11,322 tokens. The other matched through 6,855 tokens and then
differed in a tool observation that printed the same values in another
order, as in the controls smoke. Smoke outcomes are not results. The first
study started once the check passed.
