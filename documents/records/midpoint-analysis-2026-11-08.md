# COMET midpoint evidence

## Study design

This midpoint separates inference cost from AppWorld task quality. Both analyses
use existing train/dev evidence. The analysis pins the source commit and hashes
its inputs. It does not run inference or rescore any attempt.

1. **Cost of KV eviction.** Hold the model, GPU, history, continuation tokens,
   precision and memory cap fixed. Use the completed Qwen3-8B BF16 A6000 grid
   spanning 2,048 to 16,384 history tokens. The original grid has ten conditions
   per length and three technical repetitions, with 150 cells and 450 total
   passes. The main view compares full KV with StreamingLLM, R-KV and AgentKV at
   50% retention. Report median ordinary decode throughput, occupied KV and
   peak total VRAM separately. Express throughput relative to the full-KV
   median at the same length. This is one fixed history.
2. **Full-cache baseline failure analysis.** Use the corrected scores for the
   matched 8B prompt comparison. Compare terminal status and elapsed time by
   task and seed at the same 600-second limit and 40 GiB cap. Average the two
   seed differences within each task, then weight the three tasks equally.
   Omit each task in turn to check how much it drives the result. Retain all
   timeouts and context-limit cells. Report the separate 14B and older 8B
   diagnostics on their own.

## Results

At 16,384 history tokens, all three compressed methods halved occupied KV.
Peak total VRAM stayed close to full KV for StreamingLLM and AgentKV, and
increased by 6.81 GiB for R-KV. The source records 43.27 seconds in R-KV
selection in the separate instrumented pass at this length. Its selection cost
is specific to the pinned implementation and retention schedule.

| Method | Decode tok/s | % of full-KV throughput | Occupied KV (GiB) | Peak total VRAM (GiB) |
| --- | ---: | ---: | ---: | ---: |
| Full KV | 35.21 | 100.0% | 2.25 | 20.97 |
| StreamingLLM 50% | 29.70 | 84.4% | 1.125 | 20.97 |
| AgentKV 50% | 22.57 | 64.1% | 1.125 | 21.12 |
| R-KV 50% | 1.57 | 4.5% | 1.125 | 27.77 |

The [cost study and figures](https://github.com/looooonk/comet/blob/772b7e8247faf004e92731d4779b06e1368ba8f0/documents/records/history-timing-grid-2026-11-08.md)
cover all five lengths. A separate 32,600-token capacity check recorded three
R-KV cap failures. Those runs remain separate from this grid. Throughput on
forced histories cannot establish task success or the value of recovery.

The [corrected AppWorld scores](https://github.com/looooonk/comet/blob/772b7e8247faf004e92731d4779b06e1368ba8f0/documents/records/appworld-corrected-pilot-scoring-2026-11-08.md)
were **0/6 for each 8B prompt arm**, with three tasks and two seeds per arm.
Each arm had four normal completions, one timeout and one context-limit
failure. The separate 14B exploratory arm was also 0/6. The scorer repair
recognized previously missed mutations while leaving aggregate success unchanged.

The 8B candidate finished **17.48 seconds earlier on average**, but the estimate
ranged from **37.02 seconds earlier to 3.60 seconds later** when omitting one task
at a time. Task `57c3486_1` had a timeout in both arms on opposite seeds. Omitting
that task reverses the sign of the mean difference. This sensitivity check is
descriptive and has three task clusters. It supports neither a speedup claim nor
a task-quality improvement.

In the separate historical 38-rollout 8B diagnostic, 19 runs timed out, five
hit the context cap and 14 completed normally without solving the task. Eighteen
timeouts were logged during inference and one during the completion observation.
That breakdown identifies where the budget expired. The old sampler defect and
the aggregate failure labels limit attribution of why the trajectories ran out
of time.

## Follow-up experiment

Use the team's declared full-cache dev schedule to qualify an operating point
before measuring recovery quality. Require useful corrected AppWorld outcomes
across multiple task families, verified model/runtime support and measured
budget feasibility. Record the decision and freeze numerical settings on dev
before opening the test split.

- **Checkpoint diagnostic for Q1.** Select checkpoints using observable dev
  criteria, such as context length and completed tool-call count. Branch from
  identical saved transcript, environment, KV and RNG state. Compare never,
  fixed tool-count and dynamic triggers within each method and retention level.
  Charge checkpoint preparation and rebuilding to the common budget, enforce
  the transient VRAM cap, and log cap refusals separately.
- **Fresh-task evaluation for Q2.** Use the agreed test subset and paired seeds.
  Compare full-cache best-of-N and compressed best-of-N with and without
  recovery at 80%, 50% and 25% retention. Apply the same wall-clock and VRAM
  caps to each condition and start every attempt from fresh environment state.
  Score offline after execution, report actual attempt counts and cost, and
  bootstrap paired differences by task.

## Reproduction

From a COMET checkout containing source commit
`772b7e8247faf004e92731d4779b06e1368ba8f0` (the November 8 `dev/yenna` snapshot),
run the standard-library analysis. If the source object is absent, fetch the
development ref with `git fetch origin dev/yenna` first.

```sh
python3 scripts/analyze_midpoint.py . > /tmp/comet-midpoint.json
cmp /tmp/comet-midpoint.json documents/records/midpoint-analysis-2026-11-08.json
```

Slurm CPU job `13840199` completed with exit code 0 in five seconds. The
[committed result](midpoint-analysis-2026-11-08.json) matched a local rerun
byte-for-byte. Output SHA-256
`0e8e2bc13bc6ff893bbe9d1d5692e5a7cd118b3dd43df2a2837bf0375ed528a9`.
