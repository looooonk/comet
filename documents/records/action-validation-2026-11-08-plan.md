# Independent executable-action validation

The ongoing broader 4B baseline exposed a comment-only loop on dev task
`23cf851_1`, seed 17. A preserved 194-turn snapshot contains a continuous suffix
of 184 comment-only blocks after authentication failures. AppWorld reported
`Execution successful.` for those valid Python comments; an earlier such
response was followed by the model incorrectly treating authentication as
successful. These are ordinary execution observations, without evaluator
feedback. The original run remains unchanged. The
[evidence and plan](action-validation-2026-11-08-plan.json) pins the snapshot.

The legacy runner ties rejection of comment-only code to a positive error-streak
cutoff. The new independent `agent.require_executable` option permits rejection
without adding a cutoff or bounded correction guidance. Invalid responses receive
an ordinary error observation, consume the same generation/context/bookkeeping
budget, and do not execute a tool or increment tool counts. It checks for a
Python statement, not meaningful progress; `pass` and repeated valid inspections
are still possible. The old positive-limit policy keeps its behavior, and the
new false default preserves historical configuration digests.

A new paired regression uses the explicit
[control](../../configs/pilot-action-validation-control-qwen4b-v1.json) and
[candidate](../../configs/pilot-action-validation-candidate-qwen4b-v1.json)
configs on the same new source/runtime and A6000. It keeps task `23cf851_1`,
seeds 17/18, pinned 4B BF16, the current prompt, sampling, 32k context, 40 GiB
cap, one attempt and a 600-second budget per cell. Only executable-body
validation differs. Both error cutoffs remain zero. Execute all four fresh
cells before scoring either arm; no broader-run outcome is imported. New-source
runtime validation and an explicit review of unchanged numerical engine
identities are required before launching.

This experiment targets the observed failure mechanism. It cannot establish
broad task capability or select a final model. The separate train-only worked
example remains a distinct possible prompt intervention; it is not included
in either arm. Any startup accounting change likewise requires its own recorded
decision and configuration version.

The managed CPU suite passed 323 checks, with one Torch-module skip and 14 live
deselections. After adding the paired configs, all 16 config checks passed.
Regression checks preserve the recorded historical configuration digest and
show six rejected comment-only responses followed by successful continuation,
with no early cutoff, extra attempt or free generation. Live model behavior
under this option remains unmeasured.
