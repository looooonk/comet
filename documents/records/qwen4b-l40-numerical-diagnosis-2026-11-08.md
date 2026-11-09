# L40 numerical diagnosis, 2026-11-08

Job `13839937` completed the full shared suite and both numerical screens on NVIDIA L40 in 14m10s. It ended failed because the default and heldout numerical screens failed. The default suite had 278 passed, eight skipped, and one failed test. The five real AppWorld checks and all four native GPU checks passed. There was no timeout or infrastructure failure.

The source remained `fd6ee15be5b98db00ef687d43cc66cc6a8a2cb5c`; model/tokenizer revision remained `cdbee75f17c01a7cc42f958dc650907174af0554`. Driver 550.54.14 differs from the earlier A6000 driver, so this is separate device-specific evidence. CUDA 12.8, engine packages, patch hashes, BF16 precision and the 40 GiB cap remain pinned. The 32,739-token capacity check peaked at 14,764,343,296 bytes full-cache and 15,034,875,904 bytes AgentKV 80%.

The default BF16 screen failed one JS position (0.00463673); all 24 greedy predictions agreed. Heldout failed five JS positions and one greedy-regret position; greedy agreement was 23/24. All failures and raw logits remain preserved.

Both corpora were eligible to reuse CPU FP32 job `13839610`: all model/tokenizer/config/weight identities, native settings, six input histories per corpus, generated token prefixes and complete generated records matched exactly. The analysis verified prior artifact hashes, source hashes and the unchanged comparison function before recomputing metrics; no model forward ran. Full weight files had been checksum-verified at staging; the reuse check verified the same snapshot/blob identities, sizes and headers rather than performing another complete weight-file checksum.

| Corpus / native BF16 against FP32 | Maximum centered RMSE | Maximum relative centered RMSE | Maximum JS, nats | Greedy agreement | Maximum regret |
| --- | ---: | ---: | ---: | ---: | ---: |
| Default | 0.088470 | 0.028543 | 0.000554 | 24/24 | 0 |
| Heldout | 0.060181 | 0.016641 | 0.003750 | 23/24 | 0.008739 |

Two heldout native positions exceed the unchanged JS bound of 0.002: `heldout_action_choice/fresh`, step 0 (0.00375035), and `heldout_tool_state/fresh`, step 2 (0.00239542). Both greedy tokens match FP32 with zero regret. All other native metric bounds pass. HF BF16 exceeds the FP32 JS bound at five positions, with maximum 0.01259545; native pooled centered RMSE is lower in both corpora. These comparisons describe the tested vectors and do not remove the native exceedances.

No L40 pilot qualification or final-study qualification is claimed by this diagnosis. Numerical gates are unchanged. The 77 original evidence files and both reuse reports were copied and SHA-256/size verified; source checkouts, protected environment markers and the pending A6000 pilot remain unchanged.

The [portable evidence inventory](qwen4b-l40-numerical-diagnosis-2026-11-08.json) pins the numerical summaries and 27 cited artifacts. The qualified A6000 pilot remains the task-execution route; the conditional L40 pilot is not submitted.
