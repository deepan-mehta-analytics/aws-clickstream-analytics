# ── Tests: synthetic enrichment ───────────────────────────────
import pandas as pd                                                     # dataframes
from conftest import make_source, source_row                            # hand-made rows

from clickstream.enrichment import DEVICE_WEIGHTS, SHOP_TIMEZONE, add_synthetic_fields  # code under test


def fifty_visits():                                                     # 50 visits of 3 clicks each
    return make_source([source_row(v, c) for v in range(1, 51) for c in (1, 2, 3)])  # 150 rows


def test_same_seed_gives_identical_values():                            # repeatability
    first = add_synthetic_fields(fifty_visits(), seed=553)              # run once
    second = add_synthetic_fields(fifty_visits(), seed=553)             # run again
    pd.testing.assert_frame_equal(first, second)                        # byte-identical frames


def test_different_seed_changes_times():                                # the seed matters
    first = add_synthetic_fields(fifty_visits(), seed=553)              # seed 553
    other = add_synthetic_fields(fifty_visits(), seed=554)              # seed 554
    assert not first["click_time_synthetic"].equals(other["click_time_synthetic"])  # times differ


def test_long_visit_stays_inside_its_real_date():                       # Review Focus 2
    source = make_source([source_row(9, c, day=13, month=8) for c in range(1, 196)])  # 195-click visit on 2008-08-13
    enriched = add_synthetic_fields(source)                             # enrich it
    local_days = enriched["click_time_synthetic"].dt.tz_convert(SHOP_TIMEZONE).dt.date  # shop-local dates
    assert set(local_days) == {pd.Timestamp("2008-08-13").date()}       # never spills into another day
    assert enriched["click_time_synthetic"].is_monotonic_increasing     # clicks follow in order


def test_times_are_utc_and_gaps_are_5_to_300_seconds():                 # documented gap range and UTC storage
    enriched = add_synthetic_fields(fifty_visits())                     # enrich
    assert str(enriched["click_time_synthetic"].dt.tz) == "UTC"         # stored in UTC
    gaps = enriched.groupby("visit_id")["click_time_synthetic"].diff().dropna().dt.total_seconds()  # seconds between clicks
    assert gaps.between(5, 300).all()                                   # all inside the documented range


def test_one_device_per_visit_from_known_list():                        # device rules
    enriched = add_synthetic_fields(fifty_visits())                     # enrich
    assert (enriched.groupby("visit_id")["device_type_synthetic"].nunique() == 1).all()  # constant within a visit
    assert set(enriched["device_type_synthetic"]) <= set(DEVICE_WEIGHTS)  # only known device types


def test_click_id_is_built_from_visit_and_click_number():               # deterministic id
    enriched = add_synthetic_fields(make_source([source_row(7, 1)]))    # one click
    assert enriched.loc[0, "click_id"] == "uci553-7-1"                  # documented format


def test_empty_input_returns_empty_frame_with_new_columns():            # empty source
    enriched = add_synthetic_fields(make_source([]))                    # no rows
    assert enriched.empty                                               # still empty
    assert {"click_id", "click_time_synthetic", "device_type_synthetic"} <= set(enriched.columns)  # columns exist
    assert str(enriched["click_time_synthetic"].dtype) == "datetime64[ns, UTC]"  # correct type even when empty


def test_shop_time_to_utc_handles_dst_edges():                          # T1-prep: DST-safe localisation
    from clickstream.enrichment import shop_time_to_utc                 # code under test
    local = pd.Series(pd.to_datetime(["2008-03-30 02:30:00", "2008-10-26 02:30:00"]))  # a missing hour and an ambiguous hour in Warsaw
    utc = shop_time_to_utc(local)                                       # must not raise
    assert list(utc.dt.strftime("%Y-%m-%d %H:%M")) == ["2008-03-30 01:00", "2008-10-26 01:30"]  # shifted forward; ambiguous read as standard time (CET, UTC+1)


def test_shop_time_to_utc_keeps_missing_times_missing():                # NaT mixed with real values stays NaT
    from clickstream.enrichment import shop_time_to_utc                 # code under test
    local = pd.Series(pd.to_datetime(["2008-04-01 10:00:00", None, "2008-03-30 02:30:00"]))  # a normal time, a missing time, a DST-gap time
    utc = shop_time_to_utc(local)                                       # must not raise
    assert utc.isna().tolist() == [False, True, False]                  # only the missing row is NaT
    assert utc.iloc[0] == pd.Timestamp("2008-04-01 08:00:00", tz="UTC")  # April is summer time (UTC+2)
    assert utc.iloc[2] == pd.Timestamp("2008-03-30 01:00:00", tz="UTC")  # the gap shifts forward to 03:00 local = 01:00 UTC
