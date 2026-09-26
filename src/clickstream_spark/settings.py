"""Spark settings shared by the Glue job and the local tests (one source of truth)."""  # module docstring

SPARK_SETTINGS = {                                                      # runtime SQL settings, applied with spark.conf.set
    "spark.sql.session.timeZone": "UTC",                                # every timestamp is UTC, on the laptop and in Glue
    "spark.sql.ansi.enabled": "true",                                   # Spark 4 default: bad casts and overflows fail loudly
    "spark.sql.sources.partitionOverwriteMode": "dynamic",              # overwrite only the month folders a run writes
    "spark.sql.parquet.outputTimestampType": "TIMESTAMP_MICROS",        # microsecond timestamps that Athena reads natively
    "spark.sql.sources.partitionColumnTypeInference.enabled": "false",  # month partitions stay text ("2008-04"), never dates
}
