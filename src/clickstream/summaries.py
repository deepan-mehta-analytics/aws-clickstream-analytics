"""Run the dashboard summary SQL (sql/summaries/*.sql) against Gold tables in DuckDB."""  # module docstring

from pathlib import Path                                                # file paths

import duckdb                                                           # local SQL engine
import pandas as pd                                                     # dataframes
import pyarrow as pa                                                    # exact type conversion (dates stay dates)

SQL_DIR = Path(__file__).resolve().parents[2] / "sql" / "summaries"     # repo-level sql/summaries folder
SUMMARY_NAMES = ["daily_visits", "visit_depth_funnel", "bounce_rate_by_product", "visits_by_country_and_device"]  # one .sql file each


def run_summaries(tables: dict[str, pd.DataFrame], sql_dir: Path = SQL_DIR) -> dict[str, pd.DataFrame]:  # run every summary
    connection = duckdb.connect()                                       # in-memory database
    try:                                                                # always close the connection
        for name, frame in tables.items():                              # expose each Gold table by its name
            connection.register(name, pa.Table.from_pandas(frame, preserve_index=False))  # Arrow keeps date types exact
        return {                                                        # summary name -> result frame
            name: connection.execute((sql_dir / f"{name}.sql").read_text(encoding="utf-8")).df()  # run one file
            for name in SUMMARY_NAMES                                   # in a fixed order
        }
    finally:                                                            # even on error
        connection.close()                                              # release the database
