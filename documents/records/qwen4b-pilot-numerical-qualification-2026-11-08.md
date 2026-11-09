# Qwen3-4B bounded pilot qualification

The pinned Qwen3-4B-Instruct-2507 runtime has sufficient numerical and integration
evidence for the six declared exploratory full-cache dev cells on an NVIDIA RTX
A6000. This is not final-study qualification or evidence of task capability.
Both original GPU numerical screens remain **failed**; no gate was changed.
The [machine-readable record](qwen4b-pilot-numerical-qualification-2026-11-08.json)
contains the exact metrics, identities, and 25 artifact hashes.

## Fixed scope and integration

The runtime is source `fd6ee15be5b98db00ef687d43cc66cc6a8a2cb5c`, model/tokenizer
revision `cdbee75f17c01a7cc42f958dc650907174af0554`, and the pinned Mini-SGLang
engine in BF16. The pilot configuration SHA-256 is
`d342228e83ddd750a61e3086108d6f5a3c6e1e4cd629c1d8e81575b3af3ebf1b`.
The scope is three declared dev tasks, seeds 17/18, full cache, and a 40 GiB
peak VRAM cap. Submission requires separate launcher review.

GPU job `13839303` finished in 8m30s. Its full shared suite reported 278 passed,
8 skipped, and one failed numerical reference test. The separately run heldout
reference test also failed. The skips concern optional plotting and the separate
process-kill resume test. Sampling, real AppWorld state/scoring, persistence,
recovery, and memory-admission checks passed.

The nonthinking phase diagnostic preserved occupancy `[8, 8, 0, 8]` through full
restore, AgentKV branching, compressed restore, recovery, and recovered restore.
Its continuation was synthetic and executed no tools. The capacity diagnostic
reached 32,739 logical cached tokens in a 32,768-token pool; measured total peaks
were 14,567,931,904 bytes for full cache and 14,838,464,512 bytes for AgentKV 80%,
both below the unchanged cap. These checks do not establish long-task success.

## Original numerical failures

Each corpus contains six fresh/cached histories and four predictions per history.
The default screen failed relative centered RMSE at two fourth cached predictions
(0.054609 and 0.060963, bound 0.05). Both follow emitted EOS token 151645 and
predict newline token 198. They remain included. All 24 greedy predictions agreed.

The heldout screen failed Jensen-Shannon divergence at five positions, reaching
0.014610 nats against a 0.002 bound. One fresh tool-state prediction differed:
native token 40 versus HF BF16 token 785, with HF BF16 regret 0.75. Overall greedy
agreement was 23/24; all heldout centered-RMSE and relative-RMSE bounds passed.

## Independent FP32 calibration

CPU job `13839386` exhausted its 270-second diagnostic budget before saving any
vector: 83.34s went to model loading and only 1.96s to first-forward causal-mask
initialization, with approximately 185.66s in preceding validation/import work.
It remains an operational failure, not a numerical observation. The approved
retry changed only runtime bounds and repeated no completed corpus.

CPU retry `13839610` completed both corpora in 6m18s with eight threads. It used
the same pinned Transformers implementation, exact recorded histories, eager
attention, CPU FP32, and no KV cache. Serving precision remained BF16.

| Corpus / implementation against FP32 | Pooled centered RMSE | Maximum relative centered RMSE | Maximum JS, nats | Greedy agreement |
| --- | ---: | ---: | ---: | ---: |
| Default / native BF16 | 0.059202 | 0.031860 | 0.000145 | 24/24 |
| Default / HF BF16 | 0.084988 | 0.053781 | 0.001995 | 24/24 |
| Heldout / native BF16 | 0.043988 | 0.018672 | 0.001827 | 23/24 |
| Heldout / HF BF16 | 0.073471 | 0.034726 | 0.016979 | 24/24 |

The heldout argmax discrepancy is a near tie in FP32: token 785 exceeds token 40
by 0.008739, rather than the HF BF16 margin of 0.75. Native descriptive maxima
meet the existing error/regret bounds, and both corpus agreement fractions exceed
0.90. Native pooled centered RMSE is lower than HF BF16 in each corpus.

These 48 fixed vectors support the bounded pilot while limiting the inference to
the tested histories. They do not establish broad equivalence, long-trajectory
correctness, a useful task-success regime, or final qualification. No numerical
positions, original failures, or gates were removed or relabeled. All original
artifacts, source checkouts, and runtime markers remained unchanged; the GPU
evidence and both CPU outcomes were copied and SHA-256 verified.
