# Qwen3.5-9B: what fails at 50% retention, and which tasks tolerate compression

At 50% retention the compressed agent stops following the prompt's
documentation protocol before its first action. Full cache opened all 38
attempts with the compact API listing the prompt prescribes; AgentKV 50% did so
in 13 of 38 and opened 20 with a wide full-specification search whose results
fill the 16K context in two to five calls. One rebuild after four tool calls
raised passing attempts from 3 to 8 among the 13 that opened on protocol and
from 0 to 1 among the 20 that opened with the search. Across tasks, tolerance
to compression follows whether full cache solves the task at all; tool-call
count and documentation volume under full cache predict neither tolerance nor
recovery benefit. One seed, 19 dev tasks, read offline from the
[first recovery study](dev19-recovery.md); nothing was rerun.

![First action and passing attempts](figures/dev19-opening-call.png)

[PDF](figures/dev19-opening-call.pdf) |
[Compact evidence](dev19-task-characteristics.json) |
[Recovery findings](dev19-recovery.md)

## What fills the context

Read from every saved attempt of full cache (N=2), AgentKV 50% never and
AgentKV 50% fixed: 38 attempts each.

The system prompt is 3,360 tokens and tells the agent that its first action
must list one app's API names (`show_api_descriptions`) and that it should then
read one API's documentation at a time (`show_api_doc`). Retention is applied
every 128 tokens as the prompt is prefilled, so at 50% half of the prompt's
attention KV is gone before the task has been read or any action generated.

| | Full cache | AgentKV 50% |
| --- | ---: | ---: |
| Attempts opening with the compact listing | 38/38 | 13/38 |
| Attempts opening with `search_api_docs` | 0 | 20/38 |
| Attempts opening with another or a nonexistent call | 0 | 5/38 |
| `search_api_docs` calls | 0 | 67 |
| Median / largest search observation (chars) | - | 15,125 / 41,396 |
| Median / largest listing observation (chars) | 5,477 / 9,306 | 9,306 / 9,306 |
| Attempts ending at the context limit | 1 | 24 |

`search_api_docs` is not mentioned in the prompt. It returns complete
specifications for up to 20 APIs, roughly 5,000 to 7,000 tokens per call, so
two results plus the prompt exceed 16,384 tokens. In the 24 never-rebuild
attempts that ended at the context limit, the largest observation was a
documentation result in 23 (the search in 20, the listing in 3) and
documentation was a median 98% of all observation characters. Eight of the 24
ended after two or three tool calls. The agent is not printing task data and,
with one exception, not repeating calls: one attempt looped over credential
lookups for 70 tool calls. The single full-cache context-limit ending was a
large transaction listing, not documentation.

The 5 "other" openings called names that do not exist
(`show_api_docs`, `show_api_description`) or read one API's documentation
before listing any.

## Where the rebuild helped

Never and fixed use the same seed, so their actions are identical until the
rebuild: every pair shared its first four actions, or all of them when the
attempt ended sooner. Opening calls are therefore the same in both arms, and
the comparison below is within the same starts.

| First action (AgentKV 50%) | Attempts | Passed, never | Passed, fixed | Context limit, never | Context limit, fixed |
| --- | ---: | ---: | ---: | ---: | ---: |
| Compact listing | 13 | 3 | 8 | 3 | 0 |
| Wide search | 20 | 0 | 1 | 18 | 17 |
| Other or nonexistent | 5 | 1 | 1 | 3 | 2 |

Fixed recovery's gain (4 to 10 passing attempts; 3 to 7 of 19 tasks) came
almost entirely from attempts that had started on protocol. Attempts that
opened with the search were not rescued: eight reached the context limit before
the fourth tool call, so no rebuild happened, and those that were rebuilt
already held one or two search results. After the rebuild the agent issued as
many searches as without it (18 in each arm across the 30 rebuilt pairs).

In the hybrid engine a rebuild prefills the whole raw transcript without
intermediate eviction and then applies retention once, so the kept half is
chosen with the task and recent observations in view; ordinary compaction
chooses 128 tokens at a time. That the gain comes from this re-selection, and
that the opening search comes from prompt instructions evicted during prefill,
are hypotheses consistent with these counts. The saved runs do not record which
tokens were kept. The declared [trigger-timing study](dev19-recovery-design.md#supplemental-trigger-timing)
tests the timing part.

## Task characteristics

Per-task outcomes at seed 17 joined with AppWorld's dev task metadata and the
full-cache first attempt. Tolerance counts the never-rebuild arms that solved
the task among R-KV 80%, AgentKV 80%, R-KV 50% and AgentKV 50% (0 to 4).

| Group | Tasks | Full cache solved | Mean tolerance | AgentKV 50% never | AgentKV 50% fixed |
| --- | ---: | ---: | ---: | ---: | ---: |
| Question | 6 | 3 | 1.83 | 2 | 3 |
| State change | 13 | 3 | 0.54 | 1 | 4 |
| Spotify only | 10 | 4 | 1.30 | 2 | 5 |
| Phone and Venmo | 6 | 0 | 0.17 | 0 | 0 |
| Other apps | 3 | 2 | 1.33 | 1 | 2 |
| Difficulty 1 | 10 | 4 | 1.30 | 2 | 3 |
| Difficulty 2 or 3 | 9 | 2 | 0.56 | 1 | 4 |
| Solved by full cache | 6 | 6 | 2.17 | 2 | 4 |
| Not solved by full cache | 13 | 0 | 0.38 | 1 | 3 |

Rank correlations with tolerance (Spearman, 10,000-draw permutation p,
uncorrected): solved by full cache +0.76 (p = 0.001), question +0.54 (0.025),
number of required APIs -0.42 (0.07), number of apps -0.42 (0.08), difficulty
-0.35 (0.17), full-cache tool calls -0.33 (0.17), reference API calls -0.31
(0.19), full-cache documentation characters +0.11 (0.65). Only the first
survives a correction for the 48 correlations computed.

For the AgentKV 50% fixed-minus-never difference, no task property had
|rho| above 0.31 or p below 0.2. Gaining from either recovery policy at 50%
with either method was more common for questions (+0.57, p = 0.04) and for
tasks full cache solves (+0.57, p = 0.04), neither robust to correction.

Read plainly: the tasks compression tolerates are the ones within the model's
reach, questions more than state changes, and the six two-app Phone and Venmo
tasks were unsolved under every arm including full cache. How many tool calls
or how much documentation a task needs under full cache did not separate
tolerant from intolerant tasks or tasks that gained from recovery. What did
separate recovered from unrecovered attempts was a property of the compressed
run, its first action, not of the task.

## Limits

One seed, 19 tasks and two attempts per task; attempts within a task are not
independent, and counts by first action are descriptive. Trajectories were read
for three of the 29 conditions; R-KV 50%, the 80% and 25% arms and StreamingLLM
have cell records here but not this reading. Task metadata was read for dev
tasks only. The correlations are exploratory and uncorrected. The summaries
come from `comet.task_characteristics`, which reads saved artifacts and runs no
model, tool or evaluator. A seed replicate and the supplemental studies in the
[design](dev19-recovery-design.md) are queued; this record will be extended
with them rather than rewritten.
