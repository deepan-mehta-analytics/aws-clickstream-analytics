"""Run the same dashboard SQL files in Spark that DuckDB runs locally."""  # module docstring

from pyspark.sql import DataFrame, SparkSession                         # Spark types
from pyspark.sql import functions as F                                  # column functions

from clickstream_spark.sql_files import SUMMARY_NAMES                   # summary list


def _standard(frame: DataFrame, column: str):                           # one column with Athena-friendly types
    kind = dict(frame.dtypes)[column]                                   # Spark type name
    if kind.startswith("decimal") or kind == "float":                   # ROUND(...) gives decimals
        return F.col(column).cast("double").alias(column)               # declare as double in the Catalog
    if kind in ("int", "smallint", "tinyint"):                          # literals like "SELECT 1 AS shop_page"
        return F.col(column).cast("long").alias(column)                 # declare as bigint in the Catalog
    return F.col(column)                                                # unchanged


def run_summaries_spark(spark: SparkSession, visits: DataFrame, countries: DataFrame, sql_texts: dict[str, str]) -> dict[str, DataFrame]:  # every summary
    visits.createOrReplaceTempView("visits")                            # the SQL reads "visits"
    countries.createOrReplaceTempView("countries")                      # and "countries"
    results = {}                                                        # name -> DataFrame
    for name in SUMMARY_NAMES:                                          # fixed order
        frame = spark.sql(sql_texts[name])                              # same text as DuckDB runs
        results[name] = frame.select([_standard(frame, column) for column in frame.columns])  # stable types
    return results                                                      # all four
