# Legacy resource cleanup

Cleanup completed after the user stopped the old research route and expanded the request to unused Insomnia storage. Removed 10 owned environments, 9 checkouts, 5 export wrappers, unused action-runtime staging, and the entire owned HuggingFace cache, including pinned 8B and 4B weights. All 28 target scopes were verified absent, and the final Slurm queue was empty. The removed paths contained 74.79 GiB of logical regular-file data; this is **not measured recovered disk space**, because hard links and concurrent cache cleanup prevent attribution. Nine local staging/scratch targets were also removed (1,466,563 bytes).

No legacy runtime remains. Source/model identities and completed results are preserved in the [verified legacy archive](cleanup-repository-2026-11-08.md). Shared 14B weights, AppWorld benchmark assets, unrelated projects, and shared cloud infrastructure were untouched. Six final deletion journals were copied and hash-verified before their remote directory was removed. [Separate Insomnia cleanup](cleanup-insomnia-2026-11-08.md) covers other outputs and caches.

CPU setup job `13840331` installed successfully in 711 seconds, then exceeded its 60-second readiness bound; overall exit 124 after 786 seconds. Checks never began, no model or task ran, and the exact stalled substep is unknown. All 19 terminal files (31,443 bytes) were preserved; no retry occurred.

The cloud audit found no active Batch jobs, VMs, disks, reserved addresses, instance groups/templates, allocated NAT addresses, or live bucket objects. Provider retention still holds 279 deleted objects (209,163,167 bytes), with permanent-deletion dates on November 15–16. Saved COMET estimates total $3.5441, with $10 conservatively reserved against the $40 cap; actual billed spend was not verified.

The [compact machine-readable record](cleanup-resources-2026-11-08.json) identifies the full private inventories and their hashes under `cleanup-20261108/resources`. No new experiment or compute allocation was launched during cleanup.
