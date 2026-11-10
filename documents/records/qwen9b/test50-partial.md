# Fifty-task provisional results

The November 10, 2026, 15:47:57 ET snapshot contains **21 of 26 conditions**, each
with the same 50 held-out tasks and seed 17: **1,050 task-condition evaluations**.
Every condition that had completed all 50 tasks at capture time is included.
Partially finished conditions are not scored on their faster subset. The study
remains frozen and these results do not guide ongoing execution.

![Provisional compression and success curves](figures/test50-partial-aggressivity.png)

[PDF](figures/test50-partial-aggressivity.pdf) |
[All-condition CSV](test50-partial.csv) |
[Compact evidence](test50-partial-summary.json)

## Observed success

The refresh adds full-cache N=2, StreamingLLM at 25% retention, R-KV at
25% and 30%, and AgentKV at 30% and 80%. Full-cache N=2 scores 12/50 (24%)
on the first attempt and 14/50 (28%) with oracle selection. AgentKV at 80%
scores 7/50 (14%) and 9/50 (18%); the other newly added compressed points
score 0/50. All 750 previously reported outcomes are unchanged.

| Method | Retained KV target | First attempt | Oracle within budget |
| --- | ---: | ---: | ---: |
| Full cache (N=1) | 100% | 15/50 (30%) | 15/50 (30%) |
| Full cache (N=2) | 100% | 12/50 (24%) | 14/50 (28%) |
| StreamingLLM | 90% | 8/50 (16%) | 8/50 (16%) |
| StreamingLLM | 80% | 0/50 (0%) | 0/50 (0%) |
| StreamingLLM | 70% | 0/50 (0%) | 0/50 (0%) |
| StreamingLLM | 60% | 0/50 (0%) | 0/50 (0%) |
| StreamingLLM | 50% | 0/50 (0%) | 0/50 (0%) |
| StreamingLLM | 40% | 0/50 (0%) | 0/50 (0%) |
| StreamingLLM | 30% | 0/50 (0%) | 0/50 (0%) |
| StreamingLLM | 25% | 0/50 (0%) | 0/50 (0%) |
| R-KV | 90% | 11/50 (22%) | 12/50 (24%) |
| R-KV | 80% | 13/50 (26%) | 15/50 (30%) |
| R-KV | 70% | 12/50 (24%) | 15/50 (30%) |
| R-KV | 60% | 6/50 (12%) | 9/50 (18%) |
| R-KV | 50% | 1/50 (2%) | 1/50 (2%) |
| R-KV | 40% | 0/50 (0%) | 2/50 (4%) |
| R-KV | 30% | 0/50 (0%) | 0/50 (0%) |
| R-KV | 25% | 0/50 (0%) | 0/50 (0%) |
| AgentKV | 90% | 2/50 (4%) | 2/50 (4%) |
| AgentKV | 80% | 7/50 (14%) | 9/50 (18%) |
| AgentKV | 30% | 0/50 (0%) | 0/50 (0%) |

All denominators include timeouts, memory failures, context limits and errors.
Oracle success assumes perfect selection among at most two attempts sharing
120 seconds. The full-cache N=1 control permits one attempt. The matched N=2
control is now available. R-KV at 70-80% retention scores 30% oracle success
against 28% for full-cache N=2; these point estimates do not establish superiority.
The independently executed N=1 and N=2 controls have different first-attempt
outcomes. Their difference includes timing and storage effects; it is not a
causal estimate of adding an attempt. Within N=2, oracle success rises from
12/50 first-attempt successes to 14/50. Uncertainty remains substantial: the
full-cache N=1 first-attempt bootstrap interval and R-KV 70% oracle interval are
both 18-42%. Pointwise intervals do not establish a ranking.

StreamingLLM records 8/50 successes at 90% retention and 0/50 at each measured
25-80% retention setting. Zero-width bootstrap intervals for all-failure samples
do not establish zero population success. Conservative bounded intervals are
retained in the compact evidence. The horizontal axis is the configured
100 times (1 minus retention), not measured total-VRAM savings; recurrent state
remains uncompressed and realized KV occupancy varies with floors and rounding.

