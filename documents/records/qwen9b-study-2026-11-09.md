# Qwen3.5-9B study: declared samples and execution

This is the new hybrid study, separate from legacy results. The user authorized
autonomous execution, smaller models first, queue-aware hardware selection and
reasonable difficulty adjustments. See [the backend decision](../hybrid-backend.md).

## Outcome-independent sampling

For each split, group IDs by the part before the final underscore. Rank families
by SHA-256 of `comet-qwen9b-v1:` followed by the family ID, then select variant
`_1`. Hashing defines a reproducible ordering; it is not a numerical acceptance
test. Do not inspect test outcomes to select tasks.

- Initial train capability/cost pilot: `34d9492_1`, `76f2c72_1`, `771d8fc_1`,
  `692c77d_1`. Covers file organization, file-based arithmetic, phone deletion,
  and Spotify updates.
- Reserved further train coverage: `e3d6c94_1`, `29caf6f_1`, `aa8502b_1`,
  `22cc237_1`.
- Dev tuning order: `b119b1f_1`, `fac291d_1`, `4fab96f_1`, `0d8a4ee_1`.
- Separate dev confirmation order: `4ec8de5_1`, `396c5a2_1`, `37a8675_1`,
  `d4e9306_1`.
- Reserved test order: `59fae45_1`, `042a9fc_1`, `83a7951_1`, `325d6ec_1`,
  `634f342_1`, `425a494_1`, `13547f5_1`, `09b0ee6_1`. Only split IDs were
  inspected when defining this order. Final count and settings remain unfrozen.

Legacy runs exposed train/dev tasks and informed general authentication and
pagination guidance. These are not pristine development tasks. No new-model
test outcome has been inspected. The small sample and one initial replicate
seed are feasibility choices, not evidence of broad benchmark performance.

## First configuration

`configs/qwen9b/train-baseline-v1.json` declares 300 seconds per task, one
attempt, seed 17, 8,192 raw tokens, 1,024 generated tokens per turn, BF16 and
a 40 GiB total-VRAM cap on one NVIDIA RTX A6000. Nonthinking sampling uses
temperature 0.7/top-p 0.8, with top-k disabled and no presence penalty. The
prompt gives general API/authentication/pagination guidance, not task answers.

The optional one-time train environment initialization must pass its live
isolation check before this configuration is executed. Every experimental
reset, tool call, checkpoint, recovery and cleanup remains charged.

## Evidence so far

- Runtime and selector packaging committed at `e3e9fcb`; local CPU checks:
  331 passed, one optional numerical module skipped, 15 live checks deselected.
- Hybrid implementation committed at `ee27663`; local CPU checks:
  333 passed, one numerical module skipped, 16 live checks deselected.
- Fresh managed Linux hybrid environment installed successfully. The official
  9B assets were downloaded at the pinned revision. An initial CLI pattern
  invocation fetched only part of the metadata; the shared downloader was
  corrected and the snapshot completed before GPU validation.
- An A6000 validation allocation started after correcting its scheduler QoS and
  fitting a 25-minute backfill window. GPU and AppWorld results remain pending.
- GCP quota/authentication check passed for one Spot L4. No paid job submitted.
- The first live AppWorld checks found that a newly resolved FastAPI version
  removed the `embed` argument used by pinned AppWorld. The hybrid input now
  constrains AppWorld dependencies to the existing AppWorld lock, retaining
  its validated FastAPI/Starlette versions. No task outcome was collected under
  the incompatible environment. The repair requires setup and live checks again.

Large outputs remain outside tracked source. Add measured results and portable
artifact identities here only after inspection.

The second live check (`hybrid-second`, source `d8b9765`) passed all six
AppWorld integration/isolation tests. The 9B weights loaded from local scratch
in about two seconds, after substantial cold shared-library import delays.
Synthetic warmup ran all four methods. The subsequent reference prompt exposed
a Transformers 5.22 API change: chat templating returns a mapping by default.
The runner and live checks now explicitly request token IDs with
`return_dict=False`. No task outcome was collected. Three additional launcher
fixture failures came from inherited local-staging settings and are repaired.
The run retained 329 passes, 18 skips and these four failures.

