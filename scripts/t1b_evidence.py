"""Evidence helpers for the T1b window: visit A pick, expected counts without it, pass/fail checks, masking.

The window script saves one small JSON file per fact in an evidence folder; `t1b_checks` reads them.
Files (all plain JSON, written by the window script from the raw Athena / S3 output):
  format_version_step1.json, format_version_step14.json   {"silver_clicks": {"format_version": 2, "source": "show_tblproperties"
                                                          or "metadata.json"}, ... one entry per Iceberg table}
  run2_input_files.json, run3_input_files.json            {"input_files": 1}
  files_before_migration.json, files_after_migration.json [{"path", "size", "last_modified"}, ...] (April-July data files)
  weekend_null_share.json                                 {"2008-04": 1.0, ..., "2008-08": 0.0}
  weekend_mismatches.json                                 {"mismatched_rows": 0} (August values vs the local twin)
  before_delete_counts.json, after_delete_counts.json     {"silver_clicks_by_month": {...}}; after also has
                                                          "visit_rows_in_silver_clicks" and "rejects_rows_deleted"
  time_travel_step10.json                                 {"silver_clicks": {"row_count": n}, "silver_clicks_rejected": {"row_count": n}}
  time_travel_step14.json                                 {"silver_clicks": {"state": "FAILED", "error": "..."}, "silver_clicks_rejected": ...};
                                                          an entry may instead be {"state": "SUCCEEDED", "row_count": n}
  files_step8.json, files_step12.json                     ["s3 path", ...] (data files of the visit's month)
  files_step8_left_after_vacuum.json                      ["s3 path", ...] (step-8 files S3 still lists after VACUUM; expected [])
  bronze_versions_after.json                              {"version_count": 1, "contains_visit": false}
  gold_after_run3.json                                    {"visits_by_month": {...}, "clicks_by_month": {...}}
  final_counts.json                                       same keys as `expected_counts`
SQL 07 (data files of one month) returns rows of (file_path, file_size_in_bytes, record_count). For files_step8.json and
files_step12.json the window script keeps only the file_path column, as a plain JSON list of path strings. For
files_before_migration.json / files_after_migration.json it keeps path, size and last-modified time per file.
"""  # module docstring

# ── Imports ───────────────────────────────────────────────────
import argparse                                                         # command-line options
import importlib.util                                                   # load the T1a script by path
import json                                                             # JSON files
import random                                                           # seeded visit pick
import re                                                               # masking patterns
import sys                                                              # exit code
import tempfile                                                         # temporary CSV for the "without" counts
from pathlib import Path                                                # file paths

# ── Reuse the T1a helpers (loaded by path; that file is not a package) ─
_T1A_PATH = Path(__file__).resolve().parent / "t1a_evidence.py"         # sibling script
_spec = importlib.util.spec_from_file_location("t1a_evidence", _T1A_PATH)  # module spec
t1a = importlib.util.module_from_spec(_spec)                            # empty module
_spec.loader.exec_module(t1a)                                           # run it
mask_text = t1a.mask_text                                               # account ids, ARNs, buckets, emails
mask_json = t1a.mask_json                                               # same, over JSON values
expected_counts = t1a.expected_counts                                   # per-month counts from the local twin

# ── Reuse the Bronze erase script's row removal (loaded by path) ─
_ERASE_PATH = Path(__file__).resolve().parent / "t1b_erase_visit_from_bronze.py"  # sibling script
_erase_spec = importlib.util.spec_from_file_location("t1b_erase_visit_from_bronze", _ERASE_PATH)  # module spec
_erase = importlib.util.module_from_spec(_erase_spec)                   # empty module
_erase_spec.loader.exec_module(_erase)                                  # run it

# ── Constants ─────────────────────────────────────────────────
DEFAULT_SEED = 20261020                                                 # fixed seed for visit A (spec section 3.3)
EXCLUDED_MONTH = "2008-08"                                              # August is never touched by the delete evidence
VISIT_LABEL = "visit A"                                                 # public label; the real ID never appears
TABLE_NAMES = ["silver_clicks", "silver_clicks_rejected", "silver_deleted_visits"]  # the three Iceberg tables
FORMAT_VERSION_SOURCES = {"show_tblproperties", "metadata.json"}      # where the window may read the format version
S3_VERSION_ID = re.compile(                                             # S3 version ID shape: 32 characters with letters and digits
    r"(?<![A-Za-z0-9._+/-])(?=[A-Za-z0-9._+]*[0-9])(?=[A-Za-z0-9._+]*[A-Za-z])[A-Za-z0-9._+]{32}(?![A-Za-z0-9._+-])"  # not part of a longer token
)  # end of the pattern
VISIT_KEYS = {"visit_id"}                                              # JSON keys that carry the visit ID
VERSION_FIELD = re.compile(r'("?VersionId"?\s*[:=]\s*"?)([^\s",}]+)')   # a value that follows a VersionId label


