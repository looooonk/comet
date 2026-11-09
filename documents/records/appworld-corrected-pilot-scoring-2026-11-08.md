# Corrected AppWorld pilot scoring

CPU job `13839241` completed the repaired live checks and rescored three saved pilot runs with source `178e6f3f10b388c5baceb0fb1da17cb92106a4da`. The corrected oracle task success is **0/6 in each run**. This is a scoring revision of the same executions, not new inference or additional independent observations. It supersedes the provisional interpretation of the original scores described in [the scoring repair record](appworld-scoring-repair-2026-11-08.md).

| Saved execution | Corrected success | Completed attempts compared | Execution failures retained | Corrected score SHA256 |
| --- | --- | --- | --- | --- |
| 14B exploratory candidate, job 13839132 | 0/6 | 6 | none | `6549d6147c60a94db5ee80d6ebf6e3fb19d70250a07d2d19c8309b1ac0297f85` |
| 8B control, job 13837736 | 0/6 | 4 | one context limit; one timeout | `ab5ab30994f3d038927d277171ad2b37928314e368c8d6b77e617b707729b8c3` |
| 8B candidate, job 13837736 | 0/6 | 4 | one context limit; one timeout | `ca71cdc7b18fd77b7b5f7150c552fd287a8c3aae59203efd61064b5e9d2b6e7f` |

The managed AppWorld profile passed **five live tests** in 36.408 seconds: fresh state/checkpoint/offline scoring, unchanged mutation-counter roundtrip, a real phone-mutation roundtrip, explicit authentication/response parsing, and pagination coverage. One unrelated numerical module was skipped because this CPU profile has no PyTorch. The entire CPU job completed in 115 seconds. No GPU or model inference was used.

All **14 completed attempts** received `exhaustive-model-comparison-v1` checks across **103 models each**. This disables the unreliable counter-equality shortcut while retaining the pinned evaluator's actual row-count and record-hash comparisons. Ten previously failing model-change assertions now pass, and one further assertion reports a nonempty changed-model set. The successful sends and likes that exposed the defect are therefore recognized. Other task checks still fail, so the aggregate task success remains zero. Evaluator requirements were not used to choose actions, tasks, or prompts.

Each revision was produced with `comet rescore ORIGINAL --output REVISION`, analyzed separately, and the two 8B arms were compared through the shared protocol analysis. Original manifests, cell records, saved environments, raw trajectories, execution digests, scores, and analyses were checked before and after. They are unchanged. Prior score/analysis files are also archived inside each new revision. The four 8B execution failures retain their original failure status and receive no replacement attempts or extra budget. Original execution source `312691d00fe84ce52a504071ccd5ed0bdd40a0f9` and both managed runtime markers remained unchanged.

The paired 8B and separate 14B pilots each cover three declared dev tasks with two seeds and one attempt per cell. These six cells do not constitute six independent tasks. The 14B execution used its recorded pilot-only numerical qualification; rescoring does not extend that qualification or establish final-study numerical equivalence. The corrected results remain baseline diagnostics and do not yet provide a useful nondegenerate task-success regime for the retention study.

Portable artifact identifier: `appworld-rescore-178e6f3-20261108-13839241`. All 421 output files were copied and verified against their remote SHA256 inventory. Key audit files:

| Artifact | SHA256 |
| --- | --- |
| `verification-summary.json` | `a8f455091ceaf8280fd509885698789fa8d298efff72bb09d470ef57ef5f0f29` |
| `original-before.json` | `2af8ae994a7a29a6efd1cd12658a1848923bf86e6de9553d90fd8e9bcf9b1d3d` |
| `original-after.json` | `2af8ae994a7a29a6efd1cd12658a1848923bf86e6de9553d90fd8e9bcf9b1d3d` |
| `validation/pytest.xml` | `4d1471518f105fadb359b27f69e7521de12fced49fa0d9039e21568e47cf52bf` |
| `qwen8b-comparison.json` | `8e96a8ea7f5fc77b3abcc281a54313ab2729914fb22fe470bc610be0af012f23` |

Each `qwen14b`, `qwen8b-control`, and `qwen8b-candidate` subdirectory contains corrected `scores.json`, `analysis.json`, `rescoring/derivation.json`, archived prior outputs, unchanged execution artifacts, and per-completed-attempt `evaluation/state-comparison.json` evidence. Original score hashes and execution digests are pinned by the derivations and the identical before/after inventories.
