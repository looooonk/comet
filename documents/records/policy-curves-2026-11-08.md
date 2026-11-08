# Offline policy and attained-success figures

The shared analysis now retains paired observations for recovery, trigger,
attempt-count and success-over-time figures. `comet plot-success-time` draws
unsmoothed attained oracle success along recorded execution schedules, with
paired task-bootstrap and conservative bounded intervals. These are descriptive
availability curves, not claims about rerunning under smaller budgets.

Recorded attempt completion times are checked against ordering, cell duration,
budget and interruption reservations. Missing success times make a condition's
curve explicitly unavailable rather than removing tasks or counting them as
failures. A later interruption does not erase an earlier measured success.
Malformed reservation totals are rejected. Full-cache attempt limits share a
comparison panel; compressed panels use the corresponding full-cache control.

The final managed focused checks passed **55 tests**, with lint and shell syntax
checks passing. The tests cover task/seed pairing, agreement with ordinary oracle
success at the endpoint, failure and zero-attempt denominators, missing/invalid
timestamps, reservations, nonmonotone schedules, and plotting/CLI coverage.
Historical and synthetic layout renders were visually inspected. The historical
render reproduced the October pre-sampler 1/8 full-cache result; it is not a new
experiment or evidence of corrected-model performance. Synthetic renders are
layout fixtures only. The [inventory](policy-curves-2026-11-08.json) records hashes.

The new recovery, trigger, and attempt plots complement this curve command.
Their definitions and reusable commands are in [evaluation.md](../evaluation.md).
Main result figures should use focused comparisons over meaningful operating
ranges, with complete condition tables and diagnostic failures preserved
separately. No result is made nonzero by these reporting changes.
