"""Load the dashboard summary SQL, from the Glue zip or from the repo (no Spark import, so it can be tested alone)."""  # module docstring

from importlib import resources                                         # files inside a package, even inside a zip
import re                                                               # pattern matching for the DDL parser
from pathlib import Path                                                # repo paths

SUMMARY_NAMES = ["daily_visits", "visit_depth_funnel", "bounce_rate_by_product", "visits_by_country_and_device"]  # must equal clickstream.summaries.SUMMARY_NAMES (tested)
REPO_SQL_DIR = Path(__file__).resolve().parents[2] / "sql" / "summaries"  # repo-level sql/summaries (local runs and tests)


def load_summary_sql() -> dict[str, str]:                               # summary name -> SQL text
    packaged = resources.files("clickstream_spark").joinpath("sql")     # present only inside the Glue zip
    if packaged.is_dir():                                               # running in Glue
        return {name: packaged.joinpath(f"{name}.sql").read_text(encoding="utf-8") for name in SUMMARY_NAMES}  # from the zip
    return {name: (REPO_SQL_DIR / f"{name}.sql").read_text(encoding="utf-8") for name in SUMMARY_NAMES}  # from the repo


# ── Iceberg DDL and migrations: repo files only (Glue does not need them), read with a small regex parser ─
REPO_DDL_DIR = Path(__file__).resolve().parents[2] / "sql" / "ddl"      # CREATE TABLE files
REPO_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "sql" / "migrations"  # numbered ALTER TABLE files
DDL_NAMES = ["silver_clicks", "silver_clicks_rejected", "silver_deleted_visits"]  # one file per table


def load_ddl() -> dict[str, str]:                                       # table name -> SQL text with the {silver_bucket} placeholder
    return {name: (REPO_DDL_DIR / f"{name}.sql").read_text(encoding="utf-8") for name in DDL_NAMES}  # read each file


def load_migrations() -> list[tuple[str, str]]:                         # (file name, SQL text), oldest first
    return [(path.name, path.read_text(encoding="utf-8")) for path in sorted(REPO_MIGRATIONS_DIR.glob("*.sql"))]  # sorted by name


def strip_comments(sql: str) -> str:                                    # remove -- comments (this repo's DDL has no -- inside quotes)
    return re.sub(r"--[^\n]*", "", sql)                                 # cut from -- to end of line


def ddl_columns(sql: str) -> list[tuple[str, str]]:                     # [(column, athena_type)] in declared order
    match = re.search(r"CREATE\s+TABLE\s+\S+\s*\((.*?)\)\s*(?:PARTITIONED|LOCATION)", strip_comments(sql), re.DOTALL | re.IGNORECASE)  # the column list
    if match is None:                                                   # not a table definition
        raise ValueError("no CREATE TABLE column list found")           # fail loudly
    pairs = [part.split() for part in match.group(1).split(",") if part.strip()]  # "name type" per column
    return [(name, kind) for name, kind in pairs]                       # tuples


def ddl_partition(sql: str) -> str | None:                              # the PARTITIONED BY column, or None
    match = re.search(r"PARTITIONED\s+BY\s*\(\s*(\w+)\s*\)", strip_comments(sql), re.IGNORECASE)  # single partition column
    return match.group(1) if match else None                            # None when unpartitioned


def ddl_properties(sql: str) -> dict[str, str]:                         # TBLPROPERTIES as a dict
    return dict(re.findall(r"'([^']+)'\s*=\s*'([^']*)'", strip_comments(sql).split("TBLPROPERTIES", 1)[-1]))  # 'key'='value' pairs after TBLPROPERTIES
