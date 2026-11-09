# Stopped Insomnia experiments and cleanup

The user ended the experiment effort. The active broader 4B pilot, job **13840259**, was canceled at **22:50:59 EST on November 8, 2026**, after **48 minutes 28 seconds**. The user scheduler queue was empty afterward; no new jobs were submitted.

Seven of the 38 declared cells had terminated: **three normal completions and four budget timeouts**. One additional cell was interrupted and 30 never started. Scoring had not begun, so this incomplete pilot has **no task-success result**. Ordinary observations showed comment-only and bare-literal action loops; these remain compact failure evidence, without evaluator-derived recommendations. The saved manifest remained `running` and the wrapper exit text was `0` after the signal; the terminal scheduler cancellation and absent all-cell/scoring guards determine the result.

The cleanup removed:

- The canceled remote run: **121 files, 2,648,816 logical bytes**, after checking every file against the retained hash inventory.
- Redundant remote launch staging: **147 files, 2,306,720 logical bytes**. Local copies, preserved Git commits, or compact command provenance cover every input. The separately owned action-validation staging was excluded for its cleanup owner.
- Local raw trajectory prefixes and expanded trace audits, replaced by a compact ordinary-action summary and original hashes.
- Obsolete synthetic validation checkpoints/logits: **127 files, 2,869,779,858 logical bytes**. The per-file paths, sizes and SHA256 inventory remains; 101 checksums were safely reused and 26 files were hashed once. No validation tensor binaries remain in the owned validation tree.
- Redundant local source bundles: **3 files, 331,212 logical bytes**; every head commit remains in root Git.

Completed scientific task outputs and compact validation measurements, logs, and identities were preserved. Synthetic validation checkpoint/logit binaries were removed as listed above. This cleanup left the model cache (24.46 GB observed allocation), shared package cache (9.35 GB), and AppWorld data untouched. Separately authorized removal of the exclusively owned 4B snapshot is covered by the resource-cleanup owner; shared model caches remain preserved. No partial model downloads were found. A bounded AppWorld size inventory timed out; this was not used as a deletion criterion. Historical runtime removal and the retained reusable environment are covered by the separate resource-cleanup record.

Source and runtime markers were unchanged. The companion JSON contains cell-level status summaries, deletion decisions, observed sizes, and hashes for compact evidence in artifact group `cleanup-20261108/insomnia`. These sizes describe files observed, not measured physical space reclaimed. No full canceled-run trajectories were retained.

This cleanup scope removed **2,874,735,394 logical bytes remotely** and **1,135,583 logical bytes locally**. Runtime and cache cleanup totals are recorded separately; these totals must not be counted twice.
