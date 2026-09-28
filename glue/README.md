# glue/

| File | Glue job | What it does |
|---|---|---|
| `build_silver_gold.py` | `<stack>-build-silver-gold` in `infra/t1-lake/template.yaml` | Reads only **new** Bronze CSV files (job bookmark `bronze_source`), builds Silver and Gold with `src/clickstream_spark/`, overwrites only the months it read, rebuilds the whole-dataset tables, saves a quality report to the silver bucket's `_reports/`, then commits the bookmark. |

The script stays thin: all logic lives in `src/clickstream_spark/` and is tested locally with PySpark 4.1.1 (the same Spark as Glue 6.0). Parity tests compare it with the pandas twin in `src/clickstream/`.

Upload before a window (owner): `scripts/t1a-upload-glue-code.ps1` builds `build/glue/clickstream_libs.zip` (`scripts/build_glue_libs.py`) and copies it and this script to the artifacts bucket.
