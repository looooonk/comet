# Experiment ledger

This directory is COMET's human-readable experiment ledger: a place to browse
what was tried, the settings it used, its results and figures, and what those
results mean. It serves the role of an experiment tracker such as W&B or MLflow
using ordinary repository files, without a website or tracking service.

**It does not need to be maintained in real time.** Bring it up to sync with the
repository occasionally, especially after a study finishes, a result is corrected,
or a research decision changes the interpretation. A stale entry is a dated
snapshot, not a claim about the current scheduler or external storage.

**Last synchronized:** November 14, 2026, against `main` at `05774fa`.
The latest completed primary results in that snapshot are dated November 10;
the latest recorded followup status is November 11. This sync adds documentation
only and does not execute, rescore or change experiments.

## Browse the studies

Counts below are task/condition/seed **cells**, not independent samples. A cell
can contain multiple attempts. All current studies use Qwen3.5-9B; the legacy
entry is explicitly separate. Blackwell means one NVIDIA RTX PRO 6000 Blackwell
Server Edition per worker.

| Entry | Evidence and status | Coverage | Main observation |
| --- | --- | --- | --- |
| [Fifty-task compression study](test50-compression.md) | Completed and scored; test; Blackwell, 24 GiB | 50 families, 26 conditions, 1 seed; 1,300 cells | R-KV 70/80% retention: 15/50 oracle successes versus full-cache N=2: 14/50; uncertainty includes no difference. AgentKV 90% is CUDA-contaminated. |
| [Nineteen-family recovery study](dev19-recovery.md) | Completed and scored; dev; Blackwell, 24 GiB | 19 families, 29 conditions, 1 seed; 551 cells | AgentKV 50%: 3/19 without recovery, 7/19 with fixed recovery; preliminary dev evidence. |
| [Blackwell train and dev pilots](blackwell-pilots.md) | Completed and scored; pilot and checkpoint diagnostic | 78 fine-grid cells, 84 diagnostic branches, 14 dev cells | Recovery can help or harm; pilot samples are too small for a general ranking. |
| [L4 studies](l4-studies.md) | Completed and scored; capability, train/dev, diagnostic and small test; 21 GiB | 68 frozen-test cells on 2 families; 109 cells across 6 preceding runs | Selective recovery gains and losses; all test successes concern one family. |
| [Qualifications](qualification.md) | Integration and capacity evidence; includes failed checks | A6000, L4 and Blackwell, each with its own scope | KV reduction does not imply equivalent total-VRAM reduction. |
| [Investigations and followups](followups.md) | CUDA audit completed; corrective results absent from this snapshot; dev followup launches voided | Five-condition corrective test replication and three declared dev studies | Configurations and submission records do not establish completed results. |
| [Legacy midpoint studies](legacy.md) | Historical Qwen3-8B/A6000 and separate exploratory evidence | Fixed-history benchmark and corrected AppWorld pilots | Preserved for provenance; superseded as the current research direction. |

Start with the first two entries for the main findings. Each has the complete
condition-level success table, figures, settings, failures and evidence links.
Use the [reproducibility guide](reproducibility.md) to interpret metrics, recover
the exact execution conditions, or regenerate an analysis or figure.

## How this relates to the repository

| Location | Responsibility |
| --- | --- |
| `experiments/` | Curated explanations, study index, comparison boundaries and reproducibility map |
| [`configs/`](../configs/README.md) | Executable, versioned study declarations and frozen task/condition settings |
| [`documents/records/`](../documents/records/README.md) | Dated evidence, compact analyses, artifact identities and canonical figures |
| [`documents/experiments.md`](../documents/experiments.md) | Shared execution, evaluation, resume and analysis workflow |
| External project storage | Complete manifests, raw transcripts, actions, saved environments, checkpoints and scores |

Figures are embedded from their canonical locations in `documents/records/`,
so this ledger does not create duplicate image or analysis exports. It is
readable in a local Markdown viewer or on GitHub. Full reruns and rescoring
also require the external artifacts and pinned runtime; a clone contains the
compact evidence, not every raw run. Portable artifact IDs identify those
bundles, but are not download URLs.

## Occasional synchronization

1. Read changes to the configurations, research contract and evidence records
   since the last sync. Check both completed studies and unsuccessful launches.
2. Update the relevant entry using saved results. Preserve the original cohort
   when a correction or replication introduces a new source or execution setting.
   Keep unscored, voided, failed-qualification and unexecuted work explicit.
3. Reconcile task, seed, condition, cell and attempt counts with the source
   summaries. Keep first-attempt and oracle success separate, retain failures,
   and attach uncertainty and material confounds to the interpretation.
4. Link the versioned configuration, source/runtime provenance, raw artifact
   inventory and canonical figures. Record missing evidence as missing; do not
   fill it with estimates or infer completion from a job submission.
5. Check local links, figures and table values, then update the sync date and
   source revision here. Commit the ledger alongside the evidence it summarizes
   when practical. Updating the ledger never requires launching new experiments.

Use the [entry template](entry-template.md) for new studies. One entry can group
closely related pilots if each run retains its own settings, identity and result.
Do not combine hardware cohorts, train/dev/test stages, checkpoint branches and
fresh starts, or original and corrective runs into one score.
