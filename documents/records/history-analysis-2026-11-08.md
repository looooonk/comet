# Shared matched-history analysis validation

The shared `analyze-histories` and `plot-histories` commands now validate and
summarize saved cost diagnostics. The analyzer retains each run, repetition,
pass, failure and coverage count while requiring compatible source histories,
model, numerical settings, hardware and dependencies. It verifies saved hashes,
forced tokens, retention counts, throughput arithmetic and memory-cap accounting.
Only declared length, repetition, benchmark-identifier and timeout differences
are allowed; their original settings remain recorded.

Figures show one metric at a time with three method facets and a repeated full-KV
control alongside 80%, 50%, and 25% retention. Raw repetitions, medians and observed
ranges remain visible. Missing measurements break connecting lines and retain
failure/coverage markers. Occupied KV, transient peaks, reserved pool and total
VRAM are separate metrics. Whole-pass elapsed retains reset, verification and
cleanup; interrupted reserved time is never treated as a measurement.

Ordinary prefill/decode throughput uses synchronized native-loop timing, including
eviction and output processing. Selection and compaction sum all synchronized
calls over the **whole instrumented prefix-plus-continuation replay**, not
per-token rates. They are nested component costs, so adding them again to loop or
whole-pass time would double count. Instrumented throughput never substitutes for
ordinary-pass measurements.

Managed CPU checks passed 229 tests with one unavailable-Torch skip and nine GPU
or AppWorld deselections. After clarifying the whole-replay labels, all sixteen
focused history-analysis tests passed through the same managed check path. These
cover compatibility, artifact integrity, token/retention/throughput accounting,
failed later passes, missing coverage, reserved interruption time, CLI rendering,
and a regression that keeps larger values in later method facets inside the
shared y-axis range. The [evidence record](history-analysis-2026-11-08.json)
contains exact source and validation-artifact hashes.

The existing `qualified-pair-13837736/history-smoke` artifacts were reanalyzed:
all ten cells and thirty passes verified, with complete coverage for every
reported metric. The occupied-KV, ordinary-decode and instrumented-selection
single-point figures were visually inspected. Their source manifest and derived
artifact hashes are recorded alongside the implementation hashes.

This is a reanalysis of one 1,024-token prefix with one repetition, not a new GPU
run or a measured length curve. It does not establish stable speed rankings,
model accuracy or task success. The separate numerical qualification and its
unresolved reference discrepancies remain unchanged. Longer-history results and
repeated timing measurements must be reported when actually available.
