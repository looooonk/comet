# Capacity limit at 32,600 tokens

Job 13839242 completed the declared ten-condition benchmark in 274 seconds of
allocation time on an A6000. Seven conditions completed; R-KV at 80%, 50% and
25% retention failed the allocator/cap path during prefill. All 70 output files
(579,837 bytes) were copied and independently SHA-256 verified. The
[evidence record](history-feasibility-32600-2026-11-08.json) retains every
condition, partial failure, source identity and artifact hash.

The benchmark process exited normally after journaling seven complete and three
failed cells. The wrapper then failed its all-complete progression gate and
returned exit 1, as intended. Its execution summary counters remain zero because
the all-completed assertion precedes the counting loop; they are not a count of
available results. Independent shared analysis verified 21 complete passes,
three partial failed prefill passes and six subsequent passes not attempted.
There was no timeout, retry, replacement condition or cap change.

Source `312691d`, the managed runtime, qualification, A6000 and six-thread
OMP/MKL policy stayed unchanged. A separate read-only post-run check confirmed
the clean source and runtime marker because the failed gate prevented the
wrapper's final success-only check. Input tokens exactly match the original
32,609-token history prefix. Successful passes verified forced outputs,
retention, metric coverage and their 40 GiB memory cap. These forced replays
do not establish task success, tool correctness or model accuracy.

All three R-KV failures occurred during final prefill eviction. The native
counters retain 32,512 completed prefill tokens and mark the final 88-token
batch incomplete, with its estimated FLOPs recorded separately. Each failure
reported an attempted 7.92 GiB allocation, a 39.65 GiB PyTorch allowance,
31.15 GiB allocated and 8.41 GiB reserved but unallocated. This is capacity
evidence for the pinned implementation and allocator settings; it does not prove
the minimum possible memory requirement of R-KV or isolate fragmentation as a
cause. Neither allocator settings nor the experimental cap were changed.

The failed passes' sampled total peaks were 39.968–39.970 GiB. Their conservative
allocator-plus-maximum-external estimates were 40.032–40.036 GiB, exceeding the
cap by 33–37 MiB. These estimates combine peak accounting components and should
not be presented as simultaneous sampled use. Both forms remain saved; none of
the partial failures is relabeled as cap-compliant success.

Setup and warmup took 14.20 seconds and all cells, including failures, consumed
253.73 seconds. Reserved KV pool size stayed 4.50014 GiB. The table shows the
seven completed conditions and leaves failed quantities unavailable.

| Method | Retention | Status | Prefill loop tok/s | Decode loop tok/s | Selection ms/replay | Compaction ms/replay | Complete-pass peak GiB |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| Full KV | 100% | Complete | 3457.3 | 31.43 | 0.00 | 0.00 | 20.970 |
| StreamingLLM | 80% | Complete | 3369.3 | 22.64 | 6.97 | 53.61 | 21.030 |
| StreamingLLM | 50% | Complete | 3370.0 | 14.13 | 15.32 | 98.86 | 21.007 |
| StreamingLLM | 25% | Complete | 3343.4 | 19.13 | 21.84 | 71.77 | 20.970 |
| R-KV | 80% | Cap failure | — | — | — | — | — |
| R-KV | 50% | Cap failure | — | — | — | — | — |
| R-KV | 25% | Cap failure | — | — | — | — | — |
| AgentKV | 80% | Complete | 3312.2 | 24.12 | 129.11 | 55.07 | 21.345 |
| AgentKV | 50% | Complete | 3316.9 | 17.15 | 234.76 | 81.04 | 21.384 |
| AgentKV | 25% | Complete | 3317.1 | 19.16 | 215.88 | 67.45 | 21.362 |

Ordinary synchronized loop rates include eviction/output processing, while
selection and compaction are nested totals from the separate instrumented
prefix-plus-continuation replay. They are not per-token rates or additional
elapsed time. Only one repetition and eight decode forwards were measured;
first-use variation remains visible, and these values do not establish stable
speed rankings. Parked prefill occupancy for successful conditions was
32,600/26,080/16,300/8,150 entries at full/80%/50%/25% retention. Decode used
32,608 logical cached tokens and 32,608/26,087/16,304/8,152 physical entries.

Shared analysis combines all four declared feasibility lengths and preserves
failed R-KV points with explicit missing coverage. The old 1k smoke is separate.
The next [repeated timing plan](history-timing-2026-11-08-plan.md) uses 64 decode
forwards and three repetitions at 2,048, 4,096, 8,192, 12,288 and 16,384 tokens.
The 32,600-token length is excluded from that complete timing grid because of
these observed cap failures, while every condition remains in this feasibility
record and its figures. No repeated-timing job is included here.
