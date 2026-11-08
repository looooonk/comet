# Results and validation records

## Latest results

The recent [8B prompt diagnostic](execution-prompt-2026-11-08-results.md) and
separate 14B pilot completed execution, but their original zero-success scores
are provisional. A [reproduced AppWorld scoring defect](appworld-scoring-repair-2026-11-08.md)
caused saved mutations to be overlooked. The path repair passed live persistence
checks; corrected offline scoring of immutable outcomes is pending. Do not infer
model capability or prompt effects from the original scores.

The [2k](history-feasibility-2k-2026-11-08.md) and
[8k](history-feasibility-8k-2026-11-08.md) and
[16k matched-history measurements](history-feasibility-16k-2026-11-08.md) each
completed all ten conditions and thirty passes, with verified retention and
resource accounting. Longer histories and repeated timings remain in progress;
these cost diagnostics do not depend on task scoring.

The [November 8 numerical calibration](reference-calibration-2026-11-08.md)
records 165 passed L40S checks and a failed relative-error screening gate. A
separate FP32 CPU comparison found the native BF16 output closer to FP32 than
the BF16 reference on 23/24 positions. The revised default screen passed on
A6000, but the separate corpus failed. Further FP32 and fresh-cache diagnostics
did not support persistent-cache corruption. The bounded protocol pilot may
proceed under the [explicit qualification](pilot-numerical-qualification-2026-11-08.json),
preserving both failed screens; final-study qualification remains open.

The [November 8 foundation repair](foundation-repair-2026-11-08.md) passed 149 CPU
checks and reproduced the corrected-sampler baseline chart with explicit protocol
compatibility and measurement coverage. Subsequent GPU state, capacity and failure checks passed under the numerical
qualification above. The [new executable-action prompt diagnostic](execution-prompt-2026-11-08-plan.md)
completed execution; its task scores need the correction above. The historical reanalysis
adds no new model-success evidence.

The [Qwen3-14B retention pilot](retention-pilot-2026-10-20.md) completed on
October 20, 2026; its results were collected and reproduced on October 31.
Full cache solved 1/8 dev tasks, and AgentKV at 80%, 50%, and 25% retention
solved 0/8 each. All 32 attempts are accounted for, including ten timeouts and
one interruption. The report includes uncertainty, paired comparisons, resource
coverage, a figure, and reproducible artifact identifiers.

