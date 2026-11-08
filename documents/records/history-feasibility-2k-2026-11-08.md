# Completed 2k history feasibility

Job 13839209 completed all ten conditions and thirty passes on an A6000 in
46 seconds. All 78 remote files (319,008 bytes) were copied and independently
SHA-256 verified. Saved inputs match the original 2,057-token history prefix;
forced outputs, retention counts, complete metric coverage and the 40 GiB cap
verified for every pass. This establishes feasibility at 2,048 tokens for this
run, not model accuracy or task success. The [evidence record](history-feasibility-2k-2026-11-08.json)
contains the exact source, configuration, qualification and artifact hashes.

The unchanged source `312691d` runtime reused the completed GPU validation from job
13837736 after strict hash, package, lock, model, driver, CUDA and device-capacity
checks. The timed-out validation attempt 13839171 remains failed. OMP/MKL and
PyTorch intra-op threads were six; inter-op threads were 64, with six affinity
entries recorded. Earlier 1k inherited thread settings were not recorded, so that
smoke remains a separate diagnostic.

Setup and warmup took 18.45 seconds, and all cells together took 22.07 seconds.
The largest cell took 2.91 seconds. Reserved KV pool size stayed 4.50014 GiB;
the maximum observed total VRAM was 21.534 GiB.
Parked prefill occupancy was 2,048 entries for full KV, 1,639 at 80%, 1,024 at 50%,
and 512 at 25%. Decode occupancy used 2,056 logical cached tokens and respectively
2,056/1,645/1,028/514 physical entries.

| Method | Retention | Prefill loop tok/s | Decode loop tok/s | Selection ms/replay | Compaction ms/replay | Peak total GiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full KV | 100% | 5228.9 | 39.16 | 0.00 | 0.00 | 20.966 |
| StreamingLLM | 80% | 4242.8 | 6.64 | 8.91 | 9.86 | 20.966 |
| StreamingLLM | 50% | 4463.1 | 17.03 | 14.63 | 13.03 | 20.968 |
| StreamingLLM | 25% | 5130.6 | 34.42 | 20.29 | 14.79 | 20.968 |
| R-KV | 80% | 4228.2 | 23.57 | 219.50 | 8.16 | 21.534 |
| R-KV | 50% | 4270.6 | 23.00 | 224.82 | 10.50 | 21.534 |
| R-KV | 25% | 4273.0 | 22.76 | 230.89 | 11.39 | 21.532 |
| AgentKV | 80% | 5005.9 | 33.56 | 46.55 | 7.88 | 20.970 |
| AgentKV | 50% | 5021.8 | 29.64 | 77.19 | 10.54 | 20.970 |
| AgentKV | 25% | 5012.2 | 26.55 | 107.02 | 10.69 | 20.972 |

Ordinary synchronized loop rates include eviction/output processing. Selection
and compaction are whole instrumented prefix-plus-continuation replay totals,
not per-token rates and not additions to total inference. Single-point figures
for occupied KV, prefill/decode throughput, selection, compaction and total VRAM
are preserved in the artifact inventory; no length curve is claimed.

The StreamingLLM 80% ordinary decode pass took 1.2045 seconds, versus 0.2154
seconds on its instrumented replay; 50% took 0.4697 versus 0.2236 seconds.
All ordinary/instrumented pairs have identical outputs, retention events and
final occupancy. This is consistent with first-use or transient overhead, but
does not prove compilation as the cause. Instrumented timing is not substituted
for ordinary timing. AgentKV 50% also had about 1.03 seconds outside saved pass
elapsed time, which includes journals and surrounding orchestration. These
single repetitions cannot establish stable method speed rankings.

The next proposed stage is the already declared 8,192-token specification with
eight decode forwards, one repetition and 120 seconds per cell. A 30-minute
allocation preserves 120-second preflight and 1,500-second benchmark bounds.
Scaling all measured 2k cell time by the square of the fourfold length increase
and adding setup gives a conservative planning heuristic of about 372 seconds,
not a measured curve or guarantee. For \(T=8{,}200\) cached tokens, the
\(24T^2\) byte workspace estimate is about 1.50 GiB, excluding other workspaces;
feasibility still requires
the actual cap-checked run. No 8k job has been submitted by this record.

After length feasibility, separately declare 64 forced decode forwards and three
repetitions for more stable timing. The 32,719-token source contains the 32,665
tokens required even at a 32,600-token prefix. Preserve the original feasibility
data and first-use observations; do not fit or smooth invented trends.
