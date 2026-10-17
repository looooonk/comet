# Validation record

Integration checks completed on October 16, 2026, using NVIDIA RTX A6000 and L40S GPUs on
Insomnia. Neither is the required A100 80GB research hardware. No experiment
settings are frozen and no task-success or method-quality claim follows from these
checks. Exact revisions, hashes, measurements, and artifact paths are in
[the original record](validation-2026-10-16.json) and the
[follow-up record](validation-2026-10-16-followup.json).

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

No A100 appeared in the scheduler inventory. GPU jobs ran on `ins093`, RTX A6000,
49,140 MiB. Computational work ran inside scheduler allocations.

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
13511652 completed in 89 seconds.

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

Original total-memory peaks stayed below the integration cap of 40 GiB; the highest
original task peak was 18.70 GiB. KV memory is recorded separately, including a
page-ownership high-water check for transient compaction. Controlled unit tests
verify rejection when the KV pool or transient workspace cannot fit and verify
allocator tightening. Follow-up live refusal and bounded OOM checks are recorded
below. Standalone matrix peaks are process high-water values across branches and
must not be treated as independent comparative measurements.

## Real task and checkpoint pipelines

The original runs used dev task `50e1ac9_1`, paired seed 17, a provisional 120-second budget,
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

**All seven original task attempts ended with `context_limit` and count as failures.** The
execution, scoring, and analysis commands completed, retaining those failures.
For these attempts, scoring correctly skipped AppWorld outcome evaluation because
execution had failed. The separate live fixture above proves the saved-outcome
evaluator path. These runs establish integration behavior, not task-solving quality
or evidence for the research hypothesis.

## Follow-up memory and process-resume checks

Job 13511973, clean source `96a2409` on RTX A6000 `ins093`, passed both GPU tests
in 30.34 seconds with no skips. Two contrasting user instructions produced distinct
outputs; each cached continuation exactly matched a fresh full prefill while
processing only its new suffix. StreamingLLM, R-KV, and AgentKV checkpoint,
persistent-cache, and recovery checks also passed.

