# COMET

**Co-Optimizing Memory Efficiency and Test-Time Compute**

How should an AI agent spend limited time and memory: remembering more, trying
again, or recovering information it has discarded?

COMET studies this tradeoff using Qwen3.5-9B on AppWorld, a collection of tasks
that require an agent to use apps and tools. We compare three ways of compressing
the model's cached history: StreamingLLM, R-KV and AgentKV. Each gets the same
time and memory limits. Recovery rebuilds the cache from the conversation
history without undoing the agent's actions.

## Results

The completed [compression study](documents/records/qwen9b/test50-final.md)
covers **50 held-out tasks per condition and 26 conditions**, without recovery.
Its results retain every execution failure, including the
[CUDA failures affecting AgentKV at 90% retention](documents/records/qwen9b/agentkv90-investigation.md).

A separate [recovery study](documents/records/qwen9b/dev19-recovery.md) covers
**19 dev task families and 29 conditions**. At 50% retention, fixed recovery
raised AgentKV oracle success from 3/19 to 7/19 in this one-seed study.
This is preliminary dev evidence; the cohorts are reported separately.

The [experiment ledger](experiments/README.md) brings together study settings,
figures, interpretations and reproducibility details. It is updated occasionally
from the repository's [dated evidence records](documents/records/README.md).

## Getting started

- [Setup](documents/setup.md): install the tools and prepare a runtime.
- [Experiments](documents/experiments.md): run, score and analyze a study.
- [Research plan](documents/research-direction.md): questions and comparison rules.
- [Validation](documents/validation/README.md): check the pipeline before a run.

## Team

Yihan Bai, Henry He, Yenna Hwang and Chad Cai.

A Fall 2026 project for *Scaling LLMs: Systems, Optimization, and Emerging
Paradigms*, taught by Dr. Kaoutar El Maghraoui.
The [proposal](documents/proposal.pdf) describes the original plan;
[AGENTS.md](AGENTS.md) contains contributor guidance for coding agents.
