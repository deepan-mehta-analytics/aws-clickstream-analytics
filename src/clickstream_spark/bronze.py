"""Arrival columns in Spark: what the pandas Bronze step adds (clicks_received), without resends."""  # module docstring

from datetime import datetime, timezone                                 # arrival time

from pyspark.sql import DataFrame                                       # Spark table type
from pyspark.sql import functions as F                                  # column functions

from clickstream.bronze import DATA_SOURCE                              # "uci553", shared with pandas
from clickstream_spark.enrichment import ENRICHED_SCHEMA                # columns before arrival

BRONZE_COLUMNS = ENRICHED_SCHEMA.fieldNames() + ["received_time", "data_source"]  # clicks_received column order


def add_arrival(enriched: DataFrame, received_time: datetime) -> DataFrame:  # add arrival time and source label
    if received_time.tzinfo is None:                                    # arrival times must carry a timezone
        raise ValueError("received_time must have a timezone (use UTC)")  # same rule as the pandas Bronze
    arrival = F.lit(received_time.astimezone(timezone.utc)).cast("timestamp")  # UTC instant
    return enriched.withColumn("received_time", arrival).withColumn("data_source", F.lit(DATA_SOURCE)).select(BRONZE_COLUMNS)  # exact order
