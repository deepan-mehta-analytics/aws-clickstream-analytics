"""The Spark pipeline without I/O: one increment (new Bronze rows) and the whole-dataset rebuild."""  # module docstring

from dataclasses import dataclass                                       # result container
from datetime import datetime                                           # times

from pyspark.sql import DataFrame, SparkSession                         # Spark types
from pyspark.sql import functions as F                                  # column functions

from clickstream.enrichment import DEFAULT_SEED                         # default seed (553)
from clickstream_spark.bronze import add_arrival                        # arrival columns
from clickstream_spark.enrichment import add_synthetic_fields_spark     # synthetic columns
from clickstream_spark.gold import build_calendar_days_spark, build_countries_spark, build_devices_spark, build_gold_clicks_spark, build_products_spark, build_visits_spark  # Gold
from clickstream_spark.silver import SparkSilverResult, build_silver_spark  # Silver
from clickstream_spark.source import to_plain_columns                   # source reading
from clickstream_spark.summaries import run_summaries_spark             # summaries


@dataclass
class Increment:                                                        # what one run builds from new Bronze rows
    source_rows: int                                                    # raw rows read
    bronze_rows: int                                                    # rows after arrival columns
    source_months: list[str]                                            # months present in the new rows (bookmark proof)
    silver: SparkSilverResult                                           # clean clicks + rejects
    gold_clicks: DataFrame                                              # click-grain Gold rows for those months
    visits: DataFrame                                                   # visit-grain Gold rows for those months


def build_increment(raw: DataFrame, received_time: datetime, run_time: datetime | None = None, seed: int = DEFAULT_SEED) -> Increment:  # new rows -> Silver and Gold months
    source = to_plain_columns(raw).cache()                              # typed source rows (reused below)
    bronze = add_arrival(add_synthetic_fields_spark(source, seed), received_time).cache()  # enriched rows (the pandas step runs once)
    silver = build_silver_spark(bronze, run_time or received_time)      # rules
    months = sorted(row[0] for row in source.select(F.format_string("%04d-%02d", "year", "month")).distinct().collect())  # e.g. ["2008-08"]
    return Increment(source.count(), bronze.count(), months, silver, build_gold_clicks_spark(silver.clicks), build_visits_spark(silver.clicks))  # everything


def build_whole_dataset(spark: SparkSession, all_clicks: DataFrame, all_visits: DataFrame, sql_texts: dict[str, str]) -> dict[str, DataFrame]:  # tables that depend on every month
    countries = build_countries_spark(spark)                            # static reference
    tables = {                                                          # table path (under gold/) -> DataFrame
        "products": build_products_spark(all_clicks),                   # needs every click
        "countries": countries,                                         # static
        "calendar_days": build_calendar_days_spark(all_clicks),         # needs every date
        "devices": build_devices_spark(spark),                          # static
    }
    for name, frame in run_summaries_spark(spark, all_visits, countries, sql_texts).items():  # dashboard summaries
        tables[f"summaries/{name}"] = frame                             # under gold/summaries/
    return tables                                                       # all whole-dataset tables
