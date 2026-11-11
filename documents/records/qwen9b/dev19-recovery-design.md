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
runs with different seed lists. Status: declared, not yet executed.

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
is tuned from these outcomes. Status: declared, not yet executed.

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
declared, not yet executed.
