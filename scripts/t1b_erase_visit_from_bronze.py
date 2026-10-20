"""Erase one visit from the versioned Bronze S3 object (right-to-erasure evidence for the T1b window).

The owner runs this in an AWS window. It rewrites the object without the visit's rows, then deletes the old
version by its VersionId, so exactly one version (without the visit) is left. The visit ID is read from the private
JSON written by `t1b_evidence.py pick-visit`, so it never lands in shell history, and no VersionId is ever printed.

Recovery: if the script stops after the upload but before the delete finishes, the key holds 2 versions (the old one
with the visit, the new one without). The owner lists the versions, opens the newest, confirms the visit is gone, and
deletes the OLDER version by its VersionId by hand. Never delete the newest version.
"""  # module docstring

# ── Imports ───────────────────────────────────────────────────
import argparse                                                         # command-line options
import json                                                             # pick-visit file and printed result
import sys                                                              # exit code
from pathlib import Path                                                # file paths


# ── Errors ────────────────────────────────────────────────────
class UnexpectedVersionsError(RuntimeError):                            # the object's version history is not what the script expects
    pass                                                                # no extra behaviour


class NothingToEraseError(ValueError):                                  # the visit has no rows in the file
    pass                                                                # no extra behaviour


# ── Row removal ───────────────────────────────────────────────
def remove_visit_rows(csv_bytes: bytes, visit_id: int) -> tuple[bytes, int]:  # (new bytes, rows removed)
    lines = csv_bytes.splitlines(keepends=True)                         # bytes split only on CR/LF, each line keeps its ending
    if not lines:                                                       # empty file
        return csv_bytes, 0                                             # nothing to remove
    header = lines[0].decode("utf-8-sig").rstrip("\r\n").split(";")     # column names (a leading BOM is ignored)
    position = header.index("session ID")                               # where the visit ID sits
    target = str(int(visit_id)).encode("utf-8")                         # the visit ID as it appears in the file

    def is_visit(line: bytes) -> bool:                                  # does this line belong to the visit?
        fields = line.rstrip(b"\r\n").split(b";")                       # the line's values
        return len(fields) > position and fields[position] == target    # blank or short lines are never the visit

    kept = [lines[0]] + [line for line in lines[1:] if not is_visit(line)]  # header plus every other line
    removed = len(lines) - len(kept)                                    # how many lines were dropped
    return b"".join(kept), removed                                      # same bytes apart from the removed lines


# ── Version listing ───────────────────────────────────────────
def _list_versions(s3, bucket: str, key: str) -> tuple[list, list]:     # (versions, delete markers) of exactly this key
    response = s3.list_object_versions(Bucket=bucket, Prefix=key)       # prefix match, so other keys can appear
    if response.get("IsTruncated"):                                     # a cut-short listing could hide versions
        raise UnexpectedVersionsError("the version listing was truncated; refusing to continue")  # no IDs
    versions = [item for item in response.get("Versions", []) if item["Key"] == key]  # keep the exact key only
    markers = [item for item in response.get("DeleteMarkers", []) if item["Key"] == key]  # keep the exact key only
    return versions, markers                                            # both lists


# ── Erase ─────────────────────────────────────────────────────
def erase_visit(s3, bucket: str, key: str, visit_id: int) -> dict:      # rewrite the object without the visit
    versions, markers = _list_versions(s3, bucket, key)                 # step 1: what exists now
    if len(versions) != 1 or markers:                                   # only one clean version is safe to replace
        raise UnexpectedVersionsError(f"expected exactly 1 version and no delete markers, found {len(versions)} versions and {len(markers)} markers")  # counts only, no IDs
    versions_before = len(versions)                                     # count before the rewrite
    old_version_id = versions[0]["VersionId"]                           # the version to delete at the end
    original = s3.get_object(Bucket=bucket, Key=key, VersionId=old_version_id)  # step 2: read that exact version
    if original.get("ServerSideEncryption") != "AES256":                # SSE-KMS (or none) must not be downgraded silently
        raise UnexpectedVersionsError("the object is not encrypted with AES256; refusing to rewrite it")  # no IDs
    new_body, removed = remove_visit_rows(original["Body"].read(), visit_id)  # drop the visit's rows
    if removed == 0:                                                    # the visit is not in the file
        raise NothingToEraseError("the visit has no rows in this object; nothing was uploaded")  # refuse before any write
    uploaded = s3.put_object(Bucket=bucket, Key=key, Body=new_body, ContentType=original["ContentType"], ServerSideEncryption="AES256", Metadata=original.get("Metadata", {}))  # step 3: upload as a new version, same type and metadata
    new_version_id = uploaded["VersionId"]                              # the id of the version just written
    versions, markers = _list_versions(s3, bucket, key)                 # step 4: expect old plus new
    if markers or {item["VersionId"] for item in versions} != {old_version_id, new_version_id} or len(versions) != 2:  # exactly the old and the new version, nothing else
        raise UnexpectedVersionsError(f"after the upload expected 2 versions and no delete markers, found {len(versions)} versions and {len(markers)} markers")  # counts only, no IDs
    s3.delete_object(Bucket=bucket, Key=key, VersionId=old_version_id)  # step 5: permanently delete the old version by its ID
    versions_after, markers_after = _list_versions(s3, bucket, key)     # step 6: confirm the end state
    if len(versions_after) != 1 or markers_after or versions_after[0]["VersionId"] != new_version_id:  # must be the new version only
        raise UnexpectedVersionsError(f"after the delete expected 1 new version and no delete markers, found {len(versions_after)} versions and {len(markers_after)} markers")  # counts only, no IDs
    return {"rows_removed": removed, "versions_before": versions_before, "versions_after": len(versions_after)}  # summary, no IDs


# ── Command line ──────────────────────────────────────────────
def main() -> int:                                                      # entry point
    parser = argparse.ArgumentParser(description="Erase one visit from the versioned Bronze object")  # description
    parser.add_argument("--bucket", required=True)                      # Bronze bucket name
    parser.add_argument("--key", required=True)                         # object key of the source file
    parser.add_argument("--visit-file", type=Path, required=True)       # private JSON from t1b_evidence.py pick-visit
    args = parser.parse_args()                                          # read options
    import boto3                                                        # imported here so tests need no AWS
    from botocore.exceptions import ClientError                         # AWS error type, imported here for the same reason
    try:                                                                # every failure below prints a fixed message only
        visit_id = int(json.loads(args.visit_file.read_text(encoding="utf-8"))["visit_id"])  # ID read from the file, never typed
    except (OSError, ValueError, KeyError, TypeError):                  # unreadable or malformed pick file
        print("error: could not read a visit ID from the visit file", file=sys.stderr)  # fixed text, no file content
        return 1                                                        # failure
    s3 = boto3.client("s3", region_name="ap-south-1")                   # S3 client in the project region
    try:                                                                # run the erase
        result = erase_visit(s3, args.bucket, args.key, visit_id)       # the work
    except (UnexpectedVersionsError, NothingToEraseError) as error:     # known refusals, messages hold counts only
        print(f"error: {error}", file=sys.stderr)                       # counts-only text
        return 1                                                        # failure
    except ClientError as error:                                        # AWS error text can contain IDs
        print(f"error: ClientError: {error.response.get('Error', {}).get('Code', 'Unknown')}", file=sys.stderr)  # code only
        return 1                                                        # failure
    print(json.dumps(result))                                           # result counts only
    return 0                                                            # success


if __name__ == "__main__":                                              # run as a script
    sys.exit(main())                                                    # exit code for the window script
