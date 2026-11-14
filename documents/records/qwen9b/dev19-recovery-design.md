# Nineteen-family dev recovery study

Declared on November 9, 2026, before any execution. The
[fifty-family test study](test50-design.md) measures the never-rebuild fine grid;
recovery has so far been measured on two test tasks and three train families.
This study runs the core comparison matrix, including both recovery policies,
on every dev family. It is train/dev evidence: it does not open the test split,
change any frozen configuration, or pool with another cohort.

## Declared comparison

The [configuration](../../../configs/qwen9b/blackwell/dev19-recovery-v1.json)
extends the qualified Blackwell [dev confirmation](../../../configs/qwen9b/blackwell/dev-v1.json)
and changes only the task list and conditions. Qwen3.5-9B, the pinned hybrid
BF16 backend, the v4 prompt, sampling, seed 17, 16,384-token context, the
120-second budget shared by at most two sequential attempts, the 24 GiB
total-VRAM cap and the recovery thresholds (fixed after 4 tool calls; dynamic at
6,144 context tokens and 3 tool calls) are inherited unchanged.

The 29 conditions are the full-cache N=1 and N=2 controls plus StreamingLLM,
R-KV and AgentKV at 80%, 50% and 25% retention under never, fixed and dynamic
recovery. With 19 tasks there are 551 fresh-start cells and at most 18h22m of
cell budgets. First-attempt and oracle success are reported separately; oracle
selection is a perfect-selection upper bound.

## Task selection

All 19 dev families are used. Within each family the variant minimizes SHA-256
of `comet-dev19-recovery-v1:20261109:variant:<task_id>`, reading split
identifiers only. The [selection record](dev19-recovery-selection.json) lists
the families, the chosen tasks (six variant-1, six variant-2, seven variant-3)
and the expected split hash. Families `4ec8de5` and `396c5a2` were already used
for dev confirmation with variant 1; they stay in the sample and are flagged.
Bootstrap the 19 paired tasks with their conditions and attempts.

## Execution and analysis

[Four condition groups](../../../configs/qwen9b/blackwell/dev19-recovery-v1-parts/)
cover every condition exactly once with the complete task list: 152, 133, 133
and 133 cells, at most 5h04m and 4h26m of cell budgets. Each one-GPU worker
needs an RTX PRO 6000 Blackwell Server Edition, the managed hybrid runtime and
the live checks and dev smoke required for a new checkout and runtime; this
study's own runtime does not reuse another checkout's qualification. Workers
run sequentially within every cell, with automatic requeue disabled.
Interrupted cells keep their failure and budget charge.

Score each group offline after execution and analyze the four run directories
together through the ordinary shared analysis, which accepts runs that differ
only in their condition lists. Report the aggressivity curves by recovery
policy, the paired recovery-minus-never differences within each method and
retention, attempts, latency, memory, recovery admissions and costs, and every
runtime failure. Do not use these outcomes to retune thresholds for the frozen
test study.

## Status

Completed on November 10, 2026, without changes to the declared configuration.
See the [findings](dev19-recovery.md) and [compact evidence](dev19-recovery-summary.json).

## Seed replicate

Declared on November 10, 2026, after the seed-17 results and before any further
execution. The [replicate configuration](../../../configs/qwen9b/blackwell/dev19-recovery-v2.json)
extends the first study and changes only the replicate seeds, to 29 and 31:
the same 19 tasks, 29 conditions and numerical settings, 1,102 fresh-start
cells in [eight condition groups](../../../configs/qwen9b/blackwell/dev19-recovery-v2-parts/)
of 152 or 114 cells. Its purpose is to measure whether the recovery effects at
50% retention persist across seeds; no threshold, task or condition was chosen
from the seed-17 outcomes.

