# Agent instructions

## Scope and source of truth

These instructions apply throughout this repository. Read [README.md](README.md), [the current research direction](documents/research-direction.md), and [documents/proposal.pdf](documents/proposal.pdf), especially sections 5-8, before changing experimental behavior. The November 8 model pivot supersedes the proposal's original model/hardware assumptions; the implementation and collaboration conventions below keep the four contributors on one pipeline.

The repository now has the shared pipeline described in [documents/experiments.md](documents/experiments.md). Inspect the implementation, [validation guide](documents/validation.md), and applicable evidence in [documents/records/](documents/records/README.md) before assuming an integration or experiment has been validated. Add verified setup and execution instructions alongside changes. Keep the README human-facing and free of dense technical details.

General documents must be independent of individual accounts, workspaces, and run history; put personal notes and run-specific observations in `documents/records/`. Omit account-specific access details and unshared storage locations from committed records; use portable artifact identifiers and hashes instead.

Implement the agreed experiments before expanding scope. Do not silently replace the model, benchmark, inference engine, methods, metrics, or budget semantics. Record any user- or team-authorized departure from the proposal in `documents/`, with its rationale and affected comparisons, and update the corresponding instructions and configs. Routine implementation choices do not need a new research decision.

The active direction is the newer Qwen candidate family listed in [documents/experimental-models.md](documents/experimental-models.md), including models above 14B. Stop treating the legacy 4B/8B/14B baselines or their old plans as pending work. Verify exact official identities and design the necessary backend/state support in the next implementation phase. The shared Transformers hybrid backend now implements Qwen3.5-9B as the first candidate; see [the backend decision](documents/hybrid-backend.md). Other new architectures remain unsupported. Keep backend/model guards strict and do not claim qualification from legacy tests. The subsequent execution request authorizes new experiments and adequately sized resources.

The central deliverable is a fine-grained compaction-aggressivity versus task-success curve with informative intermediate behavior, paired uncertainty and explicit test-time budgets. Find that operating regime on train/dev and freeze before test. Do not manufacture differences, drop flat outcomes or select favorable test tasks.

## Research contract

COMET tests whether recovering cached history improves agent task success beyond further compressed attempts under a fixed runtime budget and memory cap.

- **Q1:** Within each eviction method and retention setting, compare a context-length/tool-call-count recovery trigger against never-rebuild and fixed-tool-count rebuild policies.
- **Q2:** Compare compressed oracle best-of-N with and without recovery at 80%, 50%, and 25% retention against full-cache best-of-N under the same runtime budget and peak VRAM cap.

The initial dynamic policy decides when to recover. It does not adapt the retention level or attempt limit during evaluation. Additional models, benchmarks, eviction methods, text summarization, quantization, training, and alternative search strategies are outside the main experiment matrix unless the team changes the plan. Papers in the proposal's literature review are context, not additional implementation requirements.

The user authorized adequately sized alternative GPUs for pilots and final evaluation on November 8, 2026. Follow [documents/experimental-hardware.md](documents/experimental-hardware.md); A100 availability must not block progress. Qualify the selected device and preserve comparable caps and budgets.

### Fixed setup

| Component | Required setup |
| --- | --- |
| Model | Qwen3.5-9B as the first candidate, pending train/dev qualification |
| Benchmark | AppWorld |
| Inference engine | Shared Transformers hybrid backend for the 9B study; Mini-SGLang remains legacy |
| Hardware | A qualified GPU configuration selected for the new model; match device model/count and caps within each comparison |
| Execution | Sequential attempts, batch size 1 |
| Baseline | Full KV with eviction disabled; one attempt and budget-matched oracle best-of-N |
| Eviction methods | StreamingLLM, R-KV, and AgentKV using the existing AgentKV engine implementations |
| Retention | 100% full-cache control; 80%, 50%, and 25% compressed conditions |
| Recovery policies | Never rebuild; fixed tool-count trigger; context-length/tool-count threshold trigger |
| Recovery limit | At most one full-history rebuild per attempt |

Retention is the fraction of KV entries that full-cache inference would store at the same step, not a fraction of GPU capacity or a shortened text prompt. Record the rounding and accounting conventions, including any mandatory retained entries, so all methods use the same denominator. Keep the full-cache control separate from compressed conditions.

The user also authorized finer experiment settings. Follow [documents/experimental-resolution.md](documents/experimental-resolution.md): retain the required retention anchors and core matrices, add explicitly declared supplemental retention/runtime/trigger points on train/dev, and freeze any final additions before test evaluation. Do not modify active configurations or select favorable test outcomes.

The proposal cites these legacy implementation revisions as starting points, not as proof of support for the new candidates:

