# Live segmentation and interruption validation

Job `13839778` passed the managed live resume check in **4m50s** on an NVIDIA
RTX A6000. It used real Qwen3-8B BF16 outputs, one declared dev task and seed,
and three ordered full-cache cells with separate 120-second budgets. No task
scores were produced. The [evidence record](resume-validation-2026-11-08.json)
pins 29 artifacts and the exact runtime, fixture and configuration identities.

The external validation fixture came from
`b5c44d2d122a8d22f404b76f74694f4c16715870`; the installed runtime remained
`fd6ee15be5b98db00ef687d43cc66cc6a8a2cb5c`. Model/tokenizer revision was
`b968826d9c46dd6066d109eabc6255188de91218`, with the pinned Mini-SGLang engine,
CUDA 12.8, driver 575.57.08 and unchanged 40 GiB cap. The fixture used the
shared validation launcher and actual experiment CLI.

| Cell | Attempt ceiling | Observed attempts | Terminal status | Charged seconds |
| --- | ---: | ---: | --- | ---: |
| Preserved | 1 | 1 | Completed | 78.956 |
| Interrupted | 2 | 1 | Interrupted | 120.000 |
| Fresh | 1 | 1 | Completed | 86.811 |

The first launch stopped cleanly after one cell with `--max-cells 1`. The
manifest remained unfinished, neither later cell started, and offline scoring
refused the incomplete run without modifying artifacts. All 22 files in that
completed cell retained their hashes and modification times through both resumes.

The second launch was paused and killed after one real generated tool action
and its saved observation, containing 3,708 raw tokens. A changed-budget resume
was rejected without changing any run artifact. Resuming the original
configuration preserved the interrupted trajectory, recorded
`process_interrupted`, consumed the entire 120-second budget and started no
replacement attempt despite its ceiling of two. This reservation is conservative
budget accounting, not measured inference time.

The remaining cell started at attempt zero with the paired seed and a distinct
AppWorld environment. All three fresh starts had identical first turns and the
same 3,708-token prefix. The manifest recorded all three launches, including the
clean-stop reason and final completion. No evaluator feedback entered execution.

All 92 output files were copied and SHA-256/size verified. A separate remote
inventory independently confirmed the completed-cell hashes and modification
times, and the interrupted trajectory hash. Protected source checkouts and runtime
markers were unchanged.

This validates clean segmentation, isolation and interruption accounting for the
tested shared runner. It does not continue a killed attempt in place, establish
task capability, change numerical gates, or qualify a final study. Combined
AppWorld/native-KV checkpoint branching and recovery remain a separate check.
Reusable instructions are in [the resume guide](../resume-validation.md).
