# COMET: new Qwen implementation and compaction study

The previous execution goal has been cleared. Old model runs are stopped and
superseded plans are archived in Git. Do not resume the legacy 4B/8B/14B pilots.
The November 8 execution request activates this plan; the user authorized
autonomous implementation and experiments with smaller models first. The new
Qwen3.5-9B runtime, frozen L4 study, supplemental Blackwell comparisons and
resource handoff are complete. Legacy pilots stay retired.

## Central result

Produce a clean, fine-grained **compaction aggressivity versus test-time task
success rate** plot that tells the reader something about accuracy, memory and
compute tradeoffs. A sweep that is entirely 0% or entirely 100% is insufficient
as the intended deliverable. Find a useful intermediate regime on train/dev;
retain and report flat outcomes rather than hiding or manufacturing differences.

- X: percentage of eligible KV entries removed, increasing with aggressivity.
  Candidate grid: **0, 10, 20, 30, 40, 50, 60, 70, 75%** removal. Refine or extend
  around a transition on dev before freezing. Keep full-cache and the original
  80%, 50% and 25% retention anchors.
- Y: AppWorld task success, with separate single-attempt and budget-matched
  oracle best-of-N views. Oracle is a perfect-selection upper bound.
- Compare the required methods with readable recovery/budget panels, paired
  task-bootstrap uncertainty, actual sample counts and all failures retained.
- Support the main figure with runtime, actual attempts, occupied KV, total peak
  VRAM, decoding throughput, estimated FLOPs and recovery overhead.

Canonical committed plan: [research direction](documents/research-direction.md).

## 1. Select the new model and infrastructure

Candidate names supplied by the user:

- Qwen3.5-9B
- Qwen3.5-27B
- Qwen3.5-35B-A3B
- Qwen3.6-35B-A3B
- Qwen3.8-27B

The former 14B ceiling is superseded. Official identities are now verified;
Qwen3.5-9B is selected and qualified on the recorded L4 and Blackwell setups.

- [x] Verify official repositories, revisions, licenses, weight formats, reasoning
  modes and architecture. See `documents/hybrid-backend.md`; the user removed
  the unavailable 14B candidate.
- [x] Select a practical model and shared serving backend for the required
  compaction/recovery comparisons. Do not masquerade a new architecture as Qwen3.
- [x] Define hybrid/recurrent/expert state, checkpoint and full-history recovery
  semantics. Specify exactly what the retention denominator includes and which
  states remain fixed; distinguish active parameters from resident model memory.
- [x] Review GPU fit, runtime and cost under the user's autonomous execution
  authorization. Prioritize 9B on available 48 GB Insomnia GPUs, monitor queues,
  and retain the $40 cumulative GCP ceiling. See `documents/hybrid-backend.md`.
- [x] Pin dependencies/assets and implement one shared integration rather than
  method-specific runners. Preserve AppWorld and offline scoring unless an
  explicit research decision changes them.

The existing GCP ceiling remains **$40 total**. Two completed cloud jobs have a
combined estimate of about **$3.54**, not a billing measurement; **$10 remains
reserved pending reconciliation**. Four short failed launches retain $3 each;
the completed baseline retains $3.25, one canceled startup $0.50, and the bounded
completed seven-hour L4 session retains a $10 allowance, leaving
**$4.25 uncommitted**. See the
[cloud ledger](documents/records/qwen9b-cloud-ledger.json). The completed L4 cohort uses a 21 GiB cap; supplemental Blackwell runs use
a separately qualified 24 GiB cap. Vast.ai still requires a separate spending
decision and is a last resort. The November 8 execution request authorizes the
new experiments within the existing GCP ceiling.

## 2. Validate the foundation once, at the intended settings

- [x] Validate model loading, chat/reasoning protocol, sampling and numerical
  output with an appropriate independent reference; do not inherit legacy
  numerical exceptions.
  A6000 reference/state checks and the corrected official-template checks passed;
  qualification of each alternate GPU/cap remains separate.
- [x] Validate persistent state across turns, saved checkpoints and independent
  branches for all required methods, including every hybrid state type.
  A6000 check `hybrid-third` passed all 24 method/retention branches.
- [x] Validate one full-history recovery, reapplication of retention, unchanged
  environment effects, RNG continuity, and transient memory-cap enforcement.
  The live L4/AppWorld fixture passed all three methods; the separate 16K check
  establishes intended-context headroom. See `qwen9b-l4-appworld-recovery.json`.
- [x] Validate fresh AppWorld attempts and isolated resets, correct saved-state
  evaluation, interruption/resume accounting and offline-only scorer access.
  AppWorld live checks, the scored arithmetic task and L4 process-kill validation
  passed; see `documents/records/qwen9b-l4-resume.json`.
- [x] Run the live check for the retained optional environment-initialization
  path before enabling it experimentally. User approved one fixed train-world
  initialization/close measured separately; every experimental reset/tool/
  checkpoint/rebuild remains charged. CPU checks are not live qualification.
  Passed in `hybrid-second` and `hybrid-third`.
- [x] Establish context/output limits and resource headroom that do not obscure
  the task comparison. Preserve and diagnose infrastructure failures.
  All four methods passed 16K generation and compressed recovery under the
  21 GiB L4 cap; the v4 baseline had no context or memory failures.

Use managed profiles and `scripts/run_checks.sh`. Avoid repeated environment
copies, large all-in-one jobs and one-off launch frameworks. Use one owned environment per active profile, bound jobs, retain compact
provenance, and stop when checks fail. Rebuild cleaned caches only as needed.

