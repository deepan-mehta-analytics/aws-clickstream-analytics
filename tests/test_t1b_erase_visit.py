# ── Tests: Bronze visit-erase script (row removal, version-safe rewrite, CLI) ─
import importlib.util                                                   # load the script by path
import io                                                               # in-memory bodies
import json                                                             # pick-visit file
import sys                                                              # fake boto3 module
import types                                                            # build the fake module
from pathlib import Path                                                # file paths

import pytest                                                           # raises and fixtures

REPO = Path(__file__).resolve().parents[1]                              # repo root
spec = importlib.util.spec_from_file_location("t1b_erase_visit_from_bronze", REPO / "scripts" / "t1b_erase_visit_from_bronze.py")  # not a package
erase = importlib.util.module_from_spec(spec)                           # empty module
spec.loader.exec_module(erase)                                          # run it

CRLF = bytes([13, 10])                                                  # CR LF line ending
HEADER = b"year;price;session ID;page" + CRLF                           # small header (session ID is the third column)
BUCKET = "example-bronze-bucket"                                        # placeholder bucket
KEY = "bronze/source/clicks.csv"                                        # placeholder key


class FakeS3:                                                           # in-memory versioned S3 client that records calls
    def __init__(self, body: bytes, extra_versions: int = 0, delete_marker: bool = False):  # starting state
        self.calls = []                                                 # ordered call names
        self.counter = 0                                                # version id counter
        self.versions = []                                              # stored versions of KEY, oldest first
        self.markers = []                                               # delete markers of KEY
        self.puts = []                                                  # put_object keyword arguments
        self.deleted = []                                               # VersionIds that were deleted
        self._add(body, "text/csv", {"source": "uci"})                  # first version
        for _ in range(extra_versions):                                 # additional versions
            self._add(body, "text/csv", {"source": "uci"})              # same content
        if delete_marker:                                               # a delete marker too
            self.markers.append({"Key": KEY, "VersionId": "marker-0001"})  # marker for KEY

    def _add(self, body, content_type, metadata):                       # store one more version
        self.counter += 1                                               # next id
        self.versions.append({"Key": KEY, "VersionId": f"version-{self.counter:04d}", "Body": body, "ContentType": content_type, "Metadata": metadata})  # new version

    def list_object_versions(self, Bucket, Prefix):                     # real boto3 name and arguments
        self.calls.append("list")                                       # record
        other = {"Key": KEY + ".other", "VersionId": "other-0001"}      # a different key sharing the prefix
        return {"Versions": [{"Key": v["Key"], "VersionId": v["VersionId"]} for v in self.versions] + [other], "DeleteMarkers": list(self.markers)}  # other key must be filtered out

    def get_object(self, Bucket, Key, VersionId=None):                  # read one version
        self.calls.append("get")                                        # record
        version = next(v for v in self.versions if VersionId in (None, v["VersionId"]))  # the requested version
        return {"Body": io.BytesIO(version["Body"]), "ContentType": version["ContentType"], "Metadata": dict(version["Metadata"])}  # like boto3

    def put_object(self, **kwargs):                                     # upload a new version
        self.calls.append("put")                                        # record
        self.puts.append(kwargs)                                        # keep the arguments
        self._add(kwargs["Body"], kwargs["ContentType"], kwargs["Metadata"])  # becomes a new version
        return {"VersionId": self.versions[-1]["VersionId"]}            # like boto3

    def delete_object(self, Bucket, Key, VersionId):                    # delete one named version
        self.calls.append("delete")                                     # record
        self.deleted.append(VersionId)                                  # remember which
        self.versions = [v for v in self.versions if v["VersionId"] != VersionId]  # gone for good
        return {}                                                       # like boto3


def csv_bytes(rows, final_newline=True, ending=CRLF) -> bytes:          # build a small file
    body = HEADER.replace(CRLF, ending)                                 # header with the chosen ending
    lines = [row.encode() for row in rows]                              # rows as bytes
    body += ending.join(lines)                                          # joined rows
    return body + (ending if final_newline else b"")                    # optional final newline


# ── remove_visit_rows ─────────────────────────────────────────
def test_remove_visit_rows_keeps_crlf_and_order():                      # line endings survive
    raw = csv_bytes(["2008;10;7;a", "2008;11;8;b", "2008;12;7;c"])      # visit 7 twice
    new, removed = erase.remove_visit_rows(raw, 7)                      # drop visit 7
    assert removed == 2 and new == HEADER + b"2008;11;8;b" + CRLF       # only visit 8 remains


def test_remove_visit_rows_keeps_a_missing_final_newline():             # no trailing newline stays absent
    raw = csv_bytes(["2008;10;7;a", "2008;11;8;b"], final_newline=False)  # ends without newline
    new, removed = erase.remove_visit_rows(raw, 7)                      # drop visit 7
    assert removed == 1 and new == HEADER + b"2008;11;8;b"              # still no final newline


