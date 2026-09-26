# ── Tests: local Spark session matches the Glue settings ──────
from clickstream_spark.settings import SPARK_SETTINGS                   # the shared settings


def test_spark_session_uses_glue_settings(spark):                      # fixture from conftest.py
    for key, value in SPARK_SETTINGS.items():                           # every shared setting
        assert spark.conf.get(key) == value, key                        # applied to the test session


def test_raw_frame_uses_source_names_and_text(spark):                  # helper mirrors Glue's CSV read
    from conftest import source_row                                     # hand-made click
    from spark_helpers import raw_frame                                 # helper under test
    frame = raw_frame(spark, [source_row(1, 1)])                         # one raw row
    assert "session ID" in frame.columns                                # source column names kept
    assert dict(frame.dtypes)["price"] == "string"                      # every value is text, like a CSV
