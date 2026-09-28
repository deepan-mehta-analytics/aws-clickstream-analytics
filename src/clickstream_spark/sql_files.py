"""Load the dashboard summary SQL, from the Glue zip or from the repo (no Spark import, so it can be tested alone)."""  # module docstring

from importlib import resources                                         # files inside a package, even inside a zip
from pathlib import Path                                                # repo paths

SUMMARY_NAMES = ["daily_visits", "visit_depth_funnel", "bounce_rate_by_product", "visits_by_country_and_device"]  # must equal clickstream.summaries.SUMMARY_NAMES (tested)
REPO_SQL_DIR = Path(__file__).resolve().parents[2] / "sql" / "summaries"  # repo-level sql/summaries (local runs and tests)


def load_summary_sql() -> dict[str, str]:                               # summary name -> SQL text
    packaged = resources.files("clickstream_spark").joinpath("sql")     # present only inside the Glue zip
    if packaged.is_dir():                                               # running in Glue
        return {name: packaged.joinpath(f"{name}.sql").read_text(encoding="utf-8") for name in SUMMARY_NAMES}  # from the zip
    return {name: (REPO_SQL_DIR / f"{name}.sql").read_text(encoding="utf-8") for name in SUMMARY_NAMES}  # from the repo
