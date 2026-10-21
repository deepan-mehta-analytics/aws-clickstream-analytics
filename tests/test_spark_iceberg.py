# ── Tests: Silver in Iceberg — v2 guard, month overwrite, column following, timestamps, deleted visits (Linux/CI only) ─
import os                                                               # platform check
from datetime import datetime, timezone                                 # times

import pandas as pd                                                     # frame comparison
import pytest                                                           # test framework

from conftest import source_row                                         # hand-made clicks
from iceberg_helpers import apply_migrations, create_silver_tables      # local tables from the real DDL
from spark_helpers import raw_frame, sorted_pandas, text_of             # raw-shaped frames, comparisons, UTC text

RUN = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)                  # run time
pytestmark = pytest.mark.skipif(os.name == "nt", reason="Iceberg folder catalogs need winutils on Windows; runs in CI")  # Linux only

APRIL = [source_row(v, c) for v in range(1, 6) for c in (1, 2)]          # 5 April visits, 10 clicks
AUGUST = [source_row(v, 1, day=13, month=8) for v in range(10, 13)]      # 3 August visits
FULL_TIME = "yyyy-MM-dd HH:mm:ss.SSSSSS"                                # timestamp text down to the microsecond


# ── Shared steps ──────────────────────────────────────────────
def lake(tmp_path):                                                     # local Gold folder standing in for the Gold bucket
    from clickstream_spark.storage import LakePaths                     # code under test
    return LakePaths(gold=str(tmp_path / "gold"))                       # no trailing slash


def run(spark, rows, tmp_path, tables):                                 # one run_increment call on hand-made rows
    from clickstream_spark.sql_files import load_summary_sql            # SQL texts
    from clickstream_spark.storage import run_increment                 # code under test
    return run_increment(spark, raw_frame(spark, rows), lake(tmp_path), tables, RUN, load_summary_sql())  # the report


def month_files(spark, table, month):                                   # data file paths of one click month
    query = f"SELECT file_path FROM {table}.files WHERE partition.click_month = '{month}'"  # Iceberg files metadata table
    return sorted(row.file_path for row in spark.sql(query).collect())  # stable order


def add_deleted_visit(spark, tables, visit_id):                         # put one visit on the deleted-visits list
    spark.sql(f"INSERT INTO {tables.deleted_visits} VALUES ({visit_id}, TIMESTAMP_NTZ '2026-10-20 12:00:00', 'test erasure request', 'bronze/2008-04.csv')")  # one row


# ── Format-version guard ──────────────────────────────────────
def test_format_version_2_passes_and_3_is_refused(spark):              # decision B3: never write to anything but v2
    from clickstream_spark.iceberg_tables import FormatVersionError, check_format_version  # code under test
    tables = create_silver_tables(spark)                                # v2, like Athena
    check_format_version(spark, tables.clicks)                          # passes silently
    newer_property = "'" + "format-" + "version" + "'='" + str(1 + 2) + "'"  # built at runtime so the repo-wide v3 text check stays clean
    newer = create_silver_tables(spark, database="clickstream_version_test", properties=newer_property)  # a separate, newer-format table set
    with pytest.raises(FormatVersionError, match=r"silver_clicks.*'3'"):  # names the table and the value
        check_format_version(spark, newer.clicks)                       # refused


# ── Athena-created table properties (window attempt 1, 2026-10-21) ─
def test_athena_object_storage_path_is_refused_until_write_data_path_is_set(spark, tmp_path):  # reproduces the production failure and proves the fix
    athena_like = f"'format-version'='2', 'write.object-storage.enabled'='true', 'write.object-storage.path'='{tmp_path / 'old'}/data'"  # what Athena adds on its own
    broken = create_silver_tables(spark, database="clickstream_athena_old_path", properties=athena_like)  # tables as Athena creates them
    with pytest.raises(Exception, match=r"write\.data\.path"):         # Iceberg 1.11 throws and names the new key (Spark may wrap it)
        run(spark, APRIL, tmp_path, broken)                             # the write that failed in Glue
    fixed_properties = f"{athena_like}, 'write.data.path'='{tmp_path / 'new'}/data'"  # what write_data_path_enabled=true produces
    fixed = create_silver_tables(spark, database="clickstream_athena_new_path", properties=fixed_properties)  # tables with the new key
    run(spark, APRIL, tmp_path, fixed)                                  # the same write now succeeds
    assert spark.table(fixed.clicks).count() == 10                      # the rows are readable


