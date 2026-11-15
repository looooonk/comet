# New study entry template

[Ledger index](README.md)

Copy this structure into a descriptively named entry when a study is ready to be
recorded. Replace the instructions with actual evidence; use "not recorded" or
"not yet scored" where appropriate. A declaration can have an entry before
completion, but its planned coverage must not be presented as measured results.

## Question and status

State the concrete comparison, why it was run, its current evidence status and
the date of that status. Lead with the main observation when scored results
exist. Distinguish completed execution, completed scoring, partial results,
failed qualification, voided launches and unexecuted plans.

## Conditions and provenance

| Field | Record |
| --- | --- |
| Study identity | Stable experiment ID, stage, declaration date and versioned config link |
| Source | Execution/evaluator revisions and relevant local changes; link the manifest/source inventory |
| Runtime | Dependency locks, package/build versions, engine patches, model/tokenizer revisions, data/bundle versions |
| Cohort | Exact split/task IDs, selection rule and exclusions, family count, seeds, prior exposure and freeze evidence |
| Comparison | All methods, retentions, recovery policies, thresholds, attempt ceilings and controls |
| Prompt and sampling | Exact prompt/config link, template, temperature/top-p, thinking, output/context limits and stopping behavior |
| State | Fresh starts or checkpoint source; saved environment/model/RNG state, branch preparation charge and recovery semantics |
| Resources | GPU model/count, total-VRAM cap/reserves, CPU threads, host RAM, storage placement and process/condition order |
| Budget | Per-cell limit, charged/excluded work, warmup, interrupt/resume and failure accounting |
| Validation | Matching source/runtime/device/cap/workload qualification and smoke evidence, including failures |
| Coverage | Expected and observed task/condition/seed cells, scored coverage, attempts, missing or unstarted work |
| Artifacts | Portable run/partition IDs and inventory with integrity records; accessible storage locator when available |

Link [shared reproduction conditions](reproducibility.md) only where they match;
spell out differences. Keep exhaustive hashes in manifests/evidence rather than
duplicating them in the prose.

## Results and figures

Include the full measured condition table, first-attempt and oracle success with
denominators, and the primary figure with a source-data link and interpretation
of its axes. Report task-paired uncertainty, bootstrap settings and limitations.
Include attempt counts/statuses, timing and throughput coverage, occupied KV,
recurrent state, total memory, estimated compute and recovery costs/refusals.
Distinguish unavailable measurements from zero values.

## Interpretation and limitations

Explain what the measurements support and what remains a hypothesis. Preserve
flat curves, failures, time overruns, source/hardware/storage confounds, prior
test exposure and small-sample uncertainty. Identify which cohorts can be
compared and which must remain separate. State any resulting research decision
and link its rationale; do not imply an unmeasured followup has a result.

## Reproduction and next synchronization

Link executable configs, exact task selection, analyses, raw artifact inventory
and compatible commands for execution, offline scoring, aggregation and plotting.
Identify required external data or unavailable inputs. State what evidence is
needed before the next status change. Add the entry to the index and update the
ledger's synchronization date when reconciled with the repository.
