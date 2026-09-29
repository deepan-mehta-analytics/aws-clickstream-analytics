"""Add the fields the UCI data lacks, as clearly labelled synthetic columns (ADR-0003)."""  # module docstring

import numpy as np                                                      # seeded random numbers
import pandas as pd                                                     # dataframes

# ── Documented generation settings (ADR-0003, illustrative) ───
SHOP_TIMEZONE = "Europe/Warsaw"                                         # ~81% of traffic is Polish; CEST (UTC+2) in Apr-Aug 2008
DEFAULT_SEED = 553                                                      # default seed, named after the UCI dataset number
HOUR_WEIGHTS = [1, 1, 1, 1, 1, 1, 2, 3, 4, 5, 6, 6, 6, 6, 6, 6, 7, 8, 9, 10, 10, 8, 5, 2]  # visit-start weight per local hour 0-23: quiet night, evening peak
SECONDS_BETWEEN_CLICKS = (5, 300)                                       # gap between clicks: 5 seconds to 5 minutes
DEVICE_WEIGHTS = {"desktop": 0.85, "mobile": 0.10, "tablet": 0.05}      # illustrative 2008 device mix
SECONDS_IN_DAY = 86_400                                                 # seconds in one day


def shop_time_to_utc(local_times: pd.Series) -> pd.Series:              # naive shop-local times -> UTC, safe at DST changes
    standard_time = np.zeros(len(local_times), dtype=bool)              # "ambiguous" wants one flag per row; False = standard time (CET)
    return local_times.dt.tz_localize(SHOP_TIMEZONE, ambiguous=standard_time, nonexistent="shift_forward").dt.tz_convert("UTC")  # missing hour -> next valid time


def add_synthetic_fields(source_clicks: pd.DataFrame, seed: int = DEFAULT_SEED) -> pd.DataFrame:  # enrich every click
    # ── Order clicks and set up the draws ─────────────────────
    clicks = source_clicks.sort_values(["visit_id", "click_number_in_visit"], kind="stable").reset_index(drop=True)  # visit order
    hour_probabilities = np.array(HOUR_WEIGHTS) / sum(HOUR_WEIGHTS)     # weights as probabilities
    device_names = list(DEVICE_WEIGHTS)                                 # device labels
    device_probabilities = list(DEVICE_WEIGHTS.values())                # device probabilities
    real_dates = pd.to_datetime(clicks[["year", "month", "day"]], errors="coerce")  # real date; NaT when missing or impossible
    can_generate = clicks["visit_id"].notna() & real_dates.notna()      # bad rows get no synthetic values; Silver rejects them
    local_series = pd.Series(pd.NaT, index=clicks.index, dtype="datetime64[ns]")  # naive shop-local times, NaT by default
    device_series = pd.Series(None, index=clicks.index, dtype="object")  # device labels, empty by default

    # ── One seeded generator per visit ────────────────────────
    for visit_id, visit in clicks[can_generate].groupby("visit_id", sort=False):  # valid rows only, in sorted visit order
        generator = np.random.default_rng([seed, int(visit_id)])        # same visit + seed -> same values
        click_count = len(visit)                                        # clicks in this visit
        gaps = generator.integers(SECONDS_BETWEEN_CLICKS[0], SECONDS_BETWEEN_CLICKS[1] + 1, size=click_count - 1)  # seconds between clicks
        offsets = np.concatenate([[0], np.cumsum(gaps)])                # seconds after the first click
        start_second = int(generator.choice(24, p=hour_probabilities)) * 3600 + int(generator.integers(0, 3600))  # start hour + second within hour
        start_second = max(0, min(start_second, SECONDS_IN_DAY - 1 - int(offsets[-1])))  # keep the whole visit inside its day
        real_date = real_dates[visit.index[0]]                          # first click carries the real date
        local_series.loc[visit.index] = (real_date + pd.to_timedelta(start_second + offsets, unit="s")).to_numpy()  # local click times
        device_series.loc[visit.index] = str(generator.choice(device_names, p=device_probabilities))  # one device for the whole visit

    # ── Attach the new columns ────────────────────────────────
    visit_text = clicks["visit_id"].astype("Int64").astype(str)         # integer text even if another row is missing its id
    click_number_text = clicks["click_number_in_visit"].astype("Int64").astype(str)  # same for click numbers
    clicks["click_id"] = "uci553-" + visit_text + "-" + click_number_text  # stable id, e.g. uci553-7-1
    clicks["click_time_synthetic"] = shop_time_to_utc(local_series)      # stored in UTC (DST-safe)
    clicks["device_type_synthetic"] = device_series                     # device labels
    return clicks                                                       # source columns + synthetic columns