The local suite after staging/plot additions passed 336 tests, with one optional
numerical module skipped and 16 live checks deselected. A managed-runtime
archive now allows identical pinned packages to be staged on local scratch;
packing, activation and configuration validation were exercised locally.

The A6000 `hybrid-third` check at `ae801bc` passed the independent full-sequence
reference comparison (logit cosine 0.99876, top-10 overlap 1.0; greedy answer
`7391`). All 24 method/retention branches passed persistent suffix generation,
checkpoint replay, full-history rebuild, RNG continuity and the one-rebuild
limit. A deliberately insufficient cap refused recovery. All four methods
completed the 8,192-token capacity check. Peak total VRAM was 29.95 GiB for full
cache, 18.66 for StreamingLLM/AgentKV and 24.13 for R-KV; peak occupied KV was
256 MiB full and 66.9 MiB compressed, including transient pre-eviction entries.
Recurrent/convolution state occupied about 49 MiB separately. These are synthetic
qualification measurements, not task-success results.
The [compact state-check artifact](qwen9b-a6000-state-check.json) preserves the
reference/capacity measurements and identifies the full 24-branch evidence.

That run had 335 passes, 17 skips and one chat-template failure. The pinned 3.5
template rejects an isolated tool response without a preceding user query.
Observation serialization now emits its verified append-only suffix, and the
live test compares it with a complete official-template dialogue in both thinking
modes. This correction still needs its live rerun.

A queue audit found available **NVIDIA RTX PRO 6000 Blackwell Server Edition**
devices (97,887 MiB reported capacity, compute capability 12.0, driver 575.57.08).
The A6000 pool was occupied after the validation allocation. The Blackwell
baseline/resume configurations retain 9B and the 40 GiB experimental cap; they
require live qualification before use. Several independent single-GPU jobs can
run concurrently when scheduler resources permit. No attempts share model or
environment state, and comparisons remain on the same GPU model.

