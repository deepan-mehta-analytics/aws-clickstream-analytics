# scripts/

Owner-run PowerShell scripts for the T1a and T1b proof windows, plus the
evidence helpers that support them. Claude never runs any of the PowerShell
scripts or the Bronze erase script, and never runs `aws`/`sam` itself (see the repo's `CLAUDE.md`
guardrails) — they are handed to the account owner to run via `!<command>`.

| Script | Who runs it | Needs AWS? | What it does |
|---|---|---|---|
| `t1a-upload-glue-code.ps1` | Owner | Yes | Builds `build/glue/clickstream_libs.zip` and uploads it plus `glue/build_silver_gold.py` to the artifacts bucket. Run once after a stack deploy, or after any change to the Glue code. |
| `t1a-window.ps1` | Owner | Yes | Runs one proof window: ingests April-July, runs Glue, ingests August alone to prove the job bookmark, runs Glue again, runs every `sql/validation/t1a/*.sql` query, then masks and saves evidence. |
| `t1a-teardown.ps1` | Owner | Yes | Empties the four T1a buckets, deletes the stack (`sam delete`), verifies it is gone, and shortens retention on the shared `/aws-glue/jobs*` log groups. |
| `t1a_evidence.py` | Anyone | No | The `expected`, `mask` and `compare` subcommands the two scripts above call. Reads/writes local files only; safe to run by hand for spot checks. |
| `t1b-window.ps1` | Owner | Yes | Runs T1b spec steps 1-18 in order: creates the three Iceberg tables (`sql/ddl/`), runs Glue twice around migration 001, erases visit A from Silver (`DELETE`, `OPTIMIZE`, `VACUUM`, with time travel before and after) and from Bronze, runs Glue a third time, then the validation SQL. Stops at the first failure with the step number and the run or query ID, and still masks the evidence gathered so far into `evidence/t1b/<date>/`. The owner deploys the stack first (step 0). |
| `t1b-teardown.ps1` | Owner | Yes | Drops the three Athena-created Iceberg tables through the stack's workgroup, confirms with `aws glue get-tables` that only the stack's own tables are left in the database, then runs `t1a-teardown.ps1`. |
| `t1b_erase_visit_from_bronze.py` | Owner (called by `t1b-window.ps1`) | Yes | Rewrites one Bronze month object without visit A and permanently deletes the old version by its version ID. Prints counts only. |
| `t1b_evidence.py` | Anyone | No | The `pick-visit`, `expected`, `checks` and `mask` subcommands the T1b window calls. Local files only. |

Raw window output (Lambda payloads, Glue run details, unmasked Athena
JSON, quality reports) is written only to `%TEMP%/t1a-window-<date>/` and
never enters the repo. `t1a-window.ps1` masks every file with
`t1a_evidence.py mask` before writing `window.json` and the Athena results
under `evidence/`, so those files carry no account IDs, ARNs, email
addresses or generated bucket names. `expected.json` and `comparison.json`
are copied or written unmasked because they hold only month labels and
counts — see `evidence/README.md`. The window script clears the previous
same-day scratch folder at the start of each run.

The T1b window follows the same rule with `%TEMP%/t1b-window-<date>/`, which
also holds the private visit pick (the real visit ID), the filled-in SQL and
the raw S3 version listings. Every file it writes under `evidence/t1b/<date>/`
(`window.json`, `expected_*.json`, `comparison.json`, `athena/`, `facts/`)
goes through `t1b_evidence.py mask --visit-file`, so the visit appears only as
"visit A" and no version ID, account ID or bucket name is kept. The console
shows the label, never the ID. If `evidence/t1b/<date>/` already exists, the
window refuses to start: move that folder aside first (it is never deleted).
