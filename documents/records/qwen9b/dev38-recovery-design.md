# Thirty-eight-task dev confirmation of recovery at 50% retention

Declared on November 14, 2026, before any execution. The
[nineteen-family study](dev19-recovery.md) and its seed replicate found that one
rebuild raises AgentKV's success at 50% retention, by +21.1 points at seed 17
and +10.5 [-5.3, +28.9] at seeds 29 and 31. Three of the 19 tasks carry most of
that gain in every seed, so more seeds on the same tasks cannot settle it. The
[research contract](../../research-direction.md) asks for a finding to be
confirmed on separate dev coverage before any test setting is frozen. This
study is that confirmation. It is train/dev evidence: it does not open the test
split, change a frozen configuration or tune a threshold.

## Declared comparison

The [configuration](../../../configs/qwen9b/blackwell/dev38-recovery-v1.json)
extends the first study and changes only the task list, the seeds and the
condition list. Qwen3.5-9B, the pinned hybrid BF16 backend, the v4 prompt,
sampling, the 16,384-token context, the 120-second budget shared by at most two
sequential attempts, the 24 GiB total-VRAM cap and the recovery thresholds
(fixed after 4 tool calls; dynamic at 6,144 context tokens and 3 tool calls)
are inherited unchanged.

Tasks are the 38 dev tasks the first study did not use: the two remaining
variants of each of its 19 families. The [selection record](dev38-recovery-selection.json)
lists them. No task is chosen or dropped by outcome. `396c5a2_1` and
`4ec8de5_1` were used by the two-task dev confirmation and stay in the sample,
flagged.

The four conditions are the first study's own, verbatim: full cache with two
attempts, and AgentKV at 50% retention under never, fixed and dynamic recovery.
Seeds are 17, 29 and 31, the seeds of the first study and its replicate. With
38 tasks there are 456 fresh-start cells in
[four condition groups](../../../configs/qwen9b/blackwell/dev38-recovery-v1-parts/)
of 114 cells, at most 3h48m of cell budgets each. R-KV, StreamingLLM and the
80% and 25% retentions are omitted to bound the study; the first study and
replicate cover them on 19 tasks. The single-attempt full-cache control is
omitted because the first attempt of the two-attempt control stands in for it:
in the first study and replicate the two received the same score in 57 of 57
task-seed pairs and took identical actions in 56.

## Hypotheses and analysis

Recorded before execution. All differences are in success within the
120-second budget, paired by task and seed, on the 38 new tasks.

| | Comparison | Metric |
| --- | --- | --- |
| H1 (primary) | AgentKV 50% fixed minus never | Oracle success |
| H2 | AgentKV 50% dynamic minus never | Oracle success |
| H3 | AgentKV 50% fixed minus never | First-attempt success |
| H4 | AgentKV 50% dynamic minus never | First-attempt success |
| H5 | AgentKV 50% never minus full cache with two attempts | Oracle success |

H1 to H4 expect a positive difference and H5 a negative one. The 19-task
estimates they come from are +14.0, +14.0, +15.8, +21.1 and -17.5 points over
three seeds.

Score the four groups offline after execution and analyze them together
through the ordinary shared analysis, which bootstraps tasks with their paired
seeds. Variants of one family share a template, so tasks within a family are
not independent. A second interval therefore resamples whole families, keeping
each family's tasks and seeds together (`comet.family_bootstrap`, 10,000
draws). Percentile intervals are anti-conservative at this size, and the
family interval is the stricter of the two. A hypothesis counts as confirmed
only when both 95% intervals exclude zero in the expected direction. The five intervals are reported unadjusted and
with a Holm adjustment across H1 to H5. A difference that is positive with an
interval including zero is reported as not confirmed, not as support.

Two mechanism hypotheses were added on November 14, 2026, still before any
execution, from the [instruction-error reading](dev19-instruction-errors.md)
of the first 19 tasks. Among first attempts that were rebuilt, the share with
a rejected login after the rebuild point is lower than among their
never-rebuild twins over the same turns: M1 for the fixed trigger, where the
19-task difference was -38 points [-54, -23], and M2 for the dynamic trigger,
-33 [-47, -20]. Each is confirmed when its family-resampled 95% interval
(`comet.instruction_errors`, 10,000 draws) excludes zero, reported unadjusted
and with a Holm adjustment across the two. They are separate from H1 to H5.

Reported descriptively, without a confirmation criterion: the same
comparisons against full cache for the recovery arms; first actions
and endings by condition and seed, read with `comet.task_characteristics` and
`comet.trigger_timing`; attempts, latency, memory, rebuild admissions and
costs; per-cell charged I/O; and every runtime failure. After the confirmation
is reported on its own, the 57 dev tasks are also summarized together at the
three seeds, labelled as combining exploratory and confirmatory tasks, with
seed 17 of the first 19 tasks marked as run on shared storage.

Expected size, recorded so it cannot be adjusted afterward: with 38 tasks, an
oracle difference near +14 points has an interval about 15 points either side,
so H1 and H2 may well stay unconfirmed even if the effect is real. The
first-attempt hypotheses are better powered. All outcomes are reported whether
or not any hypothesis is confirmed.

## Execution

Execution stays pinned to the qualified source, runtime, device and cap of the
first study, with the configuration files staged verbatim beside that checkout
and their resolved digests verified by every worker. Workers use the node-local
run directory, AppWorld root, runtime and model declared in the
[first study's design](dev19-recovery-design.md#node-local-execution-storage),
at most four at a time, with automatic requeue disabled. A guard with the same
limits reads saved cell timings from the first cells and cancels the study when
the ten most recent cells have a median reset above 5 seconds or a median save
or tool time above 8 seconds. A study the guard stops is void as a whole. A
two-cell smoke run of one new task, kept outside the study, precedes the
launch. Interrupted cells keep their failure and budget charge.

## Status

Declared and submitted on November 14, 2026; not yet executed. The qualified
Blackwell GPUs were fully allocated to their owner group that day and the
scheduler estimated a start a week later. The [queue note](dev19-recovery-design.md#queue-on-november-14-2026)
has the details.
