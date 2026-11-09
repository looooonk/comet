# Qwen3-4B six-cell pilot result, 2026-11-08

Job `13839708` completed in 13m30s. The unchanged, qualified A6000 full-cache pilot scored **0/6 task-seed cells** across three targeted dev tasks and seeds 17/18. All six attempts completed normally; no timeout, context limit, memory-cap or infrastructure failure occurred. They finished before the separately invoked evaluator and analysis. This is a targeted regression diagnostic, not a representative model-capability estimate.

The [machine-readable record](execution-qwen4b-instruct-2026-11-08-results.json) pins configuration, source, model, runtime and evidence hashes.

The repaired offline scorer compared all 103 state models in every outcome (618 comparisons total); all six saved model-counter maps were nonempty. All 191 output files were copied and SHA-256/size verified. Source and runtime markers remained unchanged.

| Task | Seed | Seconds | Tool blocks | Observed error blocks | Raw tokens | Task success |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 0d8a4ee_1 | 17 | 127.27 | 8 | 1 | 6116 | No |
| 0d8a4ee_1 | 18 | 20.90 | 7 | 0 | 5011 | No |
| 3ab5b8b_1 | 17 | 30.62 | 11 | 2 | 7955 | No |
| 3ab5b8b_1 | 18 | 43.70 | 20 | 7 | 8739 | No |
| 57c3486_1 | 17 | 20.25 | 7 | 1 | 7075 | No |
| 57c3486_1 | 18 | 42.30 | 16 | 5 | 17241 | No |

Ordinary saved traces establish these failure patterns independently of evaluator requirements:

- `0d8a4ee_1`, seed 17: Authenticated after one rejected password-as-token call; sent a real text to the supervisor's own number without discovering the requested relatives; claimed success.
- `0d8a4ee_1`, seed 18: Authenticated and sent a real text to the supervisor's own number, treating it as a proxy for relatives; claimed success.
- `3ab5b8b_1`, seed 17: Recovered from two login argument/username errors; queried liked songs and downloaded four songs from that first response while claiming completion for liked playlists; no pagination traversal observed.
- `3ab5b8b_1`, seed 18: Queried liked songs, then wrote their metadata to a file after several filesystem/authentication errors; never called a song-download API; claimed completion for liked playlists.
- `57c3486_1`, seed 17: Used a password as a token; after rejection incorrectly concluded no login endpoint was available and explicitly completed with failure.
- `57c3486_1`, seed 18: Authenticated, read one page of followed artists, then repeatedly omitted the token on like calls; eventually liked returned search results after reading the endpoint signature. No pagination traversal observed; claimed success.

Peak total VRAM was 14,572,126,208 bytes under the 40 GiB cap; peak KV was 2,542,141,440 bytes. Decode throughput was 61.18 tokens/s. The run generated 6,187 tokens and recorded estimated dense-model inference cost of 581,422,090,515,456 FLOPs (an estimate, not a measured hardware counter).

The first environment reset consumed 94.61s; later resets took 0.45-0.80s. All reset and tool costs were charged to the original 600s per-cell budget. The initial 41.41s synthetic engine warmup and model loading were excluded consistently. No budget, sampling, prompt or task changes were made during execution.

The zero-success floor does not support the intended retention/recovery comparison. It does not justify outcome-based task cherry-picking or a population-level zero-success claim.

A read-only observation audit reconstructed all **69 generated-turn prefixes**
from the actual raw token IDs with the pinned tokenizer. All 63 nonterminal
observations were carried completely into the following generation; the six
terminal responses needed no further generation. All 22 documentation responses
parsed as complete JSON. Phone listings contained 30 endpoints and Spotify
listings 92, including login, contact lookup, liked playlists, song download and
artist-following endpoints that the model ignored or claimed were unavailable.
Detailed docs contained both parameters and response schemas. No truncation
marker appeared; the largest observed output had 18,949 characters. The pinned
AppWorld stdout path has no output truncation, and API listing is unpaginated.
Missing or clipped documentation does not explain these inspected failures.
This does not establish universal numerical correctness.

The next capability check retains the [predeclared broader dev sample](baseline-qwen4b-instruct-2026-11-08-plan.md):
all 19 families, variant `_1`, and both seeds. It must run independently with
unchanged settings and preserved failures; these six cells cannot be spliced
into it. A separate recorded scope extension is required for the bounded
A6000 numerical qualification.
