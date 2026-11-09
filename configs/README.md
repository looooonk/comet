# Experiment configurations

There is no active configuration for the new Qwen study yet. Start from the
[research direction](../documents/research-direction.md) and verify the selected
model/backend before creating a versioned pilot.

- `examples/`: small legacy Qwen3 schema and integration examples, not approved
  study settings or pending jobs. Their model support does not transfer to the
  new candidate architectures.
- `diagnostics/`: independent numerical-reference inputs retained for regression
  testing. A selected new model needs a suitable, explicitly versioned corpus.
- `../tests/fixtures/` contains synthetic analysis input and one historical resolved
  config used only to verify backward-compatible config hashes.

Obsolete experiment-specific configs were removed during the November 8 cleanup.
They remain available at Git commit
`55fca50bfe3c69dfaa4420585e78850da1b3aaf4`, for example:

```sh
git show 55fca50:configs/pilot-execution-candidate-qwen14b-v1.json
```

Declare task/split IDs, paired seeds, model/tokenizer revisions, prompts, sampling,
context/output limits, runtime/memory caps, retention grid, recovery policy and
attempt ceiling before execution. Keep old/new versions separate. Freeze final
settings only after useful train/dev evidence.
