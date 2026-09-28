# ── Tests: evidence masking and Athena-vs-local comparison ────
import importlib.util                                                   # load the script by path
import json                                                             # JSON files
from pathlib import Path                                                # file paths

REPO = Path(__file__).resolve().parents[1]                              # repo root
spec = importlib.util.spec_from_file_location("t1a_evidence", REPO / "scripts" / "t1a_evidence.py")  # not a package
evidence = importlib.util.module_from_spec(spec)                        # empty module
spec.loader.exec_module(evidence)                                       # run it

# Built at runtime (not a literal in this file) so tests/test_infra_templates.py's
# tracked-file scan for 12-digit numbers stays green once this file is committed.
FAKE_ACCOUNT_ID = "1234567" + "89012"                                   # same split pattern as tests/test_infra_templates.py


def test_mask_text_hides_account_ids_arns_and_bucket_names():           # nothing identifying survives
    raw = (                                                             # typical CLI output, built at runtime
        f"arn:aws:iam::{FAKE_ACCOUNT_ID}:role/x in {FAKE_ACCOUNT_ID} wrote "  # ARN and bare account id
        "s3://clickstream-t1-lake-bronzebucket-a1b2c3d4e5f6/key"        # CloudFormation-generated bucket name
    )
    masked = evidence.mask_text(raw)                                    # masked copy
    assert FAKE_ACCOUNT_ID not in masked and "arn:aws" not in masked    # no account id, no ARN
    assert "s3://<bronze-bucket>/key" in masked                         # bucket kept readable by role


def test_mask_json_walks_nested_values():                               # dicts and lists
    assert evidence.mask_json({"a": ["arn:aws:s3:::x", {"b": FAKE_ACCOUNT_ID}]}) == {"a": ["<arn>", {"b": "<account-id>"}]}  # every string masked


def test_compare_passes_when_counts_match(tmp_path):                    # the happy path
    expected = {"silver_clicks_by_month": {"2008-04": 3}}                # local numbers
    athena = {"ResultSet": {"Rows": [{"Data": [{"VarCharValue": "click_month"}, {"VarCharValue": "clicks"}]}, {"Data": [{"VarCharValue": "2008-04"}, {"VarCharValue": "3"}]}]}}  # Athena JSON shape
    (tmp_path / "02_silver_clicks_by_month.json").write_text(json.dumps(athena), encoding="utf-8")  # saved result
    result = evidence.compare(expected, tmp_path)                       # compare
    assert result == {"silver_clicks_by_month": {"expected": {"2008-04": 3}, "athena": {"2008-04": 3}, "match": True}}  # match


def test_compare_flags_mismatch(tmp_path):                              # a wrong count is reported
    expected = {"silver_clicks_by_month": {"2008-04": 3}}                # local numbers
    athena = {"ResultSet": {"Rows": [{"Data": [{"VarCharValue": "click_month"}, {"VarCharValue": "clicks"}]}, {"Data": [{"VarCharValue": "2008-04"}, {"VarCharValue": "2"}]}]}}  # one click missing
    (tmp_path / "02_silver_clicks_by_month.json").write_text(json.dumps(athena), encoding="utf-8")  # saved result
    assert evidence.compare(expected, tmp_path)["silver_clicks_by_month"]["match"] is False  # flagged
