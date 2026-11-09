# AppWorld saved-state scoring repair

The recent 8B and 14B pilots' original zero-success scores are provisional.
A reproduced AppWorld bookkeeping defect makes offline evaluation overlook
real saved mutations. The [corrected scoring follow-up](appworld-corrected-pilot-scoring-2026-11-08.md)
now confirms 0/6 in all three recent pilot arms; retain the original scores and
execution failures. The [evidence inventory](appworld-scoring-repair-2026-11-08.json)
pins the reproduction, patch checks and affected snapshot audit.

With pinned AppWorld `42b5bcf` and SQLAlchemy 2.1.5, rendering a named-memory
database URL escapes `file:` to `file%3A`. AppWorld parses that rendered URL,
placing live mutation counters under `:memory:file%3Atask_output-<task>`, while
export and load use `:memory:task_output-<task>`. A deliberate isolated phone
send increased the saved global-message row count from 8,396 to 8,397, but its
exported `model_hashes.json` was empty. In a fresh process, the evaluator's
change-set shortcut reported no changed models. In the execution process, stale
global counters could mask this defect, explaining why superficial save/load
checks were insufficient.

The compatibility fix derives the bookkeeping identity from SQLAlchemy's
structured database URL. It preserves the existing connection and database
contents. New saved outcomes and checkpoints carry path version
`structured-memory-v1`; restore rejects older checkpoints with potentially lost
counter history. Two live regressions passed: an unchanged state and a real
phone mutation. They cover fresh reset, checkpoint and save roundtrips, clearing
global counters before offline load, and agreement between normal-counter and
exhaustive model comparisons. The staged source/test hashes are recorded;
the existing runtime source and installed packages were not modified.

Offline scoring now clears global counters and forces every model through the
pinned evaluator's actual row-count and record-hash comparison. Only temporary
comparison counters change: each is the initial counter plus one, disabling the
counter-equality shortcut without declaring that a model changed. Original SQL,
rows, task requirements and actions remain unchanged. Each report saves the
counter-file hash and comparison metadata. This allows intact historical SQL
snapshots to be scored without replaying tools or repeating inference.

`comet rescore ORIGINAL --output REVISION` preserves the source and copies its
execution artifacts with an identical execution digest. It archives the original
scores and analysis, then applies the current scorer in the separate directory.
Ordinary scoring-resume checks remain strict. Revisions are alternative scoring
of the same runs, not additional independent observations.

The managed CPU suite passed 246 checks; one numerical module lacked PyTorch and
11 live tests were deselected. The two focused live AppWorld checks passed in
10.68 seconds without a GPU or model. The full corrected scorer then passed two additional live cases in 54.48 seconds:
unchanged and deliberately mutated legacy snapshots with empty counter files.
The unmodified task evaluator observed the expected change sets; original bytes,
audit metadata, cache cleanup and temporary-directory cleanup all verified.
After error-path review, 22 focused CPU checks passed, including interrupted
copy preparation and cleanup errors. The subsequent managed AppWorld job and corrected pilot outcomes are recorded
in the linked follow-up.

The read-only snapshot audit found empty maps in all 17 available completed
snapshots: eight paired 8B, three earlier sampling runs, and six recent 14B.
SQL journals can include task initialization, so those counts alone do not prove
that every individual task score changes. Failed attempts and missing snapshots
are separate categories; no extra attempts or budget are granted. Runtime,
trajectory and cache-cost evidence remains available, but the affected success
claims must be revisited after corrected scoring.
