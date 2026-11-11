# Research contract

COMET tests whether recovering cached history improves agent task success beyond
further compressed attempts under a fixed runtime budget and memory cap. The
study uses Qwen3.5-9B on AppWorld through the shared Transformers hybrid backend.
This replaces the original proposal's Qwen3-8B/Mini-SGLang/A100 assumptions;
legacy pilots are historical, not pending work. See the
[backend decision](hybrid-backend.md), [proposal](proposal.pdf) and
[completed results](records/README.md).

## Questions and central plot

- **Q1:** Within each eviction method and retention setting, compare a
  context-length/tool-count recovery trigger with never-rebuild and fixed-tool-count
  policies, starting from identical saved pre-compression checkpoints.
- **Q2:** Compare compressed oracle best-of-N with and without recovery at 80%,
  50% and 25% retention against full-cache best-of-N, with matched budgets and caps.

The central plot shows **compaction aggressivity versus task success**. With
retention $r$, the horizontal axis is $100\left(1-r\right)$ percent of eligible
attention KV entries removed. Show first-attempt and oracle success separately,
with recovery-policy and budget panels, sample counts and paired task-bootstrap
intervals. Oracle selection is a perfect-outcome-selection upper bound, not an
online policy. Supporting figures report attempts, latency, throughput, occupied
KV, total peak VRAM, estimated FLOPs and recovery cost.

Find an informative operating regime on train/dev and confirm it on separate dev
coverage before freezing test settings. An all-zero or all-one pilot is a reason
to revisit the declared design, not to hide outcomes. Retain every predeclared
point and failure even if the final test curve is flat. Never choose favorable
test tasks, fabricate differences or imply unmeasured intermediate points.

## Fixed comparisons

| Component | Contract |
| --- | --- |
| Model and benchmark | Qwen3.5-9B, AppWorld, pinned model/tokenizer/data revisions |
| Engine | Shared Transformers hybrid backend and pinned AgentKV selectors |
| Methods | Full KV, StreamingLLM, R-KV and AgentKV |
| Retention | Separate 100% control; required 80%, 50% and 25% compressed anchors |
| Recovery | Never, fixed tool count, context-length/tool-count trigger; at most one rebuild per attempt |
| Execution | Sequential attempts, batch size one, paired seeds and identical task subsets |
| Controls | Single-attempt full cache and budget-matched full-cache oracle best-of-N |
| Hardware | Same qualified GPU model/count and experimental total-VRAM cap within each comparison |

Retention counts full-attention KV entries relative to full-cache inference at
the same raw-token step, with the [documented rounding and mandatory floors](hybrid-backend.md).
It is not a fraction of GPU capacity or a shorter text prompt. Recurrent state is
preserved and counted separately. Recovery reconstructs all model state from the
full transcript, reapplies retention and never replays tools or rolls back actions.

Each task/condition/seed has one shared wall-clock budget across all attempts.
Resets, tools, checkpoint preparation, recovery, saving and cleanup are charged.
Model initialization and post-hoc evaluation are excluded consistently. A versioned
config may opt into one isolated train-environment initialization/close per launch,
measured separately without tools, model observations or evaluator access.
Timeouts, OOM and infeasibility stay in the denominators. Recovery must fit the
same transient memory cap; failed attempts receive no replacement budget.

## Resolution and freezing

The measured supplemental retention grid is 25%, 30%, 40%, 50%, 60%, 70%, 80%
and 90%, alongside full cache. Finer train/dev grids and neighboring trigger
thresholds are authorized when declared as new versions. Preserve the required
anchors and distinguish supplemental coverage from the core matrix. The initial
dynamic policy changes when to rebuild, not retention or the attempt ceiling.

Run each declared runtime budget independently. An attained-success curve from
completion timestamps describes one executed schedule; it is not a rerun at
shorter budgets. Rebuild admission can depend on remaining time.

Freeze the model/backend/device, exact task/split IDs, prompts, sampling, seeds,
context/output limits, behavior at those limits, attempt ceiling, wall-clock
budget, total-VRAM cap, retention grid and trigger thresholds before test.
Context length and tool-count definitions, threshold combination and check timing
must be explicit. Frozen changes define a new experiment version. See the
[workflow](experiments.md) for freeze, execution and resume commands.

Additional models, benchmarks, methods, summarization, quantization, training or
alternative search strategies require a separate research decision. Larger Qwen
candidates remain unsupported until their identities and complete attention,
recurrent and expert-state handling are verified and qualified.

## Hardware and qualification

Alternative adequately sized GPUs are authorized; A100 availability must not
block progress. The completed study qualified one L4 at 21 GiB and a separate
RTX PRO 6000 Blackwell Server Edition cohort at 24 GiB. GPU capacity is not the
experimental cap. Keep these cohorts separate; different devices and host/storage
costs are not a controlled hardware comparison.

Before using another device/cap, validate numerical output and sampling, all
persistent state, compaction, checkpoints, recovery peaks, AppWorld isolation and
interruption accounting over the intended range, then run train/dev pilots.
Do not qualify a new model or device from legacy tests. Preserve the exact runtime,
local selector patches and measured evidence. Multi-GPU configurations require
explicit topology, device-count and memory-accounting support.

Use appropriately sized cluster resources where practical. The existing GCP
ceiling is $40 total, including temporary storage; consult the
[ledger](records/qwen9b/cloud-ledger.json) before paid provisioning. Historical
allowances are not measured billing. The proposal's 50-100 GPU-hour estimate was
provisional; derive future budgets from measured pilot costs.
