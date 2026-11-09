# AppWorld first-reset cost diagnostic

A CPU-only check measured **41.61 seconds for the first fresh reset and
0.21 seconds for the second**, using the same train task and seed. Both initial
database snapshots were byte-identical, and neither environment executed a tool
or loaded evaluator solutions. The [verified record](appworld-reset-cost-2026-11-08.json)
pins the source, profiles and 59 copied output files.

| Profile self-time component | First reset | Second reset |
| --- | ---: | ---: |
| Direct base-SQLite connection opens | 17.673 s | 0 s |
| Module-loader file reads | 10.102 s | 0 s |
| Other text reads | 2.992 s | <0.001 s |
| SQLite backups into fresh task databases | 2.237 s | 0.058 s |

The first reset imported 196 modules; the second imported none. Pinned AppWorld
code caches base-database connections and copies their contents into fresh
in-memory task databases. Thus fresh task state can coexist with reused process
setup. The figures above are self times, not overlapping cumulative profiler
intervals. Total profile self times closely match the measured reset durations.

Before either reset, the actual `validate_tasks` call took another 71.53 seconds.
That phase already runs before the production Runner and must not be attributed
to its charged reset cost. All timing here uses the production
`CLOCK_MONOTONIC` path, which AppWorld's simulated clock does not replace.
Earlier exploratory reset/turn timings from job `13840260` used a frozen Python
clock and remain invalid; its verified API/state evidence is separate.

This is one profiled CPU process and train task, without GPU/model imports.
Filesystem caching, host state and profiler overhead differ from GPU experiments.
It identifies a first-use mechanism but does not fully explain the earlier
94.61-second first reset or establish a latency distribution. The active broader
4B run separately measured 11.84 seconds for its first reset and 0.79 seconds
for its second, illustrating why the earlier value is not a fixed setup cost.

The proposed future short-budget protocol would initialize and close one fixed
training environment once per process, record that setup separately, and still
charge every experimental reset, tool, checkpoint and rebuild. This changes the
documented budget definition and is awaiting the user's decision. No current
run, recorded budget or failure has been altered.
