# evidence/

Masked evidence from real proof windows, written by
`scripts/t1a-window.ps1` (T1a) and `scripts/t1b-window.ps1` (T1b) and never
edited by hand. No T1b window has run yet.

## `evidence/t1a/<date>/`

One folder per window, named by the date it ran (`yyyy-MM-dd`):

| File | Contents |
|---|---|
| `window.json` | The whole run: ingest responses, both Glue run summaries, the two Glue quality reports, and the Athena query summaries (query id, bytes scanned, engine time). On a failed step, this still holds everything captured up to that point, plus a `failure` message. |
| `expected.json` | The local-twin counts (`scripts/t1a_evidence.py expected`) that the Athena results are checked against. |
| `comparison.json` | The result of `scripts/t1a_evidence.py compare`: expected vs. Athena counts per query, with a `match` flag for each. |
| `athena/*.json` | One masked Athena `get-query-results` response per file in `sql/validation/t1a/`. |

## `evidence/t1b/<date>/`

One folder per T1b window. The window refuses to start if today's folder
already exists, so an earlier run's evidence is never overwritten.

| File | Contents |
|---|---|
| `window.json` | The whole run step by step: ingest responses, the three Glue run summaries and quality reports, Athena query summaries, and a `failure` message naming the step if it stopped early. |
| `expected_before.json`, `expected_after.json` | The local-twin counts with and without visit A (`scripts/t1b_evidence.py expected`). |
| `comparison.json` | The 20 pass/fail checks from `scripts/t1b_evidence.py checks` (format version, bookmark file counts, the column change, the delete, time travel, data files after `OPTIMIZE` and `VACUUM`, the Bronze erase, run 3 and the final counts). Written only once step 8 has run. |
| `athena/*.json` | One masked Athena `get-query-results` response per query. |
| `facts/*.json` | The small inputs the checks read (counts, file lists, snapshot results, the Bronze version count), one file per fact. |

Two checks are narrower than they could be: August's `weekend_click` values
are compared with "Saturday or Sunday" worked out from each `click_date` in
Athena (the local twin's rule), not joined row by row with the local output;
and the rejects table may keep its last snapshot after `VACUUM`, because
visit A has no rejected rows and so no new commit lands there.

T1b masking adds two things to the T1a rules below: the real visit ID
becomes the label `visit A` (only in fields that carry a visit, never by a
free-text number swap), and S3 version IDs become a placeholder. The real
visit ID, the version IDs and the raw listings stay in
`%TEMP%/t1b-window-<date>/`.

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
