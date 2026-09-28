# ── Tests: summaries, quality counts and the assembled pipeline ─
import pandas as pd                                                     # comparisons

from spark_helpers import raw_frame, sorted_pandas                      # Spark helpers
from test_spark_silver import RECEIVED, edge_rows, pandas_silver        # shared sample

KEYS = {"daily_visits": ["visit_date"], "visit_depth_funnel": ["shop_page"], "bounce_rate_by_product": ["product_code"], "visits_by_country_and_device": ["country_code", "device_type_synthetic"]}  # sort keys per summary


def test_summary_names_match_pandas():                                  # one list, two engines
    from clickstream.summaries import SUMMARY_NAMES as pandas_names     # pandas list
    from clickstream_spark.sql_files import SUMMARY_NAMES, load_summary_sql  # Spark list and loader
    assert SUMMARY_NAMES == pandas_names                                # kept in step
    assert sorted(load_summary_sql()) == sorted(SUMMARY_NAMES)          # every file found in the repo


def test_summaries_match_duckdb(spark):                                 # same SQL, same answers
    from clickstream.gold import build_countries, build_visits          # pandas Gold
    from clickstream.summaries import run_summaries                     # DuckDB reference
    from clickstream_spark.gold import build_countries_spark            # Spark countries
    from clickstream_spark.sql_files import load_summary_sql            # SQL texts
    from clickstream_spark.summaries import run_summaries_spark         # code under test
    visits = build_visits(pandas_silver(edge_rows()).clicks)            # pandas visits
    expected = run_summaries({"visits": visits, "countries": build_countries()})  # DuckDB results
    actual = run_summaries_spark(spark, spark.createDataFrame(visits), build_countries_spark(spark), load_summary_sql())  # Spark results
    for name, keys in KEYS.items():                                     # each summary
        pd.testing.assert_frame_equal(sorted_pandas(actual[name], keys), sorted_pandas(expected[name], keys), check_dtype=False)  # same rows and values


def test_quality_counts_match_pandas_report(spark):                     # same report keys and numbers
    from clickstream.gold import build_products, build_visits, category_mismatches  # pandas Gold
    from clickstream.quality import build_quality_report                # pandas report
    from clickstream_spark.pipeline import build_increment              # code under test
    from clickstream_spark.gold import build_products_spark             # Spark products
    from clickstream_spark.quality import build_quality_counts, category_mismatches_spark  # code under test
    rows = edge_rows()                                                  # sample
    silver = pandas_silver(rows)                                        # pandas Silver
    visits = build_visits(silver.clicks)                                # pandas visits
    expected = build_quality_report(len(rows), len(rows), silver, visits, category_mismatches(silver.clicks, build_products(silver.clicks)))  # pandas report
    increment = build_increment(raw_frame(spark, rows), RECEIVED)       # Spark pipeline
    mismatches = category_mismatches_spark(increment.silver.clicks, build_products_spark(increment.silver.clicks))  # Spark mismatches
    actual = build_quality_counts(increment.source_rows, increment.bronze_rows, increment.silver, increment.visits, mismatches)  # Spark report
    assert actual == expected                                           # identical dict
    assert increment.source_months == ["2008-04", "2008-05"]            # months in this sample


def test_whole_dataset_tables(spark):                                   # everything rebuilt from all of Silver
    from clickstream_spark.pipeline import build_increment, build_whole_dataset  # code under test
    from clickstream_spark.sql_files import load_summary_sql            # SQL texts
    increment = build_increment(raw_frame(spark, edge_rows()), RECEIVED)  # one run
    tables = build_whole_dataset(spark, increment.silver.clicks, increment.visits, load_summary_sql())  # rebuild
    assert sorted(tables) == ["calendar_days", "countries", "devices", "products", "summaries/bounce_rate_by_product", "summaries/daily_visits", "summaries/visit_depth_funnel", "summaries/visits_by_country_and_device"]  # all tables
    assert dict(tables["summaries/daily_visits"].dtypes)["bounce_rate"] == "double"  # Athena-friendly type
