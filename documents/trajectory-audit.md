# Offline trajectory audit

Before expanding the pilot, inspect ordinary tool-use symptoms with:

```sh
python scripts/audit_trajectories.py /path/to/saved-run --output /path/to/new-audit.json
```

This CPU-only analysis reads saved `trajectory.json` files without loading a
model, invoking tools, changing outcomes, or reading evaluator feedback. Run it
through Slurm for large archives. It records input hashes and relative paths,
first error turns, longest consecutive error streaks, exact repeated action
strings, and the ordered error categories used in the October 20 report.
Only string actions enter the repetition denominator; missing actions do not.
No raw observations or action contents are exported.

These are symptoms, not proven failure causes. Missing trajectories remain
missing; counts do not establish task success or replace the shared analysis.
Keep seeds and runs separate. Existing outputs are never overwritten.

Next research steps remain: diagnose the low full-cache baseline on train/dev,
version any resulting setting changes separately, validate the required 8B/A100
pilot, freeze budgets and triggers, then run recovery and best-of-N comparisons.

Schema 2 (the default) recognizes AppWorld's `Response status code is 401/422`
messages as well as `HTTP 401/422`. Category precedence and the error-turn
predicate are unchanged. Status codes require a word boundary. To reproduce a
historical schema-1 report exactly, add `--schema-version 1`; write corrected
reports to a new output and preserve the original hashes and summaries. The
shared implementation is `comet.trajectory_audit`; the script is a thin entry point.
