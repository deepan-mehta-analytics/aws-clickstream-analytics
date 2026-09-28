# ── Tests: Spark Gold equals pandas Gold ──────────────────────
import pandas as pd                                                     # comparisons

from spark_helpers import sorted_pandas                                 # normalise and sort
from test_spark_silver import edge_rows, pandas_silver, spark_silver    # same sample and both Silvers


def both(spark):                                                        # pandas and Spark Silver clicks
    return pandas_silver(edge_rows()).clicks, spark_silver(spark, edge_rows()).clicks  # (pandas, spark)


def test_visits_match_pandas(spark):                                    # visit grain
    from clickstream.gold import build_visits                           # pandas reference
    from clickstream_spark.gold import build_visits_spark               # code under test
    expected_clicks, spark_clicks = both(spark)                         # inputs
    pd.testing.assert_frame_equal(sorted_pandas(build_visits_spark(spark_clicks), ["visit_id"]), sorted_pandas(build_visits(expected_clicks), ["visit_id"]))  # identical


def test_gold_clicks_match_pandas(spark):                               # click grain
    from clickstream.gold import build_gold_clicks                      # pandas reference
    from clickstream_spark.gold import build_gold_clicks_spark          # code under test
    expected_clicks, spark_clicks = both(spark)                         # inputs
    pd.testing.assert_frame_equal(sorted_pandas(build_gold_clicks_spark(spark_clicks), ["click_id"]), sorted_pandas(build_gold_clicks(expected_clicks), ["click_id"]))  # identical


def test_products_match_pandas_including_most_common_category(spark):   # product attributes
    from clickstream.gold import build_products                         # pandas reference
    from clickstream_spark.gold import build_products_spark             # code under test
    expected_clicks, spark_clicks = both(spark)                         # inputs
    pd.testing.assert_frame_equal(sorted_pandas(build_products_spark(spark_clicks), ["product_code"]), sorted_pandas(build_products(expected_clicks), ["product_code"]))  # identical


def test_calendar_days_match_pandas(spark):                             # date attributes
    from clickstream.gold import build_calendar_days                    # pandas reference
    from clickstream_spark.gold import build_calendar_days_spark        # code under test
    expected_clicks, spark_clicks = both(spark)                         # inputs
    pd.testing.assert_frame_equal(sorted_pandas(build_calendar_days_spark(spark_clicks), ["calendar_date"]), sorted_pandas(build_calendar_days(expected_clicks), ["calendar_date"]))  # identical


def test_static_reference_tables_match_pandas(spark):                   # countries and devices
    from clickstream.gold import build_countries, build_devices         # pandas reference
    from clickstream_spark.gold import build_countries_spark, build_devices_spark  # code under test
    pd.testing.assert_frame_equal(sorted_pandas(build_countries_spark(spark), ["country_code"]), sorted_pandas(build_countries(), ["country_code"]))  # 47 rows
    pd.testing.assert_frame_equal(sorted_pandas(build_devices_spark(spark), ["device_type"]), sorted_pandas(build_devices(), ["device_type"]))  # 3 rows
