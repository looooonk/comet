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

Declared and validated on CPU only (configuration validation and the focused
configuration tests). No model inference, AppWorld execution or GPU check has
run for this study. Job identifiers, starts and results belong in a separate
submission record once it is launched.
