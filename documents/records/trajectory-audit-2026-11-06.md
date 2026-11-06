# November 6 offline trajectory audit

Source `cb8b996` added an offline symptom audit. Three focused tests passed on
Windows and on Insomnia Linux. Ruff was unavailable in both environments, so no
lint pass is claimed. Slurm job `13817981` completed in 24 seconds, exit 0.
No inference, evaluator, or GPU allocation was used by this audit.

| Saved run ID | Seed | Trajectories | With error turns |
| --- | --- | ---: | ---: |
| `113994b3-61c4-454f-bd7e-0f5f9bf63c26` | 17 | 32 | 29 |
| `fc1712b6-991e-45f2-9c24-240078e7f9c6` | 18 | 32 | 29 |

The corresponding `trajectory-audit-2026-11-06-seed17.json` and `seed18.json`
files contain relative trajectory identifiers, input hashes and per-attempt
counts. These are different runs from the published October 20 repaired pilot;
their 32-trajectory coverage must not replace that report's 31 observed traces.
Seeds remain separate, and this audit does not claim task success rates.

Seed 17 contains 40 unknown-API and 22 unexpected-parameter error turns;
seed 18 contains 75 and 31 respectively. Invalid-action turns number 29 and
129. Longer trajectories have more opportunities for errors; these totals are
not normalized rates or proof of causality. Inspect first-error turns in the
underlying ordinary trajectories before proposing a versioned train/dev fix.
Preserve completed results; do not change the main evaluation or select tasks
using evaluator outcomes.
