# Fifty-task provisional results

The November 9, 2026, 20:20:47 ET snapshot contains **12 of 26 conditions**, each
with the same 50 held-out tasks and seed 17: **600 task-condition evaluations**.
Every condition that had completed all 50 tasks at capture time is included.
Partially finished conditions are not scored on their faster subset. The study
remains frozen and these results do not guide ongoing execution.

![Provisional compression and success curves](figures/test50-partial-aggressivity.png)

[PDF](figures/test50-partial-aggressivity.pdf) |
[All-condition CSV](test50-partial.csv) |
[Compact evidence](test50-partial-summary.json)

## Observed success

| Method | Retained KV target | First attempt | Oracle within budget |
| --- | ---: | ---: | ---: |
| Full cache (N=1) | 100% | 15/50 (30%) | 15/50 (30%) |
| StreamingLLM | 90% | 8/50 (16%) | 8/50 (16%) |
| StreamingLLM | 80% | 0/50 (0%) | 0/50 (0%) |
| StreamingLLM | 70% | 0/50 (0%) | 0/50 (0%) |
| StreamingLLM | 60% | 0/50 (0%) | 0/50 (0%) |
| StreamingLLM | 50% | 0/50 (0%) | 0/50 (0%) |
| StreamingLLM | 40% | 0/50 (0%) | 0/50 (0%) |
| StreamingLLM | 30% | 0/50 (0%) | 0/50 (0%) |
| R-KV | 90% | 11/50 (22%) | 12/50 (24%) |
| R-KV | 80% | 13/50 (26%) | 15/50 (30%) |
| R-KV | 70% | 12/50 (24%) | 15/50 (30%) |
| AgentKV | 90% | 2/50 (4%) | 2/50 (4%) |

All denominators include timeouts, memory failures, context limits and errors.
Oracle success assumes perfect selection among at most two attempts sharing
120 seconds. The full-cache N=1 control permits one attempt. The matched N=2
control is still missing, so the two 30% R-KV oracle rates cannot establish
parity with full-cache best-of-two performance. Uncertainty remains substantial:
the full-cache first-attempt bootstrap interval is 18-42%, and the R-KV 70%
oracle interval is also 18-42%. Pointwise intervals do not establish a ranking.

StreamingLLM records 8/50 successes at 90% retention and 0/50 at each measured
30-80% retention setting. Zero-width bootstrap intervals for all-failure samples
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

The snapshot lacks full-cache N=2, all 25% retention conditions, R-KV at 30-60%
retention and AgentKV at 30-80% retention. The CSV distinguishes partial
execution coverage from fully scored conditions. Missing plot points are gaps,
not zero-valued measurements.

## Execution and reporting provenance

Execution and the shared AppWorld evaluator remain pinned to `f2413b4` with
Qwen3.5-9B, the hybrid BF16 backend, RTX PRO 6000 Blackwell Server Edition,
16K context and the 24 GiB total-VRAM cap. The parent configuration and task
selection are unchanged from the [study design](test50-design.md). No model
inference, task reset or task budget was repeated to create this report.

The completed-condition snapshot copies saved environments before offline
scoring. Its 240 completed attempts were scored through the ordinary AppWorld
evaluator using four isolated CPU processes; unsuccessful execution attempts
retain failure outcomes. The shared analysis uses 2,000 paired task-bootstrap
draws. All 12 conditions were audited to retain exactly the same 50 task/seed
pairs, and every execution failure was verified to remain unsuccessful.

Shared-filesystem reads stalled the initial scoring jobs. Scoring completed in
an isolated job-local workspace using base databases freshly downloaded from
the same official AppWorld data version 0.2.0, with the existing immutable task
assets. Database filenames and sizes match the installed data; copied file
hashes are retained in the compact evidence. Only copied snapshot references
were redirected and restored. Original task outcomes and environment references
were not rewritten.
The scoring and plotting step `13847911.6` completed successfully on Insomnia;
its idle parent allocation was subsequently cancelled. No GCP resources were launched.

Partition 02 saved all 150 terminal cells before its process failed during CUDA
shutdown. Metadata-only finalization established that no eligible cells remained;
its failures and consumed budgets are preserved. The original final-report job
was cancelled by its success-only dependency. Replacement job **13847761** waits
for array 13845293 to exit, then finalizes all partitions before ordinary full
scoring. Missing or eligible cells still block that report. The other GPU workers
continue; the previously queued partition has an allocation but had produced no
completed task cells when this partial report was prepared.

The reporting implementation passed 354 CPU regression checks before the later
parallel/asset additions, with two optional Torch skips and 17 live checks
excluded. Five focused snapshot, process-isolation and asset tests passed;
the independent-asset fallback passed its updated test. Plots were rendered and
visually inspected. Full scores, analyses, evaluator provenance and original
snapshots remain in external project storage; portable IDs and content hashes
are recorded in the compact evidence.
