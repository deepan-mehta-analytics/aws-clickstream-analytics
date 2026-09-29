"""Evidence helpers for the T1a window: expected counts (local), masking, Athena comparison."""  # module docstring

# ── Imports ───────────────────────────────────────────────────
import argparse                                                         # command-line options
import json                                                             # JSON files
import re                                                               # masking patterns
import sys                                                              # exit code
from pathlib import Path                                                # file paths

# ── Masking (public repo: no account IDs, ARNs or real bucket names) ─
BUCKET = re.compile(r"(?<![a-z0-9-])[a-z0-9][a-z0-9-]*?-(bronze|silver|gold|athenaresults)bucket-[a-z0-9]+", re.IGNORECASE)  # CloudFormation-generated names: <stack>-<role>bucket-<suffix>, any stack name
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")  # any email address
ARN = re.compile(r"arn:aws[a-z-]*:[^\s\"']+")                           # any ARN
ACCOUNT_ID = re.compile(r"(?<![0-9])[0-9]{12}(?![0-9])")                # 12-digit account id
QUERY_FILES = {                                                         # comparison name -> saved Athena result file
    "bronze_rows_by_month": "01_bronze_rows_by_month.json",             # landed rows
    "silver_clicks_by_month": "02_silver_clicks_by_month.json",         # clean clicks
    "gold_visits_by_month": "03_gold_visits_by_month.json",             # visits
    "rejected_rows": "04_rejected_rows.json",                           # rejects
}


def mask_text(text: str) -> str:                                        # one string, masked
    text = BUCKET.sub(lambda match: f"<{match.group(1).lower().replace('athenaresults', 'athena-results')}-bucket>", text)  # keep the bucket's role
    text = ARN.sub("<arn>", text)                                       # hide ARNs
    text = EMAIL.sub("<email>", text)                                   # hide email addresses
    return ACCOUNT_ID.sub("<account-id>", text)                         # hide account ids


def mask_json(value):                                                   # any JSON value, masked
    if isinstance(value, str):                                          # text
        return mask_text(value)                                        # masked
    if isinstance(value, list):                                         # list
        return [mask_json(item) for item in value]                      # each item
    if isinstance(value, dict):                                         # object
        return {mask_text(str(key)): mask_json(item) for key, item in value.items()}  # keys and values
    return value                                                        # numbers, booleans, null


# ── Expected numbers from the local twin ──────────────────────
def expected_counts(source: Path) -> dict:                              # per-month counts the cloud run must match
    import pandas as pd                                                 # local only
    from clickstream.bronze import build_bronze                        # pandas Bronze
    from clickstream.enrichment import add_synthetic_fields             # pandas enrichment
    from clickstream.gold import build_visits                           # pandas visits
    from clickstream.silver import build_silver                        # pandas Silver
    from clickstream.source_file import read_source_clicks              # reader
    source_rows = read_source_clicks(source)                            # 165,474 rows
    arrival = pd.Timestamp("2026-09-26 12:00", tz="UTC")                # any fixed time (counts do not depend on it)
    silver = build_silver(build_bronze(add_synthetic_fields(source_rows), arrival), arrival)  # Silver
    months = source_rows["year"].astype(str) + "-" + source_rows["month"].astype(str).str.zfill(2)  # source month per row
    return {                                                            # the numbers
        "bronze_rows_by_month": {k: int(v) for k, v in months.value_counts().sort_index().items()},  # landed rows
        "silver_clicks_by_month": {k: int(v) for k, v in silver.clicks["click_month"].value_counts().sort_index().items()},  # clean clicks
        "gold_visits_by_month": {k: int(v) for k, v in build_visits(silver.clicks)["visit_month"].value_counts().sort_index().items()},  # visits
        "rejected_rows": {"all": int(len(silver.rejected))},            # rejects
    }


# ── Compare with Athena results ───────────────────────────────
def athena_pairs(path: Path) -> dict:                                   # first column -> second column
    rows = json.loads(path.read_text(encoding="utf-8"))["ResultSet"]["Rows"][1:]  # skip the header row
    return {row["Data"][0].get("VarCharValue", ""): int(row["Data"][1]["VarCharValue"]) for row in rows}  # e.g. {"2008-04": 3}


def compare(expected: dict, athena_dir: Path) -> dict:                  # one entry per comparison
    results = {}                                                        # name -> outcome
    for name, file_name in QUERY_FILES.items():                        # each query
        path = Path(athena_dir) / file_name                            # saved Athena result
        if name not in expected or not path.exists():                  # not run or not expected
            continue                                                    # skip
        actual = athena_pairs(path)                                    # Athena numbers
        results[name] = {"expected": expected[name], "athena": actual, "match": actual == expected[name]}  # outcome
    return results                                                      # all outcomes


# ── Command line ──────────────────────────────────────────────
def main() -> int:                                                      # entry point
    parser = argparse.ArgumentParser(description="T1a evidence helpers")  # description
    sub = parser.add_subparsers(dest="command", required=True)          # three commands
    exp = sub.add_parser("expected")                                    # local counts
    exp.add_argument("--source", type=Path, required=True)              # UCI CSV
    exp.add_argument("--output", type=Path, required=True)              # JSON file
    msk = sub.add_parser("mask")                                        # masking
    msk.add_argument("source", type=Path)                               # raw JSON
    msk.add_argument("target", type=Path)                               # masked JSON
    cmp_ = sub.add_parser("compare")                                    # comparison
    cmp_.add_argument("--expected", type=Path, required=True)           # expected JSON
    cmp_.add_argument("--athena-dir", type=Path, required=True)         # saved Athena results
    cmp_.add_argument("--output", type=Path, required=True)             # comparison JSON
    args = parser.parse_args()                                          # read options
    if args.command == "expected":                                     # compute local numbers
        args.output.parent.mkdir(parents=True, exist_ok=True)           # folder
        args.output.write_text(json.dumps(expected_counts(args.source), indent=2), encoding="utf-8")  # save
        return 0                                                        # success
    if args.command == "mask":                                         # mask a file
        args.target.parent.mkdir(parents=True, exist_ok=True)           # folder
        args.target.write_text(json.dumps(mask_json(json.loads(args.source.read_text(encoding="utf-8"))), indent=2), encoding="utf-8")  # save masked
        return 0                                                        # success
    result = compare(json.loads(args.expected.read_text(encoding="utf-8")), args.athena_dir)  # compare
    args.output.parent.mkdir(parents=True, exist_ok=True)               # folder
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")  # save
    print(json.dumps({name: outcome["match"] for name, outcome in result.items()}))  # short summary
    return 0 if result and all(outcome["match"] for outcome in result.values()) else 1  # fail on any mismatch


if __name__ == "__main__":                                              # run as a script
    sys.exit(main())                                                    # exit code for the window script