# ── Visit A ───────────────────────────────────────────────────
def pick_visit(source: Path, seed: int = DEFAULT_SEED) -> tuple[int, str]:  # (visit id, source month)
    import pandas as pd                                                 # local only
    from clickstream.bronze import build_bronze                        # pandas Bronze
    from clickstream.enrichment import add_synthetic_fields             # pandas enrichment
    from clickstream.silver import build_silver                        # pandas Silver
    from clickstream.source_file import read_source_clicks              # reader
    rows = read_source_clicks(source)                                   # every source row
    arrival = pd.Timestamp("2026-09-26 12:00", tz="UTC")                # any fixed time
    silver = build_silver(build_bronze(add_synthetic_fields(rows), arrival), arrival)  # run the Silver rules
    rejected_visits = set(silver.rejected["visit_id"].astype(int))      # visits with at least one failing click
    clean_visits = set(silver.clicks["visit_id"].astype(int)) - rejected_visits  # every click passed
    months = rows["year"].astype(str) + "-" + rows["month"].astype(str).str.zfill(2)  # source month per row
    month_of_visit = months.groupby(rows["visit_id"]).first()           # one month per visit
    candidates = sorted((int(visit), month_of_visit[visit]) for visit in clean_visits if month_of_visit[visit] != EXCLUDED_MONTH)  # sorted for determinism
    if not candidates:                                                  # nothing eligible
        raise ValueError("no clean visit outside 2008-08 in the source file")  # clear failure
    return random.Random(seed).choice(candidates)                       # seeded pick


def filter_visit_lines(raw: bytes, visit_id: int) -> bytes:             # source bytes minus one visit's lines
    return _erase.remove_visit_rows(raw, visit_id)[0]                   # one implementation, shared with the Bronze erase script


def expected_counts_without(source: Path, visit_id: int) -> dict:      # expected_counts minus one visit
    with tempfile.TemporaryDirectory() as folder:                       # scratch folder
        trimmed = Path(folder) / "trimmed.csv"                          # filtered copy
        trimmed.write_bytes(filter_visit_lines(Path(source).read_bytes(), visit_id))  # raw lines, nothing re-serialised
        return expected_counts(trimmed)                                 # the T1a calculation on the filtered file


# ── Masking ───────────────────────────────────────────────────
def mask_visit(text: str, visit_id: int) -> str:                        # visit ID -> label, whole numbers only
    return re.sub(rf"(?<![0-9]){int(visit_id)}(?![0-9])", VISIT_LABEL, text)  # not inside a longer number


def mask_versions(text: str) -> str:                                    # S3 version IDs -> placeholder
    text = VERSION_FIELD.sub(lambda match: match.group(1) + "<version-id>", text)  # labelled values
    return S3_VERSION_ID.sub("<version-id>", text)                      # unlabelled 32-character IDs


def mask_string(text: str, visit_id: int | None) -> str:                # one string value, masked
    text = mask_versions(mask_text(text))                               # T1a masking, then version IDs
    if visit_id is not None:                                            # only when we know the ID
        text = re.sub(rf"(uci553-){int(visit_id)}(-)", rf"\g<1>{VISIT_LABEL}\g<2>", text)  # the visit part of a click id, nothing else
    return text                                                         # masked string


def mask_everything(value, visit_id: int | None = None, key: str | None = None):  # parsed JSON, masked field by field
    if isinstance(value, dict):                                         # object
        return {mask_text(str(name)): mask_everything(item, visit_id, str(name)) for name, item in value.items()}  # keep the key for context
    if isinstance(value, list):                                         # list
        return [mask_everything(item, visit_id, key) for item in value]  # each item under the same key
    if key in VISIT_KEYS and value is not None:                         # a field that carries the visit
        return VISIT_LABEL                                              # label, whatever the type
    if isinstance(value, str):                                          # text
        return "<version-id>" if key == "VersionId" else mask_string(value, visit_id)  # version values are replaced whole
    return value                                                        # numbers, booleans, null stay as they are


# ── Checks (one entry per spec section 5 line) ────────────────
def _load(evidence_dir: Path, name: str):                               # a saved evidence file, or None
    path = Path(evidence_dir) / name                                    # file in the folder
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None  # missing = None


def _entry(check: str, expected, actual) -> dict:                       # one pass/fail line
    return {"check": check, "expected": expected, "actual": actual, "pass": actual == expected}  # pass = exact match


