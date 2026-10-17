# Validation record

Integration checks completed on October 16, 2026, using an NVIDIA RTX A6000 on
Insomnia. This is not the required A100 80GB research hardware. No experiment
settings are frozen and no task-success or method-quality claim follows from these
checks. Exact revisions, hashes, measurements, and artifact paths are in
[the machine-readable record](validation-2026-10-16.json).

## Environments and setup

The CPU environment installs from `uv.lock` without CUDA or AppWorld. The Linux
Python 3.12 runtime locks were resolved and installed on allocated compute nodes.
They pin AppWorld `42b5bcf3cd334fee33f0c37c02070a9f5807add5`, data 0.2.0,
Mini-SGLang `254c57bc84e4a7895159ba1062bd46c83626f511` plus the recorded local patch,
and Qwen3-8B/tokenizer `b968826d9c46dd6066d109eabc6255188de91218` in BF16.

Two installation failures were fixed in the repeatable setup: Pydantic 2.12.5
restores the interface expected by AppWorld's datetime patch, and the setup helper
retrieves AppWorld's Git LFS bundles at the pinned commit with size/SHA256 checks.
The runtime uses PyTorch 2.9.1/CUDA 12.8 libraries, toolkit 12.9.86, and driver
575.57.08. Shell syntax and Ruff checks passed. The GCP launcher was checked in
dry-run mode; no cloud resource was created or tested.

Noninteractive SSH needed `SLURM_CONF=/etc/slurm/slurm.conf`. Account `edu` used
`edu1` for CPU preparation and `short` for GPU validation. No A100 appeared in the
scheduler inventory. GPU jobs ran on `ins093`, RTX A6000, 49,140 MiB. Computational
work ran inside scheduler allocations.

## Live checks

| Job | Source | Result |
| --- | --- | --- |
| 13511498 | Initial integration checkout | AppWorld fixture passed in 4.83 s; repeated at the final revision below |
| 13511561 | `9dff866` | 12 GPU/numerical tests passed; full KV and all nine compressed method/retention cases passed; task and diagnostic pipelines completed |
| 13511652 | `6b50787` | 32 checks passed in 24.46 s, with no skips; final full-cache task pipeline and separate scoring/analysis completed |

Both recorded source revisions had clean tracked files. The final revision also
passed 79 CPU checks with three infrastructure-dependent skips; [GitHub Actions run 38984291935](https://github.com/looooonk/comet/actions/runs/38984291935)
passed. One temporary batch submission, 13511649, failed before tests
or model loading because its checkout path was wrong; corrected submission
13511652 completed in 89 seconds. No validation jobs remain active.

The live AppWorld fixture checks fresh-state isolation, a state-changing tool call,
DB and Python namespace/RNG checkpoint restore, independent branch continuation,
prompt construction, and interruption of a runaway tool by the budget watchdog.
It also executes the actual evaluator on a saved outcome after the environment
closes.

GPU checks cover eviction-disabled full KV; the existing StreamingLLM, R-KV, and
AgentKV implementations at 80%, 50%, and 25%; persistent compressed KV across
turns; checkpoint replay; and one full-history rebuild followed by retention.
The final tests additionally verify stochastic token and CUDA RNG replay, recovery
with pending observation tokens, and continuation from saved logits without
another prefill. A second rebuild is refused.

Observed total-memory peaks stayed below the integration cap of 40 GiB; the highest
recorded task peak was 18.70 GiB. KV memory is recorded separately, including a
page-ownership high-water check for transient compaction. Controlled unit tests
verify rejection when the KV pool or transient workspace cannot fit and verify
allocator tightening. No deliberate live GPU OOM or forced cap-refusal test was
run. Standalone matrix peaks are process high-water values across branches and
must not be treated as independent comparative measurements.

## Real task and checkpoint pipelines

All runs used dev task `50e1ac9_1`, paired seed 17, a provisional 120-second budget,
a 4096-token context limit, and the same 40 GiB cap. Job 13511561 ran full KV and
50%-retention fixed recovery for each compressed method. Each compressed attempt
rebuilt exactly once. Job 13511652 repeated full KV at the final source revision.

The reduced diagnostic prepared one actual model-generated tool-call checkpoint
and continued full KV and AgentKV 50% branches. Preparation completed in
13.732832815 seconds, charged to each branch's budget along with reset/restore.
Both branches preserve the same saved 2608 raw tokens plus 33 pending tokens and
the same initial tool turn. They continued to 10 and 11 tool calls respectively;
AgentKV rebuilt once. Checkpoint hashes and prefix equality checks are preserved
in the JSON record.

**All seven task attempts ended with `context_limit` and count as failures.** The
execution, scoring, and analysis commands completed, retaining those failures.
For these attempts, scoring correctly skipped AppWorld outcome evaluation because
execution had failed. The separate live fixture above proves the saved-outcome
evaluator path. These runs establish integration behavior, not task-solving quality
or evidence for the research hypothesis.

## Artifacts and remaining work

The remote source workspace is `insomnia:~/comet-validation-20261016`. Artifacts
remain under `insomnia:/insomnia001/depts/edu/users/th3213/comet-20261016/`:

- `validation/latest-13511561/`: source/device evidence, test report, all-retention matrix, diagnostic config.
- `validation/final-13511652/`: final source/device/compiler evidence, test report, live GPU evidence, full-cache config.
- `runs/live-smoke-13511561/`, `runs/live-diagnostic-13511561/`, and `runs/final-code-smoke-13511652/`: manifests, trajectories, environments, scores, and analysis; diagnostic checkpoints remain with their run.
- `logs/`: installation and scheduler output, including failed setup attempts.

Large checkpoints, model files, and trajectories are outside tracked source.
Cluster project storage is not automatically backed up. Reusing these completed
runs requires their recorded source and dependency compatibility; a changed
configuration or source version belongs in a new run.

The A100 80GB train/dev pilot, threshold/budget tuning and freeze, complete
diagnostic matrix, final evaluation, sustained resume/preemption validation, and
GCP runtime validation remain outstanding. No test-split evaluation was launched.
