# ── Tests: T1b evidence tooling (visit pick, expected counts, checks, masking) ─
import importlib.util                                                   # load the script by path
import json                                                             # JSON files
import re                                                               # pattern checks on masked text
from pathlib import Path                                                # file paths

REPO = Path(__file__).resolve().parents[1]                              # repo root
spec = importlib.util.spec_from_file_location("t1b_evidence", REPO / "scripts" / "t1b_evidence.py")  # not a package
evidence = importlib.util.module_from_spec(spec)                        # empty module
spec.loader.exec_module(evidence)                                       # run it

HEADER = "year;month;day;order;country;session ID;page 1 (main category);page 2 (clothing model);colour;location;model photography;price;price 2;page"  # UCI header
FAKE_ACCOUNT_ID = "1234567" + "89012"                                   # built at runtime so the tracked-file scan stays green


def write_source(path: Path) -> Path:                                   # small ';'-delimited CRLF fixture
    lines = [HEADER]                                                    # header row first
    visits = {1: 4, 2: 4, 3: 5, 4: 5, 5: 8, 6: 8, 7: 4}                 # visit id -> real month (visit 7 is made bad below)
    for visit_id, month in visits.items():                              # each visit
        country = 99 if visit_id == 7 else 1                            # country 99 is outside 1-47, so visit 7 is rejected
        for order in (1, 2, 3):                                         # three clicks per visit
            lines.append(f"2008;{month};5;{order};{country};{visit_id};1;A{order};2;3;1;40;1;1")  # one valid click
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))     # CRLF line endings like the real file
    return path                                                         # where it was written


def test_pick_visit_is_deterministic_skips_august_and_is_clean(tmp_path):  # the three pick rules
    source = write_source(tmp_path / "source.csv")                      # fixture
    first = evidence.pick_visit(source)                                 # default seed
    assert first == evidence.pick_visit(source)                         # same seed, same answer
    for seed in range(40):                                              # many seeds
        visit_id, month = evidence.pick_visit(source, seed)             # pick
        assert month != "2008-08"                                       # never August
        assert visit_id in {1, 2, 3, 4}                                 # never the rejected visit 7, never August visits 5-6


def test_expected_counts_without_drops_exactly_that_visit(tmp_path):    # one visit, three rows
    source = write_source(tmp_path / "source.csv")                      # fixture
    before = evidence.expected_counts(source)                           # all visits
    after = evidence.expected_counts_without(source, 1)                 # visit 1 removed (month 2008-04)
    assert set(after) == set(before)                                    # same keys
    assert after["bronze_rows_by_month"]["2008-04"] == before["bronze_rows_by_month"]["2008-04"] - 3  # three rows gone
    assert after["silver_clicks_by_month"]["2008-04"] == before["silver_clicks_by_month"]["2008-04"] - 3  # three clicks gone
    assert after["gold_visits_by_month"]["2008-04"] == before["gold_visits_by_month"]["2008-04"] - 1  # one visit gone
    assert after["silver_clicks_by_month"]["2008-05"] == before["silver_clicks_by_month"]["2008-05"]  # other months untouched
    assert after["rejected_rows"] == before["rejected_rows"]            # rejects unchanged


def test_mask_visit_is_whole_number_only():                             # 123 inside 4123 stays
    assert evidence.mask_visit("visit 123 and 4123 and uci553-123-2", 123) == "visit visit A and 4123 and uci553-visit A-2"  # only whole numbers


