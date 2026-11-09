# Qwen3-4B managed runtime preparation

On November 8, 2026, a separate owned GPU runtime was prepared for the pinned
Qwen3-4B-Instruct-2507 qualification. CPU readiness passed after correcting an
external validation helper. The original failed job remains failed. No model was
loaded and no task inference ran during this preparation.

## Identity and isolation

- Source: `fd6ee15be5b98db00ef687d43cc66cc6a8a2cb5c`, clean detached checkout.
- Model/tokenizer: `Qwen/Qwen3-4B-Instruct-2507`, revision
  `cdbee75f17c01a7cc42f958dc650907174af0554`.
- Managed profile: `gpu`, installed through `scripts/setup_runtime.sh`; package
  caches and the already verified model snapshot were reused. No weights were
  copied or downloaded again.
- Existing history source `312691d00fe84ce52a504071ccd5ed0bdd40a0f9` and scoring
  source `178e6f3f10b388c5baceb0fb1da17cb92106a4da` remained clean and unchanged.
  Both existing runtime markers also matched before and after.

The new environment occupies 9,273,930,240 bytes and its checkout 5,181,440 bytes.
The preparation reused a completed storage inventory and checked current quota,
free blocks, and free inodes. The follow-up measured only the new environment
and checkout.

## Preserved failure and follow-up

| Job | CPU allocation | Outcome |
| --- | --- | --- |
| `13839268` | 4 CPUs, 16 GiB, 30-minute ceiling | Failed after 5m32s. Managed setup exited 0; the subsequent external identity helper raised `TypeError` when it treated a namespace package's `origin=None` as a file path. |
| `13839294` | 2 CPUs, 4 GiB, 5-minute ceiling | Completed in 2s. Verified the existing environment without rerunning setup or modifying packages. |

The versioned helper verifies that `minisgl` has exactly the namespace search
directory `vendor/minisgl/python/minisgl` within the new checkout. It accepts
`origin=None`; if an origin exists, it must also resolve within that directory.
The successful follow-up verified managed locks, source cleanliness, package
compatibility, model identity, and unchanged runtime markers. All 137 installed
packages were compatible.

| Component | Installed version |
| --- | --- |
| Python | 3.12.15 |
| PyTorch | 2.9.1 |
| Transformers | 4.57.3 |
| FlashInfer | 0.5.3 |
| SafeTensors | 0.8.0 |
| AppWorld | 0.2.0.dev0 |
| SQLAlchemy / SQLModel | 2.1.5 / 0.0.48 |

## Evidence

Portable artifact groups are `qwen4b-gpu-setup-fd6ee15-13839268` and
`qwen4b-gpu-readiness-v2-fd6ee15-13839294`. Each group's 18 output files and batch
log were retrieved and SHA-256 verified. Private runtime locations remain in
ignored execution artifacts.

| Artifact | SHA-256 |
| --- | --- |
| Original setup log | `97d697b00d2c710a6a9663868019571dac2d7238e89813e52d7a2511ed338663` |
| Original failed batch log | `6decdcc9903893fcf9290d85653078615cf5160c38e9d99d1839cb119f3de3a1` |
| Versioned namespace helper | `3a85bc6022843b1555d29157229e1166fdede57bf432b54c8ac7a6195ce91bff` |
| CPU readiness wrapper | `2b3bcb0cd68155c4f5a7cc383b4426379d39922f74850a0bb8f4cd1ae27fac66` |
| Successful readiness JSON | `d28104ec38afbf6be81c6801348a7b45138ab39a868db8e27ffdfb6eeb38c575` |
| New runtime marker, unchanged | `1501cb06b05fcc086ef5e404df0807c318907a3974b8c8fd94ba99c1de4eaa23` |
| Protected source/marker inventory, unchanged | `4213a514b88ba6b57121c4ae77f697bf69b2737a79c6e64ca2870c7e502cf37a` |
| Reused model download manifest | `72245ac7f0493a80903eaa9533b36daa50f9a7fb0c004e59331ec9d4b595ed69` |

This record establishes installation readiness only. GPU numerical, capacity,
phase/state, and task-capability results require their separate saved evidence;
no older model's numerical exception transfers to this model.
