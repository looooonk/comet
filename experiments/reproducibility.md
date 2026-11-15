# Reading and reproducing the experiments

[Ledger index](README.md)

Reproduction has three levels: reading the committed result summaries,
regenerating figures from saved analyses, and rebuilding a run from its pinned
source and complete artifacts. The first two usually need no GPU. Rescoring
needs saved AppWorld environments and data; fresh execution needs the matching
qualified device and runtime. Current `main` is not automatically the execution
source of an older measurement.

## Shared Qwen3.5-9B conditions

These settings apply to the main 50-task, 19-family, Blackwell pilot and L4
frozen-test entries. Earlier capability pilots have explicit differences in
their [own entry](l4-studies.md). The resolved study configuration and original
manifest take precedence over this readable summary.

| Component | Recorded setting or authoritative source |
| --- | --- |
| Model and tokenizer | `Qwen/Qwen3.5-9B`, both at `c202236235762e1c871ad0ccb60c8ee5ba337b9a` |
| Backend and precision | Shared `transformers_hybrid`, BF16; recurrent parameters/state retain their prescribed types |
| Runtime | Python 3.12, Transformers 5.22.2, PyTorch 2.9.1; exact package/build versions and CUDA runtime belong to each manifest |
| Dependency definitions | [`dependencies.lock.json`](../dependencies.lock.json), [`uv.lock`](../uv.lock), [`hybrid.lock`](../infra/requirements/hybrid.lock) and [`appworld.lock`](../infra/requirements/appworld.lock), at the run's source revision |
| Eviction implementations | Pinned selectors from `254c57bc84e4a7895159ba1062bd46c83626f511`; hybrid R-KV uses a 256 MiB tiled redundancy workspace; preserve the recorded local implementation |
| Benchmark | AppWorld data 0.2.0; code pin `42b5bcf3cd334fee33f0c37c02070a9f5807add5`; application/test bundle hashes in the dependency lock |
| Context and output | 16,384 raw context tokens; at most 1,024 new tokens per generation; prefill chunks of 128 |
| Sampling | Temperature 0.7, top-p 0.8, thinking disabled; paired seed 17 unless explicitly varied |
| Prompt | Exact v4 prompt inherited from [`baseline-v4.json`](../configs/qwen9b/l4/baseline-v4.json); preserve its full text and model chat template |
| Agent protocol | Executable Python required; stop after four consecutive execution/action failures; evaluator feedback is unavailable to the agent |
| Attempts | Batch size one, sequential attempts; fresh task state for each ordinary attempt; N=1 controls and N=2 arms as declared |
| Time | Ordinarily 120 seconds shared by all attempts in one task/condition/seed cell; diagnostics use 90 seconds including checkpoint preparation |
| Memory | One L4 at 21 GiB or one Blackwell at 24 GiB; 2 GiB configured workspace reserve; preserve the additional allocator headroom and measured total-device cap |
| Recovery | Never, fixed after 4 tool calls, or dynamic at both 6,144 context tokens and 3 tool calls; at most one rebuild per attempt |
| Isolated warmup | Train task `82e2fac_1`, seed 0, once per launch when configured; initialization/close only, recorded separately, without model observations or tool calls |

[`base.json`](../configs/qwen9b/base.json) supplies common values; study-specific
inheritance supplies the rest. Objects merge one level and lists replace in
full. Use the [configuration guide](../configs/README.md) and saved resolved
configuration rather than reconstructing a run from this table alone. In the
dependency lock, `hybrid_model` is the current model; the older `model` entry
belongs to the legacy backend.

## What the metrics mean

**Retention** is the fraction of attention KV entries retained relative to
full-cache inference at the same raw-token step. If retention is $r$, the
figure's compaction aggressivity is $100\left(1-r\right)$ percent. It does not
measure text truncation or total-VRAM savings. Targets use decimal ceiling and
mandatory floors of 16 entries for StreamingLLM, 8 for R-KV and 24 for AgentKV,
bounded by available history. The eight full-attention layers are compressed;
the 24 recurrent layers' state is preserved and measured separately. Report
realized occupancy as well as configured retention.

**Recovery** rebuilds all hybrid model state from the full raw transcript and
then reapplies retention. It does not repeat tools or undo environment actions.
The runner checks the policy before the next generation using current raw-token
context and completed tool-call counts. A trigger requests a rebuild; memory or
remaining-time admission can still refuse it. Keep requests, admissions,
refusals, elapsed cost and transient memory in the evidence. See the
[backend contract](../documents/hybrid-backend.md) and
[policy implementation](../src/comet/policies.py).

**First-attempt success** scores the first attempt in the stated condition.
**Oracle success** counts tasks solved by any eligible attempt within its shared
budget, assuming perfect post-hoc selection. It is an upper bound, not a deployed
selection policy. A separately run N=1 control is not necessarily equal to the
first attempt of the N=2 control under timing and storage variation. Normal
execution completion does not imply evaluator success.

**Time and failures** include reset, tool execution, checkpoint preparation,
rebuild, saving and cleanup. Model loading and offline scoring are excluded
consistently. Timeouts, context limits, OOMs, protocol errors, interruptions and
infeasibility remain in their comparison denominators. In-flight work can finish
after the nominal budget; report measured overruns and do not credit late success.
An interrupted attempt keeps its original reservation and receives no free retry.