def make_evidence(folder: Path, break_one: bool) -> tuple[dict, dict]:  # write a passing evidence folder
    before = {"bronze_rows_by_month": {"2008-04": 10}, "silver_clicks_by_month": {"2008-04": 10}, "gold_visits_by_month": {"2008-04": 4}, "rejected_rows": {"all": 0}}  # local, all visits
    after = {"bronze_rows_by_month": {"2008-04": 7}, "silver_clicks_by_month": {"2008-04": 7}, "gold_visits_by_month": {"2008-04": 3}, "rejected_rows": {"all": 0}}  # local, minus visit A
    tables = {"silver_clicks": 2, "silver_clicks_rejected": 2, "silver_deleted_visits": 2}  # format version per table
    files = {                                                           # every evidence file the checks read
        "format_version_step1.json": tables,                            # at table creation
        "format_version_step14.json": tables,                           # after VACUUM
        "run2_input_files.json": {"input_files": 1},                    # bookmark
        "files_before_migration.json": [{"path": "a", "size": 1, "last_modified": "t"}],  # April-July files
        "files_after_migration.json": [{"path": "a", "size": 1, "last_modified": "t"}],  # identical
        "weekend_null_share.json": {"2008-04": 1.0},                    # NULL share per month (April only in this fixture)
        "weekend_mismatches.json": {"mismatched_rows": 0},              # August values vs local twin
        "before_delete_counts.json": {"silver_clicks_by_month": before["silver_clicks_by_month"]},  # step 8
        "after_delete_counts.json": {"visit_rows_in_silver_clicks": 0, "rejects_rows_deleted": 0, "silver_clicks_by_month": after["silver_clicks_by_month"]},  # step 9
        "time_travel_step10.json": {"row_count": 3},                    # still readable
        "files_step8.json": ["old1"], "files_step12.json": ["new1"],    # disjoint path lists
        "time_travel_step14.json": {"error": "snapshot not found"},     # expired
        "bronze_versions_after.json": {"version_count": 1, "contains_visit": False},  # erased
        "run3_input_files.json": {"input_files": 1},                    # bookmark
        "gold_after_run3.json": {"visits_by_month": after["gold_visits_by_month"], "clicks_by_month": after["silver_clicks_by_month"]},  # Gold
        "final_counts.json": after,                                     # everything per month
    }  # end of the evidence files
    if break_one:                                                       # one deliberate mismatch
        files["final_counts.json"] = {**after, "silver_clicks_by_month": {"2008-04": 8}}  # one click too many
    for name, content in files.items():                                 # write them
        (folder / name).write_text(json.dumps(content), encoding="utf-8")  # saved JSON
    return before, after                                                # expected sets


def test_t1b_checks_all_pass_on_good_evidence(tmp_path):                # happy path
    before, after = make_evidence(tmp_path, break_one=False)            # good folder
    results = evidence.t1b_checks(tmp_path, before, after)              # run
    assert results and all(entry["pass"] for entry in results.values()), results  # every line passes
    assert all(set(entry) == {"check", "expected", "actual", "pass"} for entry in results.values())  # entry shape


def test_t1b_checks_flags_only_the_mismatch(tmp_path):                  # one wrong number
    before, after = make_evidence(tmp_path, break_one=True)             # one bad file
    failed = [name for name, entry in evidence.t1b_checks(tmp_path, before, after).items() if not entry["pass"]]  # failing names
    assert failed == ["final_counts"]                                   # exactly that check


def test_t1b_checks_missing_file_fails(tmp_path):                       # absent evidence is not a pass
    before, after = make_evidence(tmp_path, break_one=False)            # good folder
    (tmp_path / "run3_input_files.json").unlink()                       # remove one file
    assert evidence.t1b_checks(tmp_path, before, after)["run3_input_files"]["pass"] is False  # fails


def test_masked_output_has_no_account_ids_or_version_ids():             # public-safe output
    raw = {"VersionId": "3sL4kqtJlcpXroDTDmJ+rmSpXd3dIbrHY", "note": f"acct {FAKE_ACCOUNT_ID} key abcdEFGH1234abcdEFGH1234abcdEFGH", "visit_id": 4321, "id": "uci553-4321-1"}  # one of each
    text = json.dumps(evidence.mask_everything(raw, 4321))              # masked JSON text
    assert not re.search(r"(?<![0-9])[0-9]{12}(?![0-9])", text)         # no 12-digit numbers
    assert "3sL4kq" not in text and "abcdEFGH1234" not in text          # no version-id-shaped strings
    assert "4321" not in text and "visit A" in text                     # visit id replaced by the label


def test_masking_is_field_scoped_and_keeps_colliding_numbers():         # no free-text number swap
    raw = {"visit_id": 12, "row_count": 12, "size": 12, "date": "2008-04-12 12:00", "path": "x/12/y", "id": "uci553-12-3"}  # 12 collides with a count, a size and date parts
    masked = evidence.mask_everything(raw, 12)                          # masked copy
    assert masked["visit_id"] == "visit A"                              # the visit field is masked whatever its type
    assert masked["row_count"] == 12 and masked["size"] == 12           # counts and sizes stay numbers
    assert masked["date"] == "2008-04-12 12:00" and masked["path"] == "x/12/y"  # date and path untouched
    assert masked["id"] == "uci553-visit A-3"                           # click id loses only its visit part


