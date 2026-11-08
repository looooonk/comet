# History feasibility allocation failures

The first two allocation attempts produced no benchmark measurements; the subsequent 2,048-token completion is recorded below. Jobs 13838134 and 13838167 failed on ins091 before validation or model loading, after 14 and 6 seconds respectively. Both raised a CUDA busy/unavailable error at `torch.cuda.mem_get_info()`. Their outputs remain separate: all seven files from the first run and all seventeen from the second were copied and checked against independently read remote SHA-256 hashes. The accompanying JSON records their portable artifact names and hashes.

The second wrapper moved the unchanged strict GPU check into a bounded `srun` step and saved allocation and NVML evidence before opening a CUDA context. It failed at the same operation. The scheduler allocated GPU index 4; the task saw visible index 0, and NVML and PyTorch agreed on the device UUID. This index difference is consistent with scheduler remapping. The GPU reported Default compute mode, 1 MiB used, and no compute processes; PyTorch reported one A6000 with 50,897,289,216 total bytes. The evidence rules out a batch-shell-only explanation for this allocation and does not support visible exclusive-process contention. It does not identify a hardware, driver, cgroup, or other root cause.

The combined follow-up allocation, 13838488, remained pending with zero runtime.
A read-only scheduler estimate suggested an earlier short-allocation opening,
motivating a split of the declared stages into separate allocations. The job was canceled with a pending-state filter, and its
terminal scheduler record confirms zero elapsed time. No running measurement was
interrupted. Scheduler forecasts are estimates, not reservations: the replacement
job subsequently received a later forecast of 22:03:44 cluster-local time rather
than obtaining the earlier estimated opening.

Replacement job 13839171 ran on ins094 and failed the validation deadline before
the 2,048-token benchmark started. Its allocation
is 25 minutes; the original configuration, engine source, numerical qualification,
hardware and stage timeouts remain identical. The wrapper differs only in job
name, allocation duration, explicit ins091 exclusion, and removal of the 8,192-token
stage. The node exclusion remains operational avoidance of repeated CUDA
initialization failure, not an established root cause. At that point the 8,192-token
stage was unsubmitted pending review of the 2,048-token result. Source
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

## Replacement validation timeout

Job 13839171 passed its CUDA preflight on ins094, reporting an A6000 with
50,897,289,216 total bytes and 50,615,156,736 free bytes. The shared validation
step then reached its 300-second bound. The job ended with exit 124 after
344 seconds overall. All 36 surviving files (28,850,183 bytes), including the
partial native evidence and two memory-denial checkpoints, were fetched and
independently SHA-256 verified. No benchmark directory or cell was created.

The console records 85 completed tests: 83 preceding checks plus native sampling
and persistence. The memory-cap check was in progress, with its first rejection's
before/after checkpoints written only 1.54 seconds before the wrapper exited.
All 85 tensor-storage payloads in those checkpoints match; this comparison does
not interpret the separate non-tensor pickle metadata. There is no final pytest
XML, completed memory evidence, or capacity evidence for this job. The partial
suite is not a passed qualification.

The same source and package versions completed the previous ins093 suite in
83.853 seconds. File timestamps show 204.38 seconds from the new validation GPU
snapshot to sampling evidence, versus 20.06 seconds previously; sampling to
persistence evidence took 65.25 seconds versus 14.09 seconds. These are artifact
intervals, not precise per-test timings. The saved native generation and recovery
prefill timings stayed close: 43.865 versus 43.277 milliseconds, and 29.177 versus
29.383 milliseconds. Source commit, source hashes, clean changes, installed
packages, Python and platform match exactly.

Initial device snapshots show the same driver and 300-watt power limit with no
active thermal slowdown, hardware slowdown or power cap. They are idle snapshots,
not measurements during the slow phase; cumulative throttle counters cannot
establish current throttling. The evidence locates most additional time outside
the recorded native forwards. Cold imports, loading, compilation, filesystem or
CPU delays remain hypotheses, and the memory test was demonstrably progressing
near termination.

Earlier 8B OMP/MKL and PyTorch thread settings were not recorded. A future
feasibility launch will explicitly pin OMP/MKL to six allocated CPUs and record
actual PyTorch thread counts and affinity. This is an operational pin, not an
established explanation or repair for the earlier slowdown. The old 1k smoke
remains diagnostic; eventual repeated cost curves require consistent thread pins.

A concrete next step is to reuse the already completed pinned-source/A6000
validation after strict source, package, model and hardware matching, while keeping
the CUDA preflight, benchmark warmup and all ten-condition checks. If another
whole suite is required, a separately reviewed 600-second allowance is supported
by the observed distributed progress. Verbose per-test reporting and an interrupt
inside the scheduler task should preserve partial JUnit and traces before a hard
kill. The failed validation remains separate from any subsequent qualified measurement;
no inference-limit change follows from this diagnosis.

## Reused-validation submission

Job 13839209 was subsequently authorized and submitted for the same 2,048-token
stage. It requests 20 minutes on one A6000 with six CPUs and 32 GiB host RAM,
retaining only the existing ins091 exclusion. The full suite is not rerun. Instead,
the 120-second preflight verifies eight exact evidence hashes from the completed
13837736 suite, its native-check completion, current clean source and packages,
managed locks, model identity, A6000 capacity, driver and CUDA runtime. The numerical
qualification is unchanged. Any mismatch stops the job. A tiny BF16 matrix product
checks current device computation without being treated as model qualification.

OMP/MKL are explicitly pinned to six threads, with actual PyTorch thread counts
and CPU affinity recorded. This operational setting is not presented as the proven
cause or fix for earlier delays. The benchmark retains its 840-second process bound
and exact committed configuration; all ten conditions and thirty pass artifacts
must complete and verify. No 8,192-token stage or automatic retry is included.

Before submission, read-only verification matched all eight prior evidence hashes,
current source/package/Python identity, the runtime marker and four managed locks.
The login host's platform differs from the prior compute node, so a strict
compute-platform check remains mandatory inside the allocated preflight. This
job completed all ten conditions and thirty passes in 46 seconds on ins093. All
78 output files were independently SHA-256 verified. See the
[2k result](history-feasibility-2k-2026-11-08.md) for measured costs, memory and
first-use timing limitations. The previous failures remain preserved.

## Subsequent 8k allocation

After reviewing the verified 2k result, job 13839222 was authorized and submitted
for the exact predeclared 8,192-token stage. It uses the same source, model,
qualification, six-thread OMP/MKL policy and A6000 settings. A 30-minute allocation
retains the 120-second preflight and 1,500-second benchmark bounds. It completed
on ins093 in 108 seconds, with all ten cells and thirty passes verified. All
78 files (377,420 bytes) were copied and independently SHA-256 checked.
The [8k result](history-feasibility-8k-2026-11-08.md) reports measured memory,
costs, two-length plots and timing limitations.

## Subsequent 16k allocation

After reviewing the verified 8k result, job 13839231 ran the exact predeclared
16,384-token configuration with the same source, runtime, qualification, hardware
and thread policy. Its 50-minute allocation retained 120-second preflight and
2,700-second benchmark bounds, with no automatic retry. It completed on ins093
in 225 seconds, verifying all ten cells and thirty passes. All 78 files
(457,852 bytes) were copied and independently SHA-256 checked. The
[16k result](history-feasibility-16k-2026-11-08.md) reports measured costs,
memory and the three-length feasibility figures. No 32,600-token or repeated
timing job has been submitted.
