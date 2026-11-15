# Legacy midpoint studies

[Ledger index](README.md)

**Historical evidence, summarized November 8, 2026.** These measurements use
Qwen3-8B and the older backend on RTX A6000, with separate exploratory model
diagnostics. They are not Qwen3.5-9B results. The current
[research contract](../documents/research-direction.md) supersedes their execution
plan; they are not pending work to restart.

## Fixed-history cost experiment

The benchmark holds model, GPU, history, continuation tokens, precision and cap
fixed: Qwen3-8B BF16 on A6000, five history lengths from 2,048 to 16,384 tokens,
ten conditions per length, three technical repetitions, 150 cells and 450 passes
in the recorded grid. One fixed history limits generalization; repeated passes
are not independent task samples.

At 16,384 tokens, the selected 50%-retention comparison is:

| Method | Decode tokens/s | Relative throughput | Occupied KV, GiB | Peak total VRAM, GiB |
| --- | ---: | ---: | ---: | ---: |
| Full KV | 35.21 | 100.0% | 2.250 | 20.97 |
| StreamingLLM 50% | 29.70 | 84.4% | 1.125 | 20.97 |
| AgentKV 50% | 22.57 | 64.1% | 1.125 | 21.12 |
| R-KV 50% | 1.57 | 4.5% | 1.125 | 27.77 |

All three methods halve occupied KV, while R-KV adds 6.81 GiB to peak total
VRAM in this implementation. A separate instrumented pass records 43.27 s in
R-KV selection. These costs are implementation-specific and do not establish
task quality or recovery benefit. A separate 32,600-token capacity check has
three R-KV cap failures and is not pooled with this grid.

The pinned [historical cost report and figures](https://github.com/looooonk/comet/blob/772b7e8247faf004e92731d4779b06e1368ba8f0/documents/records/history-timing-grid-2026-11-08.md)
preserve the original conditions, figure provenance and artifact references.

## Corrected AppWorld scoring and prompt comparison

The matched 8B prompt comparison uses three tasks, two seeds, a 600-second budget
and 40 GiB cap. Both arms score 0/6 after corrected offline scoring; each has
four normal completions, one timeout and one context-limit failure. The separate
14B exploratory arm also scores 0/6. A normal completion is not task success.

The candidate prompt finishes 17.48 s earlier on average, but omitting one task
at a time changes the estimate from 37.02 s earlier to 3.60 s later. With three
task clusters and a sign reversal, this does not support a speedup claim.
The [corrected scoring record](https://github.com/looooonk/comet/blob/772b7e8247faf004e92731d4779b06e1368ba8f0/documents/records/appworld-corrected-pilot-scoring-2026-11-08.md)
preserves the exact cohorts and artifacts.

A separate older 38-rollout 8B diagnostic has 19 timeouts, five context-limit
stops and 14 normal completions with no successes. The old sampler defect and
aggregate failure labels limit attribution. Do not pool that diagnostic, the
14B exploration or the fixed-history benchmark with the paired prompt study.

## Evidence and reproduction

The [midpoint report](../documents/records/midpoint-analysis-2026-11-08.md) and
[committed analysis](../documents/records/midpoint-analysis-2026-11-08.json)
pin source `772b7e8247faf004e92731d4779b06e1368ba8f0` and hash their inputs.
[`analyze_midpoint.py`](../scripts/analyze_midpoint.py) reads the retired inputs
directly from Git history; the report provides the managed-CPU reproduction
command. It performs offline analysis, with no inference or rescoring. Full
history is required in a shallow clone.

Recover original runtime, model/tokenizer, prompts, configurations, GPU/cap and
raw artifacts from those pinned records for historical reproduction. Current
9B defaults cannot stand in for missing legacy conditions. Historical source
links are retained instead of copying retired exports back into this directory.
