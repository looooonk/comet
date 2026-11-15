# Exploratory controls

Three opt-in controls test what a full-history rebuild restores. They are
**outside the main experiment matrix**: one contributor authorized them on
November 14, 2026, the team has not reviewed them, and their results stay
separate from the Q1 and Q2 comparisons in the
[research contract](research-direction.md). They add no eviction method. The
pinned selectors, retention accounting, budget and one-rebuild limit are
unchanged, and a configuration that does not name a control behaves and
serializes exactly as before.

| Control | Configuration | What it does |
| --- | --- | --- |
| Protected system prompt | `"protect_prompt": true` on a condition | The system turn's KV entries, through its end marker, are never evicted |
| Text reminder | `"reminder": true` on a condition | The system prompt is sent again as text, once, where the fixed policy would rebuild |
| Symptom-triggered rebuild | `"recovery": "symptom"` with `triggers.symptom_markers` | The one allowed rebuild fires when a tool observation first contains a marker |

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
and `reminder_retained` for the reminder block after it is sent. The reminder
offsets are exact to within one token at each end. The measurement runs on the
shared wall-clock budget and its time is recorded as `retention_diagnostic`.
It adds no budget check, so it cannot change where an attempt ends. Without
the field nothing is measured or recorded.

## Limits

- Protection and the measurement need the hybrid backend; other backends are
  rejected when the configuration loads.
- None of the controls is defined for the checkpoint diagnostic. A restored
  branch inherits its tool and symptom counts from the full-cache source, so
  the configuration is rejected.
- The shared figure code groups conditions by method, retention and recovery
  policy and does not plot control arms.

## Not authorized

No test-split run of these controls or of the recovery arms is authorized.
Their settings are not frozen, and held-out tasks are a shared resource the
team has not agreed to spend on them.
