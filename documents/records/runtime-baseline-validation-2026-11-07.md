# Runtime and full-cache diagnostic validation

The managed environment runs both pinned Qwen3 models through the existing
AgentKV Mini-SGLang engine. The revised baseline prompt improved one small,
targeted dev comparison from 0/3 to 1/3 tasks solved and removed the observed
HTTP 401 errors. It is a useful candidate, not an established strong baseline.

## Changes and validation

Setup now has explicit CPU, AppWorld, and GPU profiles. Each environment records
its checkout, profile, and lock hashes; setup refuses an unmanaged or differently
owned environment. The common activation helper verifies the interpreter and
installed source before selecting persistent caches, AppWorld data, and CUDA.
Asset downloads, tests, experiments, Slurm, and GCP use this path. CI exercises
both the managed Python 3.12 workflow and the Python 3.11 compatibility boundary.
Single-GPU engine instances use separate file rendezvous stores. Dependency,
model, tokenizer, precision, and upstream engine pins are unchanged.

| Check | Evidence | Result |
| --- | --- | --- |
| CPU suite, lint, shell syntax | Slurm `13831990`; repeated through the shared path in `13832407` | 100 passed; numerical tests skipped without PyTorch |
| Live AppWorld | Same jobs | 3 passed: state/reset/checkpoint/offline scoring, explicit authentication and parsed responses, pagination |
| Qwen3-8B GPU suite | Slurm `13831924`, RTX A6000 | 117 passed, one opt-in process-interruption test skipped |
| Qwen3-14B GPU suite | Slurm `13832407`, RTX A6000 | 117 passed, the same process-interruption test skipped |
| Historical audit compatibility | Slurm `13831938` | Both schema-1 reports reproduced exactly, including 64 trajectory hashes |
| Repository CI | [Run 42408510976](https://github.com/looooonk/comet/actions/runs/42408510976) | Managed CPU and Python-minimum jobs passed |

The GPU suites include cached-versus-fresh full-cache decoding, compressed KV
persistence, checkpoint replay, all three eviction implementations at 50%, one-time
recovery, live memory-cap refusal, and full/AgentKV-80% capacity checks using
32,700-token prompts plus continuation under a 40 GiB cap. The 14B capacity and
memory evidence are saved explicitly. These checks validate the exercised paths;
the separate process-kill/resume test was not rerun.

The 8B GPU suite tested the staged engine/AppWorld implementation subsequently
committed in `8affb4d`; final environment ownership/lock checks were rerun in
`13831990`. The consolidated activation path and 14B suite ran from clean source
`4a27e0b`. The evidence JSON records source hashes, package versions, test skips,
and artifact hashes. The final setup was also exercised locally with uv 0.13.0
and Python 3.12: 100 CPU tests passed. An older local uv installation was left
untouched; a separately installed pinned executable was used for this check.

During setup validation, failed preliminary jobs exposed three launcher issues:
Slurm could adjust the allocated CPU count, uv's version string included a platform
suffix, and CPU synchronization needed an actual virtual environment before its
ownership marker could be reused. These were corrected and the complete setup
rerun successfully. The new CI job initially used a path context unavailable at
job scope; corrected workspace paths passed both jobs. Failed logs were retained.

## Paired baseline trial

Job `13832005` completed execution, then scoring and separate analysis, for both
configs on one RTX A6000 allocation. Control ran first, then candidate. Both used
clean source `8affb4d`, the pinned Qwen3-14B BF16 model, seed 17, the same three dev
tasks, one fresh attempt per task, a 600-second shared cell budget, 40 GiB cap,
32,768-token context, and 4,096-token generation limit. Only the system prompt and
experiment labels differed. See the [diagnostic design](../baseline-diagnostic.md).

| Dev task | Control success | Candidate success | Control / candidate error turns |
| --- | --- | --- | --- |
| `3ab5b8b_1`: Spotify downloads | No | No | 5 / 2 |
| `23cf851_1`: Venmo likes total | No | No | 2 / 2 |
| `fac291d_1`: unique songs across libraries | No | Yes | 2 / 3 |
| Total | **0/3** | **1/3** | **9 / 7** |

HTTP 401 turns fell from 4 to 0; unexpected-parameter turns fell from 4 to 3.
The candidate still produced one HTTP 422 login-validation error. Both runs had
errors on all three trajectories. A lower error count is neither a task score
nor proof of a causal mechanism, and a successful task can still contain errors.

All six attempts reached execution completion. None timed out, exceeded context,
or ran out of memory. Their final physical and logical cached-token counts agree;
all have zero retention events and zero rebuilds. Peak total VRAM was at most
33.673 GiB. These observations support the full-cache control's intended behavior
for this trial. They do not validate every possible numerical inference path.

The targeted task selection, single paired seed, fixed run order, and bundled
prompt changes prevent a general accuracy or causal claim. Do not pool these
runs with historical pilots, or freeze the main experiment from this result.

## Remaining baseline work

Ordinary saved actions explain the two remaining candidate failures:

- On `3ab5b8b_1`, the instruction requests downloads. The agent retrieves songs
  and completes with a list of titles and links, without downloading them. It
  also guesses `email` for login and supplies a token to an endpoint that rejects
  that argument. Authentication access improved, but task completion and exact
  signature use remain weak.
- On `23cf851_1`, the agent eventually logs in correctly, but totals a single
  default page and completes without traversing the remaining pages. The generic
  pagination instruction was insufficient to establish complete coverage.

The next train/dev intervention should target explicit task-completion evidence
and adherence to inspected signatures/pagination, measured against this candidate
under unchanged numerical settings. Keep evaluator feedback offline. The one
successful library-count task is evidence for this combined candidate on that
case, not a separate validation of the response-inspection instruction.

The Qwen3-8B/A100 80GB pilot, broader dev evaluation, settings freeze, recovery and
best-of-N comparisons, and final evaluation remain separate research work.

## Artifacts

[Evidence JSON](runtime-baseline-validation-2026-11-07.json) records the per-task
outcomes, timings, metrics, runtime/source identities, and hashes. The local
ignored artifact set is `baseline-repair-20261107`; the original remote run
artifacts retain their independent manifests, environments, trajectories, scores,
and analysis. Run IDs:

- Control: `5cf43b55-a6b7-4906-a315-5d2ed4cdd233`.
- Candidate: `2185fa57-81c1-4709-b1b0-90ee86cfece9`.

Corrected historical reports are saved separately as
[seed 17 schema 2](trajectory-audit-2026-11-07-seed17-v2.json) and
[seed 18 schema 2](trajectory-audit-2026-11-07-seed18-v2.json). Their input runs are
`113994b3-61c4-454f-bd7e-0f5f9bf63c26` and
`fc1712b6-991e-45f2-9c24-240078e7f9c6`, respectively. Original schema-1 reports and
all historical configurations remain unchanged. Reproduce them with
`--schema-version 1`; use new output paths for corrected audits.
