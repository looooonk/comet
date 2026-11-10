# Results

The completed Qwen3.5-9B study has two separate hardware cohorts. Both use
AppWorld, paired tasks and offline scoring. Oracle success assumes perfect
selection among attempts; these small samples do not establish a general ranking.

- [L4 findings](qwen9b/findings.md): the frozen two-task test, train/dev pilots,
  recovery diagnostic and memory qualification.
- [Blackwell findings](qwen9b/blackwell.md): the supplemental three-family train
  grid, recovery diagnostic and dev confirmation.
- [Fifty-family study](qwen9b/test50-design.md): the new frozen test expansion
  and its parallel execution design; submission is not completed-result evidence.
- [Fifty-task provisional results](qwen9b/test50-partial.md): 15 fully covered
  conditions, 50 paired tasks per point, with missing comparisons and GPU failures explicit.
- [Validation evidence](qwen9b/validation/): live state, memory, AppWorld and
  interruption checks, including the failed Blackwell 21 GiB qualification.
- [Cloud ledger](qwen9b/cloud-ledger.json): the existing spending ceiling and
  unreconciled allowances. These are planning amounts, not billed charges.

Selected figures are kept as PNG and PDF alongside the results. Full analyses
retain all measured conditions and paired uncertainty; the plotting commands can
regenerate additional views and formats. Historical paths inside saved JSON refer
to the source layout at the recorded revision. The [configuration guide](../../configs/README.md)
identifies the current equivalent configurations.

Completed raw run directories belong in external project storage, with their
manifests, trajectories, scores, environments and diagnostic checkpoints intact.
Temporary logs, duplicate archives, interim exports and execution diaries are
not part of the source tree. Older tracked records remain in Git history.
