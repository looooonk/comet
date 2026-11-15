# Configurations

The current study uses Qwen3.5-9B through the shared hybrid backend.

| Directory | Contents |
| --- | --- |
| `qwen9b/l4/` | Capability baseline, compression and budget pilots, fine grid, diagnostic, dev confirmation and frozen test |
| `qwen9b/blackwell/` | Three-family train grid, diagnostic, dev confirmation, frozen fifty-family fine grid with eight condition partitions, and the nineteen-family dev recovery matrix with four condition groups |
| `qwen9b/a6000/` | RTX A6000 dev cohort: qualification smoke and interruption check, reference arms, rebuild before the first action, the thirty-eight-task confirmation, the retry curve and the two exploratory controls studies, each with four condition groups, plus the controls smoke and the three-group 80% retention study |
| `qwen9b/checks/` | Process-interruption validation inputs |
| `examples/` | Legacy schema/integration examples used by regression tests |
| `diagnostics/` | Pinned numerical-reference inputs for the legacy backend |

`qwen9b/base.json` contains common fields; select a study file, not the base.
`extends` paths are relative to the child file. Objects merge one level and lists
replace in full. Every retained study resolves to its original settings and
configuration hash, including `qwen9b/l4/final-v1.json` and its freeze evidence.
Superseded pilot versions and the unexecuted Blackwell test plan are in Git history.

For a new study, copy an appropriate configuration to a new version. Declare tasks,
split, paired seeds, model/tokenizer pins, prompt, sampling, context/output limits,
time/memory caps, retention, recovery thresholds and attempt ceiling. Validate with
`comet validate CONFIG`. Freeze test settings after train/dev qualification; never
edit a parent of an active or frozen study. See the
[workflow](../documents/experiments.md) and [results](../documents/records/README.md).
