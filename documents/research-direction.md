# Research direction

The November 8, 2026 user decision replaces continued tuning of the legacy
Qwen3 4B/8B/14B baselines with a new implementation phase for newer Qwen models.
The [candidate list](experimental-models.md) includes dense and MoE models up to
35B total parameters. The old 14B ceiling is no longer the selection constraint.
The original proposal remains background; this decision supersedes its model
and hardware assumptions. Backend and hybrid-state support must be designed
before new experiments. No replacement is implemented or qualified yet.

## Central deliverable

Produce a fine-grained **compaction aggressivity versus test-time task success
rate** plot that reveals useful accuracy, memory and compute tradeoffs.

- **Horizontal axis:** percentage of eligible KV entries removed,
  With retention $r$, this is $100\left(1-r\right)$, increasing from full cache
  toward stronger compaction.
  The initial candidate grid is 0, 10, 20, 30, 40, 50, 60, 70 and 75 percent.
  It includes the proposal's 80%, 50% and 25% retention anchors. Confirm and
  refine this grid on dev before freezing it; do not invent unmeasured points.
- **Vertical axis:** AppWorld task success rate. Show single-attempt success and
  oracle best-of-N within a common runtime budget as distinct views. Oracle
  selection is an upper bound; it is not an online selection policy.
- **Comparison:** full cache, StreamingLLM, R-KV and AgentKV through one validated
  backend, with clearly separated panels for recovery policies and budgets.
  Any architecture-driven method change must be explicit before evaluation.
- **Uncertainty:** paired seeds and task-bootstrap intervals. Seeds and attempts
  do not increase the number of independent tasks. Report counts and failures.
- **Supporting curves:** occupied KV and total peak VRAM, actual attempts,
  end-to-end latency, decode throughput, estimated FLOPs and rebuild cost.

A plot with every condition at 0% or 100% is not a sufficient final deliverable.
Use train/dev to find useful intermediate difficulty, context lengths and budgets
where methods can differ. Confirm that setting on separate dev coverage, then
freeze the test design. This is a design objective, not permission to manufacture
a result: retain flat outcomes, all predeclared points and failures; never pick
successful test tasks or hide unfavorable conditions. If the qualified setting
still produces a flat test curve, report it and propose a distinct experiment.

## Retained questions and invariants

Q1 compares never-rebuild, fixed-tool-count recovery and a context/tool-count
trigger at matched method and retention. Diagnostic branches start from identical
saved agent, environment, model state and RNG. Q2 compares compressed oracle
best-of-N, with and without recovery, against full-cache best-of-N under matched
runtime and total-memory caps. Final attempts always start from fresh task state.

Recovery re-prefills the full raw transcript at most once per attempt, reapplies
the retention policy and never replays tools. All attempts share a task budget;
resets, tools, checkpoints and rebuilds remain charged. Model loading and offline
scoring are excluded consistently. The user also approved measuring one fixed
training-environment initialization separately; see [timing](experiments.md).
Every condition uses the same timing definition and hardware contract.

For a hybrid model, specify which states can be compacted and how recurrent
state is restored or reconstructed. The x-axis must describe the actual object
being compressed. Record mandatory retained entries, realized retention and
non-KV memory separately. Active MoE parameters do not define resident weight
memory or inference cost by themselves.

## Next implementation handoff

1. Verify official candidate identities and select a model/backend/hardware plan.
2. Implement and validate the model's complete persistent state, sampling,
   compaction, recovery and AppWorld integration; retain one shared pipeline.
3. Establish a useful predeclared full-cache dev baseline, then pilot the fine
   aggressivity grid and independently executed runtime budgets.
4. Tune recovery on dev, freeze model/configs/tasks/seeds, and execute Q1/Q2.
5. Produce the central plot, supporting costs, uncertainty and answers.

The cleanup phase launches no jobs. Existing historical configs and dated plans
are archived in Git, summarized in [legacy results](records/legacy-results.md).
They are not a queue to resume. New infrastructure and experiments begin only
in the subsequent work requested by the user.