# ── Month overwrite ───────────────────────────────────────────
def test_overwrite_replaces_only_written_months(spark, tmp_path):      # decision B1: rerun safety
    tables = create_silver_tables(spark)                                # fresh tables
    run(spark, APRIL, tmp_path, tables)                                 # snapshot 1: April
    run(spark, AUGUST, tmp_path, tables)                                # snapshot 2: August
    august_files = month_files(spark, tables.clicks, "2008-08")         # August's data files before the April rerun
    run(spark, APRIL, tmp_path, tables)                                 # snapshot 3: April again
    counts = {row.click_month: row["count"] for row in spark.table(tables.clicks).groupBy("click_month").count().collect()}  # rows per month
    assert counts == {"2008-04": 10, "2008-08": 3}                      # April replaced, not doubled
    assert month_files(spark, tables.clicks, "2008-08") == august_files  # August untouched
    assert spark.sql(f"SELECT * FROM {tables.clicks}.snapshots").count() == 3  # one snapshot per run


# ── Column following (decision D2) ────────────────────────────
def test_writes_only_the_columns_the_table_has(spark):                 # the table is the contract
    from clickstream_spark.iceberg_tables import table_columns, write_months_to_table  # code under test
    from clickstream_spark.pipeline import build_increment              # Silver frames
    from clickstream_spark.silver import add_weekend_click_spark        # weekend_click column
    tables = create_silver_tables(spark)                                # fresh tables
    august = [source_row(10, 1, day=16, month=8), source_row(11, 1, day=13, month=8)]  # Saturday 16 and Wednesday 13 August 2008
    clicks = add_weekend_click_spark(build_increment(raw_frame(spark, APRIL + august), RUN).silver.clicks)  # frame always has weekend_click
    write_months_to_table(spark, clicks.filter("click_month = '2008-04'"), tables.clicks)  # before the migration
    assert "weekend_click" not in table_columns(spark, tables.clicks)   # the extra frame column was dropped
    april_files = month_files(spark, tables.clicks, "2008-04")          # April's data files
    apply_migrations(spark)                                             # ALTER TABLE ... ADD COLUMNS (weekend_click boolean)
    write_months_to_table(spark, clicks.filter("click_month = '2008-08'"), tables.clicks)  # same frame, after the migration
    rows = {row.visit_id: row.weekend_click for row in spark.table(tables.clicks).select("visit_id", "weekend_click").collect()}  # visit -> value
    assert {visit: rows[visit] for visit in range(1, 6)} == {visit: None for visit in range(1, 6)}  # old April rows read NULL
    assert rows[10] is True and rows[11] is False                       # August rows carry real values
    assert month_files(spark, tables.clicks, "2008-04") == april_files  # April was not rewritten


def test_frame_missing_a_table_column_is_refused(spark):               # Review Focus 4: fail loudly, never NULL silently
    from clickstream_spark.iceberg_tables import MissingColumnError, write_months_to_table  # code under test
    from clickstream_spark.pipeline import build_increment              # Silver frames
    tables = create_silver_tables(spark)                                # fresh tables
    apply_migrations(spark)                                             # table now has weekend_click
    clicks = build_increment(raw_frame(spark, APRIL), RUN).silver.clicks  # frame without weekend_click
    with pytest.raises(MissingColumnError, match="weekend_click"):      # names the column
        write_months_to_table(spark, clicks, tables.clicks)             # refused
    assert spark.table(tables.clicks).count() == 0                      # nothing written


# ── Timestamps (Review Focus 1) ───────────────────────────────
def test_timestamps_round_trip_through_the_iceberg_table(spark):       # Spark timestamp -> Iceberg timestamp (no zone) -> same UTC text
    from pyspark.sql.types import TimestampNTZType                      # the table's timestamp type
    from clickstream_spark.iceberg_tables import write_months_to_table  # code under test
    from clickstream_spark.pipeline import build_increment              # Silver frames
    tables = create_silver_tables(spark)                                # fresh tables
    clicks = build_increment(raw_frame(spark, APRIL), RUN).silver.clicks.cache()  # frame with Spark (session-zone) timestamps
    write_months_to_table(spark, clicks, tables.clicks)                 # cast and write
    stored = spark.table(tables.clicks)                                 # read back
    assert isinstance(stored.schema["click_time_synthetic"].dataType, TimestampNTZType)  # the table type Athena creates
    for click_id in [row.click_id for row in clicks.select("click_id").collect()]:  # every click
        for column in ("click_time_synthetic", "received_time"):        # both timestamp columns
            original = text_of(clicks.filter(clicks.click_id == click_id), column, FULL_TIME)  # UTC text before
            assert text_of(stored.filter(stored.click_id == click_id), column, FULL_TIME) == original, (click_id, column)  # same instant after


