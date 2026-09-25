"""Gold: star schema with two grains (clicks, visits) plus reference tables (ADR-0003)."""  # module docstring

import pandas as pd                                                     # dataframes

from clickstream.codebook import COUNTRIES, country_kind               # country decode and kind
from clickstream.enrichment import DEVICE_WEIGHTS                       # device list

# ── Output shapes ─────────────────────────────────────────────
PRODUCT_COLUMNS = [                                                     # products table columns
    "product_code", "category", "colour", "price_usd", "priced_above_category_average",  # identity and price
    "page_number_in_shop", "photo_position_on_page", "photo_angle",     # placement
]
CALENDAR_COLUMNS = ["calendar_date", "day_of_week", "week_number", "month_name"]  # calendar_days columns
GOLD_CLICK_COLUMNS = [                                                  # Gold clicks columns
    "click_id", "visit_id", "click_number_in_visit", "click_date", "click_time_synthetic",  # identity and time
    "product_code", "country_code", "device_type_synthetic", "price_usd", "click_month",  # keys, price, partition
]
VISIT_COLUMNS = [                                                       # visits table columns
    "visit_id", "visit_date", "country_code", "device_type_synthetic", "visit_start_time_synthetic", "visit_end_time_synthetic",  # identity and time
    "visit_length_seconds_synthetic", "clicks_in_visit", "products_viewed", "categories_viewed", "deepest_page_reached",  # measures
    "bounced", "first_product_viewed", "last_product_viewed", "visit_month",  # outcome and partition
]


def build_products(silver_clicks: pd.DataFrame) -> pd.DataFrame:       # one row per product
    if silver_clicks.empty:                                             # nothing to build
        return pd.DataFrame(columns=PRODUCT_COLUMNS)                    # empty with columns
    grouped = silver_clicks.groupby("product_code")                     # per product
    products = grouped.agg(**{column: (column, "first") for column in PRODUCT_COLUMNS[2:]})  # attributes fixed per product (measured)
    products.insert(0, "category", grouped["category"].agg(lambda values: values.mode().iloc[0]))  # most frequent category (A18 -> trousers)
    return products.reset_index()[PRODUCT_COLUMNS]                      # exact column order


def category_mismatches(silver_clicks: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:  # clicks whose category differs from the product's
    joined = silver_clicks.merge(products[["product_code", "category"]], on="product_code", suffixes=("", "_of_product"))  # attach product category
    different = joined[joined["category"] != joined["category_of_product"]]  # disagreements
    return different.rename(columns={"category": "click_category", "category_of_product": "product_category"})[  # plain names
        ["click_id", "product_code", "click_category", "product_category"]  # report columns
    ].reset_index(drop=True)                                            # fresh index


def build_countries() -> pd.DataFrame:                                  # one row per country code
    return pd.DataFrame(                                                # from the codebook
        [{"country_code": code, "country_name": name, "kind": country_kind(code)} for code, name in COUNTRIES.items()]  # all 47 codes
    )


def build_calendar_days(silver_clicks: pd.DataFrame) -> pd.DataFrame:  # one row per date that has clicks
    if silver_clicks.empty:                                             # nothing to build
        return pd.DataFrame(columns=CALENDAR_COLUMNS)                   # empty with columns
    dates = pd.to_datetime(pd.Series(sorted(set(silver_clicks["click_date"]))))  # distinct dates, sorted
    return pd.DataFrame({                                               # calendar attributes
        "calendar_date": dates.dt.date,                                 # the date
        "day_of_week": dates.dt.day_name(),                             # e.g. Saturday
        "week_number": dates.dt.isocalendar().week.astype("int64"),     # ISO week
        "month_name": dates.dt.month_name(),                            # e.g. April
    })


def build_devices() -> pd.DataFrame:                                    # one row per (synthetic) device type
    return pd.DataFrame({"device_type": list(DEVICE_WEIGHTS)})          # desktop, mobile, tablet


def build_gold_clicks(silver_clicks: pd.DataFrame) -> pd.DataFrame:    # Gold clicks (event table, click grain)
    return silver_clicks[GOLD_CLICK_COLUMNS].reset_index(drop=True)     # keys and measures only


def build_visits(silver_clicks: pd.DataFrame) -> pd.DataFrame:         # Gold visits (event table, visit grain)
    if silver_clicks.empty:                                             # nothing to build
        return pd.DataFrame(columns=VISIT_COLUMNS)                      # empty with columns
    ordered = silver_clicks.sort_values(["visit_id", "click_number_in_visit"])  # click order within each visit
    visits = ordered.groupby("visit_id").agg(                           # one row per visit
        visit_date=("click_date", "first"),                             # visits never cross midnight
        country_code=("country_code", "first"),                         # fixed per visit (measured)
        device_type_synthetic=("device_type_synthetic", "first"),       # fixed per visit by design
        visit_start_time_synthetic=("click_time_synthetic", "min"),     # first click time
        visit_end_time_synthetic=("click_time_synthetic", "max"),       # last click time
        clicks_in_visit=("click_id", "count"),                          # number of clicks
        products_viewed=("product_code", "nunique"),                    # distinct products
        categories_viewed=("category", "nunique"),                      # distinct categories
        deepest_page_reached=("page_number_in_shop", "max"),            # browse-depth funnel stage
        first_product_viewed=("product_code", "first"),                 # entry product
        last_product_viewed=("product_code", "last"),                   # exit product
    ).reset_index()                                                     # visit_id back to a column
    visits["visit_length_seconds_synthetic"] = (visits["visit_end_time_synthetic"] - visits["visit_start_time_synthetic"]).dt.total_seconds().astype("int64")  # duration
    visits["bounced"] = visits["clicks_in_visit"] == 1                  # one click = bounce
    visits["visit_month"] = pd.to_datetime(visits["visit_date"]).dt.strftime("%Y-%m")  # partition value
    return visits[VISIT_COLUMNS]                                        # exact column order
