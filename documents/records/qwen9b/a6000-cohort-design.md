# RTX A6000 dev cohort: qualification and declared studies

Declared on November 14, 2026, before any A6000 execution. The dev studies
declared that day were submitted on the qualified RTX PRO 6000 Blackwell
nodes and did not start: the two nodes were fully allocated to their owner
group and the scheduler's estimate for the first worker was a week away. The
[research contract](../../research-direction.md) authorizes alternative
adequately sized GPUs once the device and cap are validated, and keeps
hardware cohorts separate. This record declares an RTX A6000 cohort at the
same 24 GiB cap so the same questions can be answered sooner. It is train/dev
evidence and does not open the test split.

A cohort here is a set of runs on one GPU model that are compared only with
each other. The budget is 120 seconds of wall-clock time, so a different GPU
completes a different amount of work per attempt and success rates are not
comparable across devices. Every arm a comparison needs is therefore run on
the A6000; nothing is paired with or pooled with a Blackwell result.

## Qualification

The pinned source `6164ba9`, managed runtime, model, 16,384-token context and
24 GiB total-VRAM cap are those of the Blackwell dev studies. The
[smoke](../../../configs/qwen9b/a6000/smoke-v1.json) and
[interruption check](../../../configs/qwen9b/a6000/resume-check-v1.json)
configurations change only the device name. One job on an A6000 runs the live
checks of the hybrid qualification script (state, compaction over the
retention grid, recovery, capacity at the cap, AppWorld isolation and tool
effects, environment warm-up and process interruption) and then the four-cell
dev smoke, executed, scored and analyzed in research mode, using the
node-local model, runtime and scratch that study workers use. The studies
below are submitted to start only if that job succeeds. Its evidence is added
here when it has run.

## Declared studies

All three keep Qwen3.5-9B, the v4 prompt, sampling, seeds 17, 29 and 31, the
budget, the attempt ceiling, the cap and the recovery thresholds of their
Blackwell counterparts. Only the device name differs.

| Study | Tasks | Conditions | Cells |
| --- | --- | --- | ---: |
| [Reference arms](../../../configs/qwen9b/a6000/dev19-core-v1.json) | The 19 tasks of the first study | Full cache with two attempts; AgentKV 50% never, fixed and dynamic; never-rebuild arms of R-KV 50%, StreamingLLM 50% and AgentKV 25% | 399 |
| [Rebuild before the first action](../../../configs/qwen9b/a6000/dev19-prefill-v1.json) | The same 19 tasks | AgentKV, R-KV and StreamingLLM at 50% and AgentKV at 25%, rebuilt at the first trigger check | 228 |
| [Confirmation](../../../configs/qwen9b/a6000/dev38-recovery-v1.json) | The 38 dev tasks the first study did not use | Full cache with two attempts; AgentKV 50% never, fixed and dynamic | 456 |

The confirmation carries the hypotheses H1 to H5 and M1 and M2 of the
[thirty-eight-task design](dev38-recovery-design.md) unchanged, with the same
intervals and confirmation rule, evaluated within this cohort. The prefill
study carries the expectations recorded in the
[first study's design](dev19-recovery-design.md#rebuild-before-the-first-action),
compared with this cohort's own never-rebuild arms. The reference arms also
show whether the 19-task recovery result appears on this device at all, which
is needed to read a confirmation that fails.

The Blackwell submissions stay queued. If they run, each cohort is analyzed
and reported on its own, and both are reported. Two cohorts are two attempts
at the same hypotheses; a hypothesis confirmed in one and not the other is
reported as such, not as confirmed. Earlier A6000 work in this project was a
state check at another source revision and is not reused.

## Execution

Workers use the node-local run directory, AppWorld root, runtime and model
declared for the Blackwell studies, with automatic requeue disabled and the
same guard limits on charged reset, save and tool time. At most four workers
run per study, and the reference arms and the prefill study may run at the
same time on separate GPUs; the confirmation follows the reference arms. The
prefill study is preceded by its own two-cell smoke run, kept outside the
studies, because a rebuild on an empty cache has not been exercised before.
Each study is scored after its workers finish and analyzed through the shared
analysis on its own. A study the guard stops is void as a whole.

## Status

Declared; qualification submitted, not yet executed.
