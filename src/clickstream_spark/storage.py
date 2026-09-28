"""Write one increment to the lake (month folders) and rebuild the whole-dataset tables."""  # module docstring

from dataclasses import dataclass                                       # paths container
from datetime import datetime                                           # run time

from pyspark.sql import DataFrame, SparkSession                         # Spark types

from clickstream_spark.gold import build_products_spark                 # products for the mismatch report
from clickstream_spark.pipeline import build_increment, build_whole_dataset  # I/O-free steps
from clickstream_spark.quality import build_quality_counts, category_mismatches_spark  # report


@dataclass(frozen=True)
class LakePaths:                                                        # where each layer lives
    silver: str                                                         # e.g. s3://<silver bucket> (no trailing slash)
    gold: str                                                           # e.g. s3://<gold bucket>


def write_months(frame: DataFrame, path: str, month_column: str) -> None:  # month-partitioned table
    frame.write.mode("overwrite").partitionBy(month_column).parquet(path)  # dynamic overwrite: only these months are replaced


def write_whole(frame: DataFrame, path: str) -> None:                   # small table rebuilt every run
    frame.coalesce(1).write.mode("overwrite").parquet(path)             # one file, fully replaced


def run_increment(spark: SparkSession, raw: DataFrame, paths: LakePaths, run_time: datetime, sql_texts: dict[str, str]) -> dict:  # one Glue run
    if not raw.columns or raw.isEmpty():                                # the bookmark found no new files
        return {"status": "no new source files", "source_rows": 0, "source_months": []}  # nothing to write
    increment = build_increment(raw, run_time)                          # new months -> Silver and Gold
    write_months(increment.silver.clicks, f"{paths.silver}/clicks", "click_month")  # Silver clicks
    write_months(increment.silver.rejected, f"{paths.silver}/clicks_rejected", "source_month")  # Silver rejects
    write_months(increment.gold_clicks, f"{paths.gold}/clicks", "click_month")  # Gold clicks
    write_months(increment.visits, f"{paths.gold}/visits", "visit_month")  # Gold visits
    all_clicks = spark.read.schema(increment.silver.clicks.schema).parquet(f"{paths.silver}/clicks")  # every month, explicit schema (works even if empty)
    all_visits = spark.read.schema(increment.visits.schema).parquet(f"{paths.gold}/visits")  # every month, explicit schema
    for name, frame in build_whole_dataset(spark, all_clicks, all_visits, sql_texts).items():  # products, calendar, summaries...
        write_whole(frame, f"{paths.gold}/{name}")                      # fully replaced
    mismatches = category_mismatches_spark(increment.silver.clicks, build_products_spark(all_clicks))  # this run's clicks vs all-data products
    report = build_quality_counts(increment.source_rows, increment.bronze_rows, increment.silver, increment.visits, mismatches)  # counts for this run
    report.update({"status": "ok", "source_months": increment.source_months, "total_silver_clicks": all_clicks.count(), "total_visits": all_visits.count()})  # plus totals
    return report                                                       # saved by the Glue entry point
