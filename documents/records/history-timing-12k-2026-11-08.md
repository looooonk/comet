# Repeated 12k history timing

Job 13839324 completed all thirty cells and ninety passes at 12,288 tokens,
64 decode forwards and three repetitions. It took 880 seconds on an A6000.
All 158 output files (1,401,650 bytes) were copied and independently SHA-256
verified. Exact source tokens, forced outputs, retention, complete metric coverage
and the memory cap verified for every pass. The
[evidence record](history-timing-12k-2026-11-08.json) preserves all repetitions,
component timings, memory distinctions and artifact hashes.

Engine source `312691d`, managed runtime, numerical qualification, hardware,
configuration commit `94bd8b0` and six-thread OMP/MKL policy remained fixed.
Standard synthetic warmup and every first repetition were retained. Setup and
warmup took 46.76 seconds, cells totaled 811.31 seconds and the largest cell
took 66.70 seconds, below its 390-second allowance. Preflight took 18 seconds;
no additional full validation suite was run. No cell failed or received a
replacement attempt.

| Method | Retention | Repeat 0 tok/s | Repeat 1 tok/s | Repeat 2 tok/s | Median tok/s |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full KV | 100% | 36.295 | 36.338 | 36.317 | 36.317 |
| StreamingLLM | 80% | 22.960 | 33.273 | 33.207 | 33.207 |
| StreamingLLM | 50% | 14.451 | 31.248 | 31.526 | 31.248 |
| StreamingLLM | 25% | 15.744 | 31.304 | 30.552 | 30.552 |
| R-KV | 80% | 2.604 | 2.605 | 2.606 | 2.605 |
| R-KV | 50% | 2.592 | 2.589 | 2.591 | 2.591 |
| R-KV | 25% | 5.922 | 5.923 | 5.911 | 5.922 |
| AgentKV | 80% | 27.999 | 27.910 | 28.094 | 27.999 |
| AgentKV | 50% | 23.939 | 23.937 | 23.820 | 23.937 |
| AgentKV | 25% | 24.787 | 24.827 | 24.654 | 24.787 |

These are ordinary synchronized decode-loop rates, including eviction and output
processing. R-KV maximum-to-minimum spread stayed below 0.22% across repetitions.
StreamingLLM first-use differences persist, and its later 25% repetitions differ
by about 2.46%. Its later ordinary loops took 2.0444 and 2.0948 seconds, while
matching instrumented loops took 2.0390 and 2.0372 seconds. That roughly 50 ms
ordinary-loop difference is not reproduced by those instrumented loops; saved
boundaries do not establish its cause. The all-three medians, raw points and
observed ranges retain these differences. No point was dropped or rerun to
smooth the curves, and no instrumented rate replaces an ordinary measurement.

Maximum total VRAM was 24.814 GiB at R-KV 80%, lower than the 8k maximum of
29.747 GiB and 4k maximum of 36.812 GiB. At the 12k maximum, PyTorch reserved
peak was 24.467 GiB and allocated peak was 22.829 GiB. All per-pass and repeat
peaks remain recorded. The KV pool remained 4.50014 GiB. Allocator reservation
is non-monotone with logical length in these measurements; no monotone fit or
allocator cause is assumed. Per-pass cache clearing and peak resets remain
unchanged. Prefill-only peaks and ordinary prefix-plus-continuation decode peaks
have explicit separate boundaries.

Selection and compaction remain whole instrumented prefix-plus-continuation
totals, nested inside inference rather than extra costs to add to it. R-KV
selection totals are about 25.28/25.32/11.51 seconds at 80/50/25% retention.
Whole-pass elapsed, loop throughput, occupied KV, reserved pool and total VRAM
remain separate. These are technical repetitions of one fixed history, not model
accuracy, task success, recovery quality or task-bootstrap uncertainty.

The exact declared 16,384-token configuration was reviewed and submitted as
job 13839624, with 64 decode forwards, three repetitions, 390-second cells,
a 5,250-second process bound and a 95-minute allocation. Any capacity or
incomplete-cell failure must remain visible without a free retry or changed cap.
Interim four-point plotting was deferred: the final five-point main 50%
cross-method figures and complete all-retention supplements will preserve raw
points and ranges, with PNG, SVG and PDF exports. Separate 32,600-token R-KV
capacity failures remain in the feasibility records.
