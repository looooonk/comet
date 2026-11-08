# Completed 8k history feasibility

Job 13839222 completed all ten conditions and thirty passes on an A6000 in
108 seconds. All 78 remote files (377,420 bytes) were copied and independently
SHA-256 verified. Saved inputs match the original 8,201-token history prefix;
forced outputs, retention counts, complete metric coverage and the 40 GiB cap
verified for every pass. This establishes feasibility at 8,192 tokens for this
run, not model accuracy or task success. The [evidence record](history-feasibility-8k-2026-11-08.json)
contains exact source, configuration, qualification and artifact hashes.

Source `312691d`, the managed runtime, and the numerical qualification remained
unchanged. Preflight verified the completed source-matched GPU validation from
job 13837736 rather than rerunning it. OMP/MKL and PyTorch intra-op threads were
six, inter-op threads were 64, and CPU affinity matched the new
[2k run](history-feasibility-2k-2026-11-08.md). The earlier 1k smoke has unrecorded
inherited thread settings and remains a separate diagnostic.

Setup and warmup took 12.84 seconds; all cells together took 90.72 seconds.
The largest cell took 21.52 seconds, below the declared 120-second cell limit.
Reserved KV pool size stayed 4.50014 GiB, while maximum observed total VRAM was
23.460 GiB. Parked prefill occupancy was 8,192 entries for full KV, 6,554 at 80%,
4,096 at 50%, and 2,048 at 25%. Decode used 8,200 logical cached tokens and
respectively 8,200/6,560/4,100/2,050 physical entries. The fixed reserved pool
therefore differs from occupied KV and measured total device use.

| Method | Retention | Prefill loop tok/s | Decode loop tok/s | Selection ms/replay | Compaction ms/replay | Peak total GiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full KV | 100% | 4748.8 | 37.33 | 0.00 | 0.00 | 20.966 |
| StreamingLLM | 80% | 4492.5 | 21.87 | 8.99 | 25.37 | 20.968 |
| StreamingLLM | 50% | 3807.2 | 16.07 | 14.68 | 31.75 | 20.968 |
| StreamingLLM | 25% | 4550.7 | 21.35 | 20.58 | 25.31 | 20.968 |
| R-KV | 80% | 710.5 | 4.29 | 2795.90 | 28.31 | 23.460 |
| R-KV | 50% | 2822.3 | 5.18 | 2465.06 | 30.72 | 23.419 |
| R-KV | 25% | 2818.4 | 10.40 | 1700.58 | 24.53 | 22.161 |
| AgentKV | 80% | 4588.2 | 29.18 | 70.46 | 27.12 | 20.987 |
| AgentKV | 50% | 4602.1 | 26.68 | 93.89 | 65.32 | 20.980 |
| AgentKV | 25% | 4603.9 | 25.88 | 109.95 | 24.08 | 20.972 |

Ordinary synchronized loop rates include eviction/output processing, excluding
surrounding scheduling, reset and verification. Selection and compaction sum the
whole instrumented prefix-plus-continuation replay; they are nested costs, not
per-token rates or additions to total inference. Peak total VRAM in the table is
the maximum over all three passes; the shared memory figures separately show
the declared prefill measurement boundary.

R-KV selection totals increased from 0.220/0.225/0.231 seconds at 2k to
2.796/2.465/1.701 seconds at 8k for 80%/50%/25% retention. This supports continuing
the progressive cost and memory check. It does not establish stable method speed
rankings: R-KV 80% first prefill took 11.531 seconds, whereas the same-prefix
decode and instrumented passes spent 2.899 and 2.902 seconds in prefill.
StreamingLLM ordinary decode took 0.366/0.498/0.375 seconds, versus
0.235/0.243/0.242 seconds on the instrumented replays. All pairs have identical
forced outputs, retention events and final occupancy. First-use or transient
costs are plausible, but their mechanism was not established. The original
ordinary timings remain in the results.

The shared analyzer accepted the new 2k and 8k runs as compatible. Six focused
figures show occupied KV, prefill/decode throughput, selection, compaction and
total VRAM with one facet per eviction method and the full control in each.
They connect only the two measured lengths, retain raw points and explicitly
state one repetition and eight decode forwards; no fit or smoothed trend is
claimed. Selection and decode plots were visually inspected. Their hashes and
the shared analysis are included in the evidence record.

The next review proposes the exact predeclared 16,384-token specification with
eight decode forwards, one repetition and 240 seconds per cell. A 50-minute
allocation preserves 120-second preflight and 2,700-second benchmark bounds,
including termination grace and bookkeeping. Scaling all measured 8k cell time
by four and adding setup gives a scheduling heuristic of about 376 seconds,
not a guaranteed bound. At \(T=16{,}392\), the \(24T^2\)-byte workspace estimate
is about 6.006 GiB and excludes other transient memory. Actual cap-checked
execution decides feasibility. No 16k submission is included in this record.

After feasible lengths are known, separately declare 64 forced decode forwards
and three repetitions to reduce the influence of first-use costs. Preserve
these original feasibility observations and all earlier infrastructure failures.
