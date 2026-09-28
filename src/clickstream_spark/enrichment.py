"""Synthetic fields in Spark: the tested pandas generator runs per group of whole visits (identical values to the local twin)."""  # module docstring

import pandas as pd                                                     # the batch type applyInPandas hands over
from pyspark.sql import DataFrame                                       # Spark table type
from pyspark.sql import functions as F                                  # column functions
from pyspark.sql.types import StringType, StructField, StructType, TimestampType  # schema types

from clickstream.enrichment import DEFAULT_SEED, add_synthetic_fields   # seeded per-visit generator (NumPy), reused unchanged
from clickstream_spark.source import SOURCE_SCHEMA, TEXT_COLUMNS        # plain columns and types

# ── Why pandas here: NumPy's seeded generator cannot be reproduced with Spark functions,
# and the synthetic values must match the local twin exactly (ADR-0003). Each group holds
# whole visits, and the generator is seeded per visit, so grouping never changes a value.
ENRICHED_SCHEMA = StructType(list(SOURCE_SCHEMA.fields) + [             # source columns + three synthetic ones
    StructField("click_id", StringType(), True),                        # uci553-<visit>-<click>
    StructField("click_time_synthetic", TimestampType(), True),         # UTC
    StructField("device_type_synthetic", StringType(), True),           # desktop / mobile / tablet
])
VISIT_BUCKETS = 64                                                      # groups of whole visits (about 30k visits -> ~500 each)
WHOLE_NUMBER_COLUMNS = [field.name for field in SOURCE_SCHEMA.fields if field.name not in TEXT_COLUMNS]  # bigint columns


def enrich_batch(batch: pd.DataFrame, seed: int = DEFAULT_SEED) -> pd.DataFrame:  # one group of whole visits
    enriched = add_synthetic_fields(batch.drop(columns=["visit_bucket"], errors="ignore"), seed)  # the tested pandas step
    enriched[WHOLE_NUMBER_COLUMNS] = enriched[WHOLE_NUMBER_COLUMNS].astype("Int64")  # nullable integers survive the trip back
    return enriched[ENRICHED_SCHEMA.fieldNames()]                       # exact column order for Spark


def add_synthetic_fields_spark(source: DataFrame, seed: int = DEFAULT_SEED, buckets: int = VISIT_BUCKETS) -> DataFrame:  # enrich every click
    bucketed = source.withColumn("visit_bucket", F.pmod(F.hash(F.col("visit_id")), F.lit(buckets)))  # every click of a visit lands in the same bucket
    return bucketed.groupBy("visit_bucket").applyInPandas(lambda batch: enrich_batch(batch, seed), schema=ENRICHED_SCHEMA)  # pandas per bucket
