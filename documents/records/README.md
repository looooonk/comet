# Results

For a guided view of the studies, settings, figures and reproducibility conditions,
start with the [experiment ledger](../../experiments/README.md). This directory
retains the dated evidence and canonical artifacts that ledger entries cite.

The completed Qwen3.5-9B studies use AppWorld, paired tasks and offline scoring.
The Blackwell compression grid has 50 held-out task families per condition;
the separate recovery matrix has 19 dev families and one seed. Earlier L4 and
Blackwell pilots have smaller samples. Keep hardware cohorts and train/dev/test
stages separate. Oracle success assumes perfect selection among attempts;
uncertainty and runtime failures limit claims of a general ranking.

## Completed studies

- [Fifty-task final results](qwen9b/test50-final.md): all 26 conditions and 1,300
  evaluations, with full-range and 0-50% success plots, resource plots, CSV and
  paired uncertainty. Execution and scoring completed on November 10, 2026.
  This never-rebuild study retains the CUDA-contaminated AgentKV 90% result.
- [Fifty-family study design](qwen9b/test50-design.md): frozen task selection,
  matched settings, qualification and execution history.
- [Nineteen-family dev recovery findings](qwen9b/dev19-recovery.md): the core
  29-condition matrix with both recovery policies, 551 cells and 963 attempts,
  completed November 10, 2026. [Design](qwen9b/dev19-recovery-design.md).
  Train/dev evidence only; separate from the fifty-task test.
- [Dev failure reading and task characteristics](qwen9b/dev19-task-characteristics.md):
  what fills the context at 50% retention, where the rebuild helped, and which
  task properties go with tolerating compression. Offline, one seed.
- [L4 findings](qwen9b/findings.md): the frozen two-task test, train/dev pilots,
  recovery diagnostic and memory qualification.
- [Blackwell findings](qwen9b/blackwell.md): the supplemental three-family train
  grid, recovery diagnostic and dev confirmation.

## Investigations and followups

- [AgentKV 90% investigation](qwen9b/agentkv90-investigation.md): confirmed CUDA
  cascade, retained exception frames, bounded GPU checks and a separate
  five-condition corrective replication. The last saved launch update is from
  November 10; no corrected fifty-task results are committed here.
- [Dev recovery followups](qwen9b/dev19-recovery-design.md#status): the seed
  replicate, retention frontier and trigger-timing studies. The November 11
  record preserves voided launches, a stopped relaunch and a node-local storage
  smoke check; none supplies completed followup results.

These are dated evidence records, not live job status. Invalid launches remain
documented separately and do not enter the completed-study comparisons.

## Validation and artifacts

- [Validation evidence](qwen9b/validation/): live state, memory, AppWorld and
  interruption checks, including the failed Blackwell 21 GiB qualification.
- [Cloud ledger](qwen9b/cloud-ledger.json): the existing spending ceiling and
  unreconciled allowances. These are planning amounts, not billed charges.

Selected figures are kept as PNG and PDF alongside the results. Committed analyses
retain all measured conditions and paired uncertainty; the plotting commands can
regenerate additional views and formats. Historical paths inside saved JSON refer
to the source layout at the recorded revision. The [configuration guide](../../configs/README.md)
identifies the current equivalent configurations.

Completed raw run directories belong in external project storage, with their
manifests, trajectories, scores, environments and diagnostic checkpoints intact.
Temporary logs, duplicate archives, interim exports and execution diaries are
not part of the source tree. Superseded partial results and older tracked records
remain in Git history.

## Historical analysis

- [November 8 midpoint analysis](midpoint-analysis-2026-11-08.md): reproducible
  legacy Qwen3-8B/A6000 evidence, separate from the current Qwen3.5-9B studies.
