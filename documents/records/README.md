# Personal and run records

Keep personal notes, dated execution logs, validation results, and artifact
inventories here. General implementation, setup, and repository guidance belongs
in the parent `documents/` directory.

Use dated, descriptive filenames and preserve existing evidence when adding a
follow-up. Record the relevant source, configuration, hardware, and limitations.
Omit personal account names, SSH workspace locations, private filesystem paths,
and links other contributors cannot access. Use portable artifact filenames and
hashes; link shared storage only when it is accessible to collaborators. Large
runtime artifacts are not included in this directory.

| Record | Contents |
| --- | --- |
| [2026-10-16 validation report](validation-2026-10-16.md) | Insomnia setup observations, integration checks, task attempts, and remaining limitations |
| [Initial validation evidence](validation-2026-10-16.json) | Revisions, retention matrix, checks, measurements, and artifact hashes |
| [Follow-up validation evidence](validation-2026-10-16-followup.json) | Larger-context attempts, live memory refusal, process interruption/resume, and offline scoring |
| [Paired retention pilot plan](retention-pilot-2026-10-17-plan.md) | Declared task sample, model departure, common budgets, and uncertainty analysis |
| [14B pilot preflight evidence](retention-pilot-2026-10-17-validation.json) | Model hashes, GPU persistence/capacity/cap checks, and hardware failure records |
| [Infrastructure-compromised pilot](retention-pilot-2026-10-17-quota-failure.json) | All 32 outcomes and original hashes from the run affected by compiler-cache quota exhaustion; excluded as a whole from the repaired comparison |

See the [validation guide](../validation.md) for reusable check instructions.
