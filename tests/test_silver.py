# ── Tests: Silver clicks, quality rules and rejects ───────────
import pandas as pd                                                     # dataframes
from conftest import make_source, source_row                            # hand-made rows

from clickstream.bronze import build_bronze                             # upstream step
from clickstream.enrichment import add_synthetic_fields                 # upstream step
from clickstream.silver import SILVER_COLUMNS, build_silver              # code under test

RECEIVED = pd.Timestamp("2026-09-25 12:00:00", tz="UTC")                # fixed arrival time


def bronze_from(rows, resend_every=0):                                  # helper: rows -> Bronze
    return build_bronze(add_synthetic_fields(make_source(rows)), RECEIVED, resend_every)  # enrich then Bronze


def test_resend_is_removed_keeping_the_earliest_copy():                 # Review Focus 3
    result = build_silver(bronze_from([source_row(1, 1), source_row(1, 2)], resend_every=1), RECEIVED)  # every row resent
    assert result.duplicates_removed == 2                               # two resends removed
    assert len(result.clicks) == 2                                      # one row per real click
    assert (result.clicks["received_time"] == RECEIVED).all()           # earliest copy kept


def test_out_of_range_code_is_rejected_with_reason():                   # codebook range rule
    bronze = bronze_from([source_row(1, 1, country=99)])                # 99 is not a country code
    result = build_silver(bronze, RECEIVED)                             # build
    assert result.clicks.empty                                          # nothing passes
    assert result.rejected["rejection_reason"].tolist() == ["country_code outside 1-47"]  # reason recorded


def test_visit_with_missing_click_is_rejected_whole():                  # contiguity rule
    bronze = bronze_from([source_row(1, 1), source_row(1, 3)])          # click 2 missing
    result = build_silver(bronze, RECEIVED)                             # build
    assert result.clicks.empty                                          # whole visit rejected
    assert set(result.rejected["rejection_reason"]) == {"click numbers not contiguous in visit"}  # reason


def test_time_outside_real_date_is_rejected():                          # time rule
    bronze = bronze_from([source_row(1, 1)])                            # one click on 2008-04-01
    bronze.loc[0, "click_time_synthetic"] = pd.Timestamp("2008-04-02 12:00:00", tz="UTC")  # corrupt: next day
    result = build_silver(bronze, RECEIVED)                             # build
    assert result.rejected["rejection_reason"].tolist() == ["synthetic time outside real date"]  # reason


def test_decoding_and_derived_columns():                                # plain values
    result = build_silver(bronze_from([source_row(1, 1, category_code=4)]), RECEIVED)  # one sale click
    row = result.clicks.iloc[0]                                         # the only row
    assert list(result.clicks.columns) == SILVER_COLUMNS                # exact column set and order
    assert row["category"] == "sale"                                    # decoded category
    assert row["photo_angle"] == "front"                                # decoded angle
    assert not row["priced_above_category_average"]                     # code 2 (no) decodes to False
    assert row["click_month"] == "2008-04"                              # partition value
    assert 0 <= row["click_hour_shop_time_synthetic"] <= 23             # valid hour
    assert row["seconds_late"] > 0                                      # arrival after the click


def test_out_of_order_arrival_gives_same_result():                      # arrival order must not matter
    bronze = bronze_from([source_row(v, c) for v in (1, 2) for c in (1, 2, 3)])  # 6 clicks
    shuffled = bronze.sample(frac=1, random_state=0).reset_index(drop=True)  # scrambled arrival
    ordered_result = build_silver(bronze, RECEIVED).clicks               # normal order
    shuffled_result = build_silver(shuffled, RECEIVED).clicks            # scrambled order
    pd.testing.assert_frame_equal(ordered_result, shuffled_result)       # identical Silver


def test_empty_bronze_gives_empty_silver():                             # empty input
    result = build_silver(bronze_from([]), RECEIVED)                    # no rows
    assert result.clicks.empty and result.rejected.empty                # both empty
    assert list(result.clicks.columns) == SILVER_COLUMNS                # columns still present
    assert result.duplicates_removed == 0                               # nothing removed


# ── Review fixes: bad source rows are rejected, never crash; visits stay whole ─
def test_missing_day_is_rejected_not_a_crash():                         # review Important 1
    bad = {**source_row(2, 1), "day": None}                             # visit 2 has no day
    result = build_silver(bronze_from([source_row(1, 1), bad]), RECEIVED)  # must not raise
    assert result.clicks["visit_id"].tolist() == [1]                    # the good visit survives
    assert result.rejected["rejection_reason"].tolist() == ["missing required field"]  # bad row rejected


def test_impossible_date_is_rejected():                                 # review Important 1
    bad = {**source_row(2, 1), "month": 13}                             # month 13 does not exist
    result = build_silver(bronze_from([source_row(1, 1), bad]), RECEIVED)  # must not raise
    assert result.rejected["rejection_reason"].tolist() == ["invalid real date"]  # clear reason


def test_missing_visit_id_is_rejected():                                # review Important 1
    bad = {**source_row(2, 1), "visit_id": None}                        # no visit
    result = build_silver(bronze_from([source_row(1, 1), bad]), RECEIVED)  # must not raise
    assert result.clicks["visit_id"].tolist() == [1]                    # good visit kept, still an integer id
    assert result.clicks["click_id"].tolist() == ["uci553-1-1"]         # id format survives a missing value elsewhere
    assert result.rejected["rejection_reason"].tolist() == ["missing required field"]  # bad row rejected


def test_one_bad_click_rejects_its_whole_visit():                       # review Important 2
    bronze = bronze_from([source_row(1, 1), {**source_row(1, 2), "colour_code": 99}])  # click 2 has an invalid colour
    result = build_silver(bronze, RECEIVED)                             # build
    assert result.clicks.empty                                          # no partial visit reaches Gold
    assert sorted(result.rejected["rejection_reason"]) == ["colour_code outside 1-14", "other click in visit rejected"]  # both rows explained


def test_time_not_increasing_is_rejected():                             # review Important 3
    bronze = bronze_from([source_row(1, 1), source_row(1, 2)])          # two clicks
    bronze.loc[bronze["click_number_in_visit"] == 2, "click_time_synthetic"] = bronze.loc[bronze["click_number_in_visit"] == 1, "click_time_synthetic"].iloc[0] - pd.Timedelta(seconds=1)  # click 2 before click 1, same day
    result = build_silver(bronze, RECEIVED)                             # build
    assert "synthetic time not increasing" in set(result.rejected["rejection_reason"])  # rule fires


def test_first_failing_rule_is_the_recorded_reason():                   # review Important 3
    result = build_silver(bronze_from([{**source_row(1, 1, country=99), "colour_code": 99}]), RECEIVED)  # two failures
    assert result.rejected["rejection_reason"].tolist() == ["country_code outside 1-47"]  # earlier rule wins
