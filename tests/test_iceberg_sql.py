# ── Tests: the Iceberg DDL files, the migration and the small SQL parser (no Spark, runs on Windows) ─
import re                                                               # pattern matching
from pathlib import Path                                                # repo paths

from clickstream.silver import SILVER_COLUMNS                           # Silver clicks column order
from clickstream_spark.silver import REJECTED_COLUMNS                   # rejected column order
from clickstream_spark.sql_files import ddl_columns, ddl_partition, ddl_properties, load_ddl, load_migrations  # code under test

REPO = Path(__file__).resolve().parents[1]                              # repo root
AGREED_PROPERTIES = {                                                   # the seven pairs from the global constraints
    "table_type": "ICEBERG", "format": "parquet", "write_compression": "snappy",  # type, file format, compression
    "vacuum_max_snapshot_age_seconds": "60", "vacuum_min_snapshots_to_keep": "1",  # vacuum settings
    "optimize_rewrite_delete_file_threshold": "1", "optimize_rewrite_data_file_threshold": "1",  # optimize settings
}


def test_ddl_columns_match_the_code():                                  # column names and order equal the Python lists
    ddl = load_ddl()                                                    # table name -> SQL text
    assert [c for c, _ in ddl_columns(ddl["silver_clicks"])] == SILVER_COLUMNS  # Silver clicks
    assert [c for c, _ in ddl_columns(ddl["silver_clicks_rejected"])] == REJECTED_COLUMNS  # rejected clicks
    assert [c for c, _ in ddl_columns(ddl["silver_deleted_visits"])] == ["visit_id", "deleted_time", "reason", "bronze_key"]  # deleted visits


def template_types(resource: str, next_resource: str) -> dict[str, str]:  # column -> Glue type from the T1a template
    text = (REPO / "infra" / "t1-lake" / "template.yaml").read_text(encoding="utf-8")  # template text
    block = text.split(f"  {resource}:", 1)[1].split(f"  {next_resource}:", 1)[0]  # just that resource
    return dict(re.findall(r"\{ Name: (\w+), Type: (\w+) \}", block))      # name -> type, partition key included


def test_ddl_types_match_the_t1a_template():                            # a silent bigint -> int drift must fail
    ddl = load_ddl()                                                    # table name -> SQL text
    clicks = template_types("SilverClicksTable", "BronzeSourceClicksTable")  # Silver clicks types
    rejected = template_types("SilverClicksRejectedTable", "GoldClicksTable")  # rejected types
    assert dict(ddl_columns(ddl["silver_clicks"])) == clicks            # same name and type per column
    assert dict(ddl_columns(ddl["silver_clicks_rejected"])) == rejected  # same name and type per column
    assert ddl_columns(ddl["silver_deleted_visits"]) == [("visit_id", "bigint"), ("deleted_time", "timestamp"), ("reason", "string"), ("bronze_key", "string")]  # pinned


def test_ddl_partitions():                                              # partition column per table
    ddl = load_ddl()                                                    # table name -> SQL text
    assert ddl_partition(ddl["silver_clicks"]) == "click_month"         # by click month
    assert ddl_partition(ddl["silver_clicks_rejected"]) == "source_month"  # by source month
    assert ddl_partition(ddl["silver_deleted_visits"]) is None          # unpartitioned


def test_ddl_properties_are_exactly_the_agreed_set():                   # nothing more, nothing less
    for name, sql in load_ddl().items():                                # every table
        assert ddl_properties(sql) == AGREED_PROPERTIES, name           # exactly the seven pairs


def test_ddl_locations_are_folders_not_the_bucket_root():              # each table has its own folder
    for name, sql in load_ddl().items():                                # every table
        match = re.search(r"LOCATION\s+('[^']*')", sql)                 # the location literal
        assert match and re.fullmatch(r"'s3://\{silver_bucket\}/[a-z_]+/'", match.group(1)), name  # folder under the bucket


def test_no_v3_anywhere():                                              # Iceberg format version 3 is banned
    banned = [re.compile(r"format-version'\s*=\s*'3"), re.compile(r"table-default\.format-version")]  # both spellings
    for folder in ["sql", "src", "glue", "infra", "scripts"]:           # folders the ban covers
        for path in (REPO / folder).rglob("*"):                         # every file below
            if not path.is_file() or path.suffix not in {".sql", ".py", ".yaml", ".yml", ".md", ".json", ".ps1", ".txt"}:  # text files only
                continue                                                # skip binaries and caches
            text = path.read_text(encoding="utf-8", errors="ignore")    # file text
            for pattern in banned:                                      # each banned form
                assert not pattern.search(text), f"{path} contains {pattern.pattern}"  # must not occur


def test_migration_001_adds_weekend_click_only():                       # the one migration
    name, sql = load_migrations()[0]                                    # first migration
    assert name == "001_add_weekend_click.sql"                          # file name
    code = re.sub(r"--[^\n]*", "", sql)                                 # drop comments
    flat = " ".join(code.split()).rstrip(";").strip()                   # collapse whitespace
    assert flat == "ALTER TABLE clickstream_t1.silver_clicks ADD COLUMNS (weekend_click boolean)"  # exactly this