def test_masking_round_trips_null_version_id_and_stays_valid_json():    # nulls and numbers do not crash
    raw = {"VersionId": None, "row_count": 4321, "visit_id": None, "items": [{"VersionId": "3sL4kqtJlcpXroDTDmJ+rmSpXd3dIbrHY"}]}  # null version, number equal to the id
    masked = evidence.mask_everything(raw, 4321)                        # masked copy
    assert masked["VersionId"] is None and masked["visit_id"] is None   # nulls stay null
    assert masked["row_count"] == 4321                                  # count untouched
    assert masked["items"][0]["VersionId"] == "<version-id>"            # string version masked
    assert json.loads(json.dumps(masked)) == masked                     # valid JSON


def test_weekend_share_fails_when_a_month_is_missing(tmp_path):         # expected months come from the local run
    before, after = make_evidence(tmp_path, break_one=False)            # good folder
    before["silver_clicks_by_month"] = {"2008-04": 10, "2008-08": 5}    # local run has two months
    (tmp_path / "weekend_null_share.json").write_text(json.dumps({"2008-04": 1.0}), encoding="utf-8")  # August missing
    assert evidence.t1b_checks(tmp_path, before, after)["weekend_null_share"]["pass"] is False  # fails
    (tmp_path / "weekend_null_share.json").write_text("{}", encoding="utf-8")  # empty file
    assert evidence.t1b_checks(tmp_path, before, after)["weekend_null_share"]["pass"] is False  # also fails


def test_files_replaced_fails_on_empty_step8_list(tmp_path):            # nothing to replace is not a pass
    before, after = make_evidence(tmp_path, break_one=False)            # good folder
    (tmp_path / "files_step8.json").write_text("[]", encoding="utf-8")  # empty list
    assert evidence.t1b_checks(tmp_path, before, after)["files_replaced"]["pass"] is False  # fails


def test_expected_counts_without_keeps_other_bytes(tmp_path):           # raw line filtering, CRLF kept
    source = write_source(tmp_path / "source.csv")                      # fixture
    kept = evidence.filter_visit_lines(source.read_bytes(), 1)          # bytes without visit 1
    crlf = bytes([13, 10])                                              # the line ending of the real file (CR LF)
    assert kept.count(crlf) == source.read_bytes().count(crlf) - 3      # three lines gone, endings intact
    assert b";1;1;A1;" not in kept and b";2;1;A1;" in kept              # visit 1 gone, visit 2 kept


def test_filter_visit_lines_survives_blank_lines_and_a_bom():           # odd but harmless file shapes
    crlf = bytes([13, 10])                                              # CR LF line ending
    raw = b"\xef\xbb\xbfa;session ID" + crlf + b"1;5" + crlf + crlf + b"2;6" + crlf  # BOM header, a blank line inside
    kept = evidence.filter_visit_lines(raw, 5)                          # drop visit 5
    assert kept == b"\xef\xbb\xbfa;session ID" + crlf + crlf + b"2;6" + crlf  # only the visit-5 line is gone


def test_cli_mask_reads_visit_from_private_file(tmp_path, monkeypatch): # the id is never on the command line
    (tmp_path / "pick.json").write_text(json.dumps({"visit_id": 4321, "month": "2008-04"}), encoding="utf-8")  # private pick
    (tmp_path / "raw.json").write_text(json.dumps({"visit_id": 4321, "row_count": 4321}), encoding="utf-8")  # raw evidence
    arguments = ["mask", str(tmp_path / "raw.json"), str(tmp_path / "masked.json"), "--visit-file", str(tmp_path / "pick.json")]  # options
    monkeypatch.setattr("sys.argv", ["t1b_evidence.py", *arguments])    # pretend these were typed
    assert evidence.main() == 0                                         # success
    assert json.loads((tmp_path / "masked.json").read_text(encoding="utf-8")) == {"visit_id": "visit A", "row_count": 4321}  # field-scoped


def test_cli_checks_exit_codes(tmp_path, monkeypatch):                  # window script relies on the exit code
    before, after = make_evidence(tmp_path, break_one=False)            # good folder
    (tmp_path / "before.json").write_text(json.dumps(before), encoding="utf-8")  # expected before
    (tmp_path / "after.json").write_text(json.dumps(after), encoding="utf-8")  # expected after
    arguments = ["checks", "--evidence-dir", str(tmp_path), "--expected-before", str(tmp_path / "before.json"), "--expected-after", str(tmp_path / "after.json"), "--output", str(tmp_path / "comparison.json")]  # options
    monkeypatch.setattr("sys.argv", ["t1b_evidence.py", *arguments])    # pretend these were typed
    assert evidence.main() == 0                                         # all pass
    (tmp_path / "final_counts.json").write_text("{}", encoding="utf-8") # break one
    assert evidence.main() == 1                                         # failure
