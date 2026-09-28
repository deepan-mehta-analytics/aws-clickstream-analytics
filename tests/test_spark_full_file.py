# ── Full-file parity: pandas and Spark on all 165,474 real clicks ─
from datetime import datetime, timezone                                 # times
from pathlib import Path                                                # file paths

import pandas as pd                                                     # pandas reference
import pytest                                                           # test framework

from spark_helpers import sorted_pandas                                 # normalise and sort

SOURCE = Path(__file__).resolve().parents[1] / "data" / "e-shop clothing 2008.csv"  # real UCI file
RECEIVED = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)             # fixed arrival time

pytestmark = [pytest.mark.full_file, pytest.mark.skipif(not SOURCE.exists(), reason="UCI file not downloaded; see data/README.md")]  # CI downloads it


def test_full_file_parity(spark):                                       # every Silver and Gold table identical
    from clickstream.bronze import build_bronze                         # pandas Bronze
    from clickstream.enrichment import add_synthetic_fields             # pandas enrichment
    from clickstream.gold import build_visits                           # pandas visits
    from clickstream.silver import build_silver                         # pandas Silver
    from clickstream.source_file import read_source_clicks              # pandas reader
    from clickstream_spark.pipeline import build_increment              # code under test
    silver = build_silver(build_bronze(add_synthetic_fields(read_source_clicks(SOURCE)), pd.Timestamp(RECEIVED)), pd.Timestamp(RECEIVED))  # pandas run
    raw = spark.read.option("header", True).option("sep", ";").csv(str(SOURCE))  # all text, like Glue's CSV read
    increment = build_increment(raw, RECEIVED)                          # Spark run
    assert increment.source_rows == 165_474 and increment.silver.clicks.count() == 165_474  # measured row count, nothing rejected
    assert increment.source_months == ["2008-04", "2008-05", "2008-06", "2008-07", "2008-08"]  # all five months
    pd.testing.assert_frame_equal(sorted_pandas(increment.silver.clicks, ["click_id"]), sorted_pandas(silver.clicks, ["click_id"]))  # Silver identical
    pd.testing.assert_frame_equal(sorted_pandas(increment.visits, ["visit_id"]), sorted_pandas(build_visits(silver.clicks), ["visit_id"]))  # visits identical
