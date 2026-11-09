# Repeated 8k history timing

Job 13839267 completed all thirty cells and ninety passes at 8,192 tokens,
64 decode forwards and three repetitions. It took 514 seconds on an A6000.
All 158 output files (1,356,651 bytes) were copied and independently SHA-256
verified. Exact source tokens, forced outputs, retention, complete metric coverage
and the memory cap verified for every pass. The
[evidence record](history-timing-8k-2026-11-08.json) preserves all repetitions,
component timings, memory distinctions and artifact hashes.

Engine source `312691d`, managed runtime, numerical qualification, hardware,
configuration commit `94bd8b0` and six-thread OMP/MKL policy remained fixed.
Standard synthetic warmup and every first repetition were retained. Setup and
warmup took 13.18 seconds, cells totaled 495.61 seconds and the largest cell
took 34.69 seconds, below its 210-second allowance. No cell failed or received
a replacement attempt.

| Method | Retention | Repeat 0 tok/s | Repeat 1 tok/s | Repeat 2 tok/s | Median tok/s |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full KV | 100% | 37.452 | 37.460 | 37.380 | 37.452 |
| StreamingLLM | 80% | 24.715 | 34.116 | 34.136 | 34.116 |
| StreamingLLM | 50% | 16.894 | 31.784 | 32.940 | 31.784 |
| StreamingLLM | 25% | 32.808 | 33.041 | 33.072 | 33.041 |
| R-KV | 80% | 5.096 | 5.093 | 5.091 | 5.093 |
| R-KV | 50% | 5.142 | 5.143 | 5.143 | 5.143 |
| R-KV | 25% | 10.372 | 10.372 | 10.413 | 10.372 |
| AgentKV | 80% | 28.883 | 30.542 | 30.280 | 30.280 |
| AgentKV | 50% | 26.395 | 26.291 | 26.324 | 26.324 |
| AgentKV | 25% | 25.825 | 25.825 | 25.814 | 25.825 |

These are ordinary synchronized decode-loop rates, including eviction and output
processing. R-KV maximum-to-minimum spread stayed below 0.40% across repetitions.
StreamingLLM first-use differences persist, and its later 50% repetitions differ
by about 3.64%. AgentKV 80% spans about 5.75%. The all-three medians, raw points
and observed ranges retain those differences. No point was dropped or rerun to
smooth the curves, and no instrumented rate replaces an ordinary measurement.

The component audit locates timing variation without establishing a cause.
StreamingLLM 50% later ordinary decode loops took 2.0136 and 1.9429 seconds;
their prefill loops stayed near 1.76 seconds and reset/verification near 1 ms.
The matching instrumented decode loops took 1.9945 and 1.9557 seconds while
whole-replay compaction fell from 250.2 to 209.7 ms. Counts stayed at 33
compactions and 65 selections. This is observed component variation, not evidence
that reset or verification caused the ordinary-loop spread.

AgentKV 80% ordinary decode took 2.2159/2.0955/2.1136 seconds. Its first
instrumented replay took 2.1142 seconds. Replay compaction varied
140.9/129.4/173.1 ms alongside replay decode of 2.1142/2.1033/2.1451 seconds,
while selection totals stayed close. All ordinary/replay pairs matched outputs
and retention events. First-cell elapsed outside saved passes was also elevated
and remains separately recorded; that residual includes journals and outer
orchestration. These saved boundaries do not identify a compiler, kernel,
filesystem or infrastructure cause, or justify a steady-performance claim.

Maximum total VRAM was 29.747 GiB at R-KV 50%, lower than the 4k maximum of
36.812 GiB at R-KV 80%. The 8k R-KV 80% decode peak was 28.640 GiB, with a
28.293 GiB PyTorch reserved peak and 21.663 GiB allocated peak. At 50%, those
values were 29.747/29.400/21.609 GiB. Every repetition retains these peaks.
The KV pool remained 4.50014 GiB. Allocator reservation is non-monotone with
logical length in these measurements; no monotone fit or allocator cause is
assumed. Per-pass cache clearing and peak resets remain unchanged.

The shared analysis accepted 2k, 4k and 8k as compatible. The predeclared central
50% cross-method plots show the full control and three methods on common axes;
all-retention supplements retain the 80% memory finding. Prefill and ordinary
prefix-plus-continuation decode peaks have distinct labels. The main decode
and supplementary decode-memory figures were visually checked. Their hashes
are recorded, and lines connect measured values without smoothing or fitting.

Selection and compaction remain whole instrumented prefix-plus-continuation
totals, nested inside inference rather than extra costs to add to it. Whole-pass
elapsed, loop throughput, occupied KV, reserved pool and total VRAM remain
separate. These are technical repetitions of one fixed history, not model
accuracy, task success, recovery quality or task-bootstrap uncertainty.

The exact declared 12,288-token configuration was reviewed and submitted as
job 13839324, with
64 decode forwards, three repetitions, 390-second cells, a 5,250-second process
bound and a 95-minute allocation. No 16k job is submitted by this record.
Any capacity or incomplete-cell failure must remain visible and stop progression
without a free retry or changed cap.
