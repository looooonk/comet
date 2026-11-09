# Repeated 4k history timing

Job 13839257 completed all thirty cells and ninety passes at 4,096 tokens,
64 decode forwards and three repetitions. It took 281 seconds on an A6000.
All 158 output files (1,315,345 bytes) were copied and independently SHA-256
verified. Exact input tokens, forced outputs, retention, complete metric coverage
and the cap verified for every pass. The
[evidence record](history-timing-4k-2026-11-08.json) contains all repetitions,
pass memory measurements, source identity and artifact hashes.

Engine source `312691d`, managed runtime, numerical qualification and the
configuration commit `94bd8b0` stayed fixed. Hardware, six-thread OMP/MKL policy,
context capacity, chunk size and standard synthetic warmup match the
[2k run](history-timing-2k-2026-11-08.md). No additional per-shape warmup or
first-repetition exclusion was introduced. Setup and warmup took 10.52 seconds,
cells totaled 266.06 seconds and the largest cell took 15.16 seconds, below
its declared 210-second allowance.

| Method | Retention | Repeat 0 tok/s | Repeat 1 tok/s | Repeat 2 tok/s | Median tok/s |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full KV | 100% | 38.695 | 38.636 | 38.656 | 38.656 |
| StreamingLLM | 80% | 21.493 | 36.450 | 36.405 | 36.405 |
| StreamingLLM | 50% | 12.484 | 34.857 | 34.896 | 34.857 |
| StreamingLLM | 25% | 33.972 | 34.280 | 34.249 | 34.249 |
| R-KV | 80% | 14.067 | 14.101 | 14.082 | 14.082 |
| R-KV | 50% | 13.700 | 13.683 | 13.727 | 13.700 |
| R-KV | 25% | 19.122 | 19.112 | 19.137 | 19.122 |
| AgentKV | 80% | 33.667 | 33.608 | 33.663 | 33.663 |
| AgentKV | 50% | 29.238 | 29.289 | 29.289 | 29.289 |
| AgentKV | 25% | 26.672 | 26.730 | 26.753 | 26.730 |

These ordinary synchronized decode-loop rates include eviction and output
processing. Full-cache, R-KV and AgentKV had less than 0.33% maximum-to-minimum
spread across all three repetitions. StreamingLLM retains slower first
repetitions at 80% and 50%; its later two rates agree within 0.13%.
Every first repetition remains in the median, range and raw figures.
All thirty ordinary/instrumented pairs have matching outputs and retention
events. Instrumented rates never substitute for ordinary rates.

R-KV at 80% reached 36.812 GiB sampled total VRAM during every ordinary decode
and instrumented replay. Its PyTorch reserved peak was 36.465 GiB, whereas
allocated tensor peak was 21.664 GiB. The reserved KV pool remained only
4.50014 GiB. Other conditions peaked at no more than 22.458 GiB across their
passes. The large reservation stayed below the fixed 40 GiB cap and is retained
as a capacity-relevant result, not replaced by allocated-tensor usage.

The preflight recorded no competing process. The pinned `native.start` empties
allocator cache and resets peak counters on every pass, so this is not simply
unreleased cache inherited from a preceding method. The evidence identifies
reservation by this process without establishing a particular kernel or
fragmentation mechanism. No allocator, precision, cap or workspace setting
was changed. Prefill-only peaks do not describe this decode reservation.

The shared analyzer accepted the new 2k and 4k runs as compatible. The
predeclared central 50% view compares full KV and all three eviction methods
on common axes. All-retention supplements preserve the 80% memory result and
every raw repetition. An explicitly named ordinary-decode peak-memory view
covers the full prefix-plus-continuation pass; prefill peaks remain separately
labeled. The central decode-throughput and all-retention decode-peak figures
were visually inspected. Their hashes and the plotting source commit are in
the record. Lines connect only measured values, with no smoothing or fit.

Selection and compaction remain nested totals from the separate instrumented
prefix-plus-continuation replay, not per-token rates or extra time to add to
inference. Whole-pass elapsed, loop throughput, occupied KV, reserved pool and
total device use retain distinct meanings. These technical repetitions of one
fixed history do not establish task success, model accuracy or task-bootstrap
uncertainty.

The exact declared 8k configuration was reviewed and submitted as job 13839267
under the unchanged 40 GiB cap, 210-second cell limit, 2,490-second process bound
and 50-minute allocation. Its outcome remains separate until verified. Any
capacity failure stops progression without a free retry or relaxed cap.
