# ── Tests: Spark source reading, enrichment, arrival columns ──
from datetime import datetime, timezone                                 # arrival time

import pandas as pd                                                     # expected values
import pytest                                                           # test framework

from conftest import make_source, source_row                            # hand-made clicks
from spark_helpers import raw_frame, sorted_pandas, text_of             # Spark helpers

RECEIVED = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)             # fixed arrival time


def test_to_plain_columns_renames_and_types(spark):                     # source names -> plain names
    from clickstream_spark.source import SOURCE_SCHEMA, to_plain_columns  # code under test
    frame = to_plain_columns(raw_frame(spark, [source_row(7, 1)]))      # one row
    assert frame.schema == SOURCE_SCHEMA                                # names and types exactly
    row = frame.first()                                                 # the row
    assert (row.visit_id, row.product_code, row.price_usd) == (7, "A13", 28)  # values converted


def test_to_plain_columns_turns_bad_numbers_into_nulls(spark):          # Review Focus 4
    from clickstream_spark.source import to_plain_columns               # code under test
    bad = source_row(7, 1)                                              # start from a good row
    bad["price_usd"] = "twenty"                                         # not a number
    assert to_plain_columns(raw_frame(spark, [bad])).first().price_usd is None  # NULL, not an ANSI crash


def test_to_plain_columns_rejects_wrong_file(spark):                    # wrong delimiter or file
    from clickstream_spark.source import SourceColumnsError, to_plain_columns  # code under test
    with pytest.raises(SourceColumnsError, match="missing columns"):    # clear failure
        to_plain_columns(spark.createDataFrame([("a",)], ["only_column"]))  # nothing expected


def test_spark_enrichment_matches_pandas_exactly(spark):                # same seeded values as the local twin
    from clickstream.enrichment import add_synthetic_fields             # pandas reference
    from clickstream_spark.enrichment import add_synthetic_fields_spark  # code under test
    from clickstream_spark.source import to_plain_columns               # upstream step
    rows = [source_row(visit, click, day=1 + visit % 20) for visit in range(1, 40) for click in range(1, 1 + visit % 4 + 1)]  # 39 visits of 1-4 clicks
    expected = add_synthetic_fields(make_source(rows))[["click_id", "click_time_synthetic", "device_type_synthetic"]]  # pandas values
    actual = add_synthetic_fields_spark(to_plain_columns(raw_frame(spark, rows))).select("click_id", "click_time_synthetic", "device_type_synthetic")  # Spark values
    pd.testing.assert_frame_equal(sorted_pandas(actual, ["click_id"]), sorted_pandas(expected, ["click_id"]))  # identical


def test_add_arrival_adds_time_and_source(spark):                       # Bronze-equivalent columns
    from clickstream_spark.bronze import BRONZE_COLUMNS, add_arrival    # code under test
    from clickstream_spark.enrichment import add_synthetic_fields_spark  # upstream step
    from clickstream_spark.source import to_plain_columns               # upstream step
    frame = add_arrival(add_synthetic_fields_spark(to_plain_columns(raw_frame(spark, [source_row(1, 1)]))), RECEIVED)  # one row
    assert frame.columns == BRONZE_COLUMNS                              # exact order
    assert frame.first().data_source == "uci553"                        # source label
    assert text_of(frame, "received_time") == "2026-09-26 12:00"        # arrival time in UTC (formatted inside Spark)


def test_add_arrival_requires_timezone(spark):                          # same guard as the pandas Bronze
    from clickstream_spark.bronze import add_arrival                    # code under test
    with pytest.raises(ValueError, match="timezone"):                   # clear failure
        add_arrival(None, datetime(2026, 9, 26, 12, 0))                  # naive time
