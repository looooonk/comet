# Configurations

The current study uses Qwen3.5-9B through the shared hybrid backend.

| Directory | Contents |
| --- | --- |
| `qwen9b/l4/` | Capability baseline, compression and budget pilots, fine grid, diagnostic, dev confirmation and frozen test |
| `qwen9b/blackwell/` | Train/dev pilots, the frozen test grid, corrective replication and dev recovery studies listed below |
| `qwen9b/checks/` | Process-interruption validation inputs |
| `examples/` | Legacy schema/integration examples used by regression tests |
| `diagnostics/` | Pinned numerical-reference inputs for the legacy backend |

`qwen9b/base.json` contains common fields; select a study file, not the base.
`extends` paths are relative to the child file. Objects merge one level and lists
replace in full. Every retained study resolves to its original settings and
configuration hash, including `qwen9b/l4/final-v1.json` and its freeze evidence.
Superseded pilot versions and the unexecuted Blackwell test plan are in Git history.

## Blackwell studies

| Configuration | Scope and evidence |
| --- | --- |
| `test50-v1.json` | Frozen 50-task, 26-condition compression grid; eight partitions. [Design and results](../documents/records/qwen9b/test50-final.md) |
| `test50-cuda-repair-v2.json` | Separate five-condition corrective replication on the same 50 tasks; matching gates in `cuda-repair-dev-v1.json`. [Investigation](../documents/records/qwen9b/agentkv90-investigation.md) |
| `dev19-recovery-v1.json` | 19-family, 29-condition recovery matrix, seed 17; four groups. [Findings](../documents/records/qwen9b/dev19-recovery.md) |
| `dev19-recovery-v2.json` | Same recovery matrix with seeds 29 and 31; eight groups. [Design and launch history](../documents/records/qwen9b/dev19-recovery-design.md#seed-replicate) |
| `dev19-frontier-v1.json` | Supplemental R-KV and AgentKV retention grid; seven groups. [Design and launch history](../documents/records/qwen9b/dev19-recovery-design.md#supplemental-retention-frontier) |
| `dev19-trigger-v1/` | Four fixed-trigger thresholds at 50% retention. [Design and launch history](../documents/records/qwen9b/dev19-recovery-design.md#supplemental-trigger-timing) |

These configurations describe separate studies. A declared configuration is not
evidence of a completed run; consult its linked record for execution status,
invalid launches and comparison limits.

## New configurations

For a new study, copy an appropriate configuration to a new version. Declare tasks,
split, paired seeds, model/tokenizer pins, prompt, sampling, context/output limits,
time/memory caps, retention, recovery thresholds and attempt ceiling. Validate with
`comet validate CONFIG`. Freeze test settings after train/dev qualification; never
edit a parent of an active or frozen study. See the
[workflow](../documents/experiments.md) and [results](../documents/records/README.md).
