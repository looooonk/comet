# Full cache baseline investigation

Fix authentication and API usage first. The full-cache agent repeatedly confuses
passwords with access tokens, guesses login parameters, and assumes successful
login authenticates later calls. Task coverage and completion checks are the next
priority: some trajectories execute without errors while answering a different
question or processing only the first page of results. These are concrete
train/dev failure mechanisms; their correction has not yet been tested with model
inference.

## Evidence and scope

Both November 6 audit summaries were reproduced exactly from the original saved
trajectories, including all 64 SHA-256 hashes. This investigation inspected all
16 full-cache trajectories, their ordinary observations, task instructions, and
execution records. The published October 20 pilot's eight full-cache trajectories
were inspected separately as corroboration. No evaluator reports, scores, or
ground-truth solutions were read for this investigation.

| Run | Model and device | Full-cache execution status |
| --- | --- | --- |
| `113994b3-61c4-454f-bd7e-0f5f9bf63c26`, seed 17 | Qwen3-14B BF16, RTX A6000 | 8 completed |
| `fc1712b6-991e-45f2-9c24-240078e7f9c6`, seed 18 | Qwen3-14B BF16, RTX PRO 6000 Blackwell Server Edition | 7 completed, 1 timeout |
| `f15c5c5b-7e6b-4134-bf36-454bb434f1a4`, published pilot | Qwen3-14B BF16, RTX PRO 6000 Blackwell Server Edition | 8 completed |

Completion means the agent ended its attempt, not task success. The November
audit runs use source `33fb9210d8114311dfccf5f28e864e150f0c1caf`; the copied engine
source matches their recorded hash. Its difference from current COMET is local
single-GPU rendezvous setup and cleanup. The runner, AppWorld adapter, and prompt
match current COMET. The published pilot uses `60ccf51`. Keep these sources,
hardware, and runs separate; the seed labels do not establish a controlled
comparison of seed effects.

All runs use a 600-second cell budget, 32,768-token context limit, one attempt,
40 GiB cap, and no recovery. All inspected full-cache records have zero rebuilds
and no retention events. Fifteen of the sixteen November-audit baseline attempts
ended through agent completion; none ended with OOM or context-limit status.
The observed traces prioritize agent behavior over increasing memory or time.
This does not prove numerical correctness of every inference operation.

## What the audit hid

The current audit searches for literal `HTTP 401` and `HTTP 422`, but the actual
AppWorld observations say `Response status code is 401` or `422`. Authentication
and validation errors therefore enter `other execution error`. The following
supplemental classification recognizes both spellings, while preserving the
original error-turn predicate and category precedence. Existing audit files were
not modified.

| Full-cache symptom | Seed 17 | Seed 18 | Published pilot |
| --- | ---: | ---: | ---: |
| Trajectories with any error | 7/8 | 7/8 | 7/8 |
| Trajectories with authentication errors | 6/8 | 7/8 | 7/8 |
| Authentication error turns | 9 | 12 | 13 |
| Unexpected parameter turns | 6 | 10 | 8 |
| HTTP 422 turns | 2 | 3 | 3 |
| TypeError turns | 2 | 19 | 1 |
| Unknown API turns | 1 | 1 | 1 |
| Invalid action turns | 1 | 2 | 3 |
| Other error turns after reclassification | 0 | 1 | 1 |
| All error turns / all turns | 21/70 | 48/95 | 30/77 |

Authentication is the first observed error in four trajectories in each audited
seed. The 19 seed-18 TypeErrors all occur in one task; raw error totals would
otherwise overstate how broadly that failure occurs. Counts describe symptoms,
not independent samples or causal effect estimates.

## Fix priorities

### 1 Make authentication and signatures explicit

The most widespread pattern is incorrect use of an otherwise functioning API.
For `4fab96f_1`, seed 17 turns 3 and 5 pass the supervisor-provided password as
`access_token`, then the agent gives up. Seed 18 makes the same error on turn 5,
reads the login documentation on turn 6, logs in on turn 7, and successfully
reads payment requests on turn 8. For `3ab5b8b_1`, seed 18 logs in successfully
on turn 5, omits the token on turn 6, invents `set_access_token` on turn 7, and
eventually reports failure. The phone task similarly guesses `email` instead
of `username` and omits the token after login.

