# Repeated matched-history timing proposal

This versioned plan requires execution review; no repeated-timing job is submitted. Keep the
pinned source `312691d` engine, Qwen3-8B BF16, A6000, 40 GiB cap, 6 GiB reserve,
32,768-token context, 256-token prefill chunks, historical trace and six-thread
OMP/MKL policy. Change the declared workload to 64 actual decode forwards and
three independently reset repetitions. Use lengths 2,048, 4,096, 8,192, 12,288
and 16,384. The 32,600-token length is excluded because all three R-KV conditions
failed the allocator/cap path in job 13839242; its seven completed and three
failed conditions remain in the separate feasibility record.
No task tools or evaluator run. All five configurations passed the shared input/schema check against the exact
saved source prefix. The longest requires 16,449 of the available 32,719 tokens.

Keep the existing bounded synthetic warmup and serving source unchanged.
Additional per-method/per-shape warmup would create a new timing protocol and
could hide the startup work seen in feasibility. The current three-repetition
ordering runs all three repetitions of each condition consecutively, resetting
between passes. Report every repetition, the median of all three and observed
min/max, identifying repetition zero. Do not discard outliers or substitute
instrumented throughput. The first repetition is not a guaranteed cold-cache
trial: standard warmup, preceding conditions and persistent compilation caches
can already prime work. If repeats two and three remain unstable, diagnose
before claiming steady performance; a different warmup protocol would need a
separately declared version.

Conservative bounds multiply the entire measured eight-decode cell cost by
eight, even though prefill and bookkeeping do not require eightfold growth.
Cell limits add 30 seconds and round up to 30 seconds. Process limits multiply
the summed cell cost by three repetitions and eight, add 300 seconds, and round
up to 30 seconds. New intermediate lengths use the next higher measured length
as a planning surrogate. Allocation adds 120-second preflight, two 15-second
graces, 30-second bounded batch probes and 120-second bookkeeping, then rounds
up to five minutes. These limits are not runtime predictions or guaranteed
upper bounds.

| Prefix | Cost reference | Cell limit | Process limit | Allocation |
| ---: | ---: | ---: | ---: | ---: |
| 2,048 | measured 2,048 | 60 s | 840 s | 20 min |
| 4,096 | measured 8,192 | 210 s | 2,490 s | 50 min |
| 8,192 | measured 8,192 | 210 s | 2,490 s | 50 min |
| 12,288 | measured 16,384 | 390 s | 5,250 s | 95 min |
| 16,384 | measured 16,384 | 390 s | 5,250 s | 95 min |

The core allocation limits total 5.17 GPU-hours, with early exit on completion;
actual consumption should be measured. Each length expects
thirty cells and ninety pass records. Failures and missing coverage remain
visible, fail the progression gate and receive no free replacement. The 32,600 capacity failures remain in the supplementary result.
Passing eight-decode feasibility at the retained lengths also does not guarantee
that 64 decode forwards fit the same cap.

For the main explanatory figure, predeclare 50% retention as the central
representative condition and plot full KV, StreamingLLM, R-KV and AgentKV on
shared axes. This lets readers compare method cost directly. Give all retention
settings equal coverage in the full supplement: one method facet with
full/80%/50%/25% curves, raw repetition points and observed ranges. Preserve
shared units and clearly label any supplementary axis rescaling. Lines only
connect measured points, without smoothing or fitted trends.

Show parked KV, ordinary prefill and 64-forward decode throughput, and whole
ordinary decode-pass elapsed time. Selection and compaction are separate
instrumented prefix-plus-continuation totals, not per-token rates or extra time
to add to inference. Reserved pool and total VRAM are distinct memory views.
Keep the eight-decode feasibility figures separate from this new workload.
These are technical repetitions of one fixed history, not task-bootstrap
intervals, task accuracy or broad workload performance claims.

The [machine-readable plan](history-timing-2026-11-08-plan.json) records exact
configuration hashes and cost inputs. The five configurations live under
`configs/diagnostics/history-timing-qwen8b-a6000-l*-d64-r3-v1.json`. Stage their
committed bytes outside the unchanged engine checkout, recording the configuration
commit separately. Reuse the previously completed source `312691d`/A6000 qualification
only after the same strict compatibility preflight. The numerical qualification
remains bounded diagnostic permission, not final-study accuracy qualification.
