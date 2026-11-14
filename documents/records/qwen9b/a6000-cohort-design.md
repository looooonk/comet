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
below are submitted to start only if that job succeeds.

The job ran on November 14, 2026 and passed in 23 minutes. All 24 live checks
passed, 23 in process and the process-interruption check, with none skipped.
The numerical reference matched (logit cosine 0.9993, top-10 overlap 1.0),
the 24 method and retention combinations kept their targets, full cache and
rebuilds at the 16,384-token limit peaked at 23.05 GiB under the 24 GiB cap,
a request beyond the cap was refused, and the three recovery branches left
tool effects and random state unchanged. The four-cell dev smoke then ran,
was scored and analyzed; its one task was unsolved under all four conditions,
which is integration evidence only. Decode throughput in the smoke was 21 to
25 tokens per second, so this cohort completes less work per 120-second
budget than the Blackwell cohort. The [compact evidence](validation/a6000-cap24.json)
has the identifiers and hashes.

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

## Retry curve

Declared on November 14, 2026, before any A6000 study has executed. The
project's question is whether, under a fixed budget, it is better to rebuild a
compressed cache or to keep it compressed and spend the budget on more
attempts. An exploratory reading of the Blackwell runs, taking first attempts
at seeds 17, 29 and 31 as independent retries, gave AgentKV at 50% retention
12%, 18% and 21% for the best of one, two and three attempts without a
rebuild, against 28% for one attempt with the fixed rebuild, 33% with the
dynamic rebuild and 35% for one full-cache attempt. Three seeds cannot show
where a retry curve levels off.

The [configuration](../../../configs/qwen9b/a6000/dev19-retry-v1.json) runs
single attempts of full cache and of AgentKV at 50% retention under never,
fixed and dynamic recovery on the 19 first-study tasks at five further seeds
(37, 41, 43, 47 and 53): 380 fresh-start cells in
[four condition groups](../../../configs/qwen9b/a6000/dev19-retry-v1-parts/).
An attempt's sampling seed depends only on the cell seed and the attempt
index, so with the first attempts of the reference arms this gives eight
independent attempts per task and arm, each with its own 120-second budget.

Analysis, recorded before execution. For each arm and each k from 1 to 8,
success is the share of tasks solved by at least one of k attempts, averaged
over every choice of k seeds, with paired task-bootstrap intervals. This is a
perfect-selection upper bound and favours retrying. Three comparisons are
read at equal occupied KV, taking two 50% attempts as one full-cache attempt
and a rebuilt attempt at its full-size peak: one full-cache attempt, two
never-rebuild attempts and one rebuilt attempt; then two, four and two; then
four, eight and four. Mean seconds per attempt, occupied KV and total VRAM
are reported beside them, because in the runs so far compression freed under
100 MiB of a 24 GiB cap and did not shorten attempts. Expectations: one
rebuilt attempt is at least as good as the best of two never-rebuild
attempts, and the never-rebuild curve stays below one full-cache attempt
through k = 8. Both are reported whether or not they hold. This study varies
the number of independent attempts; it does not run attempts concurrently,
which would need an engine change and a research decision.

## Execution

Workers use the node-local run directory, AppWorld root, runtime and model
declared for the Blackwell studies, with automatic requeue disabled and the
same guard limits on charged reset, save and tool time. At most four workers
run per study, and the reference arms and the prefill study may run at the
same time on separate GPUs; the confirmation follows the reference arms and
the retry curve follows the prefill study. The
prefill study is preceded by its own two-cell smoke run, kept outside the
studies, because a rebuild on an empty cache has not been exercised before.
Each study is scored after its workers finish and analyzed through the shared
analysis on its own. A study the guard stops is void as a whole.

## Status

Qualified on November 14, 2026. The prefill smoke rebuilt all four of its
attempts at the first trigger check, in 1.6 to 3.3 seconds, with no later
rebuild, and its saved environments were scored. The reference arms started
at 17:04 and the prefill study at 18:41 the same day; the confirmation and
the retry curve are queued behind them. No study result is reported yet.
