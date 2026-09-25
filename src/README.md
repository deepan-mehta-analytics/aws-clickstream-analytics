# src/

The `clickstream` Python package: one module per pipeline stage.

| Module | Stage |
|---|---|
| `source_file.py` | Read the UCI #553 CSV; rename columns to plain names |
| `codebook.py` | Decode codes (category, colour, country, photo position and angle) |
| `enrichment.py` | Add `click_id`, `click_time_synthetic`, `device_type_synthetic` (seeded) |
| `bronze.py` | Bronze `clicks_received` |
| `silver.py` | Silver `clicks`, quality rules, `clicks_rejected` |
| `gold.py` | Gold reference tables, `clicks`, `visits` |
| `summaries.py` | Runs `sql/summaries/*.sql` in DuckDB |
| `quality.py` | Quality report |
| `local_run.py` | End-to-end local run (`python -m clickstream.local_run`) |

Design: `docs/adr/0003-data-model.md`. Columns: `docs/data-dictionary.md`.
