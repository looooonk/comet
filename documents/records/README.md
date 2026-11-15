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
- [Fifty-task provisional results](qwen9b/test50-partial.md): 12 fully covered
  conditions, 50 paired tasks per point, with missing comparisons and GPU failures explicit.
- [Nineteen-family dev recovery findings](qwen9b/dev19-recovery.md): the core
  matrix with both recovery policies on every dev family, its seed replicate on
  seeds 29 and 31, and its [design](qwen9b/dev19-recovery-design.md). Train/dev
  evidence only.
- [Dev failure reading and task characteristics](qwen9b/dev19-task-characteristics.md):
  what fills the context at 50% retention, where the rebuild helped, and which
  task properties go with tolerating compression. Offline, seed 17 with the
  replicate seeds beside it.
- [Dev trigger timing](qwen9b/dev19-trigger-timing.md): the single rebuild
  after 1, 2, 6 or 8 tool calls at 50% retention, beside the first study's 4
  and never. One seed, descriptive.
- [Dev retention frontier](qwen9b/dev19-frontier.md): R-KV and AgentKV at 70%
  to 30% retention with and without one rebuild, and the 50% consistency check
  against the first study. One seed.
- [Thirty-eight-task dev confirmation design](qwen9b/dev38-recovery-design.md):
  the declared confirmation of the 50% recovery result on the dev tasks the
  first study did not use. A declaration, not completed-result evidence.
- [Dev claims review](qwen9b/dev19-claims-review.md): an independent reading of
  which claims the dev records support, and a prior-work check.
- [RTX A6000 dev cohort design](qwen9b/a6000-cohort-design.md): qualification
  of a second device at the 24 GiB cap and the three dev studies declared for
  it. A declaration, not completed-result evidence.
- [Dev prompt-rule violations](qwen9b/dev19-instruction-errors.md): which
  system-prompt rules each compressed method breaks, what a rebuild removes
  against its never-rebuild twin, and why StreamingLLM keeps none of the
  prompt. Offline, post hoc.
- [RTX A6000 reference arms](qwen9b/a6000-dev19-core.md): the 19-task
  recovery arms on the second device over three seeds, with paired intervals,
  the rejected-login reading and failures. A repeat on the tasks that produced
  the hypothesis, not a confirmation.
- [Controls for the recovery result](qwen9b/a6000-controls-design.md): the
  decisions on a protected prompt, a text reminder, a symptom-triggered
  rebuild and a held-out run, and the two dev studies declared for the first
  three. A declaration, not completed-result evidence.
- [Validation evidence](qwen9b/validation/): live state, memory, AppWorld and
  interruption checks, including the failed Blackwell 21 GiB qualification and
  the RTX A6000 qualification at 24 GiB.
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