The final source `4baf57d` passed Ruff and 82 CPU tests in
[CI run 38990302189](https://github.com/looooonk/comet/actions/runs/38990302189),
with one optional numerical skip and four GPU/AppWorld checks deselected. The two
GPU checks and one process-resume check reported here ran separately on Insomnia.

The memory test fixed its 21,034,215,424-byte cap before engine creation. Live
rebuilds were refused separately for insufficient transient workspace and an
insufficient 512-token KV pool. Transcript, KV, session, and RNG state remained
equal, and subsequent tokens and CUDA RNG matched the saved continuation. Memory
telemetry is excluded from that equality check. A real bounded allocation injected
during forward exceeded the process allocator ceiling and raised CUDA OOM, which
the adapter translated to `MemoryCapExceeded`; it did not exhaust the device.
The JSON record identifies before/after checkpoints, reports, and hashes.

Job 13512106, clean source `8d22744` on the same A6000, passed the process-resume
test in 211.69 seconds. Three full-cache cells shared a dev task and paired seed,
with 90 seconds per cell and a 16,384-token context. The test killed the process
group with SIGKILL after a real generated tool action in the middle cell. Resume
preserved the preceding terminal cell's four file hashes and modification times,
preserved the interrupted trajectory, marked that attempt interrupted, and
launched no replacement attempt. A changed-budget resume was rejected without
artifact changes. The final cell started at attempt zero in an independent
environment; all three initial actions and 2,675-token prefixes matched.

The interrupted cell conservatively reserved and charged its full 90-second
remainder because its operation lacked a reliable end timestamp. This is a budget
reservation, not a measured duration. The preceding and following attempts timed
out after measured durations of 90.078 and 90.072 seconds. Separate scoring and
analysis retained all three failures. This proves short process-kill recovery;
scheduler preemption/requeue and sustained long-run resume remain unvalidated.

## Larger-context task attempts

The follow-ups kept the same dev task, paired seed, model, BF16 engine, 40 GiB
cap, and two conditions: full KV and AgentKV 50% with one fixed rebuild after two
tool calls. Each cell had one attempt and a shared 600-second budget. Prompt
changes used ordinary execution observations only; scoring remained post hoc.
These provisional prompt/context variants are separate integration runs, not a
method-quality comparison.

| Job / variant | Context | Full / AgentKV measured seconds | Terminal status |
| --- | ---: | ---: | --- |
| 13511817 / original prompt | 16,384 | 327.524 / 570.910 | Both `context_limit` |
| 13511973 / preloaded API protocol | 16,384 | 216.084 / 364.769 | Both `context_limit` |
| 13512106 / explicit stdout | 16,384 | 215.510 / 529.135 | Both `context_limit` |
| 13512364 / separate discovery responses | 32,768 | 281.951 / 67.853 | Both `context_limit` |
| 13512530 / reasoning enabled | 32,768 | 38.051 / 85.888 | Both `completed`; both scored unsuccessful |

The first three variants ran on RTX A6000. Their ordinary trajectories exposed
forbidden imports, omitted `print`, and discovery calls whose output was lost
when a later guessed call raised in the same block. The fourth variant ran both
conditions on one L40S on `ins058`. Its full-cache attempt received a 9,500-character
documentation/task observation (2,386 tokens with message framing), then repeated
an authentication error. AgentKV repeated the same printed documentation. All
eight earlier attempts remain failures in separate scoring/analysis artifacts; none was
eligible for the AppWorld outcome evaluator.

The final variant, clean source `4baf57d` on the same L40S, enabled reasoning and
raised the per-turn generation limit from 512 to 2,048 tokens; other numerical
settings stayed fixed. Both attempts called the supervisor completion API with an
inability-to-complete answer. After both attempts ended, the actual AppWorld
evaluator scored each saved outcome: one check passed (unchanged database state), one
failed (answer mismatch), and task success was false. Full KV used two tool calls
and no rebuild; AgentKV used three calls and one rebuild. Their peak total VRAM
was 22,710,910,976 and 22,719,299,584 bytes; peak KV was 897,859,584 and
1,332,707,328 bytes. Reports and hashes are in the follow-up record. This verifies
the model-completed outcome path through offline scoring and analysis, not task
success. No further settings were selected using evaluator results.

Job 13511973 exited 75 intentionally after task execution, scoring, and analysis
finished, before the not-yet-started resume test. Its GPU checks passed. The
separate 90-second resume fixture above replaced that planned longer fixture.
No running cell's settings or source were changed.

An unchanged v3 submission, 13512299 on A6000 `ins082`, failed during CUDA
initialization before model loading or attempts. Its manifest and log remain
saved. Pending jobs 13512329 and 13512345 were cancelled without allocations when
the scheduler predicted a multi-day wait for `ins093` and a roughly 45-minute wait
for another A6000. The available L40S supported the same BF16 engine and 40 GiB
cap; it is recorded as separate validation hardware. The research A100 contract
is unchanged, and hardware/prompt variants are not pooled.

## Artifacts and remaining work

The following portable identifiers describe the recorded artifact layout; they
are not download locations. Private account and storage references are omitted.

- `validation/latest-13511561/`: source/device evidence, test report, all-retention matrix, diagnostic config.
- `validation/final-13511652/`: final source/device/compiler evidence, test report, live GPU evidence, full-cache config.
- `runs/live-smoke-13511561/`, `runs/live-diagnostic-13511561/`, and `runs/final-code-smoke-13511652/`: manifests, trajectories, environments, scores, and analysis; diagnostic checkpoints remain with their run.
- `validation/followup-13511973/` and `validation/completion-v2-13512106/resume/`: live cap/persistence reports and checkpoints, process-resume evidence, and its separately scored run.
- `runs/long-context-13511817/`, `runs/completion-13511973/`, `runs/completion-v2-13512106/`, `runs/completion-v3-13512364/`, and `runs/completion-v4-13512530/`: separate task variants with complete trajectories and scoring/analysis artifacts; the last also contains actual AppWorld evaluation reports.
- `logs/`: installation and scheduler output, including failed setup attempts.

Large checkpoints, model files, and trajectories are not included in this
repository. Reproducing these runs requires their recorded source, configuration,
and dependencies; a changed configuration or source version belongs in a new run.
No validation jobs remained queued or running at the final scheduler check.

The A100 80GB train/dev pilot, threshold/budget tuning and freeze, complete
diagnostic matrix, final evaluation, scheduler preemption and sustained resume validation, and
GCP runtime validation remain outstanding. No test-split evaluation was launched.
