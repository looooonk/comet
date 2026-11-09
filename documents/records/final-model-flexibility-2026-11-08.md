# Authorized final-model flexibility

On November 8, 2026, the user approved using a qualified stronger model of at
most 14B parameters for the final Q1/Q2 study if it establishes a useful
baseline. This supersedes the earlier requirement to keep every alternative
model exploratory and reserve final evaluation exclusively for Qwen3-8B.

No replacement has been selected or qualified by this decision alone. Select
using corrected train/dev evidence, including broader task coverage and the
model's own numerical, state, capacity and environment checks. Freeze its exact
model/tokenizer revisions, template, prompt, sampling, limits and device before
test evaluation. Keep historical 8B, 14B and newer-model outputs separate;
never pool models within one paired comparison.

The benchmark, pinned serving engine, BF16 precision, three eviction methods,
retention denominator, recovery semantics and shared time/memory budgets remain
unchanged. A model needing different engine or cache semantics requires an
explicit documented departure; this permission does not establish support for
Qwen3.5 in the existing engine. All unsupported paths remain visible.

The current registered alternatives retain their pilot-only configuration guard
until a candidate is qualified and its selection is recorded. At that point,
update the model registry/configuration guard, dependency decision and affected
diagnostic/final configs together before execution. No further permission to
use that qualified replacement is needed under this authorization. Existing
active pilot checkouts retain their pinned code and settings.
