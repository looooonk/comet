# Exploratory controls

Three opt-in controls and one accounting option test what a full-history
rebuild restores. They are **outside the main experiment matrix**: one
contributor authorized the controls on November 14, 2026 and the accounting
option on November 15, the team has not reviewed them, and their results stay
separate from the Q1 and Q2 comparisons in the
[research contract](research-direction.md). They add no eviction method. The
pinned selectors, budget and one-rebuild limit are unchanged. Retention
accounting changes only for a condition that sets `prompt_outside_budget`,
and a configuration that does not name a control behaves and serializes
exactly as before.

| Control | Configuration | What it does |
| --- | --- | --- |
| Protected system prompt | `"protect_prompt": true` on a condition | The system turn's KV entries, through its end marker, are never evicted |
| Text reminder | `"reminder": true` on a condition | The system prompt is sent again as text, once, where the fixed policy would rebuild |
| Symptom-triggered rebuild | `"recovery": "symptom"` with `triggers.symptom_markers` | The one allowed rebuild fires when a tool observation first contains a marker |
| System prompt outside the budget | `"prompt_outside_budget": true` on a condition | The retention fraction applies to the tokens after the system turn, and the system turn's entries are added to the target |

## Protected system prompt

Each pinned selector already keeps a fixed number of leading entries, its sink.
Protection raises that existing parameter to the length of the system turn and
changes nothing else in the selector. Protected entries count **inside** the
retention target, so a protected condition stores the same number of KV entries
as its unprotected twin once the transcript is long enough:

$$\text{target} = \min\left(n, \max\left(\lceil r n \rceil, p + m\right)\right)$$

for $n$ logical tokens, retention $r$, $p$ protected tokens and the method's
ordinary mandatory floor $m$. While $\lceil r n \rceil < p + m$ the cache holds
more than the configured fraction; report $p$ and the first token count at
which the two targets agree. Full-cache conditions cannot be protected. The
Mini-SGLang engine does not implement protection and rejects it.

## System prompt outside the budget

Counting a protected prompt inside the target has a side effect at short
contexts. The engine compacts after every prefill chunk, so while
$\lceil r n \rceil < p + m$ the cache holds the prompt and only $m$ further
entries. With the 673-token prompt at 50% retention that lasts until 1,393
tokens. What is evicted there is the start of the first user turn, which
states the task, and it does not return without a rebuild.

`prompt_outside_budget` takes the system turn out of the denominator:

$$\text{target} = \min\left(n, p + \max\left(\lceil r (n - p) \rceil, m\right)\right)$$

for $n > p$, and nothing is evicted while $n \le p$. The tokens after the
prompt keep the configured fraction at every length. The option is independent
of protection. With `protect_prompt` the prompt's entries are pinned. Without
it the selector may keep the same number of entries anywhere, which gives a
control with an equal entry count and nothing pinned.

**This departs from the contract's retention definition.** A condition with
the option stores $p(1 - r)$ more entries per layer and head than its nominal
retention: about 337 for the 673-token prompt at 50%, which is 60% of a
3,355-token transcript and 54% of an 8,000-token one. Report the entries
actually held, never describe such an arm as 50% without that qualifier, and
compare it with the unpinned arm of equal entry count before attributing a
difference to pinning.

## Text reminder

The reminder is the text-only counterpart of the fixed rebuild. After the tool
call that reaches `triggers.fixed_tool_calls`, the runner appends the unchanged
system prompt in a `<system_reminder>` block to the user turn that carries the
tool response. It is sent once per attempt, repairs no KV entry and consumes
no rebuild allowance. Its tokens are ordinary transcript tokens: they count
toward context length, are charged as prefill, and are evicted like any other
text. The repeat is verbatim, not a list of the rules an agent was seen to
break, so that it uses no more knowledge of the failure than a rebuild does.

## Symptom-triggered rebuild

`symptom_markers` is a list of exact substrings. An observation that contains
one, whether a tool response or the runner's own invalid-action message, counts
as a symptom. The `symptom` policy rebuilds before the next generation after
the first symptom, subject to the same admission checks and the one-rebuild
limit. An attempt with no symptom never rebuilds. Markers are ordinary
execution observations; evaluator output never reaches the policy. Text the
runner appends as execution feedback is not searched. Markers chosen from
observed failures are tuned settings: choose them on train/dev and report
which tasks informed them.

## Measurement

`"retention_diagnostic": true` on an experiment makes every turn also record
`system_prompt_retained`, the share of the system turn's entries still cached
when the action was generated, averaged over attention layers and KV heads,
and `reminder_retained` for the reminder block after it is sent. When the
environment names its task statement, every turn also records
`task_statement_retained` for that span and the trajectory records the span as
`statement_span`. The AppWorld adapter names the instruction as the first user
turn renders it. Reminder and statement offsets are exact to within one token
at each end. The measurement runs on the shared wall-clock budget and its time
is recorded as `retention_diagnostic`. It adds no budget check, so it cannot
change where an attempt ends. Without the field nothing is measured or
recorded. A statement lookup that fails is recorded as `statement_span_error`
and does not end the attempt. The statement measurement was added on November
15, 2026, so earlier runs with the field do not carry it. Do not resume such a
run on later source: its attempts would then differ in recorded fields and in
measurement time.

## Limits

- Protection, the budget option and the measurement need the hybrid backend;
  other backends are rejected when the configuration loads.
- None of the controls is defined for the checkpoint diagnostic. A restored
  branch inherits its tool and symptom counts from the full-cache source, so
  the configuration is rejected.
- The shared figure code groups conditions by method, retention and recovery
  policy and does not plot control arms.

## Not authorized

No test-split run of these controls or of the recovery arms is authorized.
Their settings are not frozen, and held-out tasks are a shared resource the
team has not agreed to spend on them.
