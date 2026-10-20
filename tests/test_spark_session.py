# ── Tests: local Spark session matches the Glue settings ──────
import os                                                               # platform check

import pytest                                                           # skips

from clickstream_spark.settings import ICEBERG_PACKAGE, ICEBERG_VERSION, SPARK_SETTINGS  # the shared settings


def test_iceberg_version_matches_glue_6():                              # Glue 6.0 ships Iceberg 1.11.0 for Spark 4.1
    assert ICEBERG_VERSION == "1.11.0"                                  # the version Glue 6.0 uses
    assert ICEBERG_PACKAGE.endswith(":1.11.0")                          # the jar pins that same version
    assert "4.1_2.13" in ICEBERG_PACKAGE                                # built for Spark 4.1 and Scala 2.13


@pytest.mark.skipif(os.name == "nt", reason="Spark Parquet writes on Windows need winutils; runs in CI")  # Linux only
def test_local_session_has_the_iceberg_catalog(spark):                  # same catalog name as Glue
    assert spark.conf.get("spark.sql.catalog.glue_catalog") == "org.apache.iceberg.spark.SparkCatalog"  # Iceberg catalog class
    assert "IcebergSparkSessionExtensions" in spark.conf.get("spark.sql.extensions")  # Iceberg SQL extensions loaded


def test_spark_session_uses_glue_settings(spark):                      # fixture from conftest.py
    for key, value in SPARK_SETTINGS.items():                           # every shared setting
        assert spark.conf.get(key) == value, key                        # applied to the test session


def test_raw_frame_uses_source_names_and_text(spark):                  # helper mirrors Glue's CSV read
    from conftest import source_row                                     # hand-made click
    from spark_helpers import raw_frame                                 # helper under test
    frame = raw_frame(spark, [source_row(1, 1)])                         # one raw row
    assert "session ID" in frame.columns                                # source column names kept
    assert dict(frame.dtypes)["price"] == "string"                      # every value is text, like a CSV
