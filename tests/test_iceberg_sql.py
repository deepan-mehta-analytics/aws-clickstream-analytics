# ── Tests: the Iceberg DDL files, the migration and the small SQL parser (no Spark, runs on Windows) ─
import re                                                               # pattern matching
from pathlib import Path                                                # repo paths

from clickstream.silver import SILVER_COLUMNS                           # Silver clicks column order
from clickstream_spark.silver import REJECTED_COLUMNS                   # rejected column order
from clickstream_spark.sql_files import ddl_columns, ddl_partition, ddl_properties, load_ddl, load_migrations  # code under test

REPO = Path(__file__).resolve().parents[1]                              # repo root
AGREED_PROPERTIES = {                                                   # the eight pairs: the global constraints' seven plus the owner-approved write_data_path_enabled
    "table_type": "ICEBERG", "format": "parquet", "write_compression": "snappy",  # type, file format, compression
    "vacuum_max_snapshot_age_seconds": "60", "vacuum_min_snapshots_to_keep": "1",  # vacuum settings
    "optimize_rewrite_delete_file_threshold": "1", "optimize_rewrite_data_file_threshold": "1",  # optimize settings
    "write_data_path_enabled": "true",                                  # Athena writes write.data.path (Iceberg 1.9+ refuses the old key)
}


def test_ddl_columns_match_the_code():                                  # column names and order equal the Python lists
    ddl = load_ddl()                                                    # table name -> SQL text
    assert [c for c, _ in ddl_columns(ddl["silver_clicks"])] == SILVER_COLUMNS  # Silver clicks
    assert [c for c, _ in ddl_columns(ddl["silver_clicks_rejected"])] == REJECTED_COLUMNS  # rejected clicks
    assert [c for c, _ in ddl_columns(ddl["silver_deleted_visits"])] == ["visit_id", "deleted_time", "reason", "bronze_key"]  # deleted visits


PINNED_TYPES = {                                                        # the T1a Parquet tables' column types, captured before those resources were removed
    "silver_clicks": {                                                  # Silver clicks, partition key included
        "click_month": "string", "click_id": "string", "visit_id": "bigint", "click_number_in_visit": "bigint",  # key, id, visit, position
        "click_date": "date", "click_time_synthetic": "timestamp", "click_hour_shop_time_synthetic": "bigint",  # dates and times
        "product_code": "string", "category": "string", "colour": "string", "price_usd": "bigint",  # product details
        "priced_above_category_average": "boolean", "page_number_in_shop": "bigint", "photo_position_on_page": "string",  # flags and placement
        "photo_angle": "string", "country_code": "bigint", "device_type_synthetic": "string",  # angle, country, device
        "received_time": "timestamp", "seconds_late": "bigint",         # arrival
    },                                                                  # end of the Silver clicks types
    "silver_clicks_rejected": {                                         # rejected clicks, partition key included
        "source_month": "string", "year": "bigint", "month": "bigint", "day": "bigint",  # key and source date
        "click_number_in_visit": "bigint", "country_code": "bigint", "visit_id": "bigint", "category_code": "bigint",  # source codes
        "product_code": "string", "colour_code": "bigint", "photo_position_code": "bigint", "photo_angle_code": "bigint",  # more codes
        "price_usd": "bigint", "price_above_category_average_code": "bigint", "page_number_in_shop": "bigint",  # price and page
        "click_id": "string", "click_time_synthetic": "timestamp", "device_type_synthetic": "string",  # built fields
        "received_time": "timestamp", "data_source": "string", "rejection_reason": "string", "rejected_time": "timestamp",  # audit fields
    },                                                                  # end of the rejected clicks types
}                                                                       # end of the pinned types


def test_ddl_types_match_the_pinned_t1a_types():                        # a silent bigint -> int drift must fail
    ddl = load_ddl()                                                    # table name -> SQL text
    assert dict(ddl_columns(ddl["silver_clicks"])) == PINNED_TYPES["silver_clicks"]  # same name and type per column
    assert dict(ddl_columns(ddl["silver_clicks_rejected"])) == PINNED_TYPES["silver_clicks_rejected"]  # same name and type per column
    assert ddl_columns(ddl["silver_deleted_visits"]) == [("visit_id", "bigint"), ("deleted_time", "timestamp"), ("reason", "string"), ("bronze_key", "string")]  # pinned


def test_ddl_partitions():                                              # partition column per table
    ddl = load_ddl()                                                    # table name -> SQL text
    assert ddl_partition(ddl["silver_clicks"]) == "click_month"         # by click month
    assert ddl_partition(ddl["silver_clicks_rejected"]) == "source_month"  # by source month
    assert ddl_partition(ddl["silver_deleted_visits"]) is None          # unpartitioned


def test_ddl_properties_are_exactly_the_agreed_set():                   # nothing more, nothing less
    for name, sql in load_ddl().items():                                # every table
        assert ddl_properties(sql) == AGREED_PROPERTIES, name           # exactly the eight pairs


def test_every_ddl_makes_athena_write_the_data_path_property():         # 2026-10-21 window failure: Iceberg 1.11 refuses write.object-storage.path
    for name, sql in load_ddl().items():                                # every table
        assert ddl_properties(sql).get("write_data_path_enabled") == "true", name  # without it Glue's overwritePartitions throws


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
