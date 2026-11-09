# Experiment configurations

The active study uses Qwen3.5-9B with the qualified hybrid backend. Start from
the [research direction](../documents/research-direction.md); the
[findings](../documents/records/qwen9b-findings.md) distinguish completed evidence
from pending experiments.

- `qwen9b/`: versioned train/dev studies, checkpoint diagnostics and the frozen
  `final-l4-v1.json` test evaluation. L4 and Blackwell configurations use separate
  qualified caps and must be analyzed separately. Earlier versions preserve
  failed or superseded experiments; directory membership does not imply success.
- `examples/`: small legacy Qwen3 schema and integration examples, not approved
  study settings or pending jobs. Their model support does not transfer to the
  new candidate architectures.
- `diagnostics/`: independent numerical-reference inputs retained for regression
  testing. A selected new model needs a suitable, explicitly versioned corpus.
- `../tests/fixtures/` contains synthetic analysis input and one historical resolved
  config used only to verify backward-compatible config hashes.

Obsolete legacy experiment configs were removed during the November 8 cleanup.
They remain available at Git commit
`55fca50bfe3c69dfaa4420585e78850da1b3aaf4`, for example:

```sh
git show 55fca50:configs/pilot-execution-candidate-qwen14b-v1.json
```

Declare task/split IDs, paired seeds, model/tokenizer revisions, prompts, sampling,
context/output limits, runtime/memory caps, retention grid, recovery policy and
attempt ceiling before execution. Keep old/new versions separate. Freeze final
settings only after useful train/dev evidence.
