# Insomnia cleanup

The user stopped the experiment effort. Job **13840259** was canceled after **48m28s**, leaving seven terminal cells (three normal completions and four timeouts), one interrupted cell, and 30 unstarted cells. Scoring never began.

This cleanup removed **13.69 GB of remote logical file data**, including obsolete validation binaries, archived run copies, old logs/staging, generated AppWorld outputs, and **9.38 GB of exclusive caches**. It also removed redundant local prefixes and source bundles. Runtime/model cleanup is recorded separately; these logical counts do not measure physical quota reclaimed.

Completed useful evidence remains in the verified main legacy archive and a **1.87 MB supplement containing 678 additional files**. Compact hashes and measurements replace obsolete tensors and canceled working copies.

**Only the protected AppWorld benchmark root remains in the owned remote workspace.** Its generated output directory is empty. Runs, validation, jobs, logs, caches, checkouts and environments are absent, and the scheduler queue is empty. Unrelated projects and the external shared 14B snapshot were untouched. The final size walk reached its 60-second bound; explicit path checks passed.

The companion JSON identifies both archives and the ignored `cleanup-20261108/insomnia` evidence index. Per-file inventories remain outside the tracked working tree.
