# Model direction after the November 8 pivot

The user ended the effort to make the legacy Qwen3 4B/8B/14B pilots the main
baseline. The next implementation phase will investigate newer Qwen models for
a useful AppWorld task-success regime and the central
[compaction-aggressivity study](research-direction.md). The former 14B ceiling
is superseded. The first implementation candidate is Qwen3.5-9B with a shared Transformers hybrid backend; see the [verified identities and state contract](hybrid-backend.md). Live qualification remains required.

## Candidate list

The [backend decision](hybrid-backend.md) records verified official repositories,
revisions, architecture, license, reasoning modes and weight sizes for these
user-supplied candidates. Only the 9B model is implemented. Verify identities
again before selecting a different release; never substitute silently.

- Qwen3.5-9B
- Qwen3.5-27B
- Qwen3.5-35B-A3B
- Qwen3.6-35B-A3B
- Qwen3.8-27B

Do not equate an MoE model's active parameter count with its resident weight
memory. Measure the complete serving footprint, including all model state,
workspace and transient recovery allocations. The subsequent execution request
authorizes adequately sized Insomnia/GCP resources within the recorded spending
ceiling. Prefer the smaller qualified model when it supports the experiment.

## Implementation boundary

The registry requires the shared Transformers hybrid backend for Qwen3.5-9B.
The pinned Mini-SGLang adapter retains only its legacy Qwen3 profiles. Other new
architectures remain unsupported; strict checks prevent them from being silently
treated as Qwen3 or as the dense 9B hybrid. The
[historical integration guide](https://github.com/looooonk/comet/blob/55fca50bfe3c69dfaa4420585e78850da1b3aaf4/documents/experimental-models.md) retains exact old pins and
reproduction commands; historical results do not qualify a newer architecture.

Before extending to another backend or model, document its attention,
recurrent and expert state and how each required method can operate on it.
For hybrid architectures, define the retention denominator and the handling of
non-KV state. A KV-only x-axis must not imply that every kind of model memory is
compressed. Report realized retained entries, fixed state, occupied KV, reserved
pools and total VRAM separately.

Use one shared execution and evaluation pipeline for all methods. Preserve raw
transcripts, isolated task state, paired seeds, charged resets/tools/rebuilds,
one recovery per attempt and offline-only scoring. If an engine or method must
change, record the departure and affected comparisons before running them.
Do not combine old and new backend or model results into one controlled curve.

## Qualification before the sweep

1. Pin assets and dependencies and validate numerical output, sampling and the
   intended reasoning/chat protocol against an appropriate independent reference.
2. Validate every state type across turns, checkpoints, branching and recovery;
   exercise transient memory caps and fresh AppWorld resets.
3. Establish full-cache task success on a predeclared train/dev sample with useful
   intermediate difficulty. Inspect failures and test whether context/output
   limits or infrastructure are constraining behavior.
4. Choose retention, runtime and attempt settings on dev, confirm them on separate
   dev coverage, then freeze the final model, backend, tasks, seeds and budgets.

A larger model is a candidate, not evidence of a usable baseline. Report all
attempts and uncertainty; do not select test tasks or discard unfavorable points
to manufacture an attractive curve.
