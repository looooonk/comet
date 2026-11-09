# Qwen3-4B L4 structural and resume validation

Run `gpu-20261109-022402-697b39` completed the intended structural checks and
live process-interruption/resume fixture. Both independent numerical screens
failed, and the aggregate job correctly retained `FAILED` / exit 1. The later
identity-matched FP32 tensor comparison also retains one native heldout
exceedance. This is useful structural evidence, **not numerical hardware, task
capability or final-study qualification**.

The run used committed source `2c93d9439bd9d1afca8c2397ab91baaba7221348`, pinned
Mini-SGLang `254c57bc84e4a7895159ba1062bd46c83626f511`, and BF16
`Qwen/Qwen3-4B-Instruct-2507` revision
`cdbee75f17c01a7cc42f958dc650907174af0554`. One L4 Spot VM had four vCPUs and
16 GiB host RAM. CUDA 12.8 / driver 550.54.15 reported exactly 23,570,219,008
device bytes, with 23,368,695,808 initially free. The explicit 21,474,836,480-byte
(20 GiB) cap passed the CUDA preflight before model download.

| Phase | Saved phase duration | Result |
| --- | ---: | --- |
| Bootstrap and managed setup | 145 s | Passed |
| CUDA/host preflight | 9 s | Passed |
| Public model/data download and verification | 79 s | Passed |
| Native structural checks | 498 s | All four passed; pytest 493.01 s |
| Default numerical screen | 44 s | Failed |
| Heldout numerical screen | 42 s | Failed |
| Live interruption/resume | 218 s | Passed; pytest 212.99 s |

All phases finished within their declared bounds. The wrapper elapsed time was
1,040 seconds; submission through verified cleanup took 1,642 seconds. Managed
setup itself took 90.50 seconds, versus 1,544.58 seconds on the earlier cloud
run. Package preparation was 1m15s rather than 25m30s. Download concurrency was
explicitly changed from two to four, but this single observation does not isolate
its contribution from network or other startup variation.

The native checks cover sampling, full/compressed persistence and checkpoint
round-trips, recovery, tight-cap rejection and 32k capacity. Full KV stored
32,739 logical positions in a 32,768-token pool; its measured peak total VRAM was
14,472,642,560 bytes. AgentKV 80% retained 26,192 positions at that same logical
length, with peak total VRAM 14,743,175,168 bytes. The pool reserved
4,831,985,664 bytes in each case. These are structural capacity measurements,
not a retention performance sweep. Nonthinking phase occupancy evidence was
also saved.

The live resume fixture preserved the completed cell and interrupted trajectory,
rejected an incompatible resume configuration, charged the interrupted cell's
full 120-second budget, and granted no replacement attempt. Its fresh continuation
matched the paired first turn and 2,815-token raw prefix across distinct AppWorld
environments. No evaluator or task-success scoring was invoked.

Maximum recorded process RSS was about 5.79 GiB; the container cgroup peak was
about 12.26 GiB including caches, with no OOM events. Sequential native and BF16
reference loading therefore completed on this host. OMP/MKL were set to four,
while the saved preflight observed Torch intra/inter-op counts of two; this
distinction is retained. No CPU FP32 model was loaded on the cloud VM.

The original default screen had three failing positions, with 24/24 greedy
agreement; heldout had three failing positions, with 23/24 agreement. Both
original comparisons, raw logits and unchanged thresholds are preserved. Existing
FP32 vectors could be reused because complete model/tokenizer/weight/package
identity, all native records, and every per-position input token sequence matched
exactly. The native cap, local model path and source-snapshot differences were
explicitly audited. Forward, reference and metric code were unchanged; the only
engine-source change was retention argument validation, with full-retention
behavior unchanged. This does not imply equivalent hardware qualification.

The tensor-only comparison took 7.12 seconds on two CPUs, used about 550 MiB RSS,
and executed no model forward. Default native errors meet all existing bounds.
Heldout still exceeds the unchanged JS threshold at
`heldout_tool_state/fresh`, zero-based step 1:
**0.002940587 nats versus 0.002**. Other heldout native maxima meet the existing
bounds; greedy agreement is 23/24 and maximum FP32 greedy regret is 0.00873947.
No tolerance was changed and no L4 pilot qualification was granted.

Fetch verified all 171 manifest files, with no missing required outputs:
208,766,126 bytes including the manifest. Manifest SHA-256:
`193d5265ddb738caac30edf1e2711a0e49c428b815b4f08d8b807efbd32f42dc`.
The separate FP32 analysis has 13 verified files. The [machine-readable record](qwen4b-l4-validation-2026-11-08.json) contains
detailed metrics and hashes under portable artifact group
`gcp-qwen4b-20261108`; raw outputs use the `results/` prefix and tensor
comparisons use `fp32-reuse-results/`.

Cleanup removed the job and its live cloud artifact prefix after verification.
Final audits found no project VM, disk, Batch job or allocated NAT IP. The
configured storage soft-delete retention still applies. No retry or second paid
job was launched.

Provider NAT counters measured 18.8316 GiB, including image, OS/driver/packages,
8,060,917,568 model/tokenizer bytes, installed AppWorld apps/tests bundles and
the public task-data bundle. NAT processing is estimated at $0.847. The
conservative total estimate is **$1.57**, including VM/disk time and a $0.25
artifact transfer/storage/operations allowance; these are not measured billing
charges. The approved $5 allowance remains reserved, together with the prior
$5 allowance, leaving $30 uncommitted under the user's $40 cap.
