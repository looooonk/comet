# Progressive history feasibility

The completed A6000 smoke verified all ten conditions and all thirty passes,
including exact forced tokens and saved hashes. At 1,032 logical cached tokens,
occupied counts were 1,032 for full KV, 826 at 80%, 516 at 50%, and 258 at 25%.
The reserved pool remained approximately 4.50 GiB. All cells together took
13.16 seconds, excluding 10.76 seconds of setup. One short repetition cannot
rank speed: one StreamingLLM measurement changed substantially on its subsequent
instrumented replay.

The next declared stages use the same history, seed 17, eight decode forwards,
one repetition, model and A6000 settings. Lengths are 2,048, 8,192, 16,384 and
32,600 tokens. The [exact plan](history-feasibility-2026-11-08-plan.json) records
each configuration hash, per-cell timeout and whole-process bound. Initially run
only 2,048 then 8,192, stopping the progression if any condition or pass fails.
Review their measured runtime and memory before submitting the longer stages.
The initial two stages are provisionally expected to take 2-6 minutes including
checks and setup, but the allocation allows 50 minutes for their declared bounds.

R-KV forms quadratic similarity, mask and integer-index tensors. Its head-chunk
limit cannot split below one head, and a simultaneous integer-zero temporary
increases live memory. At 32,600 tokens, those single-head temporaries can
approach 18.8 GiB in addition to approximately 20 GiB of resident model/cache
state. The 40 GiB operating range therefore needs measurement. Long prefixes
also exercise in-place cache movement not established by the short smoke.

This is feasibility and cost diagnosis, not task-success evidence. The recorded
numerical qualification still applies: preserve the reference discrepancies and
do not claim numerical equivalence or final-study qualification. Keep the engine
at `312691d` while the paired task pilot runs. Stage these versioned configuration
files outside that active checkout; save their configuration commit and hashes
separately without mutating the running source or environment.

After feasibility, run three repetitions at the prespecified feasible lengths,
retaining all failed-length evidence. Freeze timing allowances using the rules
in the plan before those repetitions. Report all repeats with medians/ranges;
do not attach task-bootstrap intervals to these timing repetitions. Keep first-use
measurements visible. Synchronized prefill/decode-loop timings include eviction
and output processing, but exclude surrounding scheduling, resets and verification.
Selection and compaction times are nested components and must not be added to
those loop durations again. Preserve whole-pass and inference elapsed time too.