def test_remove_visit_rows_matches_only_the_session_id_column():        # value 7 in price must not match
    raw = csv_bytes(["2008;7;8;a", "2008;9;7;b"])                       # price 7 on visit 8; visit 7 in session ID
    new, removed = erase.remove_visit_rows(raw, 7)                      # drop visit 7
    assert removed == 1 and b"2008;7;8;a" in new                        # the price-7 row stays


def test_remove_visit_rows_zero_matches_returns_same_bytes():           # nothing to remove
    raw = csv_bytes(["2008;10;8;a"])                                    # no visit 7
    assert erase.remove_visit_rows(raw, 7) == (raw, 0)                  # unchanged


def test_remove_visit_rows_survives_a_bom_and_blank_lines():            # same tolerance as the evidence helper
    raw = b"\xef\xbb\xbfa;session ID" + CRLF + b"1;5" + CRLF + CRLF + b"2;6" + CRLF + b"3" + CRLF  # BOM, blank, short line
    new, removed = erase.remove_visit_rows(raw, 5)                      # drop visit 5
    assert removed == 1 and new == b"\xef\xbb\xbfa;session ID" + CRLF + CRLF + b"2;6" + CRLF + b"3" + CRLF  # only visit 5 gone


# ── erase_visit ───────────────────────────────────────────────
def test_erase_visit_happy_path_call_order_and_result():                # list, get, put, list, delete old, list
    s3 = FakeS3(csv_bytes(["2008;10;7;a", "2008;11;8;b"]))              # one version
    old_version = s3.versions[0]["VersionId"]                           # the version that must be deleted
    result = erase.erase_visit(s3, BUCKET, KEY, 7)                      # run
    assert s3.calls == ["list", "get", "put", "list", "delete", "list"]  # exact order
    assert s3.deleted == [old_version]                                  # deleted by its VersionId
    assert result == {"rows_removed": 1, "versions_before": 1, "versions_after": 1}  # summary
    assert s3.versions[0]["Body"] == HEADER + b"2008;11;8;b" + CRLF     # the stored file no longer has visit 7


def test_erase_visit_copies_content_type_encryption_and_metadata():     # the new version looks like the old one
    s3 = FakeS3(csv_bytes(["2008;10;7;a", "2008;11;8;b"]))              # one version
    erase.erase_visit(s3, BUCKET, KEY, 7)                               # run
    put = s3.puts[0]                                                    # the upload
    assert put["ContentType"] == "text/csv" and put["ServerSideEncryption"] == "AES256" and put["Metadata"] == {"source": "uci"}  # same attributes
    assert put["Bucket"] == BUCKET and put["Key"] == KEY                # same target


def test_two_versions_before_is_refused_without_a_put():                # only a single version is safe
    s3 = FakeS3(csv_bytes(["2008;10;7;a"]), extra_versions=1)           # two versions
    with pytest.raises(erase.UnexpectedVersionsError):                  # refused
        erase.erase_visit(s3, BUCKET, KEY, 7)                           # run
    assert "put" not in s3.calls and "delete" not in s3.calls           # nothing written


def test_a_delete_marker_is_refused():                                  # a marker means an earlier delete
    s3 = FakeS3(csv_bytes(["2008;10;7;a"]), delete_marker=True)         # marker present
    with pytest.raises(erase.UnexpectedVersionsError):                  # refused
        erase.erase_visit(s3, BUCKET, KEY, 7)                           # run
    assert "put" not in s3.calls                                        # nothing written


def test_visit_not_in_file_is_refused_without_a_put():                  # nothing to erase
    s3 = FakeS3(csv_bytes(["2008;10;8;a"]))                             # no visit 7
    with pytest.raises(erase.NothingToEraseError):                      # refused
        erase.erase_visit(s3, BUCKET, KEY, 7)                           # run
    assert "put" not in s3.calls and "delete" not in s3.calls           # nothing written


# ── Command line ──────────────────────────────────────────────
def test_cli_reads_the_visit_from_the_file_and_prints_no_version_id(tmp_path, monkeypatch, capsys):  # ID and versions stay private
    s3 = FakeS3(csv_bytes(["2008;10;4321;a", "2008;11;8;b"]))           # visit 4321 present
    fake_boto3 = types.SimpleNamespace(client=lambda *args, **kwargs: s3)  # boto3.client returns the fake
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)               # main() imports boto3 inside
    (tmp_path / "pick.json").write_text(json.dumps({"visit_id": 4321, "month": "2008-04"}), encoding="utf-8")  # private pick
    arguments = ["--bucket", BUCKET, "--key", KEY, "--visit-file", str(tmp_path / "pick.json")]  # options
    monkeypatch.setattr("sys.argv", ["t1b_erase_visit_from_bronze.py", *arguments])  # pretend typed
    assert erase.main() == 0                                            # success
    output = capsys.readouterr().out                                    # what was printed
    assert json.loads(output) == {"rows_removed": 1, "versions_before": 1, "versions_after": 1}  # result dict only
    assert "version-" not in output and "4321" not in output            # no VersionId, no visit ID
