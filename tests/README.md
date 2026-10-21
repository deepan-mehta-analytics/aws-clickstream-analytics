# tests/

pytest suite, one file per module. `conftest.py` holds helpers for hand-made clicks
and the local Spark session (with the Iceberg 1.11.0 runtime and a folder catalog
named `glue_catalog`, so the job code is the same as on AWS Glue).
`iceberg_helpers.py` builds small Iceberg tables for the T1b tests.
`test_full_file.py` reconciles the real UCI file against the measured stats in
`data/README.md`. It is skipped locally unless the file is downloaded, and CI
downloads it and verifies its MD5.

Count: **221 tests pass on Linux CI** (2026-10-21). On Windows 207 run and 14
are skipped: Spark file writes need `winutils` there, so the 9 Iceberg tests,
4 lake-storage tests and 1 session write test run only on Linux CI.

The T1b files: `test_iceberg_sql.py` (DDL and migration against the code),
`test_spark_iceberg.py` (Iceberg writes, Linux only), `test_t1b_evidence.py`
(the 20 window checks and masking), `test_t1b_erase_visit.py` (the Bronze
erase, with S3 stubbed) and `test_t1b_scripts.py` (the owner window and
teardown scripts, read statically and their PowerShell helpers on fixtures;
never against AWS).

Run: `.venv/Scripts/python -m pytest -v` (Windows) or `make test`.
