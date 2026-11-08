# Matched-history smoke declaration

Before longer retention measurements, run
`configs/diagnostics/history-smoke-qwen8b-v1.json` through the shared
[forced-history diagnostic](../history-benchmark.md). It declares one 1,024-token
prefix, eight decode forwards, one repetition and seed 17. All ten conditions
run the same prefill, decode and separately instrumented passes. Each cell has
45 seconds for those passes together; synthetic warmup has a separate 120-second
limit. These are feasibility limits, not final task-budget choices.

The input is the first task and seed from the previously declared corrected
control: `0d8a4ee_1`, seed 17, attempt 0. Its completed source run is
`sampling-control-qwen8b-20261107-13836336`; manifest SHA-256 is
`fa1e864e6b491aaa74bdcc6606885ed4b6a6b6fde3675b318cb980a93837d38e`.
The trajectory SHA-256 is
`ea8dbed01ba6628dcac268ff71820965de2f3ebc9785f25574004e02798d9f67`.
It contains 32,719 raw tokens. Its unsuccessful task outcome does not affect
this execution-cost check, and its historical actions are never executed.

The engine uses pinned Qwen3-8B BF16, a 32,768-token capacity, 40 GiB cap,
6 GiB workspace reserve and 256-token prefill chunks, matching the new task
diagnostic. The template selects an L40S. If another approved GPU is allocated,
record a resolved specification changing only its exact `device_name`; retain
the template hash and resolved specification. Run managed validation on that
GPU before collecting measurements.

Require exact forced tokens, valid retention denominators, and complete
measurements in all ten cells before expanding this diagnostic. Preserve failed
cells and partial passes. A smoke failure does not invalidate an independently
validated full-cache task run, but it blocks using this diagnostic for retention
claims until diagnosed. One short repetition cannot establish stable throughput
or long-context workspace feasibility; those remain separate measurements.
