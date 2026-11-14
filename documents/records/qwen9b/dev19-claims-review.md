# Dev recovery records: which claims they support

Read on November 14, 2026, after the [seed replicate](dev19-recovery.md#seed-replicate)
and the [retention frontier](dev19-frontier.md). Six candidate claims were put
to a reviewer that saw the records and not the authors' conclusions, with
instructions to judge each one separately and not to inflate. The reviewer was
a language-model agent, not a person, and the cross-model judge the review
procedure prefers was unavailable; treat the verdicts as provisional until a
team member has checked them. A separate prior-work search follows. Nothing
here is new evidence: it sorts what the existing dev records can and cannot
carry.

## Verdicts

Pooled over the three seeds by task, AgentKV at 50% retention solved 21.1% of
task-seeds without a rebuild, 35.1% with the fixed trigger and 35.1% with the
dynamic trigger, against 38.6% for full cache with two attempts. Fixed minus
never is +14.0 points [0.0, +31.6] for oracle success and +15.8 [+5.3, +29.8]
for first-attempt success (paired task bootstrap over 19 tasks, 10,000 draws,
seed 17 included although it ran on other storage). These pooled numbers are
exploratory.

| Claim | Verdict | What a write-up could say today |
| --- | --- | --- |
| One rebuild restores AgentKV 50% oracle success to about full-cache level | Partial | On 19 dev tasks over three seeds AgentKV 50% solved 21% without a rebuild and 35% with one, against 39% for full cache; the gain's interval reaches zero and rests on three tasks |
| The rebuild improves AgentKV 50% first-attempt success | Supported for this configuration | First-attempt success rose from 12% to 28% (fixed) or 33% (dynamic) on 19 dev tasks, in all three seeds |
| Compression degrades first-action adherence by retention and method, and the opening predicts passing | Partial | Adherence falls with retention, differently per method, and is associated with success; the association is partly task difficulty |
| StreamingLLM's zero success is explained by eviction of the system prompt | Not supported | StreamingLLM solved nothing and never followed the protocol; prompt eviction is a plausible, untested explanation |
| The rebuild must come within about four tool calls | Partial, weak | At one seed, rebuilds after six to eight calls helped less, largely because many attempts ended first |
| AgentKV has a 60% to 40% retention band where one rebuild restores success | Partial | No effect at 80% or 25% over three seeds; at seed 17 gains appeared at 60% to 40% |

The main threat across all six is that there are 19 independent units and the
net recovery gain is carried by three of them (`396c5a2_3`, `50e1ac9_3`,
`b119b1f_1`), one from a family examined earlier. The gain on those tasks is
the same at every seed, so the variance is between tasks and further seeds on
the same tasks add little: tripling the seeds narrowed the oracle interval from
36.8 to 31.6 points. The band, timing and first-action readings are post hoc on
the seed with the largest gain. The percentile bootstrap is also
anti-conservative at this size: four tasks gained and none lost excludes zero
almost by construction.

The reviewer also flagged sentences in the records that claimed more than
their own tables; those were scoped to seed 17 or corrected on the same day.
StreamingLLM solving nothing at 80% retention, where R-KV and AgentKV match
full cache, was called suspicious: the saved runs do not record which tokens
were kept, so an implementation fault is not excluded by this evidence.

## What follows from it

Three studies were declared the same day, in the order the review ranked them:
the [confirmation on the 38 unused dev tasks](dev38-recovery-design.md), and
seed replicates of the [frontier and the trigger timing](dev19-recovery-design.md#seed-replicates-of-the-frontier-and-the-trigger-timing).
Logging which tokens each method keeps would test the R-KV and AgentKV
explanations directly; it needs an engine change and is not started.

Two readings made later the same day change the picture for two of the claims.
For StreamingLLM the kept set follows from token positions, and the
[instruction-error record](dev19-instruction-errors.md#streamingllm-keeps-none-of-the-prompts-rules)
shows that it evicts 656 of the system prompt's 669 tokens before the first
action at 80% retention; the fourth claim is therefore settled by construction
for this configuration. The same record gives the rebuild a specific observed
effect, the removal of rejected logins, which the confirmation now carries as a
declared hypothesis.

## Prior work

A search on November 14, 2026 looked for the closest published work. The four
entries below were confirmed to exist with these titles from their abstracts;
the papers were not read in full, and the descriptions should be checked
before any of them is cited.

| Paper | Relation to these records |
| --- | --- |
| The Pitfalls of KV Cache Compression (arXiv 2510.00231) | Reports that KV compression can cause instructions to be ignored, with system-prompt leakage as the case study, and proposes eviction-policy changes. Single-turn instruction following, not agent task success |
| Protection Is (Nearly) All You Need (arXiv 2605.18053) | Reports that eviction policies collapse without protecting prompt boundaries and that protection matters more than the scoring rule |
| Practical Online KV Cache Compaction for LLM Agents (arXiv 2608.00902) | Agent tasks; immediate compaction hurts and delaying it recovers much of the gap. Delays compaction; does not rebuild from the transcript |
| AgentKV: Phase-Aware KV Eviction for Agentic LLMs (arXiv 2609.14872) | The eviction method these studies run. As read from its web version, it compresses every 128 decode tokens under a fixed token budget and reports agent results on BFCL and tau2-bench |
| R-KV: Redundancy-aware KV Cache Compression for Reasoning Models (arXiv 2505.24133) | The other attention-based method run here. Presented as a decode-stage method for long reasoning outputs, evaluated on math benchmarks |

A second pass read the web versions of the agent-compaction, protection, R-KV
and AgentKV papers for method details; long pages were partly read through
automatic summaries. As read: the agent-compaction study keeps the system
prompt, tool definitions and user query uncompressed and compacts each
completed turn once; the protection study evicts during decoding and names
streaming prefill and multi-turn use as untested; neither R-KV nor AgentKV
describes applying its budget to a prompt chunk by chunk during prefill. None
of them measures a one-time rebuild from the transcript, a wall-clock budget
that charges recomputation, or chunk-by-chunk prefill eviction against a
single selection at the same budget. Applying retention to the system prompt
during prefill is therefore a choice of this project's pipeline, and the 50%
and 25% results depend on it.

Read against that work, protecting the prompt from eviction is an established
control and not a contribution of this project, which bears on the open
question of whether to protect the prompt here. That eviction during prefill
removes prompt instructions is known in outline; measuring it on a multi-app
agent benchmark through first-action adherence appears to be new. The search
found no study of a single re-prefill of the transcript with a timing analysis
under a fixed wall-clock budget, which is the part of this project closest to
a new result. Further candidates the search surfaced were not verified and are
not listed.
