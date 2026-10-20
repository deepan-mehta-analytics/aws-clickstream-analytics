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
    def __init__(self, body: bytes, extra_versions: int = 0, delete_marker: bool = False, truncated: bool = False, encryption: str = "AES256", put_returns: str | None = None, extra_after_put: bool = False, delete_error: Exception | None = None, swap_after_delete: bool = False):  # starting state and failure switches
        self.truncated = truncated                                      # listings claim to be cut short
        self.encryption = encryption                                    # encryption the original object reports
        self.put_returns = put_returns                                  # VersionId the put reports instead of the stored one
        self.extra_after_put = extra_after_put                          # a concurrent writer adds a version after the put
        self.delete_error = delete_error                                # error raised by delete_object
        self.swap_after_delete = swap_after_delete                      # the surviving version has another id after the delete
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
        return {"Versions": [{"Key": v["Key"], "VersionId": v["VersionId"]} for v in self.versions] + [other], "DeleteMarkers": list(self.markers), "IsTruncated": self.truncated}  # other key must be filtered out

    def get_object(self, Bucket, Key, VersionId=None):                  # read one version
        self.calls.append("get")                                        # record
        version = next(v for v in self.versions if VersionId in (None, v["VersionId"]))  # the requested version
        return {"Body": io.BytesIO(version["Body"]), "ContentType": version["ContentType"], "Metadata": dict(version["Metadata"]), "ServerSideEncryption": self.encryption}  # like boto3

    def put_object(self, **kwargs):                                     # upload a new version
        self.calls.append("put")                                        # record
        self.puts.append(kwargs)                                        # keep the arguments
        self._add(kwargs["Body"], kwargs["ContentType"], kwargs["Metadata"])  # becomes a new version
        stored_id = self.versions[-1]["VersionId"]                      # the id really stored
        if self.extra_after_put:                                        # concurrent writer
            self._add(kwargs["Body"], kwargs["ContentType"], kwargs["Metadata"])  # a third version appears
        return {"VersionId": self.put_returns or stored_id}             # like boto3

    def delete_object(self, Bucket, Key, VersionId):                    # delete one named version
        self.calls.append("delete")                                     # record
        if self.delete_error is not None:                               # simulated failure
            raise self.delete_error                                     # propagate it
        self.deleted.append(VersionId)                                  # remember which
        self.versions = [v for v in self.versions if v["VersionId"] != VersionId]  # gone for good
        if self.swap_after_delete:                                      # simulate a concurrent replacement
            self.versions[0]["VersionId"] = "version-9998"              # different survivor
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


# ── Hardening (fix round 1) ───────────────────────────────────
def test_a_truncated_listing_is_refused():                              # a cut-short listing cannot be trusted
    s3 = FakeS3(csv_bytes(["2008;10;7;a"]), truncated=True)             # IsTruncated true
    with pytest.raises(erase.UnexpectedVersionsError):                  # refused
        erase.erase_visit(s3, BUCKET, KEY, 7)                           # run
    assert "put" not in s3.calls                                        # nothing written


def test_non_aes256_encryption_is_refused():                            # no silent downgrade from SSE-KMS
    s3 = FakeS3(csv_bytes(["2008;10;7;a"]), encryption="aws:kms")       # original uses KMS
    with pytest.raises(erase.UnexpectedVersionsError):                  # refused
        erase.erase_visit(s3, BUCKET, KEY, 7)                           # run
    assert "put" not in s3.calls                                        # nothing written


def test_a_different_new_version_is_refused_without_a_delete():         # put id not in the listing
    s3 = FakeS3(csv_bytes(["2008;10;7;a"]), put_returns="version-7777")  # put reports an id that is not stored
    with pytest.raises(erase.UnexpectedVersionsError):                  # refused
        erase.erase_visit(s3, BUCKET, KEY, 7)                           # run
    assert "delete" not in s3.calls and len(s3.versions) == 2           # old version survives


def test_a_third_version_after_the_put_is_refused_without_a_delete():   # concurrent writer
    s3 = FakeS3(csv_bytes(["2008;10;7;a"]), extra_after_put=True)       # three versions after the put
    with pytest.raises(erase.UnexpectedVersionsError):                  # refused
        erase.erase_visit(s3, BUCKET, KEY, 7)                           # run
    assert "delete" not in s3.calls and len(s3.versions) == 3           # nothing deleted


def test_a_failed_delete_propagates_and_leaves_two_versions():          # recovery state
    s3 = FakeS3(csv_bytes(["2008;10;7;a"]), delete_error=RuntimeError("boom"))  # delete fails
    with pytest.raises(RuntimeError):                                   # error propagates
        erase.erase_visit(s3, BUCKET, KEY, 7)                           # run
    assert len(s3.versions) == 2                                        # old and new both remain


def test_a_different_survivor_after_the_delete_is_refused():            # final identity check
    s3 = FakeS3(csv_bytes(["2008;10;7;a"]), swap_after_delete=True)     # survivor id differs from the put's
    with pytest.raises(erase.UnexpectedVersionsError):                  # refused
        erase.erase_visit(s3, BUCKET, KEY, 7)                           # run


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


def run_cli(tmp_path, monkeypatch, s3, pick=None):                      # run main() against a fake client
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=lambda *args, **kwargs: s3))  # fake boto3
    (tmp_path / "pick.json").write_text(json.dumps(pick or {"visit_id": 4321, "month": "2008-04"}), encoding="utf-8")  # private pick
    monkeypatch.setattr("sys.argv", ["t1b_erase_visit_from_bronze.py", "--bucket", BUCKET, "--key", KEY, "--visit-file", str(tmp_path / "pick.json")])  # pretend typed
    return erase.main()                                                 # exit code


def test_cli_client_error_prints_only_the_code(tmp_path, monkeypatch, capsys):  # AWS error text can hold ids
    from botocore.exceptions import ClientError                         # the real error type
    secret = "version-SECRET-4321"                                      # an id inside the message text
    error = ClientError({"Error": {"Code": "NoSuchVersion", "Message": secret}}, "DeleteObject")  # carries the id
    s3 = FakeS3(csv_bytes(["2008;10;4321;a"]), delete_error=error)      # delete raises it
    assert run_cli(tmp_path, monkeypatch, s3) != 0                      # non-zero exit
    captured = capsys.readouterr()                                      # stdout and stderr
    assert "NoSuchVersion" in captured.err and secret not in captured.out + captured.err  # code only


def test_cli_bad_visit_file_prints_a_fixed_message(tmp_path, monkeypatch, capsys):  # unreadable pick file
    assert run_cli(tmp_path, monkeypatch, FakeS3(b""), pick={"month": "2008-04"}) != 0  # no visit_id key
    assert "visit file" in capsys.readouterr().err                      # fixed message


def test_cli_refusal_prints_counts_only_and_fails(tmp_path, monkeypatch, capsys):  # known refusals
    s3 = FakeS3(csv_bytes(["2008;10;4321;a"]), extra_versions=1)        # two versions
    assert run_cli(tmp_path, monkeypatch, s3) != 0                      # non-zero exit
    assert "version-" not in capsys.readouterr().err                    # no ids
