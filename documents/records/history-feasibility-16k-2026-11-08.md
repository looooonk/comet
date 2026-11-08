# Completed 16k history feasibility

Job 13839231 completed all ten conditions and thirty passes on an A6000 in
225 seconds. All 78 remote files (457,852 bytes) were copied and independently
SHA-256 verified. Saved inputs match the original 16,393-token history prefix;
forced outputs, retention counts, complete metric coverage and the 40 GiB cap
verified for every pass. This establishes feasibility at 16,384 tokens for this
run, not model accuracy or task success. The [evidence record](history-feasibility-16k-2026-11-08.json)
contains the exact source, configuration, qualification and artifact hashes.

Source `312691d`, managed runtime and numerical qualification stayed unchanged.
The completed source-matched GPU validation from job 13837736 was reused after
strict compatibility checks. OMP/MKL and PyTorch intra-op threads were six,
inter-op threads were 64, and affinity matched the new 2k and 8k runs.
Earlier 1k inherited thread settings were unrecorded, so that smoke remains
separate. No task tools or evaluator ran.

Setup and warmup took 13.93 seconds; all cells together took 205.63 seconds.
The largest cell took 43.73 seconds, below its 240-second limit. Reserved KV
pool size remained 4.50014 GiB, whereas maximum observed total VRAM reached
27.786 GiB. Parked prefill occupancy was 16,384 entries for full KV, 13,108
at 80%, 8,192 at 50%, and 4,096 at 25%. Decode used 16,392 logical cached
tokens and respectively 16,392/13,114/8,196/4,098 physical entries.

| Method | Retention | Prefill loop tok/s | Decode loop tok/s | Selection ms/replay | Compaction ms/replay | Peak total GiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full KV | 100% | 4240.4 | 35.10 | 0.00 | 0.00 | 20.966 |
| StreamingLLM | 80% | 4090.6 | 24.40 | 9.20 | 50.64 | 20.972 |
| StreamingLLM | 50% | 4121.4 | 15.28 | 14.67 | 60.99 | 20.970 |
| StreamingLLM | 25% | 4173.1 | 29.12 | 20.61 | 61.16 | 20.968 |
| R-KV | 80% | 1920.9 | 0.74 | 10682.15 | 44.73 | 27.786 |
| R-KV | 50% | 1901.3 | 1.56 | 9414.47 | 74.32 | 27.773 |
| R-KV | 25% | 1913.3 | 3.62 | 6548.42 | 78.24 | 27.759 |
| AgentKV | 80% | 4051.8 | 23.08 | 111.87 | 56.39 | 21.134 |
| AgentKV | 50% | 4049.8 | 22.33 | 138.75 | 55.14 | 21.118 |
| AgentKV | 25% | 4062.5 | 22.72 | 144.19 | 47.61 | 21.105 |

Ordinary synchronized loop rates include eviction/output processing, excluding
surrounding scheduling, reset and verification. Selection and compaction sum
the whole instrumented prefix-plus-continuation replay. They are nested costs,
not per-token rates or additions to total inference. Table peaks take the maximum
over all three passes; shared memory figures use their declared prefill boundary.

R-KV whole-replay selection totals reached 10.682/9.414/6.548 seconds at
80%/50%/25% retention, compared with 2.796/2.465/1.701 seconds at 8k.
Single-repeat noise remains visible: its 80% ordinary decode took 10.860 seconds
versus 6.348 seconds on the instrumented replay. StreamingLLM 80% and 50%
ordinary decode took 0.328 and 0.523 seconds, versus 0.261 and 0.274 seconds
on their instrumented replays. All ordinary/instrumented pairs have identical
outputs, retention events and final occupancy. These differences are compatible
with first-use or transient costs, without proving a cause. Instrumented timing
does not replace ordinary measurements, and these feasibility runs do not support
stable method speed rankings.

The shared analyzer accepted the new 2k, 8k and 16k runs as compatible. Six
focused figures show occupied KV, prefill/decode throughput, selection,
compaction and total VRAM. Each uses one facet per method, repeats the full
control, retains raw measured points and connects only the three measured
lengths. They explicitly state one repetition and eight decode forwards; no
fitted or smoothed trend is claimed. The selection figure was visually inspected.
Hashes identify all figures and the common analysis in the evidence record.

The next declared length is 32,600 tokens, with eight decode forwards, one
repetition, 480-second cells and a 5,100-second benchmark bound. No wrapper or
submission for that length is included here. Scaling all measured 16k cell time
by the squared length ratio and adding setup gives about 828 seconds as a
scheduling heuristic, not an upper bound. The conservative \(24T^2\) workspace
term at \(T=32{,}608\) is 23.766 GiB before linear and other allocations, making
feasibility under 40 GiB uncertain. This term belongs to recovery admission;
forced-history generation uses allocator and live cap enforcement. It should
not be added mechanically to an already measured total peak. Preserve any
capacity failure without relaxing cap, precision or retention.

Once feasible lengths are known, separately declare 64 forced decode forwards
and three repetitions for the main cost plots. Keep these original feasibility
observations and earlier infrastructure failures in the supplementary evidence.
