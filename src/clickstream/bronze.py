"""Bronze: clicks as they arrived, possibly with resends (ADR-0003)."""  # module docstring

import pandas as pd                                                     # dataframes

DATA_SOURCE = "uci553"                                                  # label for every row from the UCI file


def build_bronze(enriched_clicks: pd.DataFrame, received_time: pd.Timestamp, resend_every: int = 0) -> pd.DataFrame:  # build clicks_received
    if received_time.tzinfo is None:                                    # arrival times must carry a timezone
        raise ValueError("received_time must have a timezone (use UTC)")  # clear message
    bronze = enriched_clicks.copy()                                     # never modify the caller's frame
    bronze["received_time"] = pd.Series(received_time.tz_convert("UTC"), index=bronze.index, dtype="datetime64[ns, UTC]")  # arrival time in UTC
    bronze["data_source"] = pd.Series(DATA_SOURCE, index=bronze.index, dtype="object")  # source label
    if resend_every > 0 and not bronze.empty:                           # optionally simulate resends
        resent = bronze.iloc[::resend_every].copy()                     # every Nth row
        resent["received_time"] = resent["received_time"] + pd.Timedelta(seconds=1)  # arrives one second later
        bronze = pd.concat([bronze, resent], ignore_index=True)         # originals then resends
    return bronze.reset_index(drop=True)                                # fresh, unique index
