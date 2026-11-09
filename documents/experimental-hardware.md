# Hardware qualification

The proposal initially specified one A100 80GB. On November 8, 2026, the user
authorized other adequately sized GPUs for pilots and final evaluation, provided
the workload finishes in a reasonable time. A100 availability is not a prerequisite
for progressing the study.

The selected Qwen3.5-9B study uses one GPU: L4 with a 21 GiB cap or, for separate
supplemental train studies, RTX PRO 6000 Blackwell Server Edition with a 24 GiB
cap. See the [qualification records](records/README.md). Larger candidates remain
unqualified; any future model-parallel configuration needs its own device-count,
topology and memory-accounting qualification before use.

Each controlled comparison must use the same GPU model/count, engine/runtime,
precision, task configuration, and experimental peak total VRAM cap. Keep measurements from
different GPU models separate. Device capacity is not the experimental memory cap.
Retain sequential attempts and batch size one. No change to models, benchmark,
retention definitions, recovery semantics, or shared task budgets follows from
this hardware decision.

Qualify a selected GPU with the managed live tests, the intended context/retention
range, transient memory checks, and train/dev execution before freezing settings.
Record the exact device and runtime in each run. Older alternative-device smoke
results remain exploratory; this decision does not retrospectively qualify them.
The runtime and freeze checks must require an explicitly selected, validated
device for new final runs instead of silently accepting arbitrary hardware.

Use Insomnia for larger experiments where practical. The authorized GCP spending
ceiling for this work is $40 total, including temporary storage. Inspect current
quota, availability, sizing and cost before paid provisioning; do not trade away
the pinned BF16 method or comparable memory budget merely to fit a smaller GPU.
