# lambdas/

| Folder | Function | What it does | Tier |
|---|---|---|---|
| `ingest_source/` | `IngestFunction` in `infra/t1-lake/template.yaml` | Downloads the UCI #553 zip, checks its MD5, and writes the raw rows into the Bronze bucket as `source_month=YYYY-MM/clicks.csv` (header + that month's rows; line endings changed to LF, field values unchanged). Calling it again for a month already landed from the same file does nothing. | T1a |

Standard library + boto3 only (both are in the Lambda Python 3.13 runtime), so there is nothing to package.
Tests: `tests/test_ingest_source.py` (no network, stubbed S3).