The first long Blackwell request could not start because of host CPU contention;
it was replaced with a smaller qualification allocation. Subsequent Insomnia
monitoring was interrupted when the SSH credential agent stopped responding.
GCP still has one Spot L4 quota and no A100 quota. The declared L4 fallback
pilot uses a 22 GiB cap and 2 GiB recovery workspace, which must pass its own
capacity/state checks. It is a separate hardware cohort and cannot be pooled
with the 40 GiB Insomnia results. One bounded one-hour cloud run is reserved
at a conservative $5 including staging/network/storage overhead, within the
existing $40 total ceiling and separate $10 historical reserve. No cloud task
result is claimed from this declaration. Current [official Spot pricing](https://cloud.google.com/spot-vms/pricing)
informed the estimate; final billed charges remain distinct from estimates.

Cloud run `gpu-20261109-060734-d05896` was submitted with a 3,600-second workload
limit and zero retries. It stages only runtime source, tests, configs and locks
from `faef892`, with the upstream identity saved separately, and downloads public
pinned assets on the worker. It uses an official Ubuntu 24.04 amd64 image pinned
at `sha256:78d4744ead1f5b19b04d0df558ab182a5300903900755e515b2ca4d10eb2044d`.
Live checks gate the four-task baseline; execution is followed by separate
scoring. Submission is not evidence that provisioning or the experiment passed.

The first cloud launch ended before model loading: the L4 reports
23,570,219,008 usable bytes, slightly below the declared 22 GiB. All six
AppWorld checks and both thinking/nonthinking chat-template modes passed;
the suite had 335 passes, 17 skips and this one capacity refusal. No task
attempt ran. `train-baseline-l4-v2.json` explicitly lowers the cap to 21 GiB
while keeping the 2 GiB workspace and all other settings. The failed launch
is retained as infrastructure evidence; it is not a task-success measurement.

The failed cloud launch's 15 output files were fetched and verified; its VM,
disk, Batch job and live artifact prefix were removed. The corrected launch
`gpu-20261109-061851-5d856b` stages source `57e815e`. Reserve $5 for each
cloud launch until reconciliation, plus the separate historical $10 reserve,
leaving $20 uncommitted under the $40 ceiling. These are conservative reservations,
not billing measurements.

Checkpoint diagnostics now support clean cell segments using the existing
launcher. Saved source checkpoints and their original charges survive resume.
The CPU check compares uninterrupted and segmented trajectories, budgets, failed
source preparation, scoring and checkpoint preservation; 70 focused tests passed.
A matching L4 process-interruption configuration is prepared; its live execution
is still pending.

The corrected-cap cloud launch loaded the weights, then failed its first warmup
because FLA had cached its CPU backend. Its device discovery suppresses Triton
initialization errors. The minimal image lacked Python development headers,
which Triton's driver extension requires; the next launch adds them and probes
Triton before asset download. The engine now surfaces driver initialization
failures before loading weights. This cause still requires the fresh live probe.
The failed launch's 16 output files were fetched, and compute/live cloud artifacts
were removed. No task attempts ran. Three focused CPU checks passed after the
early driver check; the model's inference mathematics are unchanged.

Cloud launch `gpu-20261109-063527-7c75c0` stages `f87541f`, retains the declared
21 GiB L4 configuration and adds the missing system headers. Its early probe
passed: Triton CUDA target 8.9, FLA CUDA device and `Python.h` present. This
confirms the repaired toolchain. The focused shared check invocation covers
hybrid state/reference/capacity and the chat protocol (15 tests); unchanged
AppWorld isolation/scoring checks already passed in both earlier cloud launches.
The run remains bounded to 3,600 seconds with zero retries. Three cloud launch
reservations of $5 plus the historical $10 reserve leave $15 uncommitted pending
cost reconciliation; these are not billed charges.

That launch passed all 24 L4 retention branches, checkpoint replay, one-rebuild
semantics, RNG continuity and refusal at an insufficient cap. Its independent
reference had cosine 0.99892, top-10 overlap 1.0 and greedy answer `7391`.
The subsequent full-cache 8,192-token capacity check exceeded the 21 GiB cap;
the suite stopped with 14 passes and one failure, before any task attempt.
Observed non-PyTorch memory reached about 792 MiB after lazy kernel loading.
The allocator now leaves a separate 1 GiB runtime allowance rather than letting
its reserved pool consume the full initial free allowance. The experimental
cap remains 21 GiB, and failed capacity evidence is retained. The next focused
rerun keeps three method branches and all four capacity checks; it need not
repeat all 24 already-passed short-history retention branches.
The [portable L4 state record](qwen9b-l4-state-check.json) preserves the measured
reference and branch results and identifies the raw evidence.

The capacity repair runs as `gpu-20261109-065347-42f701`, source `3cc4f27`.
The prior launch was fetched and its VM, disk, job and live cloud prefix were
removed. The new launch retains the one-hour limit and zero retries. At the
unchanged conservative $5 reservation per launch, $30 is reserved including
the historical $10, leaving $10 uncommitted pending reconciliation.

The [cloud ledger](qwen9b-cloud-ledger.json) subsequently reconciles those three
short completed failures to a conservative $3 allowance each, using observed
creation-to-cleanup lifetimes below 20 minutes, a $1/hour compute allowance,
50 GiB of network processing per launch and $0.40 for other charges. The displayed
[Spot price](https://cloud.google.com/spot-vms/pricing) was $0.423016/hour in the
default table; the larger planning rate avoids asserting an exact regional bill.
[Public NAT processing](https://cloud.google.com/nat/pricing) is $0.045/GiB.
The historical $10 and active $5 reservations remain, leaving $16 uncommitted.
Neither the transfer allowance nor these totals are measured billed usage.

The headroom rerun passed its three method branches and reference comparison
(cosine 0.99902, top-10 overlap 0.8, answer `7391`) but reported another cap
failure during full-cache prefill at 3,584 tokens. Its expanded failure record
isolated an estimator race: the sampled device peak was 21,351,301,120 bytes
(19.89 GiB), while the conservative estimate was 23,270,195,200 bytes (21.67 GiB).
Reading device use before a PyTorch pool release and pool size after it falsely
inflated the external-memory component. External samples now require unchanged
pool size across the device query. A focused regression reproduces this race;
17 CPU checks passed. The 21 GiB cap, precision and inference logic are unchanged.
No task attempt ran under the faulty estimator, and the original failure remains
preserved. The fetched outputs and completed cloud cleanup identify that launch.

The final accounting correction enforces the cap against device-wide samples
at 10 ms and forward boundaries. The sum of independently observed allocator
and external-memory maxima remains a separately labeled conservative estimate,
not a measured peak. Exact PyTorch allocation/reservation peaks are also saved.
Sub-10-ms external transients remain a measurement limitation; the separate
1 GiB allocator headroom remains in place. Eighteen focused CPU checks passed.

The corrected measurement run is `gpu-20261109-071607-51dbc9`, source `ebd58fb`,
with the same 21 GiB cap and four-task baseline. Four completed short failures
now retain $3 each; the new $5 reservation and historical $10 leave $13
uncommitted under the $40 ceiling. All four prior compute cleanups are verified.


The corrected L4 run passed all 17 focused checks, including full-cache and
all three compressed 8,192-token capacity checks. Reference cosine was 0.99898,
top-10 overlap 0.9 and the greedy answer was `7391`. Measured capacity peaks
were 20.05 GiB full, 18.58 GiB StreamingLLM/AgentKV and 20.01 GiB R-KV, below
the unchanged 21 GiB cap. This qualifies the intended synthetic state/context
range on the L4; task competence is a separate question.

The first four-task full-cache pilot scored **0/4**. All four attempts stopped
after four consecutive API errors, at 67.8-130.6 seconds. Three tasks repeatedly
imported app modules instead of using the preloaded `apis` object. The phone
task tried HTTP requests, an invented client, wrong login arguments and guessed
credentials. Resets took about one second; decoding was about 13.6 tokens/s.
There were no timeout, context-limit or memory failures. See the
[portable baseline record](qwen9b-l4-baseline.json). These failures remain in
the evidence and do not establish a compaction effect.

`train-protocol-l4-v3.json` declares a matched prompt-only correction on the same
four train tasks: explicit preloaded-object examples, a documentation-first
initial action and authentication from observed account records. The examples
follow the pinned [AppWorld usage guide](https://github.com/StonyBrookNLP/appworld/blob/42b5bcf3cd334fee33f0c37c02070a9f5807add5/README.md).
Sampling, context, task/seed selection, budget and cap remain unchanged. No
answers, evaluator feedback or test outcomes inform the agent. This is a new
pilot version, not a relabeling of the failed baseline.


The baseline's 47 output files were fetched and verified, and its compute and
live cloud prefix were removed. A bounded seven-hour session replaces repeated
cold-start jobs. Plans are copied once, source is fixed within each experiment, closed cell
segments are backed up, and scoring remains outside execution. The helper's
submission timeout was explicitly extended for this job and restored to its
one-hour default immediately afterward; concurrency remains one GPU with no
automatic retries.

The first session allocation, `gpu-20261109-074144-380cde`, was canceled before
its workload started during an unnecessary mount audit. The actual returned
Batch definition already included the storage mount; no helper patch was
needed. No task computation or outputs were lost. Compute deletion was verified,
and its input/queue-only prefix was removed after retaining the local inputs
and log record. The replacement is `gpu-20261109-074439-b5e235`, source `ae8762d`.
It first executes the declared prompt-only pilot. The revised ledger reserves
$10 for up to 7.25 hours at $1/hour plus 50 GiB NAT and $0.40 other charges,
leaving $4.25 uncommitted. These remain conservative allowances, not billing.


The corrected protocol's arithmetic task reached agent completion in 66.5 seconds
and ten tool turns; correctness remains pending offline scoring. The file
organization task still hit four consecutive errors after six tool turns.
The live interruption check is therefore declared as `resume-check-l4-v2.json`
using the arithmetic train task and corrected prompt. This selects a useful
integration fixture, not a research sample or favorable test outcome. It retains
the 120-second budget, preserved/interrupted/fresh arms and existing real-process
validation harness; its outputs are explicitly ineligible as freeze evidence.


Offline scoring confirms the v3 arithmetic task is correct: **1/4 success**,
versus 0/4 under the original prompt. The other v3 attempts comprise one API
error and two context-limit failures. The phone attempt had 7,202 processed
and 1,607 pending tokens; the Spotify attempt exhausted 8,192 processed tokens.
These are ordinary observed histories, not evaluator-guided online choices.
The matched [machine-readable comparison](qwen9b-protocol-v3.json) and
[PNG](../figures/qwen9b/protocol-v3.png), [SVG](../figures/qwen9b/protocol-v3.svg)
and [PDF](../figures/qwen9b/protocol-v3.pdf) preserve all four tasks. Four tasks
provide very weak population precision; the shorter v3 duration partly reflects
context failures and is not a throughput improvement claim.

`train-protocol-l4-v4.json` is a separately declared follow-up: 16,384 raw tokens,
a working generic login example using observed credentials, token-variable reuse
and concise printing of large collections. It preserves all four tasks and the
300-second budget, 21 GiB cap, model, sampling and seed. The new context is gated
by a four-method capacity/recovery check. The raw transcript is never truncated
or summarized by the engine. The metadata-only plan initially failed because a
helper named `inspect.py` shadowed Python's standard module; the corrected plan
renames it and reads only the predeclared train/dev task metadata.


The next matched compression screen is declared as `train-compression-l4-v1`:
first two original train families, 150 seconds shared by at most two attempts,
full single/oracle controls and all three methods at 25% retention, plus fixed
and dynamic AgentKV arms. It keeps the first family's earlier failure instead
of selecting only the successful task. The budget is motivated by the measured
67-second full-cache arithmetic attempt. Fixed recovery checks four cumulative
Python executions. Dynamic recovery requires both 6,144 raw-context tokens and
three executions. The observed v3 histories reached that length after about
2-6 tools, so it can differ from the fixed trigger. These are pilot choices,
not an optimal-policy claim or frozen final settings. The queued plan is gated
on the 16,384-token qualification and a completed v4 pilot with at least one
success. This train-stage capability gate operates between experiments; no
scorer is consulted by the online runner or within an attempt schedule.


The live process-interruption harness passed in plan `02-resume-check`. Its
first and fresh arithmetic attempts reached completion in 66.7 and 67.2 seconds.
The killed attempt retained its transcript and consumed the full reserved
120-second cell budget, with no replacement attempt. Completed work survived,
incompatible configuration resume was rejected, incomplete scoring was rejected,
and all three environments were distinct. The paired initial 3,161-token prefix
was preserved. This is integration evidence, separate from task-quality evidence;
see the [portable check record](qwen9b-l4-resume.json).


The 16,384-token check passed full-cache generation and StreamingLLM recovery,
then R-KV recovery exhausted allocator headroom during its final redundancy
calculation. The pinned selector created a full quadratic integer temporary;
the failed plan and its partial measurements remain preserved. Source `0d438bf`
replaces that calculation with bounded query-row tiles, preserving the selector
rules while allowing small BF16 reduction-order differences. This explicit
source release occurs between closed experiments on the existing worker; earlier
outputs retain their original source. New source and patch identities are saved
with plan `05-tiled-context-pilot`. Its live numerical check and 16K qualification
gate the v4 baseline and the replacement compression plan `06-compression-pilot`.
The earlier plans `03` and `04` contain no v4 or compression task attempts.

A separate live fixture checks all three methods against a real AppWorld phone
mutation, saved Python state and restored hybrid checkpoints. It checks unchanged
tool effects, RNG continuity, retention, the one-rebuild limit and measured cap.
Forced fixture actions are integration evidence only, never task-success data.


Plan `05-tiled-context-pilot` passed all five numerical selector checks and all
four 16,384-token generation conditions. Every compressed method also admitted
and completed a full-history rebuild with retention reapplied. Maximum observed
total VRAM was 20.05 GiB under the 21 GiB cap; 16K rebuilds took 21.6-22.8 seconds.
See the [capacity record](qwen9b-l4-context-16384.json). The local managed CPU
suite passed 339 tests; two numerical modules lacked local Torch, and 17 live
checks were deselected. GPU numerical checks ran separately on the L4.

The [v4 capability pilot](qwen9b-protocol-v4.json) solved **3/4 train tasks**:
file organization (124.1 seconds), arithmetic (57.3 seconds), and phone deletion
(51.6 seconds). Spotify failed after confusing song IDs with review IDs and
repeated authorization/duplicate-review errors (112.8 seconds). No task reached
the context or memory limit. All four tasks and the failed earlier versions are
retained. This is a useful capability regime without changing model size.
The versions differ in prompt/context/backend, so this is descriptive evidence,
not a causal attribution of the success gain to one change.

Independent 90- and 120-second versions of the seven-condition, two-task
compression screen are declared alongside the 150-second run. The measured
124-second file attempt and 57-second arithmetic attempt motivate these endpoints
around one longer attempt or two shorter attempts. They execute fresh task
states with unchanged settings, and will be scored separately after completion.


The first closed compression segment confirms the budget boundary: full-cache
arithmetic completed two attempts in 114.5 seconds; the file task completed one
and timed out its second under the shared 150-second limit. Correctness of this
new run still awaits its separate scorer. StreamingLLM at 25% retention reached
83 tool executions and the context limit on the file task, then exhausted the
remaining budget; arithmetic timed out after 27 tool executions. Its ordinary
saved traces ask for an already supplied task or execute no-progress print/pass
blocks. The R-KV file attempt timed out after eight tools, with 15.6 seconds of
recorded compaction within 150 seconds and more generated tokens than full cache.
These are observed failure symptoms and costs, not an isolated causal attribution.

The next declared diagnostic uses one functioning arithmetic train fixture and
all 28 common-checkpoint arms at 80/50/25% retention, with 90 seconds per branch
including preparation and restore. It is a one-task mechanistic check with no
population-precision claim. The fine-grid pilot measures all eight candidate
retentions for all methods, one attempt on that train fixture within 120 seconds.
Separate confirmation uses the first two predeclared dev-confirmation families,
all seven initial pilot conditions and the 120-second/N=2 setting. No held-out
test task has run or informed these declarations.

Cloud CLI credential renewal required interactive sign-in during the compression
pilot. The already authenticated browser console still exposes the running job
and its result store; queued plans run independently of the local CLI session.
The sign-in handoff is pending while browser-based monitoring continues.


The final candidate is now explicit but **not frozen or launched**: the first two
predeclared test-normal families, seed 17, 120 seconds, N=2, one L4 and the same
21 GiB cap. It retains all 29 core conditions and five supplemental AgentKV
no-recovery points (90/70/60/40/30% retention), for 34 conditions and 68 cells.
The separate train pilot covers the full eight-level grid for all three methods.
Focusing supplemental final points on AgentKV saves 40 maximum GPU-minutes
compared with 44 conditions, preserving time for the complete core matrix and
recovery diagnostic. This is a declared time-limited scope reduction, not a
selection using test outcomes. Competitors' unmeasured intermediate final points
must not be implied. Freeze requires completed 120-second pilot/dev evidence,
at least one dev success, and both successes and failures in the train fine grid.
The two-task/one-seed final remains a small research study with weak population
precision; all failures and uncertainty must be reported.

The browser console session also expired at approximately 09:21 UTC. Both cloud
access routes now require Columbia sign-in. Queued computation remains bounded
and independent of this local authentication interruption; final freezing,
retrieval and additional launches await renewed access.
