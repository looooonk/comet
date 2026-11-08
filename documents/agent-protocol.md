# Agent execution protocol

The shared runner supports a versioned, opt-in correction policy through
`agent.max_consecutive_errors`. Omitted or zero preserves the legacy protocol.
A positive integer enables all of the following for every inference method:

- Reject a Python block containing only comments before executing it.
- Append brief guidance after an invalid action or an AppWorld execution error.
  Guidance distinguishes missing authentication, response-shape errors, malformed
  reasoning/actions, and other API errors. It uses only ordinary observations.
- End the attempt with status `error` and an `AgentProtocolError` failure reason
  when the configured number of consecutive errors is reached. A successful
  execution resets the streak. No replacement attempt or extra budget is granted.

Raw observations remain unchanged in `trajectory.json`. Each turn additionally
records `agent_feedback` and `consecutive_errors`; the feedback is appended to
the next model input and consumes the same time and context budget. The streak
is part of the saved agent state and survives diagnostic checkpoint restoration.
Normal task completion takes precedence over the error limit; a failed block can
have already executed earlier actions. A checkpoint boundary cannot bypass the
error limit. The ordinary offline evaluator continues to count execution errors
as failed attempts.

The policy does not roll back or replay tools, use evaluator feedback, or infer
task success from a tool returning without error. It does not detect every
unproductive successful action: repeatedly printing an unchanged value can still
use up the task budget. Correction messages explicitly warn that earlier actions
in a failed block may already have taken effect.

The agent setting participates in configuration hashes, checkpoint/run
compatibility, and the final-settings freeze. It must be shared across compared
retention conditions. Changing it defines a new experiment version.

The [corrected-sampler control](../configs/pilot-sampling-control-qwen8b.json)
and [bounded candidate](../configs/pilot-agent-guard-qwen8b.json) use identical
prompts and numerical settings. Both require the patched sampler described in
[engine.md](engine.md); the only agent-protocol difference is the provisional
five-error limit and its associated correction behavior. Validate on train/dev
before adopting that setting for a broader pilot or final evaluation.
