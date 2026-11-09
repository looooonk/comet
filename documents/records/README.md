# Results and cleanup records

- [Verified Qwen3.5-9B findings](qwen9b-findings.md): completed frozen L4 test,
  train/dev comparisons, recovery effects, measured costs and limitations.
- [Frozen test summary](qwen9b-final-summary.json): all 68 cells and 101 attempts,
  with [complete paired analysis](qwen9b-final-analysis.json),
  [trajectory case study](qwen9b-final-case-study.json) and
  [24 figure exports](qwen9b-final-figures.json).
- [Resource handoff](qwen9b-resource-handoff.json): verified cloud compute
  and cluster cleanup, retrieved outputs and retained backup inventory.
- [Optional Blackwell test status](qwen9b-final-blackwell-status.json): frozen
  but not executed because queue capacity could not meet the deadline.
- [Completed L4 pilot summary](qwen9b-pilot-summary.json): all 109 paired cells
  from compression, recovery, budgets, fine-grid and dev runs; full analyses and
  [figure exports](qwen9b-pilot-figures.json) retain their individual outcomes.
- [Live AppWorld recovery check](qwen9b-l4-appworld-recovery.json): independent
  environment restores, preserved tool effects/RNG and all three methods.
- [Blackwell qualification](qwen9b-blackwell-cap24.json): 16K generation and
  recovery at 24 GiB, preserving the [failed 21 GiB check](qwen9b-blackwell-cap21-failure.json).
- [Three-family Blackwell findings](qwen9b-blackwell-findings.md): 78 train
  fine-grid cells, 84 common-checkpoint branches, paired uncertainty and
  27 figure exports; analyzed separately from L4.
- [Blackwell dev confirmation](qwen9b-dev-confirmation-blackwell-summary.json):
  14 cells, a second-attempt full-cache success and
  [six figure exports](qwen9b-dev-confirmation-blackwell-figures.json).
- [Qwen3.5-9B study](qwen9b-study-2026-11-09.md): declared samples and current
  implementation/validation progress for the new hybrid backend.
- [A6000 state check](qwen9b-a6000-state-check.json) and
  [L4 state check](qwen9b-l4-state-check.json): compact reference, state and
  capacity evidence, including the L4 capacity failure.
- [16K L4 qualification](qwen9b-l4-context-16384.json): bounded R-KV workspace,
  all-method generation and full-history recovery under the 21 GiB cap.
- [V4 capability pilot](qwen9b-protocol-v4.json): 3/4 train successes, with all
  earlier failed pilot versions preserved in the study record.

- [Legacy results](legacy-results.md): useful findings, two retained cost figures,
  limitations, and links to archived evidence.
- [Compact verified summary](legacy-results.json): figure hashes and the completed
  eight-level GPU persistence check, which postdates the archive.
- [Repository reset](cleanup-repository-2026-11-08.md): removals, retained evidence
  and verification.
- [Insomnia cleanup](cleanup-insomnia-2026-11-08.md).
- [Runtime and cloud cleanup](cleanup-resources-2026-11-08.md).

Older plans, diagnostics, interim charts and per-run inventories are archived at
[commit 55fca50](https://github.com/looooonk/comet/tree/55fca50bfe3c69dfaa4420585e78850da1b3aaf4/documents/records).
They are historical evidence, not instructions for the next study. Keep new
records concise and portable; omit personal access paths and raw trajectories.