- [AgentKV](https://github.com/LiuTaowen-Tony/agentkv/tree/b5280b7c42bd90962712c19f8e0047c89ca40d6d): `b5280b7c42bd90962712c19f8e0047c89ca40d6d`.
- [kv-management-minisgl](https://github.com/LiuTaowen-Tony/kv-management-minisgl/tree/254c57bc84e4a7895159ba1062bd46c83626f511): `254c57bc84e4a7895159ba1062bd46c83626f511`.
- Within that engine, the cited eviction implementations are `python/minisgl/eviction/streamingllm.py` and `python/minisgl/eviction/r1kv.py`.

Pin and record actual dependency revisions and local patches. Do not silently track upstream main branches or substitute a different serving engine to make one method easier to run.

## Shared pipeline

Use one configuration-driven pipeline for all methods. Method and recovery-policy selection must not create separate copies of task execution, budget enforcement, or evaluation logic.

1. **Integration checks:** Validate AppWorld execution and reset, full-cache inference, each eviction implementation, compressed KV persistence across turns and checkpoints, and full-history recovery. Surface unsupported paths instead of silently falling back to full KV.
2. **Train/dev pilot:** Measure feasibility and cost, tune triggers, and freeze the experiment settings before test evaluation. The provisional compute estimate is 50-100 GPU-hours, not a measured requirement. If necessary, reduce tasks, samples, or configurations during the pilot while preserving comparable budgets; record any scope reduction.
3. **Checkpoint diagnostic:** Branch from identical saved pre-compression agent and environment checkpoints. Preserve the state needed to reproduce each branch, including transcript, KV state, and random state. After branching, let each trajectory evolve independently. Compare recovery policies within each method and retention condition, with the 100% control available for reference.
4. **Final evaluation:** Start every attempt from the task's initial environment state. Use the same task subset, prompts, sampling settings, and paired seeds across methods. Do not reuse diagnostic continuation checkpoints as final-evaluation starting states or carry state between attempts.
5. **Post-hoc scoring and analysis:** After all attempts for a task/configuration have finished, run the AppWorld evaluator on saved outcomes. Aggregate results through a shared analysis path. Keep pilot, diagnostic, and final-evaluation outputs distinguishable.

### Settings to freeze

The proposal does not supply numerical values for the following. Establish them on train/dev, store them in a versioned configuration, and do not invent defaults presented as settled experiment choices:

- Per-task wall-clock budget and peak VRAM cap. The GPU's capacity is not itself a chosen experimental cap.
- Maximum context length and the behavior when that limit is reached.
- Sampling settings, prompts, maximum attempts N, and the seed schedule.
- Task count, split identifiers, and exact task subset.
- Fixed tool-count threshold and dynamic context-length/tool-count thresholds, including the trigger rule and when it is checked.

Define observable context length and tool-call count consistently, including whether counts are cumulative or measured since a checkpoint. Tune thresholds only on train/dev tasks. Freeze these definitions with the settings. Do not use test outcomes to retune policies or choose a favorable subset. A changed frozen setting defines a new experiment version; do not mix its results into the old comparison.

## Recovery and state semantics

- Retain the current attempt's full raw token transcript independently of the compressed KV cache. Recovery re-prefills that transcript and then reapplies the configured retention policy.
- Recovery does not summarize or truncate history, restart the task, roll back the environment, or replay tool actions. Historical tool calls are transcript content during re-prefill, not commands to execute again.
- Allow at most one rebuild per attempt. Log the trigger inputs, decision, rebuild cost, and whether recovery was disallowed by the cap.
- Disallow a rebuild that cannot fit the peak VRAM cap, including its transient allocation. Do not temporarily bypass the cap or switch precision to make recovery fit.
- Preserve KV state across agent turns. An unintended full re-prefill on every turn would introduce unrecorded recovery and invalidate the comparison.
- Keep each attempt's environment and agent state isolated. A retry or resumed job must not inherit tool effects from a different attempt.

## Budget and evaluation invariants

- All attempts for a task/configuration share one wall-clock budget. N is an upper limit, not a promise that N attempts will fit. Do not grant each attempt a fresh per-task budget.
- Charge attempts, tool calls, experimental environment resets, checkpoint preparation, and rebuilds to that same budget. Exclude model loading and post-hoc evaluation consistently. The user approved one fixed train-environment initialization/close per launch outside task timing, recorded separately with no model observations or tools; opt in through a versioned config and keep historical accounting unchanged. Record all timings by component.
- Enforce the same peak VRAM cap across comparisons, including transient rebuild peaks. Track peak total VRAM separately from peak KV-cache memory; they are not interchangeable.
- Count timeout and out-of-memory attempts as failures. Report infeasibility separately without silently dropping failed tasks/configurations from comparisons or giving them free replacement attempts.
- The primary metric is **oracle task success rate within budget**: the fraction of tasks solved by any of up to N attempts. Label this as an upper bound assuming perfect outcome selection, not an online selection policy.
- AppWorld evaluator feedback must never select actions, trigger recovery, rank attempts during execution, or stop further attempts after a successful score. Keep the evaluator outside the online runner. Ordinary task observations and tool responses remain available to the agent.
- Also report single-attempt success, actual attempt counts, estimated inference FLOPs, end-to-end latency, decoding throughput, and peak KV-cache memory. Document metric units, timing boundaries, and the FLOPs estimation method; do not present estimates as measurements.
- Use paired comparisons across seeds and task-bootstrap confidence intervals. Resample tasks, preserving their associated attempts and paired conditions, rather than treating attempts as independent tasks.

## Implementation and collaboration conventions

These are repository conventions for implementing the proposal, not claims that the directories already exist. Add them as needed:

| Location | Purpose |
| --- | --- |
| `src/comet/` | Shared engine integration, AppWorld adapter, recovery policies, runner, evaluator, and analysis |
| `configs/` | Versioned pilot and frozen experiment configurations |
| `scripts/` | Thin entry points that call shared package code |
| `tests/` | Focused tests of state, recovery, budgets, and evaluation behavior |
| `documents/` | General proposal, implementation, setup/run instructions, and shared experimental decisions |
| `documents/records/` | Personal notes, dated execution/validation records, and artifact inventories |

Keep execution, scoring, and analysis separately callable while sharing configuration and artifact definitions. A notebook may explore recorded outputs; it must not become the only implementation of a required experiment or metric. Avoid adding a general framework or unrelated dependencies when a small explicit interface suffices.

Before changing a shared interface, inspect its callers and existing work. Keep configuration fields, checkpoint formats, and result schemas consistent across contributors; document changes and update affected consumers together. Use the planned roles in the README for coordination, not as exclusive ownership of files. Preserve others' uncommitted changes and keep patches scoped to the task.

For every run, preserve enough information to reproduce and audit it:

- Run ID, stage, code commit and local changes, dependency/model/tokenizer revisions, hardware, and resolved configuration.
- Task/split ID, seed, attempt index, method, retention, and recovery policy.
- Raw token transcript, tool observations/actions, recoverable checkpoints where needed, and final environment state or an equivalent evaluator-compatible artifact.
- Trigger decisions, component timings, memory measurements, attempt status/failure reason, and separately produced evaluator outcomes.

Save intermediate trajectories and completed results so interrupted work can resume without rerunning completed computation. Resume only compatible configurations and preserve accumulated budget accounting; a resume must not grant extra time or attempts. Keep outputs from distinct runs separate. Store large trajectories, model files, caches, and checkpoints outside tracked source or in explicitly ignored paths; commit small configs and summaries that identify the underlying artifacts.

## Validation and handoff

Use the managed profiles from `scripts/setup_runtime.sh` and the shared
`scripts/run_checks.sh` validation path. Direct runtime commands must first source
`scripts/activate_runtime.sh` with the matching profile; do not synchronize a GPU
environment with `uv run`. Keep a separate owned environment per checkout/profile,
reuse persistent caches, and preserve the pinned engine and package locks. Slurm
and GCP use the same experiment launcher. Record evidence in a fresh output
directory and audit storage before retaining additional environments or models.

When implementation exists, run the checks relevant to the change. For changes to the experimental pipeline, prioritize checks that demonstrate:

- Full KV disables eviction and compressed retention follows the configured policy.
- Checkpoint round-trips preserve agent/environment/KV state, and fresh attempts reset state correctly.
- Recovery uses the full transcript once at most, reapplies retention, and leaves tool effects unchanged.
- Shared budgets include tool/reset/checkpoint/rebuild costs, and transient memory limits are enforced.
- Evaluator feedback cannot enter execution; failures remain in aggregation and oracle success is computed per task.

Use small fixtures and train/dev smoke runs before launching sweeps. Report which checks ran and which require unavailable GPU or AppWorld infrastructure; passing mocks alone does not validate the integration. Do not add behavioral tests for documentation-only edits.

In handoffs and PR descriptions, state what changed, the affected experiment or interface, validation performed, and any unresolved limitation or decision. Do not claim an experiment succeeded without saved results. Human contributors review generated code and its behavior. When checking research prose, preserve the authors' intended meaning and distinguish evidence from hypotheses.

## Code and comments

- Keep code succinct without over-simplifying it. Prefer clear, direct code over verbose scaffolding or obscure tricks.
- Keep comments succinct. Explain non-obvious reasoning or experimental constraints, not operations already clear from the code.
- Use only ASCII characters in code comments; use LaTeX notation if needed.
- Do not add delimiter comments. Split files when structure requires it.
