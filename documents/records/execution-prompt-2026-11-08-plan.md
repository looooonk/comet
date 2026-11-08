# Executable-action baseline diagnostic

The corrected-sampler traces still contain hypothetical authentication, guessed
API signatures, placeholder recipients, repeated unchanged failures and premature
completion. For example, the control's `0d8a4ee_1` seed 17 begins with invented
recipient numbers; `57c3486_1` seed 17 repeatedly comments that authentication is
assumed while calling a protected endpoint; and `3ab5b8b_1` seed 17 interprets a
returned access token as login failure because an invented `status` key is absent.
These observations come from ordinary saved trajectories, not evaluator solutions.

The new explicit configs are `pilot-execution-control-qwen8b-v1.json` and
`pilot-execution-candidate-qwen8b-v1.json`. Both use the same targeted dev tasks
(`0d8a4ee_1`, `3ab5b8b_1`, `57c3486_1`) and seeds 17 and 18. These identities were
declared before new outcomes. Both use pinned Qwen3-8B BF16, corrected sampling,
full KV, one attempt, no recovery, 600 seconds per cell, a 40 GiB cap, 32,768-token
context, up to 4,096 generated tokens per turn, and reasoning enabled. Both explicitly select `NVIDIA L40S` under the authorized
hardware policy. Temperature
and top-p retain the previous corrected-control values. All settings are resolved
in the new files rather than inherited from obsolete smoke configurations.

The candidate changes only the system prompt. It emphasizes live executable
actions, documentation before calls, observed return values, explicit tokens,
complete pagination, and verifying effects before completion. It supplies no
task-specific solution, recipient, expected answer or evaluator feedback. Neither
arm adds an early-stop guard. This isolates the prompt package, not individual
sentences. The old guarded comparison remains separate.

Run both arms on the same source revision, managed runtime, and GPU model; use
fresh task environments and separate output directories. Twelve cells have a
combined two-hour task-budget ceiling plus loading and checks. Score only after
both executions finish, then compare task success, failure statuses, error turns
per response turn, duration, and memory/metric coverage. Preserve every failure,
including context limits and interruptions. Reduced errors alone do not validate
a useful baseline. No new model result is claimed by this plan.

If 8B remains ineffective, test the pinned 14B exploratory model on the same
declared diagnostic before trying newer architectures. Any useful candidate still
requires broader declared dev confirmation before retention/recovery sweeps. The
hardware and newer-model authorizations are recorded in
[hardware qualification](../experimental-hardware.md) and
[exploratory models](../experimental-models.md).
