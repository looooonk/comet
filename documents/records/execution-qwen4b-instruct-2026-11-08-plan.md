# Nonthinking 4B instruction-model pilot

This exploratory pilot tests whether the newer instruction model can execute
the existing three targeted dev tasks usefully after corrected scoring left
both earlier models at zero successes. It is not a representative capability
estimate, an isolated model-size comparison, or a change to the final study.
The user authorized newer models of at most 14B as exploratory fallbacks.

`configs/pilot-execution-candidate-qwen4b-instruct-v1.json` fixes
`Qwen/Qwen3-4B-Instruct-2507` and its tokenizer to revision
`cdbee75f17c01a7cc42f958dc650907174af0554`. Keep BF16 and the existing pinned
MiniSGLang implementation. The declared device is an NVIDIA RTX A6000. Do not
reuse another model's numerical qualification or change the serving engine.

## Declared execution

| Setting | Value |
| --- | --- |
| Stage and split | Exploratory pilot, AppWorld dev |
| Tasks | `0d8a4ee_1`, `3ab5b8b_1`, `57c3486_1` |
| Seeds | 17 and 18, six cells in configured order |
| Cache and recovery | Full KV, eviction disabled, never rebuild |
| Attempt ceiling | One fresh attempt per task/seed |
| Cell budget | 600 seconds, including reset, tools and checkpoint work |
| Peak total VRAM cap | 40 GiB, including transient allocations |
| Workspace reserve | 6 GiB |
| Context and prefill | 32,768 tokens; 256-token chunks |
| Sampling | Temperature 0.6, top-p 0.95, 4,096 output tokens per turn |
| Mode | Nonthinking, using the pinned model's native chat template |
| Error-streak cutoff | Disabled |

The prompt keeps the existing executable-action instructions and removes the
permission to emit a thinking block. Sampling is inherited from the earlier
pilot; it is not the model card's recommended top-k configuration or a claim
of optimal settings. Model, mode and template change together, so outcomes
cannot isolate their individual effects. Paired seed labels aid provenance but
do not make different models' random draws equivalent.

All six cells execute before offline scoring. Evaluator results cannot change
actions, recovery decisions, stopping or the remaining task order. Preserve
normal failures, timeouts, context limits and infrastructure errors separately.
The six task budgets total at most one GPU-hour, excluding model loading and
offline evaluation; this is a ceiling, not a runtime prediction. An allocation
must also cover validation and setup, or run those stages separately.

## Qualification before task execution

Use an independently owned checkout and managed GPU environment so ongoing 8B
timing measurements retain their exact source and package identities. Run the
shared GPU checks with capacity and numerical checks enabled. Record the
explicit nonthinking default corpus and the separate heldout corpus. Their
existing numerical thresholds remain unchanged. Failures stop task execution
until diagnosed; prior 8B and 14B exceptions do not transfer.

The 4B-only phase check uses the native template with a short forced Python
action and a synthetic tool observation. It records phase labels and query-ring
occupancy across full checkpoint restore, an AgentKV 50% branch, compressed
restore, full-history recovery and recovered restore. It executes no task
tools. The existing parser assigns Python without thinking delimiters to its
assistant-text phase, leaving its second assistant phase empty. Verify the
expected 8/8/0/8 occupied query slots and preserve this model-specific behavior;
do not silently fill an empty phase or change AgentKV scoring.

All 13 model files were downloaded in CPU staging job `13839251` and checked
against official LFS SHA-256 or Git blob identities. They total 8,060,917,568
bytes; BF16 tensor headers contain 4,022,468,096 stored parameters. The download
manifest SHA-256 is
`72245ac7f0493a80903eaa9533b36daa50f9a7fb0c004e59331ec9d4b595ed69`.
An initial staging job failed its storage-audit timeout before downloading;
both attempts remain preserved. A CPU-only check using the actual pinned
tokenizer confirmed initial and appended observation serialization without
loading model weights or initializing CUDA. Its result SHA-256 is
`c6d913677c600fbadc73f7b51dd743714c5648eb46b19385ff5458f6cfad4080`.
These checks do not establish live inference support or model accuracy.
The complete managed CPU suite passed 264 checks; one module lacked PyTorch
and 12 live checks were deselected. The
[integration record](qwen4b-instruct-integration-2026-11-08.json) identifies
the configuration, corpus and validation artifacts. GPU qualification remains
pending.

## Interpretation and next decisions

Retain these three tasks as targeted diagnostics. Useful performance must be
confirmed on a broader declared dev selection before retention or recovery
settings are frozen. A failed targeted pilot likewise does not establish that
every dev family is unsolvable. Preserve all outcomes and identify prior prompt
development tasks in broader analysis. Any final-model change requires an
explicit recorded decision, separate numerical qualification and a new frozen
experiment version; no test outcomes may determine that choice.
