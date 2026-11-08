# Checkpoint eligibility and failure accounting

An audit reproduced a Q1 source that finished its task exactly at the declared
tool-count boundary, was saved as a usable checkpoint, and then received another
action in each branch. Sources now require an incomplete task at the boundary.
Early or exact-boundary completion is retained as an unavailable checkpoint, with
its preparation trajectory and costs preserved. This uses ordinary supervisor
completion state, not evaluator feedback.

Preparation costs are charged before branch reset and attached to the attempt
even if reset, restoration, or source preparation fails. Source tool counts are
identified separately from actions actually executed by the branch. Early
rejection saves an empty branch transcript and does not read stale engine state.
Synchronization, close, and final memory-probe errors preserve the primary
failure and known measurements; cleanup consumes budget and can invalidate an
otherwise completed source.

The managed CPU validation passed **64 focused checks**, with lint and shell
syntax checks passing. Cases cover both completion boundaries, unsupported
checkpoint state, reset timeout, one-time preparation charging, resume without
rerunning, cleanup/probe failures, and cleanup budget overrun. The accompanying
[artifact inventory](checkpoint-repair-2026-11-08.json) identifies this evidence.
Live combined AppWorld/GPU branching remains required before a scientific Q1 run.

The first meaningful diagnostic should use a predeclared nonterminal boundary
from ordinary train/dev traces, full cache, and never/fixed/dynamic recovery for
one feasible method and retention. A fixed threshold already reached at the
boundary fires immediately; a dynamic threshold already met there gives the
same initial decision. Such settings cannot establish a useful trigger tradeoff.
Choose and record useful train/dev thresholds before execution, then validate on
separate declared tasks. The old diagnostic template's short context, output
limit and prompt are not current frozen settings.
