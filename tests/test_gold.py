# ── Tests: Gold star schema ───────────────────────────────────
import pandas as pd                                                     # dataframes
from conftest import make_source, source_row                            # hand-made rows

from clickstream.bronze import build_bronze                             # upstream step
from clickstream.enrichment import add_synthetic_fields                 # upstream step
from clickstream.gold import (                                          # code under test
    VISIT_COLUMNS, build_calendar_days, build_countries, build_devices, build_gold_clicks, build_products, build_visits, category_mismatches,
)
from clickstream.silver import build_silver                             # upstream step

RECEIVED = pd.Timestamp("2026-09-25 12:00:00", tz="UTC")                # fixed arrival time


def silver_from(rows):                                                  # helper: rows -> Silver clicks
    return build_silver(build_bronze(add_synthetic_fields(make_source(rows)), RECEIVED), RECEIVED).clicks  # full upstream chain


def test_product_keeps_most_frequent_category_and_mismatch_is_reported():  # the real A18 case
    rows = [source_row(v, 1, product_code="A18", category_code=1) for v in (1, 2, 3)] + [source_row(4, 1, product_code="A18", category_code=2)]  # 3 trousers, 1 skirts
    silver = silver_from(rows)                                          # build Silver
    products = build_products(silver)                                   # build products
    assert products.set_index("product_code").loc["A18", "category"] == "trousers"  # most frequent wins
    mismatches = category_mismatches(silver, products)                  # clicks that disagree
    assert mismatches["click_category"].tolist() == ["skirts"]          # exactly the one skirts click


def test_countries_have_47_rows_and_kinds():                            # Review Focus 5
    countries = build_countries().set_index("country_code")             # all codes
    assert len(countries) == 47                                         # full codebook
    assert countries.loc[12, "kind"] == "unknown"                       # unidentified
    assert set(countries.loc[[43, 44, 45, 46, 47], "kind"]) == {"web domain"}  # domains
    assert countries.loc[20, "kind"] == "country"                       # India is a country


def test_visit_metrics():                                               # visits table
    rows = [source_row(1, 1, page=1), source_row(1, 2, page=2, product_code="B1"), source_row(1, 3, page=3, product_code="C1")]  # 3-click visit
    rows += [source_row(2, 1, page=1)]                                  # 1-click visit
    visits = build_visits(silver_from(rows)).set_index("visit_id")      # build
    assert list(build_visits(silver_from(rows)).columns) == VISIT_COLUMNS  # exact columns
    assert visits.loc[1, "clicks_in_visit"] == 3                        # three clicks
    assert visits.loc[1, "deepest_page_reached"] == 3                   # reached page 3
    assert visits.loc[1, "products_viewed"] == 3                        # three products
    assert not visits.loc[1, "bounced"]                                 # not a bounce
    assert visits.loc[1, "first_product_viewed"] == "A13"               # entry product
    assert visits.loc[1, "last_product_viewed"] == "C1"                 # exit product
    assert visits.loc[2, "bounced"]                                     # one click = bounce
    assert visits.loc[2, "visit_length_seconds_synthetic"] == 0         # no time between clicks
    assert visits.loc[1, "visit_month"] == "2008-04"                    # partition value


def test_calendar_devices_and_gold_clicks():                            # remaining tables
    silver = silver_from([source_row(1, 1, day=5)])                     # one click on 2008-04-05
    calendar = build_calendar_days(silver)                              # calendar
    assert calendar.loc[0, "day_of_week"] == "Saturday"                 # 2008-04-05 was a Saturday
    assert calendar.loc[0, "month_name"] == "April"                     # month name
    assert set(build_devices()["device_type"]) == {"desktop", "mobile", "tablet"}  # device list
    assert "click_month" in build_gold_clicks(silver).columns           # partition column kept


def test_empty_silver_gives_empty_gold():                               # empty input
    empty = silver_from([])                                             # no clicks
    assert build_visits(empty).empty and list(build_visits(empty).columns) == VISIT_COLUMNS  # empty visits with columns
    assert build_products(empty).empty                                  # empty products
    assert build_calendar_days(empty).empty                             # empty calendar
