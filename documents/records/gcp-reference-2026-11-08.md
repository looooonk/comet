# Bounded L4 reference attempt

One GCP L4 Spot job attempted the short Qwen3-8B numerical check from source
`2309d44`, with a one-hour workload limit and a $5 planning allowance within
the authorized $40 total. Managed setup completed, both AppWorld bundles were
verified, and all five pinned model shards passed their full checksums. Native
inference then refused initialization: the configured 22 GiB cap exceeded the
usable CUDA device capacity. No model was loaded and no logits were produced.

The device report listed an NVIDIA L4 with 23,034 MiB total, 555 MiB reserved
and 22,478 MiB free. The requested cap was 22,528 MiB. These rounded device
figures are not an exact CUDA-total measurement; failure occurred before native
provenance was saved. A future attempt must record both PyTorch CUDA totals
and validate its cap before downloading weights. The provisional 21 GiB short
check described in the validation guide remains unvalidated and does not qualify
longer task settings.

Cold setup took 25m45s; model download and full hashing took 3m14s. The 16 GiB
host passed its initial memory check, but model-loading memory fit was not
tested. A base PyTorch image alone would not remove this installation cost:
the managed runtime creates its own pinned environment rather than importing
the image's existing Python packages.

Twenty-five artifacts were fetched and checksum-verified, including the failed
status, source identities, setup logs and model hashes. Cleanup confirmed the
job, VM and disks absent, removed the verified cloud artifacts, and found no
allocated NAT IP. No retry was submitted.

Observed NAT traffic was 27.55 GiB, corresponding to approximately $1.24 in
processing charges at the [published NAT rate](https://cloud.google.com/nat/pricing).
The conservative total estimate is
**$1.98**, including machine time, disk and a storage/transfer reserve. Actual
billing remains unmeasured; the original $5 allowance stays reserved when
planning against the $40 ceiling. See the
[portable evidence record](gcp-reference-2026-11-08.json) for identities,
timings, cost assumptions and cleanup evidence.
