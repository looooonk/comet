# Comparison taxonomy

COMET varies three independent choices: which cached entries remain, when the
current attempt rebuilds its history, and how many fresh attempts fit within
the shared task budget. The [proposal](proposal.pdf), sections 4-7, defines the
methods and comparison questions. This table describes the experimental design;
it does not claim that any method improves task success or speed.

| Cache family | Implementation in COMET | Retention settings | Recovery policies | Attempt allocation |
| --- | --- | --- | --- | --- |
| Full history | Full KV, eviction disabled | 100% | Never rebuild | One attempt and budget-matched oracle best-of-N |
| Recency and attention sinks | Pinned StreamingLLM | 80%, 50%, 25% | Never; fixed tool count; context/tool thresholds | Sequential fresh attempts, bounded by N and one shared time budget |
| Importance and redundancy | Pinned R-KV | 80%, 50%, 25% | Same three policies | Same attempt and budget rules |
| Phase-aware history | Pinned AgentKV | 80%, 50%, 25% | Same three policies | Same attempt and budget rules |

Retention counts KV entries against the full-cache logical history at the same
step. Mandatory entries, rounding and physical ownership are documented in
[engine accounting](reference/engine.md). Occupied KV, reserved pool capacity and total
VRAM are separate measurements. Different selection costs and independently
evolving trajectories can offset memory savings; a smaller cache does not imply
faster execution.

Recovery rebuilds the current raw token transcript and reapplies retention. It
does not replay tools, undo environment effects, summarize text or restart the
task. Each attempt can admit at most one rebuild. Fixed and dynamic triggers use
the observable counts defined in [the workflow](experiments.md); the dynamic
policy chooses when to rebuild, not a new retention setting or attempt ceiling.

The checkpoint diagnostic has **28 conditions**: one full-cache reference and
three methods times three retentions times three policies. Every branch starts
from the same saved agent, environment, KV and random state, then evolves
independently. The fresh-start evaluation has **29 conditions**: two full-cache
attempt controls and those 27 compressed conditions. All attempts in one
task/configuration/seed cell share its time budget and memory cap. N is an upper
limit; it does not grant time for N attempts.

The primary success measure is the fraction of tasks solved by any permitted
attempt, assuming perfect post-hoc selection. This is an oracle upper bound.
Evaluator scores never guide actions, triggers, early stopping or attempt
selection during execution. First-attempt success, actual attempt counts,
component costs and failed/infeasible cells make that upper bound interpretable.

## Adjacent approaches

| Approach | What it changes | Relationship to COMET |
| --- | --- | --- |
| Text-context compression or summarization | The text supplied to the model | Contextual literature; COMET retains raw text independently of KV eviction |
| Adaptive search, beam search or outcome-based selection | Which candidate trajectories are explored or selected | Contextual literature; COMET uses sequential fresh attempts and offline oracle selection |
| Resource-aware orchestration | Scheduling or allocation across workflows | Contextual literature; COMET isolates one model, one GPU and one active attempt |
| Hierarchical cache storage/offloading | Where cache state is stored | Contextual literature; not an additional method in the declared comparison matrix |
| Weight or KV quantization | Numerical representation | Outside the current BF16 comparison |

These neighboring categories explain the scope; they are not unimplemented
requirements. A newly authorized model or hardware exploration retains its own
configuration and evidence, as described in [models](research-direction.md) and
[hardware](research-direction.md).