## 3. Establish an informative baseline and aggressivity sweep

- [x] Declare a train/dev sample by task-family coverage or a reproducible rule,
  not by which tasks happened to succeed. Record prior dev exposure.
  See `documents/records/qwen9b-study-2026-11-09.md` and the baseline config.
- [x] Establish useful full-cache task success. Inspect ordinary trajectories for
  task interpretation, API use, pagination and premature completion failures.
  Larger parameter count alone is not qualification.
  The v4 train protocol solved 3/4 tasks at 16,384 tokens; earlier 0/4 and
  1/4 outcomes remain recorded. The remaining failure confuses Spotify review
  IDs with song IDs, rather than exceeding context or memory.
- [x] Measure reset, tool, inference, compaction and recovery costs to choose
  granular runtime budgets and attempt limits. Keep one budget per task/seed/
  condition; never give each attempt a fresh budget.
  Full-cache arithmetic fit two completed attempts in 114.5 seconds, while the
  file task took about 125 seconds for one. Independent 90/120/150-second
  endpoints are declared; 16K recovery costs 21.6-22.8 seconds on the L4.
- [x] Run a small matched full-cache/compressed comparison, then the declared
  fine-grained grid. Keep every measured point, including flat/failed outcomes.
  The L4 grid measures all 25 conditions; the separate three-task Blackwell
  grid completed all 78 cells and shows intermediate outcomes. No pooling.
- [x] Extend or refine dev settings only as a new declared experiment version.
  Confirm an informative regime on separate dev coverage before final freezing.
  The two-family confirmation found full-cache oracle success on one family
  versus none at 25% retention; all single first attempts failed.

## 4. Recovery and test-time compute

- [x] Q1: branch from identical saved pre-compaction state and compare never,
  fixed-tool-count and context/tool-threshold recovery within each method and
  retention level. Tune thresholds only on train/dev.
  All 28 L4 arms and 84 three-family Blackwell branches completed. Recovery
  produces both benefits and harms; effects do not generalize across settings.
- [x] Q2: compare full-cache and compressed oracle best-of-N, with/without
  recovery, under identical wall-clock and peak total-VRAM caps.
  The frozen L4 study completed 68 cells and 101 attempts; AgentKV 50%
  recovery solves 1/2 tasks versus 0/2 without recovery or with full cache.
  R-KV 80% recovery harms success. N=2 adds no success on this test sample.
- [x] Independently rerun granular runtime budgets; do not treat truncation of
  one long trajectory as a rerun with a shorter budget.
  The paired 90/120/150-second runs completed and were scored separately.
- [x] Freeze model, backend, prompts, sampling, context limits, task/split IDs,
  paired seeds, retention grid, thresholds, N, memory and timing definitions.
  `configs/qwen9b/final-l4-v1.json` preserves the November 9 freeze.
- [x] Execute fresh-start final evaluation without evaluator feedback online.
  Preserve paired task structure; retain timeout/OOM/infeasibility outcomes.
  Two predeclared test families, seed 17, 120 seconds and 21 GiB; all outcomes
  retained and separately scored after execution. No observed cap violation.

## 5. Deliver answers and figures

- [x] Central aggressivity-versus-task-success figure, single attempt and oracle
  best-of-N distinguished, with useful dev-selected operating range and paired
  uncertainty. No fitted or fabricated intermediate measurements.
- [x] Supporting memory, latency, throughput, FLOPs, attempts and recovery-cost
  figures; clearly label occupied KV, reserved pools and total VRAM separately.
  Eight frozen-test figures and the synthetic 16K capacity figure are exported.
  See `documents/records/qwen9b-findings.md`.
- [x] Answer Q1 and Q2 with effect sizes, task counts, uncertainty, trigger
  admissions/refusals and limitations, including genuine negative results.
- [x] Export publication-ready PNG/SVG/PDF and machine-readable summaries with
  versioned configurations and portable artifact identities.

## 6. Finish supplemental runs and resource handoff

- [x] Retrieve and analyze the already launched three-family Blackwell fine
  grid and Q1 diagnostic, keeping their hardware cohort separate from L4.
  Both complete runs passed local scored-run verification; 27 figure exports
  and full summaries are linked from `documents/records/qwen9b-blackwell-findings.md`.
- [x] Verify cloud and cluster jobs have ended, preserve useful artifacts and
  record cleanup. The optional Blackwell test replication is not required if
  its predeclared access, dev-confirmation or launch-time gates cannot be met.
  No GPU jobs remain. Completed outputs are retrieved; the 1.237 GiB cloud
  backup is retained after an incomplete global transfer. The optional frozen
  Blackwell test was not executed because queue estimates exceeded the deadline.
  See `documents/records/qwen9b-resource-handoff.json` and
  `documents/records/qwen9b-final-blackwell-status.json`.

## What to reuse

- Shared runner, AppWorld adapter, repaired offline scoring, budget/resume/state
  invariants, paired analysis, plotting and managed setup/check launchers.
- Existing native implementation as a reference, not as proof of support for
  the new models. Keep unsupported-model checks strict until integration exists.
- [Compact legacy evidence](documents/records/legacy-results.md): prior baseline
  failures, verified state checks and the measured five-point inference-cost
  figures. These are historical, not results for the new Qwen study.

Obsolete configs, plans and run diaries are available at Git commit `55fca50`.
The completed cleanup and resource records are indexed in
[documents/records/README.md](documents/records/README.md).
