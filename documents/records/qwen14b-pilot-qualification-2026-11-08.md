# Bounded Qwen3-14B pilot qualification

The pinned Qwen3-14B BF16 runtime is qualified for the declared six-cell
exploratory task pilot on NVIDIA L40 under a 40 GiB cap. The default numerical
screen remains **failed**, its tolerances are unchanged, and this is **not final
study qualification**. The [machine-readable record](qwen14b-pilot-qualification-2026-11-08.json)
pins the config, runtime and underlying artifacts.

GPU validation `13838687` used source `312691d`, the corrected sampler,
Mini-SGLang `254c57b`, model/tokenizer `40c0698`, and the managed package locks.
All 186 other checks passed; three optional checks were skipped. The default
reference failed only relative RMSE at three of 24 positions: 0.050887,
0.051121 and 0.051223 against the unchanged 0.05 bound. Its maximum centered
RMSE was 0.155744 and Jensen-Shannon divergence was 0.000156 nats, both within
their existing bounds. Greedy tokens agreed at all 24 positions. The separately
declared corpus passed every gate, with maximum relative RMSE 0.033073,
centered RMSE 0.113507 and Jensen-Shannon divergence 0.001948 nats.

CPU calibration `13838767` evaluated the exact default histories in FP32 with
the same pinned Transformers implementation. Native BF16 versus FP32 had
maximum relative RMSE 0.033464, centered RMSE 0.101769 and Jensen-Shannon
divergence 0.000249 nats. Transformers BF16 versus FP32 also stayed within all
existing bounds. Both matched FP32 greedy tokens at all 24 positions. Native
pooled RMSE was 0.062449 versus 0.086950 for Transformers BF16. These findings
support numerical precision drift as the narrow screen failure's explanation;
they do not prove equivalence of all output probabilities or task behavior.

Live capacity checks retained the complete 32,768-token pool. Full-cache
inference reached 32,739 cached tokens with a peak total VRAM use of
36,344,037,376 bytes; AgentKV at 80% reached 36,599,889,920 bytes, both below
the 42,949,672,960-byte cap. The latter is integration evidence only; the
qualified task pilot uses full cache, one fresh attempt and no recovery.

The [predeclared pilot](execution-qwen14b-2026-11-08-plan.md) retains the three
dev tasks, seeds 17/18, 600 seconds per cell, 32,768-token context, 4,096-token
output limit, sampling settings and executable-action prompt. Its config SHA256
is `ea166a427df86046402898af3248fc0d76f552522c1b8ce6f451b19a6e1edaa9`.
The launcher must save this qualification and explicitly exclude only
`test_full_cache_against_transformers` from a fresh managed GPU suite; every
other applicable check must pass. It must execute all six cells before offline
scoring and retain failed or infeasible outcomes. No numerical gate is changed
or reported as passing by exclusion. This record reports no 14B task results.
