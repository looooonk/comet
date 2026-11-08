# Separate 14B executable-action pilot

The corrected-sampler 8B diagnostic previously scored zero successes in both
six-attempt arms. Its new executable-action prompt comparison is running. If
that comparison still cannot support an informative retention study, the user
has authorized this separate 14B exploration. Its configuration is declared
before new 14B outcomes; review the current 8B results and fresh 14B validation
before launching it.

`configs/pilot-execution-candidate-qwen14b-v1.json` uses pinned Qwen3-14B BF16 and
the executable-action candidate prompt, with the same three dev tasks and seeds
17/18. It retains 600 seconds per cell, a 40 GiB cap, 32,768-token context,
4,096-token output limit, temperature 0.6, top-p 0.95, and thinking enabled.
There are six fresh full-cache attempts, N=1 and no recovery. These settings are
provisional exploration, not frozen final choices or a representative accuracy
sample. The task/seed subset must not change after seeing outcomes.

The template selects L40 to avoid unnecessary queue constraints. Any authorized
GPU with at least 40 GiB of usable CUDA capacity can be selected before execution
by changing only the resolved device name and retaining both config hashes.
Validate the allocated device and record its exact model; all conditions in a
subsequent comparison must share hardware and the same cap. No model weights,
precision, engine, sampling, or runtime budget may change during this pilot.

Fresh validation uses the shared managed GPU checks, including persistence,
sampling, checkpoint/recovery, transient cap refusal, and long-context capacity.
It also runs the unchanged v2 reference screen on both the default and previously
declared separate corpus. A failed numerical screen remains failed and requires
review; the existing 8B pilot exception does not apply to 14B. These checks do not
establish task-solving capability. Historical 14B capacity evidence supports
sizing only; its old sampler outcomes do not estimate corrected performance.

Run all six cells to terminal outcomes before scoring. Preserve failures and
timing/memory coverage. A stronger baseline should solve a useful fraction of
tasks with actual requested effects, not merely produce fewer errors or earlier
completion. Inspect ordinary traces for residual protocol/environment failures.
Then predeclare broader dev coverage and tune informative retention, trigger and
attempt settings there. The goal is measured tradeoff curves, without favorable
test-task selection, altered scoring, or forced trends. Main-model replacement
and final settings remain separate decisions.
