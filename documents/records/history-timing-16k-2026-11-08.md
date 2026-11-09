# Repeated 16k history timing

Job 13839624 completed all thirty cells and ninety passes at 16,384 tokens,
64 decode forwards and three repetitions. It took 1,237 seconds on an A6000.
All 158 output files (1,445,269 bytes) were copied and independently SHA-256
verified. Exact source tokens, forced outputs, retention, complete metric coverage
and the memory cap verified for every pass. The
[evidence record](history-timing-16k-2026-11-08.json) preserves all repetitions,
component timings, memory distinctions and artifact hashes.

Engine source `312691d`, managed runtime, numerical qualification, hardware,
configuration commit `94bd8b0` and six-thread OMP/MKL policy remained fixed.
Standard synthetic warmup and every first repetition were retained. Setup and
warmup took 11.69 seconds, cells totaled 1,220.47 seconds and the largest cell
took 110.55 seconds, below its 390-second allowance. Preflight took two seconds;
no additional full validation suite was run. No cell failed or received a
replacement attempt.

| Method | Retention | Repeat 0 tok/s | Repeat 1 tok/s | Repeat 2 tok/s | Median tok/s |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full KV | 100% | 35.208 | 35.212 | 35.182 | 35.208 |
| StreamingLLM | 80% | 16.622 | 32.033 | 31.932 | 31.932 |
| StreamingLLM | 50% | 16.216 | 29.973 | 29.702 | 29.702 |
| StreamingLLM | 25% | 29.207 | 29.421 | 29.310 | 29.310 |
| R-KV | 80% | 1.531 | 1.531 | 1.531 | 1.531 |
| R-KV | 50% | 1.571 | 1.571 | 1.568 | 1.571 |
| R-KV | 25% | 3.608 | 3.610 | 3.610 | 3.610 |
| AgentKV | 80% | 26.374 | 26.406 | 26.469 | 26.406 |
| AgentKV | 50% | 22.446 | 22.574 | 22.885 | 22.574 |
| AgentKV | 25% | 22.401 | 23.023 | 22.831 | 22.831 |

These are ordinary synchronized decode-loop rates, including eviction and output
processing. R-KV maximum-to-minimum spread stayed below 0.25% across repetitions.
StreamingLLM first-use differences persist. AgentKV 50% and 25% span about
1.96% and 2.78%, respectively. At 50%, its ordinary loops took
2.8513/2.8352/2.7965 seconds and replay loops took 2.8314/2.8303/2.8175 seconds.
At 25%, ordinary loops took 2.8570/2.7799/2.8032 seconds while replay loops took
2.8046/2.7844/2.8913 seconds. Replay selection and compaction also vary; these
boundaries do not establish a cause of the ordinary-loop variation. No point
was dropped or rerun to smooth the curves, and no instrumented rate replaces
an ordinary measurement.

Maximum total VRAM was 27.786 GiB at R-KV 80%, with 27.439 GiB PyTorch reserved
and 24.938 GiB allocated peaks. The fixed KV pool remained 4.50014 GiB. The 16k
maximum exceeds 12k's 24.814 GiB but remains below the 4k and 8k maxima.
Reservation remains non-monotone with logical length; all points are retained
without an inferred allocator cause. Per-pass cache clearing and peak resets
remain unchanged. Prefill-only peaks and ordinary prefix-plus-continuation decode
peaks have explicit separate boundaries.

Selection and compaction are whole instrumented prefix-plus-continuation totals,
nested inside inference rather than extra costs to add to it. R-KV selection
totals are about 44.42/43.27/20.33 seconds at 80/50/25% retention. Whole-pass
elapsed, loop throughput, occupied KV, reserved pool and total VRAM remain
separate. These are technical repetitions of one fixed history, not model
accuracy, task success, recovery quality or task-bootstrap uncertainty.

This completes the five predeclared lengths. The
[grid report](history-timing-grid-2026-11-08.md) identifies the main 50% decode
throughput and ordinary decode-pass peak-memory figures, with PNG, SVG and PDF
exports, supporting metrics and complete all-retention supplements. No further
job or sweep is submitted. Separate 32,600-token R-KV capacity failures remain
preserved in the feasibility records.
