# ── Tests: ingest Lambda (no network, stubbed S3) ─────────────
import hashlib                                                          # checksums
import importlib.util                                                   # load the handler from its folder
import inspect                                                          # introspect function signatures
import io                                                               # in-memory zip
import zipfile                                                          # build a fake UCI zip
from pathlib import Path                                                # file paths

import boto3                                                            # real S3 client, stubbed
import pytest                                                           # test framework
from botocore.stub import ANY, Stubber                                  # fake S3 responses

HANDLER_PATH = Path(__file__).resolve().parents[1] / "lambdas" / "ingest_source" / "handler.py"  # code under test
spec = importlib.util.spec_from_file_location("ingest_handler", HANDLER_PATH)  # not a package: load by path
ingest = importlib.util.module_from_spec(spec)                          # empty module
spec.loader.exec_module(ingest)                                         # run it

HEADER = "year;month;day;order;country;session ID;page 1 (main category);page 2 (clothing model);colour;location;model photography;price;price 2;page"  # real UCI header
CSV_TEXT = "\r\n".join([HEADER, "2008;4;1;1;29;1;1;A13;1;5;1;28;2;1", "2008;4;1;2;29;1;1;A16;1;6;1;33;2;1", "2008;8;13;1;29;9;2;B4;3;2;1;52;1;1"]) + "\r\n"  # CRLF like the real file
LAMBDA_TIMEOUT_SECONDS = 60                                             # Lambda function timeout (fixed in global constraints)


@pytest.fixture(autouse=True)                                           # every test in this file
def fake_aws_credentials(monkeypatch):                                  # never read the owner's real AWS sign-in
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")                  # environment credentials come first in boto3's chain
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")              # fake secret
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")                  # fake session token
    monkeypatch.setenv("AWS_CONFIG_FILE", str(Path(__file__).parent / "no-such-aws-config"))   # ignore ~/.aws/config (an `aws login` profile needs botocore[crt])
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(Path(__file__).parent / "no-such-aws-credentials"))   # ignore ~/.aws/credentials


def fake_zip(text=CSV_TEXT):                                            # zip holding the CSV, like UCI's
    buffer = io.BytesIO()                                               # in memory
    with zipfile.ZipFile(buffer, "w") as archive:                       # write a zip
        archive.writestr(ingest.CSV_NAME, text)                         # same file name as UCI
    return buffer.getvalue()                                            # zip bytes


def test_split_by_month_keeps_header_and_rows_and_uses_lf():            # rows unchanged, LF endings
    parts = ingest.split_by_month(CSV_TEXT, ["2008-04", "2008-08"])     # two months
    assert parts["2008-04"] == HEADER + "\n" + "2008;4;1;1;29;1;1;A13;1;5;1;28;2;1\n2008;4;1;2;29;1;1;A16;1;6;1;33;2;1\n"  # April only
    assert parts["2008-08"].splitlines() == [HEADER, "2008;8;13;1;29;9;2;B4;3;2;1;52;1;1"]  # August only


def test_check_md5_rejects_changed_file():                              # the source file changed upstream
    with pytest.raises(ingest.IngestError, match="MD5"):                # clear failure
        ingest.check_md5(b"not the UCI file", "bf7a47493025ffb35eebc7a65caf9988")  # wrong bytes


def test_download_retries_with_backoff_then_succeeds():                 # transient network errors
    calls, waits = [], []                                               # what happened

    class Response(io.BytesIO):                                         # context-manager response
        def __exit__(self, *exc):                                       # closing does nothing special
            return False                                                # do not swallow errors

    def opener(url, timeout):                                           # fails twice, then works
        calls.append(url)                                               # count attempts
        if len(calls) < 3:                                              # first two attempts
            raise OSError("temporary failure")                          # network error
        return Response(b"zip-bytes")                                   # third attempt succeeds
    assert ingest.download("https://example.test/x.zip", opener=opener, sleep=waits.append) == b"zip-bytes"  # final bytes
    assert waits == [1.0, 2.0]                                          # exponential backoff


