# Executable-action prompt results

The original **0/6 scores in each arm are provisional** after the
[AppWorld scoring defect](appworld-scoring-repair-2026-11-08.md) was reproduced.
All eight completed snapshots have empty change-counter maps, which can hide
real saved mutations. Preserve these original results while corrected offline
scoring is prepared; they cannot yet establish the prompt's effect on task success.
Each arm had four normal completions, one context-limit failure, and one
600-second timeout. Those execution outcomes and their budgets remain unchanged.

Slurm job `13837736` completed in 54 minutes 30 seconds on an RTX A6000 using
source `312691d`, pinned Qwen3-8B BF16 and Mini-SGLang. Both arms ran to terminal
outcomes before offline scoring. The prompt was the only declared protocol
difference; hardware, task/seed schedule, 600-second cell budget, 40 GiB cap,
32,768-token context and sampling were matched. The explicit
[numerical qualification](pilot-numerical-qualification-2026-11-08.json) applied:
186 launch checks passed, three were skipped, and the independent reference
screen was explicitly excluded without relabeling its earlier failures.

| Measurement | Control | Candidate |
| --- | ---: | ---: |
| Original task scores (provisional) | 0/6 | 0/6 |
| Normal completion / context limit / timeout | 4 / 1 / 1 | 4 / 1 / 1 |
| Mean cell time | 267.95 s | 250.47 s |
| Task/seed-normalized error turns | 64.0% | 59.8% |
| Raw error turns / saved turns | 431 / 466 | 273 / 307 |
| Mean cell peak occupied KV | 3.211 GiB | 2.463 GiB |
| Maximum total VRAM | 20.972 GiB | 20.972 GiB |

The paired mean time difference was -17.48 seconds, with a task-bootstrap 95%
interval of [-59.64, 21.61] seconds. Shorter trajectories and lower
occupied KV do not establish better useful execution or a cache-method tradeoff.
There are only three task clusters; seeds are not extra independent tasks.
The all-zero bootstrap success interval is degenerate, so the figure also shows
the conservative bounded interval. No interruption time was imputed in this run.

Ordinary candidate traces show residual execution problems:

- On `0d8a4ee_1`, seed 17 sent a message to the supervisor's own number without
  establishing the intended recipient set. Seed 18 repeated authentication and
  unclosed-reasoning failures until the context cap.
- On `3ab5b8b_1`, download loops stopped when a song was already downloaded.
  Both attempts declared completion without establishing all requested downloads.
- On `57c3486_1`, seed 17 misread the account-password response and repeated
  validation errors until timeout. Seed 18 repeatedly omitted the access token
  and eventually reported failure to retrieve the artists.

These symptom labels use saved actions and observations, not evaluator answers.
All twelve trajectories contain errors. The separately declared
[14B pilot](execution-qwen14b-2026-11-08-plan.md) has also completed, with its
original scores affected by the same defect. Correct scoring before choosing
the next train/dev operating regime or expanding retention sweeps.

The bounded [transcript audit](execution-transcript-audit-2026-11-08.json)
reconstructed all twelve saved trajectories using the pinned tokenizer: consumed
responses and observations matched across 773 turns, with the two expected
incomplete final responses at the explicit context limit. Supervisor identity,
available apps and task context were present; message roles and reasoning
retention followed the pinned Qwen template and canonical AppWorld conventions.
No transport or template defect was identified within this audit. This does not
prove that the model, inference engine or environment is universally correct.

The [result inventory](execution-prompt-2026-11-08-results.json) records run IDs,
configuration and artifact hashes, paired uncertainty, resource coverage and
estimated FLOPs. The [attempt table](execution-prompt-2026-11-08-attempts.csv)
contains all twelve outcomes. All 318 copied run files were verified against
their remote SHA-256 inventory. The short forced-history smoke also completed
all ten conditions and thirty passes; longer histories remain separate work.

[Diagnostic figure](execution-prompt-2026-11-08-baseline.svg). This figure preserves the original provisional
scores and must not be presented as a validated task-success comparison.

Reproduce the paired report from the intact execution directories, then render it
in the managed plotting environment:

```sh
comet compare-protocol "$CONTROL_RUN" "$CANDIDATE_RUN" --protocol-field prompt \
  --output "$REPORT_DIR/comparison.json"
comet plot-baseline "$REPORT_DIR/comparison.json" \
  --output "$REPORT_DIR/baseline.svg" \
  --title "Executable-action prompt diagnostic: no task successes"
```