The first proposed agent intervention is a new versioned train/dev prompt with
a concise, generic authentication example: inspect the login signature, obtain
the app's password, use the documented username, store the returned token in a
Python variable, and pass it only to endpoints whose signature requires it.
Explicitly distinguish passwords from tokens and explain that login does not
establish an implicit client session. Read-only endpoints can have different
authentication requirements from write endpoints; adding a token everywhere is
also wrong. Keep authentication as ordinary agent tool calls charged to the
existing budget.

The current prompt already says to inspect signatures. Merely repeating that
instruction is not evidence of a fix. Measure adherence and authentication-error
frequency in the new pilot, as well as separately scored task success.

### 2 Check task scope and pagination before completion

Errors are an incomplete diagnostic. On `50e1ac9_1`, seed 17 gives up after one
API-listing turn without an execution error. Seed 18 retrieves four globally
popular R&B songs and completes successfully at the tool level, although the
instruction asks for songs across the user's own libraries. On `0d8a4ee_1`,
seed 17 messages parents and siblings without checking Venmo membership; seed
18 sends the message to the supervisor's own phone number. These mismatches
are visible from ordinary instructions and actions without evaluator feedback.

Both seeds answer `23cf851_1` from a single default page of transactions. The
documentation shown to the agent specifies `page_limit=5`. An isolated API probe
confirmed twelve matching transactions and a different total when all pages are
included. Seed 18 also completes `4fab96f_1` after reminding one request from a
single page without checking the requested roommate relationship.

A subsequent prompt revision should ask the agent to retain the task's entity,
scope, filters, and required coverage, and verify each against ordinary tool
observations before completion. Explicitly handle pagination for requests using
"all" or aggregates. Do not make the runner infer success from a completion call
or introduce evaluator feedback into execution.

### 3 Inspect response shapes after errors

On `fac291d_1`, seed 18 reaches a 23-turn consecutive error streak, including
19 TypeErrors on turns 12-30, then times out at 600.03 seconds. It alternates
between iterating a dictionary as if it were a list of song objects and passing
an already parsed list to `json.loads`. It does not isolate and print the actual
response shape before retrying the larger script.

Prefer short inspection actions after a type or schema error, then correct one
assumption before continuing. This targets an observed loop without granting
extra attempts or time. Formatting is a lower-priority issue in these full-cache
records: only one and two invalid-action turns occur in seeds 17 and 18.

## Live confirmation and next experiment

CPU-only AppWorld job `13831760` completed in 15 seconds with exit code 0. It
used fresh, isolated dev environments and the pinned AppWorld revision. It
confirmed that missing tokens, password-as-token values, and the `email` login
keyword fail; the documented login and explicit returned token succeed; and a
later call still needs that token. The pagination probe returned 5 records by
default and 12 across pages, with different likes totals. Neither probe invoked
the model, evaluator, supervisor completion API, or a task-changing domain API.

Before another sweep:

1. Version the audit's HTTP classification correction and regenerate separate
   diagnostic outputs; preserve the published v1 summaries.
2. Test the authentication/signature prompt intervention against the existing
   prompt on the same declared dev tasks and paired seeds, on one hardware type,
   with the same numerical settings and budgets. Record it as a new experiment
   version. Do not mix it with these completed runs.
3. If authentication improves, test task-coverage and response-inspection changes
   separately. Score saved outcomes only after execution finishes.
4. Establish a useful full-cache baseline before expanding retention or recovery
   comparisons. The required Qwen3-8B/A100 main pilot remains a separate step.

No shared execution code, prompts, dependency pins, completed runs, or historical
audit summaries were changed by this investigation. No GPU inference was run.

## Reproducibility

[Evidence JSON](full-cache-investigation-2026-11-07.json) contains per-trajectory
hashes, turn numbers and categories, execution statuses, source/configuration
identity, and the live probe result. Large originals and the analysis/probe
scripts are retained in the ignored artifact set
`baseline-investigation-20261107`; their script hashes are recorded in the JSON.
The published pilot's separate source artifact is
`retention-export-13514420-13515534`.

The existing `scripts/audit_trajectories.py` reproduces each November audit
unchanged when run against its corresponding saved run. Supplemental category
matching adds `Response status code is 401\b` and `Response status code is 422\b`
as aliases for the two HTTP categories, with no change to first-match order.
Per-task observations above refer to one-based trajectory turn numbers. These
diagnoses identify fixes to test; they do not measure their effect on task success.