## Runtime failures and missing comparisons

AgentKV at 90% retention has **59 CUDA illegal-access attempt failures** and
31 OOM attempts, with only ten completed attempts. Its 2/50 success point
therefore reflects substantial runtime failure as well as task behavior; it
cannot isolate the method's reasoning quality. R-KV at 90% retention has
28 OOM attempts. These failures remain in the data and receive no free retries.

Only five AgentKV points remain incomplete: 25%, 40%, 50%, 60% and 70%
retention, with 46, 37, 36, 35 and 42 of 50 cells completed respectively. The CSV
distinguishes partial execution coverage from fully scored conditions. Missing
plot points are gaps, not zero-valued measurements.

## Execution and reporting provenance

Execution and the shared AppWorld evaluator remain pinned to `f2413b4` with
Qwen3.5-9B, the hybrid BF16 backend, RTX PRO 6000 Blackwell Server Edition,
16K context and the 24 GiB total-VRAM cap. The parent configuration and task
selection are unchanged from the [study design](test50-design.md). No model
inference, task reset or task budget was repeated to create this report.

The completed-condition snapshot copies saved environments before offline
scoring. The refresh reuses 277 previously scored completed attempts after verifying
unchanged terminal-cell hashes and the same evaluator/runtime. It scores 88 newly
covered completed attempts through the ordinary AppWorld evaluator using four
isolated CPU processes; unsuccessful execution attempts retain failure outcomes.
The parent snapshot and score hashes are preserved. Both reports and the original
saved environments remain in external storage. The shared analysis uses 2,000 paired task-bootstrap
draws. All 21 conditions were audited to retain exactly the same 50 task/seed
pairs, and every execution failure was verified to remain unsuccessful.

Shared-filesystem reads stalled the initial scoring jobs. Scoring completed in
an isolated job-local workspace using base databases freshly downloaded from
the same official AppWorld data version 0.2.0, with the existing immutable task
assets. Database filenames and sizes match the installed data; copied file
hashes are retained in the compact evidence. Only copied snapshot references
were redirected and restored. Original task outcomes and environment references
were not rewritten.
Refresh job `13853126` completed scoring and plotting on Insomnia in 2m20s. The freshly downloaded
base-database hashes match the previous scorer's copies. No GCP resources were launched.

Partition 02 saved every cell before a CUDA shutdown failure and was finalized
without inference. Partitions 00 and 03 also finished. Five other workers stopped
near their allocation limits overnight, leaving 1,246/1,300 terminal cells. The
old final scorer correctly refused to proceed while inference remained eligible.

The [November 10 resume record](test50-resume-20261110.json) queues array
`13853125` for the five unfinished partitions, preserving their original source,
configurations, completed cells and consumed budgets. There are 49 unstarted
cells plus five inflight journals to settle through the existing resume rules.
Each request has one matching PRO 6000 GPU and a two-hour scheduler allocation;
experimental cell budgets remain 120 seconds. Dependent scorer `13853128` first
requires every partition to finalize, then produces the complete study report.

At submission, all eight GPUs on ins046 were occupied and ins047 was still
marked down and not responding after maintenance. The scheduler forecast a
November 12, 14:30 ET start; this is not a reservation and may move forward if
capacity returns. Allow roughly 45-75 minutes of inference after the last worker
starts, plus 15-45 minutes for full scoring. No resume has started yet.

The reporting implementation passed 354 CPU regression checks before the later
parallel/asset additions, with two optional Torch skips and 17 live checks
excluded. Five focused snapshot, process-isolation and asset tests passed;
the independent-asset fallback passed its updated test. The refresh passed six
focused checks and an exact comparison of all 750 prior scored cells. Plots were rendered and
visually inspected. Full scores, analyses, evaluator provenance and original
snapshots remain in external project storage; portable IDs and content hashes
are recorded in the compact evidence.
