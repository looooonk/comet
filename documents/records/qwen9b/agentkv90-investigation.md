# AgentKV 90% failure investigation

The November 10 investigation establishes that the original **2/50 (4%)**
AgentKV result at 90% retention is contaminated by execution bugs. It cannot
be interpreted as a clean accuracy effect of retaining more KV. The original
measurement and all failures remain in the [final study](test50-final.md).
No success estimate is computed by discarding failed tasks.

**November 11 update:** the [five-condition corrective replication](test50-cuda-repair.md)
is complete. AgentKV 90% scores **10/50 (20%)**, versus 9/50 (18%) at 80%, with
zero CUDA errors or OOMs across all 383 attempts. The collapse did not recur;
the paired difference is +2 percentage points with a 95% interval of [-10, +14].
Shared-storage delays still limit method comparisons and historical attribution.

## What failed

![Attempt failure timeline](figures/agentkv90-failure-timeline.png)

[Vector PDF](figures/agentkv90-failure-timeline.pdf). Task order is the original
execution order; blue means execution completed, not necessarily task success.

The original partition executed StreamingLLM 90%, R-KV 90%, then AgentKV 90%
in the same process. AgentKV's 100 attempts comprise ten completed executions,
31 allocator OOMs and 59 CUDA illegal-memory-access errors. Completed execution
is distinct from successful offline evaluation.

