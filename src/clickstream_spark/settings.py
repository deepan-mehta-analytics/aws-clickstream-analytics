"""Spark settings shared by the Glue job and the local tests (one source of truth)."""  # module docstring

SPARK_SETTINGS = {                                                      # runtime SQL settings, applied with spark.conf.set
    "spark.sql.session.timeZone": "UTC",                                # every timestamp is UTC, on the laptop and in Glue
    "spark.sql.ansi.enabled": "true",                                   # Spark 4 default: bad casts and overflows fail loudly
    "spark.sql.sources.partitionOverwriteMode": "dynamic",              # overwrite only the month folders a run writes
    "spark.sql.parquet.outputTimestampType": "TIMESTAMP_MICROS",        # microsecond timestamps that Athena reads natively
    "spark.sql.sources.partitionColumnTypeInference.enabled": "false",  # month partitions stay text ("2008-04"), never dates
}

ICEBERG_VERSION = "1.11.0"                                              # Iceberg release that AWS Glue 6.0 ships
ICEBERG_PACKAGE = f"org.apache.iceberg:iceberg-spark-runtime-4.1_2.13:{ICEBERG_VERSION}"  # Maven jar for Spark 4.1 and Scala 2.13
CATALOG = "glue_catalog"                                                # catalog name in Spark: same in Glue and on the laptop
