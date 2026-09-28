"""Ingest Lambda (tier T1a): land the raw UCI #553 CSV in Bronze, one file per source month."""  # module docstring

# ── Imports (standard library + boto3, both in the Lambda runtime) ─
import hashlib                                                          # MD5 of the downloaded zip
import io                                                               # in-memory zip
import json                                                             # structured log lines
import logging                                                          # CloudWatch logs
import os                                                               # settings from environment variables
import time                                                             # backoff waits
import urllib.request                                                   # HTTPS download without extra packages
import zipfile                                                          # open the UCI zip

import boto3                                                            # S3 client
from botocore.exceptions import ClientError                             # S3 error type

# ── Settings ──────────────────────────────────────────────────
SOURCE_URL = os.environ.get("SOURCE_URL", "https://archive.ics.uci.edu/static/public/553/clickstream+data+for+online+shopping.zip")  # canonical UCI download
SOURCE_MD5 = os.environ.get("SOURCE_MD5", "bf7a47493025ffb35eebc7a65caf9988")  # checksum measured 2026-09-25 (data/README.md)
CSV_NAME = "e-shop clothing 2008.csv"                                   # file inside the zip
VALID_MONTHS = {"2008-04", "2008-05", "2008-06", "2008-07", "2008-08"}  # months present in the dataset
ATTEMPT_TIMEOUT_SECONDS = 15                                            # per-attempt socket timeout; 3 tries + backoff stays under the 60 s Lambda timeout
logger = logging.getLogger()                                            # Lambda's root logger
logger.setLevel(logging.INFO)                                           # info and above


class IngestError(Exception):                                           # any failure this Lambda reports on purpose
    """Ingest failed for a reason worth a clear message."""             # class docstring


# ── Steps ─────────────────────────────────────────────────────
def download(url, attempts=3, first_wait=1.0, opener=urllib.request.urlopen, sleep=time.sleep):  # fetch bytes with retries
    for attempt in range(1, attempts + 1):                              # 1, 2, 3
        try:                                                            # one attempt
            with opener(url, timeout=ATTEMPT_TIMEOUT_SECONDS) as response:  # HTTPS request
                return response.read()                                  # whole body (about 0.8 MB)
        except OSError as error:                                        # URLError, timeouts and resets are OSErrors
            if attempt == attempts:                                     # out of attempts
                raise IngestError(f"download failed after {attempts} attempts: {error}") from error  # give up clearly
            sleep(first_wait * 2 ** (attempt - 1))                      # wait 1 s, then 2 s (exponential backoff)


def check_md5(data, expected):                                          # make sure it is the expected file
    actual = hashlib.md5(data, usedforsecurity=False).hexdigest()       # integrity check, not security
    if actual != expected:                                              # upstream file changed or download corrupted
        raise IngestError(f"MD5 mismatch: expected {expected}, got {actual}; update SOURCE_MD5 only after checking the new file")  # stop


def read_csv_text(zip_bytes):                                           # the CSV inside the zip, as text
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:             # open in memory
        return archive.read(CSV_NAME).decode("utf-8")                   # plain ASCII in practice


def split_by_month(text, months):                                       # month -> header + that month's rows
    lines = text.splitlines()                                           # drops CRLF/LF endings; field values unchanged
    header, rows = lines[0], lines[1:]                                  # first line is the header
    parts = {month: [header] for month in months}                       # start every month with the header
    for line in rows:                                                   # each data row
        if not line.strip():                                            # skip blank lines
            continue                                                    # nothing to land
        year, month = line.split(";", 2)[:2]                            # first two fields
        key = f"{int(year):04d}-{int(month):02d}"                        # e.g. 2008-04
        if key in parts:                                                # a requested month
            parts[key].append(line)                                     # keep the row as it is
    return {month: "\n".join(lines_) + "\n" for month, lines_ in parts.items()}  # LF endings (Athena reads the last column cleanly)


def land_months(s3, bucket, month_texts, source_md5):                   # write each month unless already landed
    results = {}                                                        # month -> outcome
    for month, body in month_texts.items():                             # each requested month
        key = f"source_month={month}/clicks.csv"                        # partition-style key (not "month=", which clashes with the month column)
        rows = len(body.splitlines()) - 1                               # data rows (header excluded)
        try:                                                            # is it already there?
            existing = s3.head_object(Bucket=bucket, Key=key).get("Metadata", {}).get("source-md5")  # checksum it was landed from
        except ClientError as error:                                    # S3 said no
            if error.response["Error"]["Code"] not in ("404", "NoSuchKey", "NotFound"):  # anything but "not found"
                raise                                                   # real problem: surface it
            existing = None                                             # not landed yet
        if existing == source_md5:                                      # same source file already landed
            results[month] = {"rows": rows, "action": "skipped (same source file)"}  # idempotent: no new S3 version
            continue                                                    # next month
        s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"), ContentType="text/csv",  # write the month
                      Metadata={"source-md5": source_md5, "rows": str(rows)}, ServerSideEncryption="AES256")  # provenance + SSE-S3
        results[month] = {"rows": rows, "action": "written"}            # report
    return results                                                      # all months


# ── Entry point ───────────────────────────────────────────────
def handler(event, context, s3=None, fetch=download):                   # Lambda handler (s3/fetch injectable for tests)
    months = sorted(set((event or {}).get("months") or []))             # requested months, de-duplicated
    unknown = [month for month in months if month not in VALID_MONTHS]  # months the dataset does not have
    if not months or unknown:                                           # nothing valid requested
        raise IngestError(f"months must be a non-empty list from {sorted(VALID_MONTHS)}; got {event!r}")  # before any download
    bucket = os.environ["BRONZE_BUCKET"]                                # set by the SAM template
    data = fetch(SOURCE_URL)                                            # download with retries
    check_md5(data, SOURCE_MD5)                                         # right file?
    results = land_months(s3 or boto3.client("s3"), bucket, split_by_month(read_csv_text(data), months), SOURCE_MD5)  # land
    logger.info(json.dumps({"event": "landed", "results": results}))    # structured log line
    return {"months": results}                                          # returned to the caller
