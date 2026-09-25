"""Quality report: reconciliation counts and reported (non-fatal) findings (ADR-0003)."""  # module docstring

import pandas as pd                                                     # dataframes

from clickstream.silver import SilverResult                             # Silver output type


def build_quality_report(source_rows: int, bronze_rows: int, silver: SilverResult, visits: pd.DataFrame, mismatches: pd.DataFrame) -> dict:  # JSON-ready dict
    reasons = silver.rejected["rejection_reason"].value_counts() if not silver.rejected.empty else pd.Series(dtype="int64")  # rejects per reason
    return {                                                            # plain-named counts
        "source_rows": int(source_rows),                                # rows read from the source file
        "bronze_rows": int(bronze_rows),                                # rows received, including resends
        "duplicates_removed": int(silver.duplicates_removed),           # resends dropped in Silver
        "rejected_rows": int(len(silver.rejected)),                     # rows that failed a hard rule
        "rejections_by_reason": {str(reason): int(count) for reason, count in reasons.items()},  # breakdown
        "silver_clicks": int(len(silver.clicks)),                       # clean clicks
        "visits": int(len(visits)),                                     # visits built
        "one_click_visits": int(visits["bounced"].sum()) if not visits.empty else 0,  # bounces
        "category_mismatches": mismatches.to_dict(orient="records"),    # reported, not rejected (expected: A18 once)
    }
