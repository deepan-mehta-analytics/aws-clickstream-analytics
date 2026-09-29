# scripts/

Owner-run PowerShell scripts for a T1a proof window, plus the evidence
helper that supports them. Claude never runs any of the three PowerShell
scripts, and never runs `aws`/`sam` itself (see the repo's `CLAUDE.md`
guardrails) — they are handed to the account owner to run via `!<command>`.

| Script | Who runs it | Needs AWS? | What it does |
|---|---|---|---|
| `t1a-upload-glue-code.ps1` | Owner | Yes | Builds `build/glue/clickstream_libs.zip` and uploads it plus `glue/build_silver_gold.py` to the artifacts bucket. Run once after a stack deploy, or after any change to the Glue code. |
| `t1a-window.ps1` | Owner | Yes | Runs one proof window: ingests April-July, runs Glue, ingests August alone to prove the job bookmark, runs Glue again, runs every `sql/validation/t1a/*.sql` query, then masks and saves evidence. |
| `t1a-teardown.ps1` | Owner | Yes | Empties the four T1a buckets, deletes the stack (`sam delete`), verifies it is gone, and shortens retention on the shared `/aws-glue/jobs*` log groups. |
| `t1a_evidence.py` | Anyone | No | The `expected`, `mask` and `compare` subcommands the two scripts above call. Reads/writes local files only; safe to run by hand for spot checks. |

Raw window output (Lambda payloads, Glue run details, unmasked Athena
JSON, quality reports) is written only to `%TEMP%/t1a-window-<date>/` and
never enters the repo. `t1a-window.ps1` masks every file with
`t1a_evidence.py mask` before writing `window.json` and the Athena results
under `evidence/`, so those files carry no account IDs, ARNs, email
addresses or generated bucket names. `expected.json` and `comparison.json`
are copied or written unmasked because they hold only month labels and
counts — see `evidence/README.md`. The window script clears the previous
same-day scratch folder at the start of each run.
