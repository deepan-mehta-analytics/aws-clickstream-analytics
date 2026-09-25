# tests/

pytest suite, one file per module. `conftest.py` holds helpers for hand-made clicks.
`test_full_file.py` reconciles the real UCI file against the measured stats in
`data/README.md`. It is skipped locally unless the file is downloaded, and CI
downloads it and verifies its MD5.

Run: `.venv/Scripts/python -m pytest -v` (Windows) or `make test`.