**Resources** distinguish occupied KV, uncompressed recurrent state, PyTorch
allocation/reservation and sampled total-device VRAM. Device memory is sampled
every 10 ms and at forward boundaries; shorter external transients can be missed.
Estimated inference FLOPs omit recurrent updates, eviction, elementwise work and
vision. Throughput and resource averages must retain their measurement coverage;
missing observations are not zeros. Storage latency is part of the wall-clock
result and must not be labeled GPU compute time.

**Uncertainty** resamples tasks with their paired conditions, seeds and attempts.
Attempts and repeated variants are not independent tasks. Intervals are pointwise
95%, not simultaneous across a whole grid. The original 50-task and smaller
analyses use 2,000 bootstrap draws; the 19-family report uses 10,000 with bootstrap
seed 20261109. Consult each analysis for its exact procedure and bootstrap seed.
Zero-width intervals at all-failure/all-success points do not establish population
certainty; conservative bounded intervals are retained where provided.

## Recovering a run

Each study entry links its configuration and evidence summary. From those:

1. Identify the original run or partition IDs, execution and evaluator source,
   local source changes, resolved configuration/digest and freeze provenance.
   Historical paths may predate the current configuration layout. Match resolved
   values and the saved source, not just a similar filename.
2. Obtain the complete external run directories and verify their recorded artifact
   identities. Retain `manifest.json`, `cells/<id>/cell.json`, ordered attempts,
   raw token transcripts, actions/observations, metrics, recovery decisions,
   evaluator-compatible environments, `scores.json`, `analysis.json` and any
   diagnostic `checkpoints/`. A portable ID alone does not locate a download;
   obtain the corresponding bundle from project storage. Availability was not
   re-audited during this documentation sync.
3. Recreate the owned runtime at the run's source using
   [`setup_runtime.sh`](../scripts/setup_runtime.sh) and the recorded pins,
   patches, model/tokenizer and AppWorld data. Preserve package/build versions,
   CUDA/driver and device details, CPU threads, host RAM, storage placement,
   warmup, condition order and process lifetime. These matter under time limits.
4. For fresh execution, qualify the exact device/cap/source/runtime and intended
   workload through [`run_checks.sh`](../scripts/run_checks.sh) and the
   [live validation workflow](../documents/validation/README.md), then use a new
   run directory. A valid old check does not qualify new code or hardware.
5. Score saved outcomes offline using the compatible evaluator. Analyze only
   compatible complete groups; verify every expected task/condition/seed tuple
   exactly once. Preserve all failures and measurement gaps.

Do not synchronize a managed GPU environment with `uv run`. Activate its matching
profile before direct commands. A compatible resume uses the original directory,
source, configuration, device and runtime and preserves consumed budgets; a new
replication is a separate cohort. See [setup](../documents/setup.md) and the
[execution/resume workflow](../documents/experiments.md) for launch commands.

## Regenerating the main figures

From the repository root, prepare the owned CPU environment and its plotting
extra as described in [setup](../documents/setup.md), then activate it:

```sh
export COMET_REPO="$PWD"
export COMET_ENV="$COMET_REPO/.venv-cpu"
source scripts/activate_runtime.sh cpu
export COMET_FIGURES=/path/to/new/figure-directory
mkdir -p "$COMET_FIGURES"

comet plot-aggressivity documents/records/qwen9b/analysis/test50-final-analysis.json \
  --y-limits 0 50 --output "$COMET_FIGURES/test50-compression.png"
comet plot-resources documents/records/qwen9b/analysis/test50-final-analysis.json \
  --policy never --output "$COMET_FIGURES/test50-resources.png"
comet plot-aggressivity documents/records/qwen9b/analysis/final-analysis.json \
  --output "$COMET_FIGURES/l4-test.png"
comet plot-aggressivity documents/records/qwen9b/analysis/train-finegrid-blackwell-analysis.json \
  --output "$COMET_FIGURES/blackwell-train.png"
comet plot-recovery documents/records/qwen9b/analysis/q1-diagnostic-blackwell-analysis.json \
  --output "$COMET_FIGURES/blackwell-diagnostic.png"
```

Replace `.png` with `.pdf` for vector output. The 19-family compact summary is
not a full analysis input: retrieve its recorded compact bundle's `analysis.json`
to use the shared plotting commands. To rebuild that analysis from its four
already scored groups, use the recorded bootstrap settings:

```sh
comet analyze /path/to/part-00 /path/to/part-01 /path/to/part-02 /path/to/part-03 \
  --bootstrap-samples 10000 --seed 20261109 \
  --output /path/to/new/dev19-analysis.json
comet plot-aggressivity /path/to/new/dev19-analysis.json \
  --output "$COMET_FIGURES/dev19-recovery.png"
```

For the frozen 50-task study, aggregation must additionally pass its frozen parent
with `--study-config configs/qwen9b/blackwell/test50-v1.json` and all eight scored
partitions. This verifies complete parent coverage. The commands above reproduce
views of existing observations; new execution produces a new experiment result.
