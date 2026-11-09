# Repeated 2k history timing

Job 13839253 completed the declared 2,048-token, 64-decode-forward workload with
all three repetitions: thirty cells and ninety passes. It took 207 seconds on
an A6000. All 158 output files (1,292,852 bytes) were copied and independently
SHA-256 verified. Exact source tokens, forced outputs, retention counts, metric
coverage and the cap verified for every pass. The
[evidence record](history-timing-2k-2026-11-08.json) contains each repetition,
all-three medians/ranges, source identity and artifact hashes.

Engine source `312691d` and its managed runtime stayed unchanged. Configuration
commit `94bd8b0` declares this separate repeated-timing version. The run reused
the completed compatible GPU validation and retained its bounded numerical
qualification. It used the same A6000, 40 GiB cap, 6 GiB reserve, 32,768-token
context, 256-token prefill chunks, six OMP/MKL/intra-op threads, 64 inter-op
threads and recorded six-CPU affinity. Standard synthetic warmup was unchanged;
there was no extra per-shape warmup. The first repetition is not guaranteed to
have cold compilation caches.

Setup and warmup took 10.71 seconds; cells totaled 192.38 seconds. The largest
cell took 9.40 seconds, below its 60-second limit. Maximum recorded total VRAM
was 21.536 GiB and reserved KV pool size remained 4.50014 GiB. Prefill occupancy
uses 2,048 logical cached tokens; the sixty-four decode forwards extend that
denominator to 2,112. Reserved pool, occupied KV and total VRAM remain separate.

| Method | Retention | Repeat 0 tok/s | Repeat 1 tok/s | Repeat 2 tok/s | Median tok/s |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full KV | 100% | 39.402 | 39.356 | 39.361 | 39.361 |
| StreamingLLM | 80% | 24.407 | 37.657 | 37.676 | 37.657 |
| StreamingLLM | 50% | 18.271 | 35.907 | 35.906 | 35.906 |
| StreamingLLM | 25% | 16.644 | 34.723 | 34.909 | 34.723 |
| R-KV | 80% | 25.325 | 25.333 | 25.349 | 25.333 |
| R-KV | 50% | 23.040 | 23.008 | 23.023 | 23.023 |
| R-KV | 25% | 22.864 | 22.839 | 22.806 | 22.839 |
| AgentKV | 80% | 34.453 | 34.454 | 34.434 | 34.453 |
| AgentKV | 50% | 29.536 | 29.599 | 29.590 | 29.590 |
| AgentKV | 25% | 26.633 | 26.616 | 26.709 | 26.633 |

These are ordinary synchronized decode-loop rates, including eviction and output
processing. Full-cache, R-KV and AgentKV rates had at most 0.35% maximum-to-minimum
spread across all three repetitions. StreamingLLM's first repetitions were
slower; its later two agreed within 0.54%. At 80%/50%/25% retention, the first
ordinary decode took 2.622/3.503/3.845 seconds, versus 1.703/1.785/1.842 seconds
for its instrumented replay. Later ordinary passes matched the replay more
closely. All ordinary/replay pairs had identical outputs and retention events.
This locates the timing difference in first observed ordinary execution, without
establishing a compiler or kernel cause.

Every first repetition remains in the raw points, median and observed range.
No point is discarded and no instrumented rate replaces ordinary throughput.
Selection and compaction remain separate whole prefix-plus-continuation replay
totals, nested in instrumented inference rather than added to it. The JSON and
CSV include all pass times and component costs. Single-length prefill, decode
and selection figures preserve the three raw points and ranges; the decode
figure was visually inspected. No length trend is inferred from this one point.

The predeclared 4,096-token configuration was subsequently approved as job
13839257, with unchanged settings and all ninety expected passes. It retains
the original conservative 210-second cell and 2,490-second process bounds in a
50-minute allocation. The result is separate until fetched and verified.
All repeated timing stays separate from eight-decode feasibility, the unpinned
1k smoke and task-success evaluation. Three technical repetitions of one history
do not provide task-bootstrap confidence intervals or establish model accuracy.
