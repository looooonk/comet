# Repository reset for the new Qwen study

The user cleared the previous execution goal, stopped the old-model effort,
and requested aggressive cleanup before any new infrastructure or experiments.
The [current direction](../research-direction.md) makes fine-grained compaction
aggressivity versus task success the central result, with useful intermediate
behavior established on train/dev. The candidate list supersedes the old 14B
ceiling; model availability, selection and support remain unverified.

## Working tree

- Reset local `TODO.md` to the new implementation and evaluation checklist.
  It remains locally ignored; the shared direction and model requirements are
  committed in `documents/` and linked from the README and agent instructions.
- Reduced `configs/` from 32 files to five: guidance, two legacy schema examples
  and two numerical-reference corpora. Removed obsolete pilot/sweep plans.
  Analysis tests use small fixtures; one historical config preserves hash
  compatibility coverage.
- Replaced 111 archived dated record files with a compact legacy summary, keeping
  six main cost-figure exports unchanged. The later uncommitted 24/24 GPU check
  was condensed with its verified hashes before removing its two dated files.
  Prior tracked files remain at commit `55fca50`.
- Consolidated repeated plotting-panel construction. Three representative
  synthetic renders matched byte-for-byte after excluding creation timestamps.
- Reconciled the already-written optional environment-initialization feature:
  setup is recorded separately, task costs remain charged and legacy config
  hashes are preserved. No config enables it. Its live AppWorld isolation check
  remains required before experimental use; no new live experiment was launched.

## Data disposal and retention

Local cleanup removed 2,313,992,015 logical bytes of obsolete validation binaries,
synthetic plot scratch, superseded CPU checks and a redundant environment.
Separate [Insomnia cleanup](cleanup-insomnia-2026-11-08.md) records cancellation,
staging and remote validation-binary disposal. Large deleted validation tensors
were untracked and are not recoverable from Git; compact measurements, identities
and per-file hash inventories remain. Completed task outcomes, trajectories,
environments and history-cost measurements were preserved.

Remaining local legacy artifacts were consolidated into `legacy-20261108.tar.gz`:
8,031 entries, 89,329,523 compressed bytes, with every archived file/link checked
before deleting unpacked copies. SHA-256:
`c1b897ae83bf6f3fe19f3e9445f593b1226f2b67cac608b285b97eb28d226e4e`.
The ignored archive and full cleanup inventories are retained as portable artifact
groups `legacy-20261108` and `cleanup-20261108`. Extract only needed evidence;
do not recreate the old workspace wholesale.

## Verification and handoff

The managed CPU suite passed **331 tests**, with one unavailable Torch-module
skip and 15 live GPU/AppWorld deselections. Lint, shell syntax, both retained
example configs, Markdown links and Git whitespace checks passed. No source
changed afterward; only examples/documentation and cleanup records were revised.
[GitHub Actions checks](https://github.com/looooonk/comet/actions/runs/42560429831)
also passed on cleanup commit `23110f7`.
Pytest XML SHA-256:
`508857c8da88df893ff9363ed4b296694f6dc239ba949fa83d8a8e36e78caead`.

Upstream `main` was checked at `86603d6` (midpoint analysis); it was not merged.
The shared pipeline and pinned legacy implementation remain a tested starting point.
The new model/backend implementation and all new experiments are subsequent
work, not outcomes of this cleanup.
