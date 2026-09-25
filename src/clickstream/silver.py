"""Silver: one cleaned row per real click; failing rows go to clicks_rejected (ADR-0003)."""  # module docstring

from dataclasses import dataclass                                       # simple result container

import pandas as pd                                                     # dataframes

from clickstream.codebook import CATEGORIES, COLOURS, PHOTO_ANGLES, PHOTO_POSITIONS  # decode tables
from clickstream.enrichment import SHOP_TIMEZONE                        # shop local timezone

# ── Rules and output shape ────────────────────────────────────
REQUIRED_COLUMNS = [                                                    # fields every click must have
    "click_id", "visit_id", "year", "month", "day", "click_number_in_visit", "country_code", "category_code",  # identity, date, codes
    "product_code", "colour_code", "photo_position_code", "photo_angle_code", "price_usd",  # product fields
    "price_above_category_average_code", "page_number_in_shop", "click_time_synthetic", "received_time",  # flags and times
]
VALID_CODE_RANGES = {                                                   # allowed code ranges from the codebook
    "country_code": (1, 47), "category_code": (1, 4), "colour_code": (1, 14), "photo_position_code": (1, 6),  # geo, category, colour, position
    "photo_angle_code": (1, 2), "price_above_category_average_code": (1, 2), "page_number_in_shop": (1, 5),  # angle, price flag, page
}
SILVER_COLUMNS = [                                                      # Silver clicks columns, data-dictionary order
    "click_id", "visit_id", "click_number_in_visit", "click_date", "click_time_synthetic", "click_hour_shop_time_synthetic",  # identity and time
    "product_code", "category", "colour", "price_usd", "priced_above_category_average", "page_number_in_shop",  # product
    "photo_position_on_page", "photo_angle", "country_code", "device_type_synthetic", "received_time", "seconds_late", "click_month",  # context
]


@dataclass
class SilverResult:                                                     # everything build_silver returns
    clicks: pd.DataFrame                                                # rows that passed every hard rule
    rejected: pd.DataFrame                                              # rows that failed, with a reason
    duplicates_removed: int                                             # resent copies dropped


def build_silver(bronze: pd.DataFrame, run_time: pd.Timestamp) -> SilverResult:  # Bronze -> Silver
    # ── Remove resends: keep the earliest copy of each click ──
    ordered = bronze.sort_values(["click_id", "received_time"], kind="stable")  # earliest copy first
    duplicates_removed = int(ordered.duplicated("click_id").sum())      # how many resends there were
    unique = ordered.drop_duplicates("click_id", keep="first").copy()   # one row per click_id
    if unique.empty:                                                    # nothing to check
        rejected = unique.assign(rejection_reason=pd.Series(dtype="object"), rejected_time=pd.Series(dtype="datetime64[ns, UTC]"))  # empty rejects
        return SilverResult(pd.DataFrame(columns=SILVER_COLUMNS), rejected, duplicates_removed)  # empty result with columns

    # ── Hard rules: the first failing rule is the recorded reason ─
    reasons = pd.Series("", index=unique.index, dtype="object")         # empty string = passed so far

    def flag(failed: pd.Series, reason: str) -> None:                   # record a reason where none exists yet
        reasons[failed.fillna(True).astype(bool) & (reasons == "")] = reason  # first failing rule wins

    flag(unique[REQUIRED_COLUMNS].isna().any(axis=1), "missing required field")  # every required field present
    for column, (low, high) in VALID_CODE_RANGES.items():              # each coded field
        flag(~unique[column].between(low, high), f"{column} outside {low}-{high}")  # inside codebook range
    contiguous = unique.groupby("visit_id")["click_number_in_visit"].transform(lambda numbers: sorted(numbers) == list(range(1, len(numbers) + 1)))  # 1..n with no gaps
    flag(~contiguous.astype(bool), "click numbers not contiguous in visit")  # the whole visit fails together
    real_date = pd.to_datetime(unique[["year", "month", "day"]], errors="coerce").dt.date  # the real 2008 date
    local_time = unique["click_time_synthetic"].dt.tz_convert(SHOP_TIMEZONE)  # shop-local synthetic time
    flag(local_time.dt.date != real_date, "synthetic time outside real date")  # synthetic time on the real date
    in_visit_order = unique.sort_values(["visit_id", "click_number_in_visit"])  # rows in click order
    gap_seconds = in_visit_order.groupby("visit_id")["click_time_synthetic"].diff().dt.total_seconds().fillna(1)  # seconds since previous click
    flag((gap_seconds <= 0).reindex(unique.index), "synthetic time not increasing")  # times must increase

    # ── Split into rejected and passing rows ──────────────────
    failed = reasons != ""                                              # rows with a reason
    rejected = unique[failed].assign(rejection_reason=reasons[failed], rejected_time=run_time.tz_convert("UTC"))  # rejects with reason
    passing = unique[~failed]                                           # clean rows
    passing_local = local_time[~failed]                                 # their local times

    # ── Decode codes and derive columns ───────────────────────
    clicks = pd.DataFrame({                                             # Silver clicks in plain words
        "click_id": passing["click_id"],                                # unique id
        "visit_id": passing["visit_id"],                                # visit
        "click_number_in_visit": passing["click_number_in_visit"],      # position
        "click_date": real_date[~failed],                               # real date
        "click_time_synthetic": passing["click_time_synthetic"],        # UTC synthetic time
        "click_hour_shop_time_synthetic": passing_local.dt.hour,        # local hour 0-23
        "product_code": passing["product_code"],                        # product
        "category": passing["category_code"].map(CATEGORIES),           # decoded category
        "colour": passing["colour_code"].map(COLOURS),                  # decoded colour
        "price_usd": passing["price_usd"],                              # price
        "priced_above_category_average": passing["price_above_category_average_code"] == 1,  # 1 = yes
        "page_number_in_shop": passing["page_number_in_shop"],          # listing page
        "photo_position_on_page": passing["photo_position_code"].map(PHOTO_POSITIONS),  # decoded position
        "photo_angle": passing["photo_angle_code"].map(PHOTO_ANGLES),   # decoded angle
        "country_code": passing["country_code"],                        # country code
        "device_type_synthetic": passing["device_type_synthetic"],      # synthetic device
        "received_time": passing["received_time"],                      # arrival time
        "seconds_late": (passing["received_time"] - passing["click_time_synthetic"]).dt.total_seconds().astype("int64"),  # arrival minus click
        "click_month": pd.to_datetime(real_date[~failed]).dt.strftime("%Y-%m"),  # partition value
    })[SILVER_COLUMNS]                                                  # exact column order
    clicks = clicks.sort_values(["visit_id", "click_number_in_visit"]).reset_index(drop=True)  # stable output order
    return SilverResult(clicks, rejected.reset_index(drop=True), duplicates_removed)  # all three outputs
