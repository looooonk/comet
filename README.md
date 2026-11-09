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

Our main plots show how task success changes as more cached history is removed.
The initial study found that recovery can help some settings and hurt others.
The samples are small: two test tasks on L4 and three training tasks in the
supplemental Blackwell study.

See the [results and figures](documents/records/README.md) for the comparisons
and their limitations.

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
