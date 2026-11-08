# Corrected sampling and bounded-agent retry

The [declared diagnostic](sampling-repair-2026-11-07-plan.md) is submitted on
Insomnia from clean source `396e7743bab1062d523dbf5e36b78758942dd806`.
The original 38-rollout job `13832917`, its checkout/runtime, and its dependent
scorer `13832918` are preserved. The new task run must pass live GPU checks before
starting; submission does not establish task-solving improvement.

## Implementation

Commit `3d3d726` passes the attempt-seeded CUDA generator through all four
Mini-SGLang sampling paths. RNG advancement, seed variation, and exact replay
are now explicit GPU assertions, including the model's saved checkpoint state.
Upstream revisions and package pins are unchanged. The normalized patch SHA-256
is `7997786346ee813e00f21e6b23fa0b1a7a289ac512f1f5142c5baf64423676b4`.

Commit `396e774` adds the opt-in [agent protocol](../agent-protocol.md): reject
comment-only actions, append observation-based corrective guidance, and stop an
attempt after a configured consecutive-error limit. The candidate uses five;
the control uses zero and preserves the existing protocol. The streak survives
checkpoints and resets on successful execution. Errors remain failures, all work
shares the original budget, and scoring remains offline.

The control digest is
`a6987e12b12cbed448b719de69ba950aa9478c3dc18e2e7816525f85854595cc`;
the candidate digest is
`7ec8bcd9e986a0d3846ff3ac5935362290a4f5cf49329c8fc07498a0f13bcc6f`.
Both contain three dev tasks and seeds 17/18, for twelve total fresh N=1
rollouts. Both run sequentially in one allocation with matching Qwen3-8B BF16,
prompt, full-cache/no-recovery settings, 600-second budgets, 40 GiB caps,
32768-token context, 4096-token generation limit, temperature 0.6, and top-p 0.95.

## Validation and submission

The [submission evidence](sampling-repair-2026-11-07.json) records source hashes,
artifact hashes, and the scheduler snapshot.

The local managed CPU suite passed 112 tests, lint, and shell syntax; eight live
integration checks were deselected and the numerical engine module was skipped
because the CPU profile omits PyTorch. It covers error termination, accounting,
comment-only rejection, successful-execution reset, checkpoint streak restoration,
configuration pairing, and freeze compatibility. An initial validation-message
regression was corrected before the passing suite. The patched pinned engine
also passed application and source-hash checks.

Both repository CI jobs passed for
[the sampler commit](https://github.com/looooonk/comet/actions/runs/42435500211)
and [the agent protocol commit](https://github.com/looooonk/comet/actions/runs/42436058867).
The retained local CPU JUnit artifact has SHA-256
`53a940974f472fea7f0850c200e1ead722e2416530b1dbc62c71a8afa76bce62`.

| Slurm job | Purpose |
| --- | --- |
| `13834427` | Managed GPU runtime setup on a CPU node |
| `13834449` | Separate shared package files and verify runtime isolation |
| `13834428` | Full GPU/AppWorld suite, including sampling and near-limit context checks |
| `13834429` | Corrected-sampler control followed by bounded-agent candidate |
| `13834430` | Offline scoring, schema-2 trajectory audit, and separate analysis after both runs |
| `13834455` | Whole-workspace storage audit on a CPU node |

The execution artifact identifiers are
`sampling-control-qwen8b-20261107-13834429` and
`agent-guard-qwen8b-20261107-13834429`. The dependency chain requires successful
setup, package isolation, and GPU validation before execution, then successful
completion of both executions before scoring. Failed attempts stay in each
run's denominator. Alternative GPUs use integration mode and cannot qualify the
required A100 research experiment. The two configurations are analyzed separately.

At the submission check, setup `13834427` had completed, isolation `13834449`
was running, and GPU checks, paired execution, scoring, and storage auditing were
pending on their dependencies. The original job was still running. Live GPU
validation and task outcomes are not yet established by this record.

## Runtime isolation

The concurrent test has its own checkout and managed environment. It reuses the
pinned model snapshot and persistent caches without downloading another model.
Installed package files initially shared inodes with the active environment;
a separate CPU job copies those files before any new GPU check or task can start.
The isolation check requires no remaining hard-linked regular package files and
verifies that the original FlashInfer source hash is unchanged. Future setup for
this private runtime selects copy mode explicitly.

Task outcomes and live validation results remain pending at submission. Compare
scores together with error categories, context use, elapsed time, and seed
variation; an earlier failure stop alone is not evidence of a stronger baseline.
