# ── Tests: Spark Silver equals pandas Silver ──────────────────
from datetime import datetime, timezone                                 # times

import pandas as pd                                                     # expected values

from conftest import make_source, source_row                            # hand-made clicks
from spark_helpers import raw_frame, sorted_pandas, text_of             # Spark helpers

RECEIVED = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)             # arrival time
RUN = datetime(2026, 9, 26, 12, 5, tzinfo=timezone.utc)                  # run time


def edge_rows():                                                        # every rule exercised at least once
    rows = [source_row(1, 1), source_row(1, 2, product_code="B4", category_code=2, page=3)]  # clean two-click visit
    rows += [source_row(2, 1)]                                          # clean one-click visit (bounce)
    rows += [source_row(3, 1, day=31)]                                  # April 31 does not exist -> invalid real date
    rows += [source_row(4, 1, country=48)]                              # country outside 1-47
    rows += [source_row(5, 1), source_row(5, 3)]                        # click numbers 1,3 -> not contiguous
    rows += [source_row(6, 1), source_row(6, 2, category_code=9)]       # one bad click -> whole visit rejected
    missing = source_row(7, 1)                                          # missing product
    missing["product_code"] = None                                      # empty field
    rows += [missing]                                                   # -> missing required field
    rows += [source_row(8, n, day=2, month=5) for n in range(1, 4)]     # clean May visit
    return rows                                                         # 12 clicks


def pandas_silver(rows):                                                # the reference result
    from clickstream.bronze import build_bronze                         # pandas Bronze
    from clickstream.enrichment import add_synthetic_fields             # pandas enrichment
    from clickstream.silver import build_silver                         # pandas Silver
    return build_silver(build_bronze(add_synthetic_fields(make_source(rows)), pd.Timestamp(RECEIVED)), pd.Timestamp(RUN))  # run it


def spark_silver(spark, rows):                                          # the Spark result
    from clickstream_spark.bronze import add_arrival                    # Spark Bronze columns
    from clickstream_spark.enrichment import add_synthetic_fields_spark  # Spark enrichment
    from clickstream_spark.silver import build_silver_spark             # code under test
    from clickstream_spark.source import to_plain_columns                # Spark source
    return build_silver_spark(add_arrival(add_synthetic_fields_spark(to_plain_columns(raw_frame(spark, rows))), RECEIVED), RUN)  # run it


def test_silver_clicks_match_pandas(spark):                             # clean rows identical
    from clickstream.silver import SILVER_COLUMNS                       # expected columns
    expected, actual = pandas_silver(edge_rows()), spark_silver(spark, edge_rows())  # both engines
    assert actual.clicks.columns == SILVER_COLUMNS                      # same columns, same order
    pd.testing.assert_frame_equal(sorted_pandas(actual.clicks, ["click_id"]), sorted_pandas(expected.clicks, ["click_id"]))  # same values


def test_rejected_rows_and_reasons_match_pandas(spark):                 # rejects identical
    expected, actual = pandas_silver(edge_rows()), spark_silver(spark, edge_rows())  # both engines
    columns = ["click_id", "rejection_reason"]                          # what matters
    pd.testing.assert_frame_equal(sorted_pandas(actual.rejected.select(columns), ["click_id"]), sorted_pandas(expected.rejected[columns], ["click_id"]))  # same rows, same reasons
    assert actual.duplicates_removed == expected.duplicates_removed == 0  # no resends here


def test_rejected_rows_carry_run_time_and_source_month(spark):          # partition value always present
    rejected = spark_silver(spark, edge_rows()).rejected                # Spark rejects
    assert {row.source_month for row in rejected.select("source_month").collect()} == {"2008-04"}  # every reject in this sample is April
    assert {row[0] for row in rejected.selectExpr("date_format(rejected_time, 'yyyy-MM-dd HH:mm')").collect()} == {"2026-09-26 12:05"}  # run time, UTC


def test_duplicates_keep_earliest_copy(spark):                          # resend handling
    from pyspark.sql import functions as F                              # column functions

    from clickstream_spark.bronze import add_arrival                    # Spark Bronze columns
    from clickstream_spark.enrichment import add_synthetic_fields_spark  # Spark enrichment
    from clickstream_spark.silver import build_silver_spark             # code under test
    from clickstream_spark.source import to_plain_columns                # Spark source
    once = add_arrival(add_synthetic_fields_spark(to_plain_columns(raw_frame(spark, [source_row(1, 1)]))), RECEIVED)  # original
    resent = once.withColumn("received_time", F.col("received_time") + F.expr("INTERVAL 1 SECOND"))  # resend, 1 s later
    result = build_silver_spark(once.unionByName(resent), RUN)           # both copies
    assert result.duplicates_removed == 1 and result.clicks.count() == 1  # one kept
    assert text_of(result.clicks, "received_time", "yyyy-MM-dd HH:mm:ss") == "2026-09-26 12:00:00"  # the earliest copy
