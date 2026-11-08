# History feasibility allocation failures

The initial 2,048-to-8,192-token cost diagnostic has not produced benchmark measurements. Jobs 13838134 and 13838167 failed on ins091 before validation or model loading, after 14 and 6 seconds respectively. Both raised a CUDA busy/unavailable error at `torch.cuda.mem_get_info()`. Their outputs remain separate: all seven files from the first run and all seventeen from the second were copied and checked against independently read remote SHA-256 hashes. The accompanying JSON records their portable artifact names and hashes.

The second wrapper moved the unchanged strict GPU check into a bounded `srun` step and saved allocation and NVML evidence before opening a CUDA context. It failed at the same operation. The scheduler allocated GPU index 4; the task saw visible index 0, and NVML and PyTorch agreed on the device UUID. This index difference is consistent with scheduler remapping. The GPU reported Default compute mode, 1 MiB used, and no compute processes; PyTorch reported one A6000 with 50,897,289,216 total bytes. The evidence rules out a batch-shell-only explanation for this allocation and does not support visible exclusive-process contention. It does not identify a hardware, driver, cgroup, or other root cause.

The combined follow-up allocation, 13838488, remained pending with zero runtime.
A read-only scheduler estimate suggested an earlier short-allocation opening,
motivating a split of the declared stages into separate allocations. The job was canceled with a pending-state filter, and its
terminal scheduler record confirms zero elapsed time. No running measurement was
interrupted. Scheduler forecasts are estimates, not reservations: the replacement
job subsequently received a later forecast of 22:03:44 cluster-local time rather
than obtaining the earlier estimated opening.

Replacement job 13839171 is pending for the 2,048-token stage only. Its allocation
is 25 minutes; the original configuration, engine source, numerical qualification,
hardware and stage timeouts remain identical. The wrapper differs only in job
name, allocation duration, explicit ins091 exclusion, and removal of the 8,192-token
stage. The node exclusion remains operational avoidance of repeated CUDA
initialization failure, not an established root cause. The 8,192-token stage has
not been submitted and requires review of the 2,048-token result first. Source
`312691d` was verified clean and the runtime marker unchanged before submission.

The replacement requests one A6000, six CPUs and 32 GiB host RAM, with the same
40 GiB GPU cap, 6 GiB workspace reserve, 32,768-token context and 256-token prefill
chunks. Bounds remain 120 seconds for preflight, 300 seconds for managed validation
and 840 seconds for the 2,048-token stage. Including termination graces and bounded
NVML probes gives 1,335 seconds, leaving 165 seconds of bookkeeping margin within
the 1,500-second allocation. All ten conditions and thirty passes must complete
and verify. The unsubmitted 8,192-token stage retains its declared 1,500-second
process bound.

These infrastructure failures are neither failed task attempts nor evidence that either requested history length is infeasible. They supply no throughput or retention measurements. The separate numerical qualification and its unresolved reference discrepancies remain unchanged.