def t1b_checks(evidence_dir: Path, expected_before: dict, expected_after: dict) -> dict:  # all checks
    results = {}                                                        # name -> entry

    def load(name: str):                                                # shorthand for one evidence file
        return _load(evidence_dir, name)                                # saved JSON or None

    def add(name: str, description: str, expected, actual) -> None:     # record one check
        results[name] = _entry(description, expected, actual)           # a missing file shows as actual=None and fails

    def field(data, *path):                                             # dig into optional data
        for key in path:                                                # each step
            data = data.get(key) if isinstance(data, dict) else None    # None when absent
        return data                                                     # value or None

    def versions(fact):                                                 # {"table": version} from a format-version fact
        if not isinstance(fact, dict):                                  # missing or malformed file
            return None                                                 # fails the check
        return {name: field(fact, name, "format_version") if field(fact, name, "source") in FORMAT_VERSION_SOURCES else None for name in TABLE_NAMES}  # an unknown source counts as missing

    def expired(entry) -> bool:                                         # a step-14 time travel that failed on the snapshot
        return isinstance(entry, dict) and entry.get("state") == "FAILED" and bool(entry.get("error")) and "row_count" not in entry  # only a recorded FAILED state counts

    all_v2 = {name: 2 for name in TABLE_NAMES}                          # format version 2 on all three tables
    add("format_version_step1", "format version 2 on all three tables at step 1", all_v2, versions(load("format_version_step1.json")))  # spec line 1
    add("format_version_step14", "format version 2 on all three tables at step 14", all_v2, versions(load("format_version_step14.json")))  # spec line 1
    add("run2_input_files", "run 2 read exactly 1 input file", 1, field(load("run2_input_files.json"), "input_files"))  # bookmark
    add("files_unchanged_across_migration", "April-July data files identical before and after the migration", load("files_before_migration.json") or "missing", load("files_after_migration.json"))  # path, size, time
    share = load("weekend_null_share.json")                            # NULL share per month
    expected_share = {month: (0.0 if month == EXCLUDED_MONTH else 1.0) for month in expected_before["silver_clicks_by_month"]}  # months from the local run: August 0, others 1
    add("weekend_null_share", "weekend_click NULL share 1.0 for April-July and 0.0 for August", expected_share, share)  # D2 evidence
    add("weekend_values_match", "August weekend_click rows differing from the local twin", 0, field(load("weekend_mismatches.json"), "mismatched_rows"))  # per-row equality
    add("pre_delete_counts", "Silver clicks per month before the delete match the local run", expected_before["silver_clicks_by_month"], field(load("before_delete_counts.json"), "silver_clicks_by_month"))  # step 8
    add("visit_removed", "visit A rows left in silver_clicks after the delete", 0, field(load("after_delete_counts.json"), "visit_rows_in_silver_clicks"))  # step 9
    add("rejects_delete_zero", "rows the rejects DELETE affected (the real data has no rejects)", 0, field(load("after_delete_counts.json"), "rejects_rows_deleted"))  # step 9
    add("other_counts_unchanged", "Silver clicks per month after the delete equal the local run minus visit A", expected_after["silver_clicks_by_month"], field(load("after_delete_counts.json"), "silver_clicks_by_month"))  # step 9
    travel10 = load("time_travel_step10.json")                          # step 10 result
    add("time_travel_returns_visit", "step 10 time travel on silver_clicks still returns rows of visit A (more than 0)", True, None if travel10 is None else (field(travel10, "silver_clicks", "row_count") or 0) > 0)  # merge-on-read only hides
    add("time_travel_rejected_step10", "step 10 time travel on silver_clicks_rejected answers with 0 rows of visit A (a clean visit)", 0, field(travel10, "silver_clicks_rejected", "row_count"))  # the query ran at the step-8 snapshot
    before_files, after_files = load("files_step8.json"), load("files_step12.json")  # data file lists
    add("files_replaced", "step 12 data files share no path with step 8's list", True, None if not before_files or after_files is None else not (set(before_files) & set(after_files)))  # OPTIMIZE rewrote them
    add("files_step8_deleted", "step 8 data files still in S3 after VACUUM (the file list decides, not the query status)", [], load("files_step8_left_after_vacuum.json"))  # spec section 6 risk 3
    travel14 = load("time_travel_step14.json")                          # step 14 result per table
    add("time_travel_fails", "step 14 time travel on silver_clicks fails with state FAILED (snapshot expired)", True, None if travel14 is None else expired(field(travel14, "silver_clicks")))  # VACUUM expired it
    rejected14 = field(travel14, "silver_clicks_rejected")              # the rejects table's step-14 result
    rejected14_ok = expired(rejected14) or (isinstance(rejected14, dict) and rejected14.get("state") == "SUCCEEDED" and rejected14.get("row_count") == 0)  # its step-8 snapshot may still be the current one
    add("time_travel_rejected_step14", "step 14 time travel on silver_clicks_rejected fails (snapshot expired) or returns 0 rows of visit A", True, None if travel14 is None else rejected14_ok)  # visit A never had rejects
    add("bronze_clean", "Bronze key has exactly one version and no visit A", {"version_count": 1, "contains_visit": False}, load("bronze_versions_after.json"))  # step 15
    add("run3_input_files", "run 3 read exactly 1 input file", 1, field(load("run3_input_files.json"), "input_files"))  # bookmark reprocessed the rewritten file
    gold = load("gold_after_run3.json")                                 # Gold after run 3
    add("gold_counts", "Gold visits and clicks per month equal the local run minus visit A", {"visits_by_month": expected_after["gold_visits_by_month"], "clicks_by_month": expected_after["silver_clicks_by_month"]}, gold)  # step 17
    add("final_counts", "final per-month counts equal the local run minus visit A", expected_after, load("final_counts.json"))  # step 18
    return results                                                      # every check