Execution stays pinned to the qualified source, runtime, device and cap of the
first study, with the new configuration files staged verbatim beside that
checkout so their resolved digests are unchanged. Analyze the two new seeds
through the shared analysis, bootstrapping tasks with their paired seeds, and
report seed 17 alongside them descriptively; the shared analysis does not pool
runs with different seed lists. Status: completed on November 12, 2026 on
node-local storage, without changes to the declared configuration. See the
[findings](dev19-recovery.md#seed-replicate) and [compact evidence](dev19-recovery-summary.json).

A first launch on November 10-11, 2026 was stopped after 28 cells and is void.
Shared-storage stalls were being charged to the cell budgets: the 24 completed
cells averaged 29.2 seconds saving trajectories and 18.6 seconds in tools,
against 2.2 and 1.4 in the first study, and full-cache cells that had finished
in 16-18 seconds were reaching the 120-second budget. A small atomic write on
the shared filesystem took a median 3.6 seconds at the time. The partial run is
kept outside project comparisons and is not resumed; the replicate will be
launched unchanged into a fresh run directory once storage is healthy, and the
first cells' save and tool times checked against the first study before it is
allowed to continue.

## Supplemental retention frontier

Declared on November 10, 2026, before any execution of this grid. The
[frontier configuration](../../../configs/qwen9b/blackwell/dev19-frontier-v1.json)
keeps the 19 dev tasks, seed 17 and every numerical setting of the first study
and measures R-KV and AgentKV at 70%, 60%, 50%, 40% and 30% retention under
never and fixed recovery, with the full-cache N=2 control: 21 conditions and 399
fresh-start cells in [seven condition groups](../../../configs/qwen9b/blackwell/dev19-frontier-v1-parts/).
The research contract authorizes finer train/dev retention grids declared as
new versions. Its purpose is to locate the range of compression over which a
single rebuild restores success; the first study showed an effect at 50% and
none at 80% or 25%. StreamingLLM and the dynamic trigger are omitted to bound
the grid. The 50% conditions repeat the first study with the same seed as a
consistency check. All points are reported, including flat ones; no threshold
is tuned from these outcomes. Status: completed on November 12, 2026 on
node-local storage, without changes to the declared configuration. See the
[findings](dev19-frontier.md) and [compact evidence](dev19-frontier.json).

## Supplemental trigger timing

Declared on November 10, 2026, before any execution of these configurations and
after reading the seed-17 trajectories. [Four configurations](../../../configs/qwen9b/blackwell/dev19-trigger-v1/)
keep the 19 dev tasks, seed 17 and every other setting of the first study and
change only the fixed threshold: AgentKV and R-KV at 50% retention with the
single rebuild after 1, 2, 6 or 8 tool calls instead of 4. Each has 38
fresh-start cells, 152 in total. The first study supplies the threshold-4 and
never-rebuild points for the same tasks and seed. Triggers are selected on
train/dev under the research contract; these outcomes do not retune the frozen
test study.

Expectation recorded before execution: in the first study eight of AgentKV 50%'s
38 attempts reached the context limit before the fourth tool call, so no rebuild
occurred, and attempts that opened with a wide documentation search were not
rescued by a rebuild at the fourth call. If an earlier rebuild restores the
prompt's lookup protocol, thresholds 1 and 2 should end fewer attempts at the
context limit than threshold 4, and thresholds 6 and 8 should approach the
never-rebuild arm. All four points are reported whether or not this holds.
Each configuration has its own trigger and is analyzed as a separate run;
comparisons across thresholds are paired by task and descriptive. Status:
completed on November 11, 2026 on node-local storage, without changes to the
declared configurations. See the [findings](dev19-trigger-timing.md) and
[compact evidence](dev19-trigger-timing.json).

## Voided launches on November 11, 2026

The seed replicate, the trigger-timing study and the retention frontier were
launched together on November 11 and all three launches are void. Up to 16
workers ran at once on two nodes (4, 8 and 4), against four in the first study.
AppWorld resets, which are charged to the cell budget, stalled as workers were
added:

| Workers running | Cells | Median reset per cell (s) |
| --- | ---: | ---: |
| 2 (first ten trigger cells) | 10 | 1.0 |
| 12 | about 400 | 57 to 117 |
| 16 | about 190 | 180 to 1,480 |
| First study, 4 workers | 551 | 0.9 (mean) |

Trajectory saves and tool calls stayed fast (under one second per cell), unlike
the first voided replicate launch. In the replicate 224 attempts ended with the
budget expiring during reset. The 152 trigger, 438 replicate and 57 frontier
cells written before the jobs were cancelled are kept outside project
comparisons and are not resumed or scored. That the stalls come from the
workers contending on the shared AppWorld data is a hypothesis the worker
counts fit; storage latency outside these jobs was also above its morning level.

The three studies are relaunched with unchanged configurations into fresh run
directories, one study at a time in the order trigger timing, replicate,
frontier, with at most four workers and scoring only after a study's workers
finish, as in the first study. A guard job reads the saved cell timings every
four minutes and cancels the running study and everything queued behind it when
the ten most recent cells have a median reset above 5 seconds or a median save
or tool time above 8 seconds. The guard never excludes individual cells: a
study it stops is void as a whole.

The guard stopped that relaunch of the trigger-timing study at 16:22 on
November 11 after 38 cells, and that launch is void. The ten most recent cells
had a median 9.0 seconds of trajectory saving (4.3 in tools, 1.1 in reset). Only
two workers had produced cells, and saves were slow from the first cell, so
worker count does not explain it. On the same conditions:

| Run | Cells | Median save per cell (s) | Median tool time per call (s) |
| --- | ---: | ---: | ---: |
| First study, 50% fixed conditions | 57 | 0.22 | 0.013 |
| Stopped relaunch, AgentKV 50% fixed | 38 | 5.58 | 0.209 |

The runner writes the trajectory after every turn and syncs the file and its
directory, about 35 synced writes per cell on the shared filesystem. The
replicate and the frontier had not started and were cancelled with it. In the
first study itself the save limit was exceeded in 7 of 542 ten-cell windows
(largest median 10.1 seconds), and 9 of its 963 attempts ended with the budget
expiring during a save, so the limit is tighter than the reference run it
protects.

## Node-local execution storage

Declared on November 11, 2026, after the voided launches above and before the
next relaunch. Workers for the trigger-timing study, the seed replicate and the
retention frontier keep the run directory and the AppWorld root on the compute
node's local disk. A background copy mirrors the run directory to shared
storage every minute and again at exit. The AppWorld data is unpacked on each
node from one archive of the pinned 0.2.0 installation, checked against its
SHA-256 (`f577ec02e4a9...`) before every use, and offline scoring recreates each
part's recorded root on the scoring node from the same archive. The source
commit, runtime, model, device, cap, configurations and their digests are
unchanged; the change is in job scripts outside the checkout. Resets, tool calls
and saves are still charged to the cell budget and now measure local disk.

A two-cell smoke run on November 11 (AgentKV 50%, rebuild after one tool call,
seed 17, kept outside the studies) checked the change:

| Check | Result |
| --- | --- |
| Trajectory save per cell | 0.03 s (5.58 in the stopped relaunch, 0.22 in the first study) |
| Reset per attempt | 0.5 s |
| Actions against the same cells in two shared-storage launches | all 23 turns of 4 attempts identical |
| First action against the first study's never arm | identical in 4 of 4 attempts |
| Offline scoring through a recreated root | 3 of 3 saved environments scored |

Tool time was 11.3 seconds in the first smoke cell and 0.7 in the second: the
first cell of a worker loads tool libraries from the shared runtime
environment. Replayed on local disk the same calls took 0.03 to 0.4 seconds
each. Workers now read those libraries once before their first cell; that step
was added after the smoke run and reads files only.

The first study ran on shared storage while it was healthy (0.9 seconds of
reset, 2.2 of saving and 1.4 of tools per cell on average), so the relaunched
studies charge a few seconds less I/O per 120-second cell. Per-cell I/O times
are reported beside every comparison with seed 17. The frontier's 50%
conditions repeat the first study, and each trigger-timing attempt shares its
actions with the first study up to its rebuild; both are checked action for
action. The order (trigger timing, replicate, frontier), the four-worker limit
and the guard are as declared above.

The first launch on node-local storage, at 17:38 on November 11, is void. Its
four trigger-timing workers ran on one node, each completed one cell and all
four died with a bus error between 17:46:25 and 17:47:02 during their second
cell. At least 17 jobs of four other users failed on that node between 17:46
and 17:49, and the replicate and frontier arrays released by the failure could
not be launched there and wrote no cells. The four completed cells averaged
0.04 seconds of saving and 1.2 of reset. The eight cells are kept outside
project comparisons and are not resumed. The workers still loaded their Python
libraries from shared storage; the cause of the node fault was not established.

Declared after that launch and before the next: workers also unpack the managed
runtime onto the node's local disk, through the packed-runtime option in the
[setup guide](../../setup.md), and stage the model and scratch beside it. The
archive was packed from the same qualified environment and activation verifies
its identity and lock digests. The library read added after the first smoke run
is removed as redundant. Compiled-kernel caches and the once-a-minute mirror
are the remaining uses of shared storage during execution.

A second two-cell smoke run of the same cells repeated every check of the
first: all 23 turns identical to the two shared-storage launches, first actions
identical to the first study, three of three saved environments scored. Per
cell it averaged 0.03 seconds of saving, 0.75 of tools and 1.1 of reset, and
the first cell no longer carried a library-loading charge.

The relaunch at 18:33 on November 11 completed the trigger-timing study: 152
cells with means of 0.9 seconds of reset, 0.1 of saving and 0.7 of tools per
cell, and no worker failure. Its guard was queued to start once every worker
of the study had started, so it began at 19:11, 34 minutes after the first
cell; timings over that interval were checked by hand and are inside the
limits. For the replicate and the frontier, whose workers start in two rounds,
a second guard with the same limits was started at 20:22, after the
replicate's first 44 cells (medians of 0.5 seconds of reset, 0.04 of saving and
0.4 of tools), and another is queued to start with the frontier's first worker.

