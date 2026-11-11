# Agent execution protocol

The shared runner supports a versioned, opt-in correction policy through
`agent.max_consecutive_errors`. Omitted or zero preserves the legacy protocol
unless the independent action-validation option below is enabled.
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

`agent.require_executable: true` independently rejects empty/comment-only
Python bodies with an ordinary `Invalid action:` observation. It leaves
`max_consecutive_errors: 0` available: invalid responses consume generation,
context and bookkeeping budget, but do not execute tools, increment tool counts,
add bounded-correction guidance, or terminate an attempt early. A subsequent
valid block can continue normally. This checks for a Python statement, not
whether that statement will accomplish useful work; `pass`, docstrings and
unchanged inspection calls are not semantic progress checks.

The new option defaults to false and is omitted from canonical serialization
when false, preserving historical configuration and freeze digests. A positive
error limit still rejects comment-only blocks regardless of this option, so the
earlier bounded policy keeps its meaning. Enabling the new option defines a
separate protocol version and must not mutate a running or completed baseline.

Both agent settings participate in configuration hashes, checkpoint/run
compatibility, and the final-settings freeze. It must be shared across compared
retention conditions. Changing it defines a new experiment version.

The earlier protocol pilots are historical evidence, not pending experiments.
For a new model, choose and validate the protocol on train/dev before comparing
retention conditions; use identical settings in every arm.
