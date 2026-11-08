# COMET

**Co-Optimizing Memory Efficiency and Test-Time Compute**

COMET studies how language-model agents should divide limited time and memory between retaining information, making additional attempts, and recovering information they have discarded. Keeping less information may make more attempts affordable, but those attempts only help if the agent still has what it needs to finish the task.

This is a Fall 2026 project for *Scaling LLMs: Systems, Optimization, and Emerging Paradigms*, taught by Dr. Kaoutar El Maghraoui. The [project proposal](documents/proposal.pdf) describes the research plan.

## What we are investigating

We focus on two questions:

1. Can an agent use information available during a task to decide when rebuilding its memory is worthwhile, compared with never rebuilding or rebuilding on a fixed schedule?
2. Under the same time and memory limits, how do additional attempts and memory recovery affect success as we retain less information?

We will compare full memory with three ways of retaining less of the model's cached history: StreamingLLM, R-KV, and AgentKV. The main experiment uses Qwen3-8B on AppWorld, a collection of multi-step tasks with verifiable outcomes. Rebuilding memory means reconstructing the model's cache from the current attempt's history; it does not undo actions already taken.

Our main result will be the share of tasks solved by at least one attempt within the budget. Outcomes are checked afterward, so this measures what would be possible with perfect selection among attempts. It does not assume that the agent can recognize a successful attempt while running. We will also report the time and memory costs.

## Project workflow

1. **Validate the foundation.** Connect the model, task environment, and memory methods in one shared pipeline.
2. **Run a pilot.** Establish feasible budgets and settings using development tasks, then freeze the evaluation plan.
3. **Compare recovery strategies.** Start from matching saved task states to study when recovery helps.
4. **Evaluate complete tasks.** Run the agreed comparisons from fresh task states on the fixed test set.
5. **Analyze and report.** Compare success and cost, explain uncertainty, and preserve the records needed to reproduce results.

The repository includes a shared experiment runner, pinned AgentKV Mini-SGLang integration, AppWorld execution and offline scoring, and paired task-level analysis. Small pilot and checkpoint experiments are provided; final settings must be established on train/dev before evaluation.

Start with the [setup guide](documents/setup.md), then the [experiment workflow](documents/experiments.md). The [validation guide](documents/validation.md) explains the checks; [personal and run records](documents/records/README.md) preserve dated evidence and limitations. One managed setup and validation path serves local development, CI, Insomnia, and GCP. Insomnia job scripts support short development runs; the same environment and commands run on a suitably sized GCP GPU for longer experiments.

The authorized [Qwen3-14B exploratory pilot](documents/experimental-models.md) assesses a stronger model while keeping its results separate from the Qwen3-8B research plan. The [results and validation index](documents/records/README.md) identifies the latest completed comparison, its limitations, and the remaining research work.

## Working together

[AGENTS.md](AGENTS.md) contains the implementation rules and experimental constraints for coding agents. Keep this README focused on the project overview; put technical procedures and reproducibility details in the implementation documentation as it is added.

The proposal assigns these coordination roles; contributors share the pipeline and may work across files.

| Contributor | Planned role |
| --- | --- |
| Yihan Bai | Experiment and ablation analysis |
| Henry He | Experiment setup and execution |
| Yenna Hwang | Infrastructure and code framework setup |
| Chad Cai | Infrastructure and experiment setup |

## Planned milestones

| Date (2026) | Milestone |
| --- | --- |
| October 30 | Baseline experiments complete |
| November 9 | Midpoint check-in and first comparisons |
| November 20 | Dynamic recovery experiments conclude |
| December 4 | Recovery policy optimization and evaluation conclude |
| Week of December 14 | Final paper, code, and presentation |
