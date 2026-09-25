# ── Tests: dashboard summaries ────────────────────────────────
import pandas as pd                                                     # dataframes
from conftest import make_source, source_row                            # hand-made rows

from clickstream.bronze import build_bronze                             # upstream step
from clickstream.enrichment import add_synthetic_fields                 # upstream step
from clickstream.gold import build_countries, build_visits              # upstream step
from clickstream.silver import build_silver                             # upstream step
from clickstream.summaries import SUMMARY_NAMES, run_summaries          # code under test

RECEIVED = pd.Timestamp("2026-09-25 12:00:00", tz="UTC")                # fixed arrival time


def summaries_for(rows):                                                # helper: rows -> summaries
    silver = build_silver(build_bronze(add_synthetic_fields(make_source(rows)), RECEIVED), RECEIVED).clicks  # upstream chain
    return run_summaries({"visits": build_visits(silver), "countries": build_countries()})  # run the SQL


def test_all_four_summaries_are_produced():                             # completeness
    assert set(summaries_for([source_row(1, 1)])) == set(SUMMARY_NAMES)  # one frame per summary


def test_funnel_counts_visits_reaching_each_page():                     # browse-depth funnel
    rows = [source_row(1, 1, page=1), source_row(1, 2, page=3), source_row(2, 1, page=1), source_row(3, 1, page=2)]  # deepest pages 3, 1, 2
    funnel = summaries_for(rows)["visit_depth_funnel"]                  # run
    assert funnel["shop_page"].tolist() == [1, 2, 3, 4, 5]              # every page listed
    assert funnel["visits_reaching_page"].tolist() == [3, 2, 1, 0, 0]   # visits with deepest page >= each page


def test_daily_visits_bounce_rate():                                    # daily summary
    rows = [source_row(1, 1), source_row(1, 2), source_row(2, 1)]       # one 2-click visit, one bounce, same day
    daily = summaries_for(rows)["daily_visits"]                         # run
    assert daily["visits"].tolist() == [2]                              # two visits
    assert daily["clicks"].tolist() == [3]                              # three clicks
    assert daily["bounce_rate"].tolist() == [0.5]                       # one of two bounced


def test_bounce_rate_by_product_and_country_names():                    # remaining summaries
    result = summaries_for([source_row(1, 1, product_code="A1", country=20), source_row(2, 1, product_code="A1", country=20)])  # two Indian bounces on A1
    bounce = result["bounce_rate_by_product"].set_index("product_code")  # by product
    assert bounce.loc["A1", "visits_started"] == 2                      # two visits started on A1
    assert bounce.loc["A1", "bounce_rate"] == 1.0                       # both bounced
    geo = result["visits_by_country_and_device"]                        # by country and device
    assert set(geo["country_name"]) == {"India"}                        # decoded via countries
    assert geo["visits"].sum() == 2                                     # all visits counted


def test_summary_sql_avoids_values_row_lists():                          # review Important 4: Redshift has no VALUES in FROM
    from clickstream.summaries import SQL_DIR                           # summary folder
    for name in SUMMARY_NAMES:                                          # every summary file
        assert "VALUES" not in (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8").upper()  # portable to DuckDB, Athena and Redshift