The first illegal access occurred on task `fd1f8fa_3`, the 21st task, during
its second attempt after 140 generated tokens. The following **58 attempts on
29 tasks** failed almost immediately without generating tokens. The runner
continued using a poisoned CUDA context. NVIDIA documents that an illegal
address leaves the process inconsistent and requires a restart:
[CUDA error definitions](https://docs.nvidia.com/cuda/archive/12.6.0/cuda-driver-api/group__CUDA__TYPES.html).
These are one initial CUDA fault followed by a cascade, not 59 independent
accuracy failures. The originating kernel is not identified by the saved logs.

All 59 OOM attempts in the original grid belong to R-KV 90% (28) and AgentKV
90% (31). They hit the experimental allocator allowance, not physical GPU
exhaustion: the first AgentKV OOM reports 71.96 GiB physically free, a 22.46 GiB
PyTorch allowance, and a failed 112 MiB allocation. The allowance reserves
external-runtime memory and 1 GiB headroom within the unchanged 24 GiB total
cap. [PyTorch documents this allocator limit](https://docs.pytorch.org/docs/main/generated/torch.cuda.memory.set_per_process_memory_fraction.html).
Increasing the allowance would change the comparison and is not this repair.

A second confirmed runner bug stores exception objects in the inference and
recovery loop. Each exception retains its traceback, including failed-operation
local tensors, until cyclic garbage collection. A regression test reproduces
retained objects with collection disabled for both operations; saving only the
exception text releases them immediately. This can amplify memory pressure
across attempts. The exact fraction of the historical 59 OOMs caused by it is
not established; fragmentation and transient working memory remain possible.

## Repairs and evidence

- `22f97ea`: stop after fatal CUDA errors, preserve the failed cell and its
  original budget reservation, and leave later cells unstarted. A compatible
  fresh-process resume continues only unstarted work. Ordinary allocator OOM
  handling remains separate.
- `49740e2`: store failure text instead of exception objects, releasing failed
  inference/recovery frames without waiting for cyclic garbage collection.
- `d97c49d`: save inference/recovery stack traces as text for any recurrence;
  45 pipeline checks pass, including preserved trace text and released frames.
- CPU checks: 363 passed, two optional Torch modules skipped, 17 live checks
  deselected. Tests cover fatal failures during generation, synchronization
  and memory measurement, preserved journals on resume, normal OOM handling,
  and object release for inference and recovery. Both object-release cases
  fail before the second repair and pass afterward.

Array `13857295` ran four fresh-process fixed-history checks on the original
engine: AgentKV 90%, AgentKV 80%, R-KV 90%, and full KV. Each completed two
16K-context prefill/decode passes without OOM or CUDA errors. Array `13857321`
replayed the saved first-OOM and first-CUDA histories at AgentKV 90% and 80%,
twice each; all eight passes also completed. The latter uses approximate
forward boundaries reconstructed from compaction events, extends the saved
pending input, and never replays tools or evaluates task success. It is not
bitwise reproduction of the interrupted execution.

All diagnostics use the pinned Qwen3.5-9B hybrid BF16 engine, RTX PRO 6000
Blackwell Server Edition, original 24 GiB total cap, and synchronous CUDA
launches to expose error locations. They explicitly clear state and collect
garbage between passes. Consequently, these passes establish fresh-process
feasibility but do not reproduce the original long-lived process, asynchronous
launch timing, or AppWorld workload. The first illegal access has not recurred. The approximate first-OOM history
replay peaks at 18.92 GiB allocated, compared with 21.86 GiB recorded for the
original failed attempt. This supports accumulated memory pressure as a
contributor without identifying the cause of every OOM.
Initial diagnostic array `13857261` failed before inference because its helper
passed an unsupported settings field; the replacement uses a separate version.

## Corrective replication decision

The user authorized additional Insomnia experiments to investigate the anomaly.
The new comparison repeats **all 50 original tasks** for AgentKV 90% and 80%,
R-KV 90% and 80%, and full-cache N=2. Every condition uses repaired runner code,
the same model/runtime/device, BF16, seed 17, prompt, sampling, 16K context,
24 GiB cap and 120-second shared two-attempt budget. Each condition receives a
separate process and GPU. This removes condition-order carryover uniformly.
Each worker uses an owned job-local checkout, runtime and generated AppWorld
code cache, while reusing the pinned package archive, shared model/kernel
caches and the original dataset. This avoids observed shared-filesystem setup
stalls; the cache-placement change is another reason historical before/after
differences cannot be attributed solely to the runner repairs.

A [two-task dev gate](../../../configs/qwen9b/blackwell/cuda-repair-dev-v1.json)
uses the two previously declared dev families for all five conditions. The
full-cache and both R-KV gates completed without CUDA errors, OOMs or
infeasibility. The [replication](../../../configs/qwen9b/blackwell/test50-cuda-repair-v2.json)
is frozen from the completed full-cache pilot. Each worker independently repeats
its matching two-task gate and must pass before starting its 50-task condition.
Validation and final execution use separate processes within one GPU allocation,
so a successful gate does not relinquish scarce GPU capacity. AgentKV 90% and
80% are scheduled first. This v2 orchestration supersedes the unexecuted v1
proposal; numerical settings and all five comparisons are unchanged.
Ordinary task errors and timeouts remain observations. No method, retention,
prompt or budget is selected using the new success scores.

This is a separate corrective replication on previously inspected held-out
tasks, not a fresh test set. It does not replace failed original attempts,
pool cohorts, or rewrite the original curve. All new failures remain in their
own denominators. Bootstrap paired tasks, report first-attempt and oracle
success, and compare AgentKV 90% with 80% within the repaired cohort. Historical
before/after comparisons also include run-time variation and should not be
attributed entirely to either code change.

Compact audit and launch evidence are in [the investigation record](agentkv90-investigation.json).
Raw trajectories, diagnostic reports and source snapshots remain in external
project storage under their recorded portable artifact IDs.

## Completed corrective jobs

The frozen [five partitions](../../../configs/qwen9b/blackwell/test50-cuda-repair-v2-parts/index.json)
cover 250 task/condition cells. Source is pinned to `d97c49d`; each worker uses
one RTX PRO 6000, four host CPU threads and the original 24 GiB cap. Array
`13857623` runs qualification and final execution; CPU job `13857624` scores
saved outcomes and verifies complete parent coverage after all workers finish.
All five matching dev gates and final workers completed. Four workers started
at 00:32:40 ET on November 11; full cache started at 02:32:33. Final execution
finished at 03:52:40 and scoring at **04:02:54 ET**, superseding the previous
18:00 planning estimate. All study/scoring jobs exited successfully. No GCP
resources were launched and no corrective study jobs remain queued.

The [completed report](test50-cuda-repair.md) preserves all 250 scored cells,
success and failure counts, paired uncertainty, timing audit and plots. Seven
of the ten new AgentKV 90% successes were previously unusable tasks in the CUDA
cascade. However, shared run storage still cost the compressed conditions
38-43 seconds per cell in trajectory saving, versus 15 seconds for full cache,
which ran later. Consequently these results establish that the CUDA/OOM
collapse did not recur, without establishing a clean method ranking or the
isolated accuracy benefit of either repair. The original first CUDA kernel
fault and the fraction of original OOMs attributable to retained frames remain
unresolved.

The later repository refactor did not change these completed runs: execution
and scoring stayed pinned to `d97c49d`. The current analysis API reproduces
their saved aggregates and paired comparisons. Reporting from the refactored
checkout does not constitute GPU qualification of its newer execution code.