def test_download_gives_up_after_three_attempts():                      # permanent failure
    def opener(url, timeout):                                           # always fails
        raise OSError("down")                                           # network error
    with pytest.raises(ingest.IngestError, match="3 attempts"):          # clear failure
        ingest.download("https://example.test/x.zip", opener=opener, sleep=lambda seconds: None)  # no real waiting


def test_download_retry_budget_fits_in_lambda_timeout():                # worst case must not exceed Lambda timeout
    sig = inspect.signature(ingest.download)                            # download function signature
    attempts = sig.parameters["attempts"].default                       # number of retry attempts
    first_wait = sig.parameters["first_wait"].default                   # initial backoff wait (seconds)
    per_attempt_timeout = ingest.ATTEMPT_TIMEOUT_SECONDS                # timeout per attempt (seconds)
    total_time = attempts * per_attempt_timeout + first_wait + first_wait * 2.0  # worst case: all attempts timeout + waits
    assert total_time < LAMBDA_TIMEOUT_SECONDS                          # must fit inside Lambda timeout


def test_land_months_writes_new_month():                                # nothing there yet
    s3 = boto3.client("s3", region_name="ap-south-1")                   # client to stub
    with Stubber(s3) as stub:                                           # fake responses in order
        stub.add_client_error("head_object", service_error_code="404", http_status_code=404, expected_params={"Bucket": "bronze", "Key": "source_month=2008-04/clicks.csv"})  # not found
        stub.add_response("put_object", {}, {"Bucket": "bronze", "Key": "source_month=2008-04/clicks.csv", "Body": ANY, "ContentType": "text/csv", "Metadata": {"source-md5": "abc", "rows": "2"}, "ServerSideEncryption": "AES256"})  # write expected
        result = ingest.land_months(s3, "bronze", {"2008-04": HEADER + "\nr1\nr2\n"}, "abc")  # two data rows
    assert result == {"2008-04": {"rows": 2, "action": "written"}}      # reported


def test_land_months_skips_same_source_file():                          # Review Focus 5: no second S3 version
    s3 = boto3.client("s3", region_name="ap-south-1")                   # client to stub
    with Stubber(s3) as stub:                                           # only a head call is expected
        stub.add_response("head_object", {"Metadata": {"source-md5": "abc"}}, {"Bucket": "bronze", "Key": "source_month=2008-04/clicks.csv"})  # same file already there
        result = ingest.land_months(s3, "bronze", {"2008-04": HEADER + "\nr1\n"}, "abc")  # same source
        stub.assert_no_pending_responses()                              # no put_object happened
    assert result["2008-04"]["action"] == "skipped (same source file)"  # reported as skipped


def test_handler_rejects_unknown_month_before_download(monkeypatch):    # validate first, spend nothing
    monkeypatch.setenv("BRONZE_BUCKET", "bronze")                       # required setting
    fetched = []                                                        # download calls
    with pytest.raises(ingest.IngestError, match="months must be"):     # clear failure
        ingest.handler({"months": ["2009-01"]}, None, s3=object(), fetch=fetched.append)  # unknown month
    assert fetched == []                                                # never downloaded


def test_handler_lands_requested_months(monkeypatch):                   # end to end with fakes
    monkeypatch.setenv("BRONZE_BUCKET", "bronze")                       # required setting
    data = fake_zip()                                                   # fake source
    monkeypatch.setattr(ingest, "SOURCE_MD5", hashlib.md5(data).hexdigest())  # accept the fake file
    s3 = boto3.client("s3", region_name="ap-south-1")                   # client to stub
    with Stubber(s3) as stub:                                           # fake responses
        stub.add_client_error("head_object", service_error_code="404", http_status_code=404)  # August not there
        stub.add_response("put_object", {})                             # write succeeds
        result = ingest.handler({"months": ["2008-08"]}, None, s3=s3, fetch=lambda url: data)  # run
    assert result == {"months": {"2008-08": {"rows": 1, "action": "written"}}}  # one August row