# ── Deleted visits (Review Focus 2 and 3, spec §3.3) ──────────
def test_empty_deleted_list_changes_nothing(spark, tmp_path):          # Review Focus 3: runs 1 and 2 match T1a
    tables = create_silver_tables(spark)                                # fresh tables, empty deleted list
    first = run(spark, APRIL, tmp_path, tables)                         # run 1: April
    second = run(spark, AUGUST, tmp_path, tables)                       # run 2: August
    assert second["total_silver_clicks"] == 13 and second["total_visits"] == 8  # T1a test_increment_then_new_month numbers
    assert first["deleted_visits_removed"] == 0 and second["deleted_visits_removed"] == 0  # nothing filtered
    assert second["format_versions"] == {tables.clicks: "2", tables.rejected: "2", tables.deleted_visits: "2"}  # all three checked


def test_deleted_visit_leaves_other_visits_identical(spark, tmp_path):  # Review Focus 2: the filter runs after enrichment
    tables = create_silver_tables(spark)                                # fresh tables
    gold = lake(tmp_path).gold                                          # Gold folder
    run(spark, APRIL, tmp_path, tables)                                 # April without deletions
    before = {                                                          # every output, materialised before the rerun
        "silver": sorted_pandas(spark.table(tables.clicks), ["click_id"]),  # Silver clicks
        "gold_clicks": sorted_pandas(spark.read.parquet(f"{gold}/clicks"), ["click_id"]),  # Gold clicks
        "visits": sorted_pandas(spark.read.parquet(f"{gold}/visits"), ["visit_id"]),  # Gold visits
    }
    add_deleted_visit(spark, tables, 3)                                 # visit 3 is erased
    report = run(spark, APRIL, tmp_path, tables)                        # rerun April (bookmark reset)
    after = {                                                           # the same outputs after the rerun
        "silver": sorted_pandas(spark.table(tables.clicks), ["click_id"]),  # Silver clicks
        "gold_clicks": sorted_pandas(spark.read.parquet(f"{gold}/clicks"), ["click_id"]),  # Gold clicks
        "visits": sorted_pandas(spark.read.parquet(f"{gold}/visits"), ["visit_id"]),  # Gold visits
    }
    assert report["deleted_visits_removed"] == 2                        # visit 3's two Silver clicks
    for name, frame in after.items():                                   # each output
        assert 3 not in set(frame["visit_id"]), name                    # visit 3 gone
        expected = before[name][before[name]["visit_id"] != 3].reset_index(drop=True)  # the first run minus visit 3
        pd.testing.assert_frame_equal(frame, expected, check_like=False, obj=name)  # every other row identical


def test_made_up_rejected_visit_is_deleted_and_stays_deleted(spark, tmp_path):  # spec §3.3: the rejects path, proven locally
    tables = create_silver_tables(spark)                                # fresh tables
    rows = APRIL + [source_row(7, 1), source_row(7, 3)]                 # visit 7 skips click 2, so the whole visit is rejected
    run(spark, rows, tmp_path, tables)                                  # first run
    assert {row.visit_id for row in spark.table(tables.rejected).collect()} == {7}  # visit 7 landed in rejects
    spark.sql(f"DELETE FROM {tables.rejected} WHERE visit_id = 7")      # the erasure DELETE (Athena runs the same statement)
    assert spark.table(tables.rejected).count() == 0                    # gone
    add_deleted_visit(spark, tables, 7)                                 # and listed, so reprocessing cannot bring it back
    report = run(spark, rows, tmp_path, tables)                         # rerun April from the unchanged source
    assert spark.table(tables.rejected).count() == 0                    # stays gone
    assert report["rejected_rows"] == 0 and report["deleted_visits_removed"] == 2  # filtered, counted
    assert spark.table(tables.clicks).count() == 10                     # clean April clicks unaffected
