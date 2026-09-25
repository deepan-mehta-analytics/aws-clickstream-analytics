# ── Tests: Bronze clicks_received ─────────────────────────────
import pandas as pd                                                     # dataframes
import pytest                                                           # test framework
from conftest import make_source, source_row                            # hand-made rows

from clickstream.bronze import build_bronze                             # code under test
from clickstream.enrichment import add_synthetic_fields                 # upstream step

RECEIVED = pd.Timestamp("2026-09-25 12:00:00", tz="UTC")                # fixed arrival time for tests


def four_clicks():                                                      # two visits of two clicks
    return add_synthetic_fields(make_source([source_row(1, 1), source_row(1, 2), source_row(2, 1), source_row(2, 2)]))  # enriched rows


def test_adds_received_time_and_source():                               # pipeline columns
    bronze = build_bronze(four_clicks(), RECEIVED)                      # build
    assert (bronze["received_time"] == RECEIVED).all()                  # same arrival time
    assert (bronze["data_source"] == "uci553").all()                    # source label


def test_naive_received_time_is_rejected():                             # timezone discipline
    with pytest.raises(ValueError, match="timezone"):                   # must refuse naive times
        build_bronze(four_clicks(), pd.Timestamp("2026-09-25 12:00:00"))  # no tz


def test_resends_append_later_copies():                                 # simulated resends
    bronze = build_bronze(four_clicks(), RECEIVED, resend_every=2)      # every 2nd row resent
    assert len(bronze) == 6                                             # 4 originals + 2 resends
    resent = bronze[bronze["click_id"].duplicated(keep="first")]        # the resent copies
    assert (resent["received_time"] == RECEIVED + pd.Timedelta(seconds=1)).all()  # arrive one second later
