# Exploratory model decision

The user authorized a stronger model if Qwen3-8B is inadequate for the requested
AppWorld success, latency, and KV-memory comparison. Qwen3-14B is an exploratory
train/dev pilot option for that comparison. This does not replace Qwen3-8B in the
proposal or authorize a different serving engine, precision, benchmark, or
eviction algorithm. Its configuration must say `stage: "pilot"`; diagnostic and
final configurations reject it, including during freeze preparation. Keep its
runs, scores, plots, and uncertainty estimates separate from 8B results.

On November 8, 2026, the user additionally authorized newer models with at most
14B parameters, including Qwen3.5-4B and Qwen3.5-9B, if the Qwen3 series remains
too brittle for useful comparisons. This authorizes exploratory investigation;
it does not establish engine support or equivalent retention/recovery semantics.
First test the already supported 14B model. Before a newer-model run, pin its
model/tokenizer revisions, establish implementation and state-accounting support,
and document any required serving-engine departure and affected comparisons.
Do not bypass the model registry checks or mix these results into the 8B study.

## Pinned implementation

Model and tokenizer use `Qwen/Qwen3-14B` revision
`40c069824f4251a91eefaf281ebe4c544efd3e18`, verified through the
[Hugging Face model API](https://huggingface.co/api/models/Qwen/Qwen3-14B) and
[commit history](https://huggingface.co/Qwen/Qwen3-14B/commit/40c069824f4251a91eefaf281ebe4c544efd3e18).
The API records 14,768,307,200 BF16 parameters; the
[weight index](https://huggingface.co/Qwen/Qwen3-14B/blob/40c069824f4251a91eefaf281ebe4c544efd3e18/model.safetensors.index.json)
records 29,536,614,400 weight bytes.

The pinned Mini-SGLang revision already implements `Qwen3ForCausalLM` with
configuration-driven dimensions. The 14B model has 40 layers, 40 query heads,
8 KV heads, head dimension 128, and hidden size 5120. It shares the existing
engine, BF16 path, FlashInfer backend, query rings, retention methods, runner,
and offline evaluator. No upstream engine patch was added for this model.
COMET checks the model/revision/tokenizer combination, pinned architecture
fields, BF16 tensor headers, and total parameter count before loading weights.
The model name and exploratory scope are recorded in engine provenance, and
model identity participates in checkpoint and run compatibility.

`Qwen3.5-9B` is not supported by this pinned engine. Its
[configuration](https://huggingface.co/Qwen/Qwen3.5-9B/blob/main/config.json)
uses `Qwen3_5ForConditionalGeneration` with 24 linear-attention layers and
8 full-attention layers. That architecture is absent from the pinned model
registry; its recurrent state also requires different cache accounting and
recovery semantics. Do not relabel it as Qwen3 or substitute a serving engine.

## Capacity estimate and required preflight

These are static estimates, not measured fit or throughput results. For 14B,
each logical BF16 KV token occupies `4 * 40 * 8 * 128 = 163840` bytes. A
32,768-token full-cache pool occupies 5 GiB, and weights occupy 27.508 GiB.
With a 6 GiB workspace reserve, the sum is 38.508 GiB, leaving approximately
1.492 GiB for initially observed non-PyTorch device use under a 40 GiB cap.
If that use is larger, the engine reserves fewer than 32,768 physical tokens.
The preflight requires the complete pool so full-cache tasks are not limited
by a smaller physical pool before reaching their configured context limit.

A 48 GB L40S may fit this configuration; live initialization and long-context
checks must establish that. An H100 80GB using the same 40 GiB experimental cap
has the same accounting constraint. Increasing the cap requires a distinct
configuration applied to every compared condition. Keep hardware-specific
latency measurements separate.

AgentKV compaction can temporarily own old and new KV pages. The pinned engine
switches to in-place compaction when free pages cannot hold the replacement;
it does not require a second full pool. Consequently, parked KV occupancy at
32K would be about 4, 2.5, and 1.25 GiB at 80%, 50%, and 25% retention, but these
are not peak-KV predictions. Report the actual page-ownership peak, reserved
pool, and total VRAM separately. The preflight exercises the in-place path for
AgentKV 80% near the context limit and records the observed kernel calls.

The existing setup helper can fetch the pinned exploratory model:

```sh
bash scripts/download_assets.sh "$COMET_ENV" "$COMET_APPWORLD_ROOT" --model-14b
```

On an exclusively allocated GPU with the installed runtime and the pinned
snapshot available, use the same managed GPU checks as Qwen3-8B:

```sh
export COMET_TEST_MODEL=Qwen/Qwen3-14B
export COMET_MODEL_PATH=/path/to/snapshots/40c069824f4251a91eefaf281ebe4c544efd3e18
export COMET_CHECK_OUTPUT="$COMET_STORAGE/validation/qwen14b-unique-id"
export COMET_TEST_CAPACITY=1
bash "$COMET_REPO/scripts/run_checks.sh" gpu
```

The separately opted-in capacity check uses a fixed 40 GiB cap, 6 GiB workspace
reserve, 32,768-token context, and 256-token prefill chunks. It compares full KV
and AgentKV 80% on a 32,700-token synthetic prompt plus a cached continuation;
it does not use AppWorld or recovery. The shorter checks cover cached/fresh
equivalence, all three eviction implementations, checkpoint replay, recovery,
and fixed-cap refusal. These checks support integration only. Saved AppWorld
execution and separate evaluator outcomes are still required for task-success
claims, and a successful preflight alone does not establish a useful model.