This exploratory run used alternative hardware, one attempt per condition, and
no recovery. It does not qualify the main Qwen3-8B/A100 experiment or resolve
the recovery and best-of-N questions. Main-pilot tuning and freeze, the full
diagnostic matrix, and final evaluation remain outstanding. See the report's
[remaining work](retention-pilot-2026-10-20.md#remaining-research-work).

The [November 7 full-cache investigation](full-cache-investigation-2026-11-07.md)
reproduces the two November 6 trajectory audits and prioritizes authentication,
API signatures, task coverage, and pagination. Isolated CPU AppWorld probes
confirm the authentication and pagination mechanisms; no new model-success
result or changed experiment setting is claimed.

The [November 7 runtime and baseline validation](runtime-baseline-validation-2026-11-07.md)
validated both pinned models through Mini-SGLang and the shared managed setup.
Each model's GPU suite passed 117 checks. A separate three-task dev prompt trial
improved from 0/3 to 1/3 successes and from four HTTP 401 turns to zero; task
completion and pagination remain unresolved. This targeted diagnostic does not
replace the broader retention pilot or qualify the main A100 experiment.

The [partial 8B trajectory diagnosis](baseline-qwen8b-2026-11-07-trajectory-diagnosis.md)
inspects 24 terminal attempts from the ongoing 38-rollout pilot. It identifies
repeated authentication, formatting, and data-shape failures, plus a confirmed
sampling-generator defect in the pinned runtime. Fix and validate sampling
before treating seeds 17 and 18 as independent model-sampling replicates. The
record is a partial diagnostic, not the completed pilot's success estimate.

The [completed broader 8B pilot](baseline-qwen8b-2026-11-08-completion.md)
finished all 38 rollouts and offline scoring: zero task successes, with 19
timeouts, five context-limit failures, and fourteen unsuccessful normal
completions. It used the defective sampler identified above; retain it as
diagnostic evidence, not an estimate of corrected-model performance.

The [November 8 corrected-sampler validation](sampling-repair-2026-11-08-validation.md)
passed 130 live GPU/AppWorld and shared-pipeline tests. It recovered the initial
setup timeout and started the paired twelve-rollout 8B diagnostic. The
[completed paired results](sampling-repair-2026-11-08-results.md) have zero
successes in each arm; one guarded rollout was preempted and conservatively
finalized as an interrupted failure. Sampling varies correctly, but agent task
success remains unresolved.

The October 17 interruption and October 19 pending-job records below are
historical snapshots. The continuation, postflight, and export all completed;
the [completion evidence](retention-pilot-2026-10-20.json) supersedes their
pending status.

## Record conventions

Keep personal notes, dated execution logs, validation results, and artifact
inventories here. General implementation, setup, and repository guidance belongs
in the parent `documents/` directory.

Use dated, descriptive filenames and preserve existing evidence when adding a
follow-up. Record the relevant source, configuration, hardware, and limitations.
Omit personal account names, SSH workspace locations, private filesystem paths,
and links other contributors cannot access. Use portable artifact filenames and
hashes; link shared storage only when it is accessible to collaborators. Large
runtime artifacts are not included in this directory.

## Evidence index

| Record | Contents |
| --- | --- |
| [AppWorld scoring repair (2026-11-08)](appworld-scoring-repair-2026-11-08.md) | Reproduced counter-path defect, validated state-preservation fix, and separate rescoring; original recent task scores provisional |
| [16k matched-history result (2026-11-08)](history-feasibility-16k-2026-11-08.md) | Thirty verified passes, 27.786 GiB peak total VRAM, and actual three-length cost figures |
| [8k matched-history result (2026-11-08)](history-feasibility-8k-2026-11-08.md) | Thirty verified passes and actual two-length cost figures; first-use timing caveats |
| [2k matched-history result (2026-11-08)](history-feasibility-2k-2026-11-08.md) | Ten conditions and thirty verified passes; single-repetition timing caveats |
| [History allocation failures and split (2026-11-08)](history-feasibility-allocation-2026-11-08.md) | Preserved CUDA and full-suite timeout failures, exact validation reuse, completed 2k/8k measurements and progressive allocation evidence |
| [Shared matched-history analysis (2026-11-08)](history-analysis-2026-11-08.md) | Strict artifact/metric accounting, 229 CPU checks and inspected real single-point smoke figures; longer curves remain pending |
| [Executable-action prompt results (2026-11-08)](execution-prompt-2026-11-08-results.md) | Original 0/6 scores provisional after the AppWorld defect; verified 12 attempts and preserved execution/resource evidence |
| [Offline policy and attained-success figures (2026-11-08)](policy-curves-2026-11-08.md) | Paired curves, timestamp and reservation coverage, 55 focused checks; historical/synthetic render validation only |
| [Bounded Qwen3-14B pilot qualification (2026-11-08)](qwen14b-pilot-qualification-2026-11-08.md) | 186 integration checks passed, failed default screen preserved, separate corpus passed and FP32 calibration; [evidence](qwen14b-pilot-qualification-2026-11-08.json) |
| [Separate 14B executable-action pilot plan (2026-11-08)](execution-qwen14b-2026-11-08-plan.md) | Predeclared six-cell fallback, unchanged task/sampling/budget settings, fresh validation required |
| [Checkpoint eligibility and cost repair (2026-11-08)](checkpoint-repair-2026-11-08.md) | Completed-source rejection, prefix cost preservation, cleanup accounting and 64 CPU checks; [evidence](checkpoint-repair-2026-11-08.json) |
| [Bounded GCP L4 attempt (2026-11-08)](gcp-reference-2026-11-08.md) | Verified setup and weights, pre-load cap rejection, estimated $1.98 cost and completed cleanup; [evidence](gcp-reference-2026-11-08.json) |
| [Numerical screen and FP32 calibration (2026-11-08)](reference-calibration-2026-11-08.md) | Original failed screen, independent higher-precision diagnosis, revised gate, failed separate corpus and explicit bounded-pilot qualification; [evidence](reference-calibration-2026-11-08.json) |
| [Corrected-sampler paired results (2026-11-08)](sampling-repair-2026-11-08-results.md) | Both arms scored 0/6, bounded errors, verified seed variation, and conservative preemption handling; [evidence](sampling-repair-2026-11-08-results.json) |
| [Sampling repair validation and relaunch (2026-11-08)](sampling-repair-2026-11-08-validation.md) | Overnight setup failure, completed GPU validation, active paired run, and measured storage; [evidence](sampling-repair-2026-11-08-validation.json) |
| [Broader 8B pilot completion (2026-11-08)](baseline-qwen8b-2026-11-08-completion.md) | All 38 outcomes, offline scores, resource summary and artifact hashes; [evidence](baseline-qwen8b-2026-11-08-completion.json) |
| [Corrected sampling and agent retry (2026-11-07)](sampling-repair-2026-11-07.md) | Seeded sampler repair, optional bounded error handling, validation and isolated twelve-rollout submission |
| [Corrected-sampling diagnostic plan (2026-11-07)](sampling-repair-2026-11-07-plan.md) | Isolated managed runtime, RNG and checkpoint validation, and a paired twelve-rollout test of bounded execution guidance |
| [Partial 8B trajectory diagnosis (2026-11-07)](baseline-qwen8b-2026-11-07-trajectory-diagnosis.md) | 24 inspected attempts, error-loop and budget attribution, sampling-generator defect, and fix priorities; [evidence](baseline-qwen8b-2026-11-07-trajectory-diagnosis.json) |
| [Broader 8B baseline plan (2026-11-07)](baseline-qwen8b-2026-11-07-plan.md) | Declared 38-rollout dev pilot: all 19 families, two replicate seeds, unchanged candidate prompt and full-cache settings |
| [Runtime and baseline validation (2026-11-07)](runtime-baseline-validation-2026-11-07.md) | Managed environments, 8B/14B live GPU tests, paired prompt diagnostic, corrected historical audits; [evidence](runtime-baseline-validation-2026-11-07.json) |
| [November 7 baseline investigation](full-cache-investigation-2026-11-07.md) | Full-cache failure mechanisms, audit classification gap, live CPU confirmation, and fix priorities |
| [Baseline investigation evidence](full-cache-investigation-2026-11-07.json) | Verified trajectory hashes, per-turn error categories, execution status, and live probe results |
| [November 6 trajectory audit](trajectory-audit-2026-11-06.md) | Separate seed-17 and seed-18 offline symptom summaries; both reproduced by the November 7 investigation |
| [October 20 pilot results](retention-pilot-2026-10-20.md) | Completed 32-attempt comparison, uncertainty, cost, trajectory observations, and remaining research work; reviewed October 31 |
| [Completed analysis](retention-pilot-2026-10-20-analysis.json) | Shared condition and paired estimates with standard errors, intervals, and resource coverage |
| [Per-attempt results](retention-pilot-2026-10-20-attempts.csv) | All 32 outcomes and selected measurements, with missing data left empty |
| [Completion evidence](retention-pilot-2026-10-20.json) | Resolved config, revisions, validation, integrity checks, and artifact hashes |
| [Retention figure](retention-pilot-2026-10-20.svg) | Success, budget-accounted time, and occupied KV with pointwise uncertainty |
| [2026-10-16 validation report](validation-2026-10-16.md) | Insomnia setup observations, integration checks, task attempts, and remaining limitations |
| [Initial validation evidence](validation-2026-10-16.json) | Revisions, retention matrix, checks, measurements, and artifact hashes |
| [Follow-up validation evidence](validation-2026-10-16-followup.json) | Larger-context attempts, live memory refusal, process interruption/resume, and offline scoring |
| [Paired retention pilot plan](retention-pilot-2026-10-17-plan.md) | Declared task sample, model departure, common budgets, and uncertainty analysis |
| [14B pilot preflight evidence](retention-pilot-2026-10-17-validation.json) | Model hashes, GPU persistence/capacity/cap checks, and hardware failure records |
| [Infrastructure-compromised pilot](retention-pilot-2026-10-17-quota-failure.json) | All 32 outcomes and original hashes from the run affected by compiler-cache quota exhaustion; excluded as a whole from the repaired comparison |
| [Repaired-pilot interruption](retention-pilot-2026-10-17-interruption.json) | Historical driver stall, preservation of 25 terminal cells, and conservative continuation policy |
| [October 19 queue follow-up](retention-pilot-2026-10-19-status.json) | Historical pending-job snapshot and eligibility change; superseded by the October 20 completion evidence |

See the [validation guide](../validation.md) for reusable check instructions.