The replicate then ran from 20:10 on November 11 to 03:14 on November 12 and the
frontier from 03:59 to 06:49, each with at most four workers on one node and no
worker failure, preemption or requeue. Neither guard tripped. Read afterward
from every saved cell:

| Run | Cells | Mean reset (s) | Mean save (s) | Mean tools (s) | Ten-cell windows over a guard limit |
| --- | ---: | ---: | ---: | ---: | ---: |
| Seed replicate | 1,102 | 0.9 | 0.15 | 0.8 | 0 of 1,093 |
| Retention frontier | 399 | 0.9 | 0.09 | 1.3 | 0 of 390 |
| First study, shared storage | 551 | 0.9 | 2.2 | 1.4 | 7 of 542 (saving) |

Each study was scored in one job after its workers finished and analyzed
through the shared analysis. The frontier's repeated conditions solved the same
tasks as the first study and matched it action for action, apart from attempts
cut at a different turn by the deadline and one attempt whose observation
printed a set in a different order; the [frontier record](dev19-frontier.md#consistency-with-the-first-study)
has the counts.

## Seed replicates of the frontier and the trigger timing

Declared on November 14, 2026, after the seed-17 frontier and trigger-timing
results and the seed replicate of the core matrix, and before any execution of
these configurations. An [independent reading](dev19-claims-review.md) of the
records found the retention band and the timing result to rest on seed 17
alone, the seed with the largest recovery gain. Both replicates keep the 19 dev
tasks and every numerical setting and change only the seeds, to 29 and 31, and
the condition lists, to AgentKV. The research contract authorizes train/dev
grids and neighboring trigger thresholds declared as new versions; no threshold
or retention is chosen from these outcomes.

The [frontier replicate](../../../configs/qwen9b/blackwell/dev19-frontier-v2.json)
runs AgentKV at 70%, 60%, 40% and 30% retention under never and fixed recovery:
eight conditions, 304 fresh-start cells in [four condition groups](../../../configs/qwen9b/blackwell/dev19-frontier-v2-parts/).
The 50% arms and the full-cache control at these seeds are in the seed
replicate of the core matrix. R-KV is omitted: its frontier showed no
consistent range and it solved nothing below 50%. Expectation recorded before
execution: if the seed-17 band holds, fixed minus never is positive at 60% and
40% and near zero at 70% and 30% at both seeds.

The [timing replicate](../../../configs/qwen9b/blackwell/dev19-trigger-v2/)
runs AgentKV at 50% retention with the single rebuild after 1, 2, 6 or 8 tool
calls: four configurations of 38 cells, 152 in total. Threshold 4 and never at
these seeds are in the seed replicate of the core matrix. Expectation recorded
before execution: thresholds 1 and 2 solve at least as many tasks as threshold
4, and thresholds 6 and 8 fall between never and threshold 4. Attempts that end
before their rebuild are reported separately from attempts that were rebuilt.

Both are analyzed through the shared analysis on their own seeds, with seed 17
beside them descriptively, and every point is reported. They run after the
[thirty-eight-task confirmation](dev38-recovery-design.md) on the same
node-local storage, worker limit and guard. Status: declared, not yet executed.
