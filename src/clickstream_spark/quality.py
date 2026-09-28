"""Quality counts in Spark: the same keys and meaning as clickstream.quality.build_quality_report."""  # module docstring

from pyspark.sql import DataFrame                                       # Spark table type
from pyspark.sql import functions as F                                  # column functions

from clickstream_spark.silver import SparkSilverResult                  # Silver output type


def category_mismatches_spark(clicks: DataFrame, products: DataFrame) -> DataFrame:  # clicks whose category differs from the product's
    joined = clicks.join(products.select("product_code", F.col("category").alias("product_category")), "product_code")  # attach product category
    return joined.filter(F.col("category") != F.col("product_category")).select(  # disagreements
        "click_id", "product_code", F.col("category").alias("click_category"), "product_category")  # report columns


def build_quality_counts(source_rows: int, bronze_rows: int, silver: SparkSilverResult, visits: DataFrame, mismatches: DataFrame) -> dict:  # JSON-ready dict
    reasons = {row["rejection_reason"]: row["count"] for row in silver.rejected.groupBy("rejection_reason").count().collect()}  # rejects per reason
    return {                                                            # same keys as the pandas report
        "source_rows": int(source_rows),                                # rows read from the source
        "bronze_rows": int(bronze_rows),                                # rows received, including resends
        "duplicates_removed": int(silver.duplicates_removed),           # resends dropped
        "rejected_rows": int(sum(reasons.values())),                    # rows that failed a hard rule
        "rejections_by_reason": {str(reason): int(count) for reason, count in sorted(reasons.items(), key=lambda item: -item[1])},  # biggest first, like value_counts
        "silver_clicks": int(silver.clicks.count()),                    # clean clicks
        "visits": int(visits.count()),                                  # visits built
        "one_click_visits": int(visits.filter(F.col("bounced")).count()),  # bounces
        "category_mismatches": [row.asDict() for row in mismatches.orderBy("click_id").collect()],  # reported, not rejected
    }
