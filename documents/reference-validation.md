# Independent full-cache numerical check

The existing cached-versus-fresh checks compare two paths through Mini-SGLang.
They can expose state loss while missing a numerical defect shared by both paths.
The optional `tests/test_reference_gpu.py` compares full-cache Mini-SGLang logits
with the pinned Transformers Qwen3 implementation, using the same local model and
tokenizer snapshot in BF16. This is an inference correctness diagnostic, not an
alternative experiment backend or an AppWorld task-success result.

The inspected runtime lock and saved GPU package inventory contain PyTorch 2.9.1,
Transformers 4.57.3, Safetensors 0.8.0, Accelerate 1.15.0, and FlashInfer 0.5.3.
The test checks their installed versions against `infra/requirements/gpu.lock`
before either model loads. It adds no dependencies. The native model still uses
the pinned patched engine and its normal FlashInfer attention path. The reference
uses the explicit `eager` attention implementation in
[Transformers 4.57.3 Qwen3](https://github.com/huggingface/transformers/blob/v4.57.3/src/transformers/models/qwen3/modeling_qwen3.py),
which computes attention with ordinary PyTorch operations rather than the native
FlashInfer kernel.

## What runs

Two fresh subprocesses run sequentially on the same allocated GPU, so both models
are never resident together. The first runs three fixed synthetic prompts:
Python output with thinking disabled, arithmetic with thinking enabled, and a
multi-turn tool-observation history long enough to cross a 64-token prefill chunk.
Each produces four greedy tokens, then continues its existing KV with a fixed new
user turn and four further tokens. Full-cache accounting and the expected suffix
prefill length are checked. A test-local sampler wrapper copies pre-sampling
logits to CPU without changing those logits or the production engine.
The pinned scheduler marks intermediate chunks `prefill_only`; at batch size 1
the patched engine skips sampling those chunks, and the scheduler emits no token
for them. Only the final prefill and decode steps reach the wrapper. The test
asserts exactly four captured distributions per turn and verifies their argmax
tokens against the four emitted tokens before reference comparison.

The second process loads `Qwen3ForCausalLM` directly from the same local snapshot,
with BF16 parameters, eager attention, and `use_cache=False`. Missing, unexpected,
or mismatched loaded weight keys fail the check. It verifies tokenization and
evaluates each exact native token history, teacher-forcing the native generated
tokens. Thus each of the 24 compared distributions conditions on identical token
IDs, including the cached continuation. An early greedy disagreement cannot
change the reference's later input and conceal where divergence began. The
reference does not execute any historical tool action or consult AppWorld scores.

Both processes default to the existing 40 GiB short-check memory allowance. An
explicit `COMET_REFERENCE_CAP_BYTES` can select a smaller allowance for this
synthetic check. Before downloading model weights, record
`torch.cuda.mem_get_info()` and `torch.cuda.get_device_properties(0).total_memory`
on the allocated device and reject a cap above either reported total. Nominal
GPU capacity and the `nvidia-smi` total can include memory reserved by the device;
they do not establish the usable CUDA allowance. For a short Qwen3-8B check on an
L4, `22548578304` (21 GiB) is a provisional fallback that still needs this
preflight and live validation. It is not a validated long-context setting.
The selected cap is saved in the native settings and reused by the reference
process. This does not alter any experiment configuration or qualify the smaller
device for those settings. The native engine enforces its usual cap; the
reference bounds its PyTorch allocator after
accounting for initially external allocations. Reference allocator peaks are
diagnostic metadata, not measured total-VRAM peaks for an experiment comparison.
The GPU must have room for that allowance and the pinned BF16 model. Neither
quantization nor CPU offloading is used to rescue insufficient hardware.

## Predeclared comparison gates

Finite logits are required at every checked position. Centering subtracts each
vector's mean because an additive constant does not change its softmax
distribution. Every position must satisfy all four gates below; at least 90% of
the 24 greedy tokens must agree exactly.

| Quantity | Maximum | Interpretation |
| --- | ---: | --- |
| Centered logit RMSE | 0.20 | Absolute logit error across the vocabulary |
| Centered relative RMSE | 0.05 | RMSE divided by the centered reference's root-mean-square magnitude |
| Jensen-Shannon divergence | 0.002 nats | Difference between next-token distributions at temperature 1, using natural logarithms |
| Reference greedy regret | 0.125 | Reference maximum logit minus its logit for the native-selected token |

The initial screen used 0.02 for relative RMSE. Independent
[FP32 calibration](records/reference-calibration-2026-11-08.md) found that this
also rejected ordinary Transformers BF16 arithmetic, while native error was
smaller. Version `bf16-fp32-calibrated-v2` changes only that limit to 0.05 and
requires separate prompt validation; the original failed result stays intact.
These are engineering screening thresholds, not guaranteed error bounds. BF16
has limited mantissa precision, and fused reductions need not match eager
operations bit for bit; [PyTorch's numerical accuracy guidance](https://docs.pytorch.org/docs/2.9/notes/numerical_accuracy.html)
also explains why different mathematically equivalent evaluation orders can
disagree. The absolute and relative gates jointly constrain scale-sensitive
error, while distribution divergence checks its probability effect. Regret
allows only near-tie token changes: 0.125 corresponds to a reference odds ratio
of at most \(e^{0.125}\approx 1.133\). The exact-agreement gate additionally
prevents many near ties from hiding widespread token disagreement.

A failure is a reason to inspect raw logits, loading, normalization, positions,
attention, and cache state. It does not by itself identify a defect or prove
AppWorld behavior is caused by inference. Do not silently relax tolerances to
obtain a pass. Any revised tolerance needs a separate rationale and a new saved
validation record. Passing these short histories does not establish long-context,
eviction, recovery, sampling, or agent capability correctness.

Set `COMET_REFERENCE_CASES` to a declared JSON corpus to run separate cases,
such as `configs/diagnostics/reference-heldout-v1.json`. Its hash becomes part
of the recorded identity. Each case specifies an ID, thinking mode, messages
and a continuation. Omit this variable for the original three synthetic cases.
Use a fresh evidence directory for every corpus and screen version.

## Run and preserve evidence

Use an exclusively allocated GPU and the existing managed GPU environment:

```sh
export COMET_MODEL_PATH=/path/to/the/pinned/model/snapshot
export COMET_TEST_MODEL=Qwen/Qwen3-8B
export COMET_CHECK_OUTPUT="$COMET_STORAGE/validation/reference-unique-id"
export COMET_TEST_REFERENCE=1
bash "$COMET_REPO/scripts/run_checks.sh" gpu
```

The exploratory 14B model uses its own pinned snapshot and
`COMET_TEST_MODEL=Qwen/Qwen3-14B`; keep its evidence separate. The ordinary GPU
suite still runs. Without `COMET_TEST_REFERENCE=1`, this additional test skips
explicitly. The parent waits at most 15 minutes per subprocess, including model
loading and compilation; an infrastructure timeout fails and retains its log.

The new `reference/` subdirectory contains separate process logs, `status.json`,
`native.json`, `native-logits.pt`, `reference-logits.pt`, and `comparison.json`.
The comparison records per-position errors, exact token IDs, greedy margins,
thresholds, source hashes, dependency versions, loading results, and artifact
hashes. A failed numerical comparison is saved before the assertion fails.
Native token histories and raw CPU logits support inspecting the first mismatch.
These are trusted local tensor artifacts; the test reads them with
`torch.load(..., weights_only=True)`.

Each subprocess also writes a `*-partial.json` journal and hashed
`*-partial-logits.pt` checkpoint. These distinguish completed cases from the
current unvalidated capture, including a generation exception or an assertion
in the first case. They are always marked incomplete; successful final artifacts
supersede them. A process killed during a write can leave only the preceding
checkpoint, so partial evidence is not a numerical pass.

Model identity includes the pinned revision, configuration/tokenizer hashes,
parameter count, and weight filenames, sizes, blob identifiers, and header hashes.
This does not recompute a full hash of every multi-gigabyte weight shard; retain
the asset-download checksum records alongside it. Keep the large logit artifacts
outside tracked source and commit only a small validation record identifying
their hashes and results. Until a saved live GPU run completes, this optional
test is implemented but not numerically validated.

## Diagnose a BF16 disagreement

`scripts/calibrate_reference_cpu.py` compares six-case evidence for either
registered, pinned Qwen3-8B or Qwen3-14B against FP32 CPU Transformers inference
on the same exact token histories. It checks the saved artifact hashes and pinned model/runtime identity,
loads the original BF16 weights as FP32, and uses eager attention without a KV
cache. It reports both native and Transformers BF16 errors relative to FP32,
including per-position and pooled error ratios. It does not change tolerances
or declare that either implementation passes.

Use the managed GPU-profile environment for its pinned package versions, but
request CPU resources only; the helper disables CUDA. The 8B example below uses
64 GiB host RAM and 12 CPUs with a 30-minute allocation. Size the 14B
allocation separately for its larger FP32 weights and forward-pass memory:

```sh
source "$COMET_REPO/scripts/activate_runtime.sh" gpu
python "$COMET_REPO/scripts/calibrate_reference_cpu.py" \
  --reference-run /path/to/completed/reference \
  --model-path "$COMET_MODEL_PATH" --output /path/to/new/calibration \
  --threads 12 --timeout-seconds 1500
```

Keep the raw FP32 logits, partial progress, source hashes, loading metadata,
CPU memory/timings and `calibration.json`. The scheduler should impose an outer
timeout because an individual model forward cannot be interrupted by the
helper's between-operation budget checks. This is a numerical diagnostic, not
an FP32 task experiment or evidence of GPU throughput.

To localize a discrepancy in cached continuations, use
`scripts/diagnose_cached_reference.py` on the same GPU model as the saved run.
It restores the recorded full-cache settings, resets the native engine, and
re-prefills each exact cached input history. The sampler forces the four recorded
tokens while preserving the fresh logits and their own argmax choices. This
keeps every conditional input identical, even if the fresh path would choose a
different token. It reports descriptive cached-versus-fresh errors without
changing or applying acceptance gates.

```sh
python "$COMET_REPO/scripts/diagnose_cached_reference.py" \
  --reference-run /path/to/completed/reference --model-path "$COMET_MODEL_PATH" \
  --cases "$COMET_REPO/configs/diagnostics/reference-heldout-v1.json" \
  --output /path/to/new/cache-diagnostic --timeout-seconds 600
```

Use the same reference-test source and corpus identity as the saved run. Keep
`fresh.json`, raw fresh logits, provenance and partial captures alongside the
original cached and independent reference tensors.
