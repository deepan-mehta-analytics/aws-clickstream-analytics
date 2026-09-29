# evidence/

Masked evidence from real T1a proof windows, written by
`scripts/t1a-window.ps1` and never edited by hand.

## `evidence/t1a/<date>/`

One folder per window, named by the date it ran (`yyyy-MM-dd`):

| File | Contents |
|---|---|
| `window.json` | The whole run: ingest responses, both Glue run summaries, the two Glue quality reports, and the Athena query summaries (query id, bytes scanned, engine time). On a failed step, this still holds everything captured up to that point, plus a `failure` message. |
| `expected.json` | The local-twin counts (`scripts/t1a_evidence.py expected`) that the Athena results are checked against. |
| `comparison.json` | The result of `scripts/t1a_evidence.py compare`: expected vs. Athena counts per query, with a `match` flag for each. |
| `athena/*.json` | One masked Athena `get-query-results` response per file in `sql/validation/t1a/`. |

## Masking

`window.json` and `athena/*.json` have been through
`scripts/t1a_evidence.py mask`, which removes anything that identifies the
AWS account before they are written: AWS account IDs (12-digit numbers),
full ARNs, email addresses, and the CloudFormation-generated bucket names
(`<stack>-<role>bucket-<suffix>`, replaced with a role-only placeholder such
as `<bronze-bucket>`).

`expected.json` and `comparison.json` are not passed through the masker.
They are written by `t1a_evidence.py` itself and hold only month labels and
row counts, so they carry nothing account-specific. The masking regexes are
the only thing enforcing the rest, so they are not a substitute for reading
a new file type before it is added here.

## What is never here

The source CSV (`data/e-shop clothing 2008.csv`) is never copied into
`evidence/`; `.gitignore` ignores `*.csv` repo-wide. Raw, unmasked window
output lives only in `%TEMP%/t1a-window-<date>/` on the machine that ran
the window. It is not deleted automatically; the next same-day run clears it,
and the owner can delete it by hand once the masked copy above exists.
