# Combined checkpoint integration check

`tests/test_runner_integration.py` combines the real AppWorld adapter and pinned
Qwen3-8B engine through `Runner.run`, including common checkpoint preparation,
branch restoration, tool execution, recovery, and budget accounting. It runs in
one bounded child process and loads one engine for all branches. It does not
submit jobs or use the evaluator.

The declared fixture is **dev task `0d8a4ee_1`, seed 17**; runtime split validation
must confirm its membership. One full-cache source executes an isolated self-message
and stores a Python marker and Python/NumPy random draws. The source remains
incomplete at its one-tool boundary. Three independent continuations use full KV,
AgentKV 50% without recovery, and AgentKV 50% with a fixed trigger at one tool call.
Each branch sends its own message and then calls the supervisor completion API.
The test forces native sampled token IDs to these bounded Python actions; all
model forwards, cache operations, and tool executions remain real. These outputs
are **integration evidence, not task-success or recovery-quality evidence**.

Validation limits are explicit: 120 seconds per cell including its charged source
preparation, 40 GiB peak total VRAM, 6 GiB workspace reserve, an 8,192-token context,
256-token prefill chunks, at most 512 generated tokens per turn, and nonthinking
serialization. The underlying sampling configuration is temperature 0.6/top-p
0.95, but the test replaces sampled IDs. The enclosing process has a 900-second
deadline, including loading. These are synthetic test limits, not frozen research
settings. The resolved configuration is saved with every invocation.

Inside an existing GPU allocation with the managed environment:

```sh
export COMET_MODEL_PATH=/path/to/pinned/Qwen3-8B/snapshot
export COMET_APPWORLD_ROOT=/path/to/appworld
export COMET_CHECKPOINT_ARTIFACT_DIR=/path/to/new/checkpoint-evidence
export COMET_CHECK_OUTPUT=/path/to/new/managed-check-evidence
PYTEST_ADDOPTS='tests/test_runner_integration.py' \
  bash "$COMET_REPO/scripts/run_checks.sh" gpu
```

Both evidence directories must be new. The test is opt-in even within the shared
GPU suite; omit `COMET_CHECKPOINT_ARTIFACT_DIR` to skip it. A GPU with less than the
declared cap cannot run this fixture. The current diagnostic-stage model guard
requires Qwen3-8B. Permission to qualify another model does not establish that
qualification or select it for this fixture.

`report.json`, `process.log`, the resolved config, and the complete shared-runner
artifacts remain on failure. The report records source file hashes, full-KV tensor
hashes, branch-entry state and RNG fingerprints, exact forced/generated tokens,
tool observations, and recovery evidence. It checks that:

- Each branch restores the same raw transcript, pending observation, environment,
  Python marker, request history, and corresponding saved RNG states. Full KV
  matches the source tensors; compressed branches meet the retention target.
- The source action executes only during preparation. Branches restore its
  mutation without replay, start without another branch's marker or effects,
  and produce identical next Python/NumPy random draws.
- The pending observation enters inference exactly once, including the immediate
  recovery path. Recovery leaves the environment and RNG unchanged and consumes
  its allowance once. Forced output does not validate stochastic sampling; the
  separate native sampler and checkpoint checks cover that behavior.
- Each branch charges the same preparation cost once, plus its own reset,
  restoration, inference, tools, and recovery. Inference costs increase beyond
  the prefix, total timing respects the cell budget, and the source files remain
  unchanged. No scores are produced.

This verifies transport and state accounting for a controlled checkpoint. Selecting
useful ordinary agent checkpoints and measuring independent policy outcomes remain
separate train/dev experiments. Clean process segmentation and forced interruption
are covered by [resume-validation.md](resume-validation.md).
