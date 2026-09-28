# ── Tests: run_increment writes months and rebuilds whole tables (Linux/CI; Spark writes need Hadoop tools on Windows) ─
import os                                                               # platform check
from datetime import datetime, timezone                                 # times

import pytest                                                           # test framework

from conftest import source_row                                         # hand-made clicks
from spark_helpers import raw_frame                                     # raw-shaped frames

RUN = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)                  # run time
pytestmark = pytest.mark.skipif(os.name == "nt", reason="Spark Parquet writes on Windows need winutils; runs in CI")  # Linux only

APRIL = [source_row(v, c) for v in range(1, 6) for c in (1, 2)]          # 5 April visits, 10 clicks
AUGUST = [source_row(v, 1, day=13, month=8) for v in range(10, 13)]      # 3 August visits


def lake(tmp_path):                                                     # local folders standing in for S3 buckets
    from clickstream_spark.storage import LakePaths                     # code under test
    return LakePaths(silver=str(tmp_path / "silver"), gold=str(tmp_path / "gold"))  # no trailing slash


def test_increment_then_new_month(spark, tmp_path):                     # the bookmark flow, locally
    from clickstream_spark.sql_files import load_summary_sql            # SQL texts
    from clickstream_spark.storage import run_increment                 # code under test
    paths = lake(tmp_path)                                              # folders
    first = run_increment(spark, raw_frame(spark, APRIL), paths, RUN, load_summary_sql())  # run 1: April
    second = run_increment(spark, raw_frame(spark, AUGUST), paths, RUN, load_summary_sql())  # run 2: only August is new
    assert first["source_months"] == ["2008-04"] and second["source_months"] == ["2008-08"]  # each run saw only its input
    assert second["total_silver_clicks"] == 13 and second["total_visits"] == 8  # both months present afterwards
    months = sorted(row.click_month for row in spark.read.parquet(f"{paths.silver}/clicks").select("click_month").distinct().collect())  # partitions
    assert months == ["2008-04", "2008-08"]                             # April kept, August added


def test_rerun_same_month_does_not_duplicate(spark, tmp_path):          # Review Focus 1
    from clickstream_spark.sql_files import load_summary_sql            # SQL texts
    from clickstream_spark.storage import run_increment                 # code under test
    paths = lake(tmp_path)                                              # folders
    run_increment(spark, raw_frame(spark, APRIL), paths, RUN, load_summary_sql())  # first time
    again = run_increment(spark, raw_frame(spark, APRIL), paths, RUN, load_summary_sql())  # same month again (bookmark reset)
    assert again["total_silver_clicks"] == 10                           # replaced, not appended


def test_run_increment_with_no_new_files(spark, tmp_path):              # Review Focus 2
    from clickstream_spark.storage import run_increment                 # code under test
    empty = spark.createDataFrame([], "x string").select()               # what DynamicFrame.toDF() gives when the bookmark finds nothing
    report = run_increment(spark, empty, lake(tmp_path), RUN, {})       # no SQL needed
    assert report == {"status": "no new source files", "source_rows": 0, "source_months": []}  # nothing written


def test_all_rejected_month_still_rebuilds(spark, tmp_path):            # Review Focus 3
    from clickstream_spark.sql_files import load_summary_sql            # SQL texts
    from clickstream_spark.storage import run_increment                 # code under test
    bad = [source_row(1, 1, country=99)]                                 # the only click fails a rule
    report = run_increment(spark, raw_frame(spark, bad), lake(tmp_path), RUN, load_summary_sql())  # must not crash
    assert report["rejected_rows"] == 1 and report["total_silver_clicks"] == 0  # reject recorded, empty Silver read back
