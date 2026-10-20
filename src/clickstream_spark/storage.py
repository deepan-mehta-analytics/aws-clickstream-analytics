"""Write one increment to the lake (Silver Iceberg tables, Gold month folders) and rebuild the whole-dataset tables."""  # module docstring

from dataclasses import dataclass                                       # paths container
from datetime import datetime                                           # run time

from pyspark.sql import DataFrame, SparkSession                         # Spark types

from clickstream_spark.gold import build_products_spark                 # products for the mismatch report
from clickstream_spark.iceberg_tables import ALLOWED_FORMAT_VERSION, SilverTables, check_format_version, deleted_visit_ids, remove_deleted_visits, write_months_to_table  # Silver Iceberg
from clickstream_spark.pipeline import build_increment, build_whole_dataset  # I/O-free steps
from clickstream_spark.quality import build_quality_counts, category_mismatches_spark  # report
from clickstream_spark.silver import SparkSilverResult, add_weekend_click_spark  # Silver result type, weekend_click column


@dataclass(frozen=True)
class LakePaths:                                                        # where the Parquet layer lives (Silver is in Iceberg tables now)
    gold: str                                                           # e.g. s3://<gold bucket> (no trailing slash)


def write_months(frame: DataFrame, path: str, month_column: str) -> None:  # month-partitioned Parquet table (Gold)
    frame.write.mode("overwrite").partitionBy(month_column).parquet(path)  # dynamic overwrite: only these months are replaced


def write_whole(frame: DataFrame, path: str) -> None:                   # small table rebuilt every run
    frame.coalesce(1).write.mode("overwrite").parquet(path)             # one file, fully replaced


def run_increment(spark: SparkSession, raw: DataFrame, paths: LakePaths, tables: SilverTables, run_time: datetime, sql_texts: dict[str, str]) -> dict:  # one Glue run
    if not raw.columns or raw.isEmpty():                                # the bookmark found no new files
        return {"status": "no new source files", "source_rows": 0, "source_months": []}  # nothing to write

    # ── Guard: every Silver table must be Iceberg format version 2 before anything is built or written ─
    format_versions = {}                                                # table -> checked version
    for table in (tables.clicks, tables.rejected, tables.deleted_visits):  # all three Silver tables
        check_format_version(spark, table)                              # raises FormatVersionError otherwise
        format_versions[table] = ALLOWED_FORMAT_VERSION                 # passed the check

    # ── Build, then drop deleted visits (after enrichment, so other visits' seeded values cannot shift) ─
    increment = build_increment(raw, run_time)                          # new months -> Silver and Gold
    deleted = deleted_visit_ids(spark, tables).cache()                  # the deleted-visits list, read once
    clicks = remove_deleted_visits(increment.silver.clicks, deleted).cache()  # Silver clicks without deleted visits
    rejected = remove_deleted_visits(increment.silver.rejected, deleted).cache()  # Silver rejects without deleted visits
    gold_clicks = remove_deleted_visits(increment.gold_clicks, deleted)  # Gold clicks without deleted visits
    visits = remove_deleted_visits(increment.visits, deleted)           # Gold visits without deleted visits
    removed = (increment.silver.clicks.count() - clicks.count()) + (increment.silver.rejected.count() - rejected.count())  # Silver click rows + reject rows removed this run
    silver = SparkSilverResult(clicks, rejected, increment.silver.duplicates_removed)  # filtered Silver for the report

    # ── Write: Silver into Iceberg (table's columns only), Gold months as Parquet ─
    write_months_to_table(spark, add_weekend_click_spark(clicks), tables.clicks)  # weekend_click is written only once the table has it
    write_months_to_table(spark, rejected, tables.rejected)             # Silver rejects
    write_months(gold_clicks, f"{paths.gold}/clicks", "click_month")    # Gold clicks
    write_months(visits, f"{paths.gold}/visits", "visit_month")         # Gold visits

    # ── Whole-dataset Gold and the report ─
    all_clicks = spark.table(tables.clicks)                             # every month, from the Iceberg table
    all_visits = spark.read.schema(increment.visits.schema).parquet(f"{paths.gold}/visits")  # every month, explicit schema
    for name, frame in build_whole_dataset(spark, all_clicks, all_visits, sql_texts).items():  # products, calendar, summaries...
        write_whole(frame, f"{paths.gold}/{name}")                      # fully replaced
    mismatches = category_mismatches_spark(clicks, build_products_spark(all_clicks))  # this run's clicks vs all-data products
    report = build_quality_counts(increment.source_rows, increment.bronze_rows, silver, visits, mismatches)  # counts for this run
    report.update({"status": "ok", "source_months": increment.source_months, "total_silver_clicks": all_clicks.count(), "total_visits": all_visits.count()})  # plus totals
    report.update({"deleted_visits_removed": int(removed), "format_versions": format_versions})  # deletion filter and guard results
    return report                                                       # saved by the Glue entry point