# ── Command line ──────────────────────────────────────────────
def main() -> int:                                                      # entry point
    parser = argparse.ArgumentParser(description="T1b evidence helpers")  # description
    sub = parser.add_subparsers(dest="command", required=True)          # four commands
    pick = sub.add_parser("pick-visit")                                 # choose visit A
    pick.add_argument("--source", type=Path, required=True)             # UCI CSV
    pick.add_argument("--seed", type=int, default=DEFAULT_SEED)         # fixed seed
    pick.add_argument("--output", type=Path, required=True)             # private JSON (holds the real ID)
    exp = sub.add_parser("expected")                                    # local counts
    exp.add_argument("--source", type=Path, required=True)              # UCI CSV
    exp.add_argument("--without-visit", type=int, default=None)         # leave this visit out
    exp.add_argument("--output", type=Path, required=True)              # JSON file
    chk = sub.add_parser("checks")                                      # pass/fail lines
    chk.add_argument("--evidence-dir", type=Path, required=True)        # saved window results
    chk.add_argument("--expected-before", type=Path, required=True)     # counts with every visit
    chk.add_argument("--expected-after", type=Path, required=True)      # counts without visit A
    chk.add_argument("--output", type=Path, required=True)              # comparison JSON
    msk = sub.add_parser("mask")                                        # public-safe copy
    msk.add_argument("source", type=Path)                               # raw JSON
    msk.add_argument("target", type=Path)                               # masked JSON
    msk.add_argument("--visit-file", type=Path, default=None)           # private pick-visit JSON; its visit ID becomes "visit A"
    args = parser.parse_args()                                          # read options
    if args.command == "pick-visit":                                   # choose visit A
        visit_id, month = pick_visit(args.source, args.seed)            # pick
        args.output.parent.mkdir(parents=True, exist_ok=True)           # folder
        args.output.write_text(json.dumps({"visit_id": visit_id, "month": month}), encoding="utf-8")  # private file
        print(json.dumps({"label": VISIT_LABEL, "month": month}))       # the console shows no ID
        return 0                                                        # success
    if args.command == "expected":                                     # local counts
        counts = expected_counts(args.source) if args.without_visit is None else expected_counts_without(args.source, args.without_visit)  # all or minus one
        args.output.parent.mkdir(parents=True, exist_ok=True)           # folder
        args.output.write_text(json.dumps(counts, indent=2), encoding="utf-8")  # save
        return 0                                                        # success
    if args.command == "mask":                                         # public-safe copy
        args.target.parent.mkdir(parents=True, exist_ok=True)           # folder
        raw = json.loads(args.source.read_text(encoding="utf-8"))       # raw JSON
        visit_id = json.loads(args.visit_file.read_text(encoding="utf-8"))["visit_id"] if args.visit_file else None  # ID read from the private file, never typed
        args.target.write_text(json.dumps(mask_everything(raw, visit_id), indent=2), encoding="utf-8")  # save masked
        return 0                                                        # success
    results = t1b_checks(args.evidence_dir, json.loads(args.expected_before.read_text(encoding="utf-8")), json.loads(args.expected_after.read_text(encoding="utf-8")))  # run checks
    args.output.parent.mkdir(parents=True, exist_ok=True)               # folder
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")  # save
    print(json.dumps({name: entry["pass"] for name, entry in results.items()}))  # short summary
    return 0 if results and all(entry["pass"] for entry in results.values()) else 1  # fail on any mismatch


if __name__ == "__main__":                                              # run as a script
    sys.exit(main())                                                    # exit code for the window script
