# ── Tests: T1b owner window and teardown scripts (static text checks, no AWS) ─
import json                                                             # harness answers
import re                                                               # pattern checks on script text
import shutil                                                           # find pwsh on PATH
import subprocess                                                       # run the PowerShell parser
from pathlib import Path                                                # file paths

import pytest                                                           # skip marker

REPO = Path(__file__).resolve().parents[1]                              # repo root
WINDOW = REPO / "scripts" / "t1b-window.ps1"                            # the owner window script
TEARDOWN = REPO / "scripts" / "t1b-teardown.ps1"                        # the owner teardown script
TABLES = {"silver_clicks", "silver_clicks_rejected", "silver_deleted_visits"}  # the three Iceberg tables
GENERATED_BUCKET = re.compile(r"[a-z0-9-]+-(bronze|silver|gold|athenaresults)bucket-[a-z0-9]+", re.IGNORECASE)  # CloudFormation-made bucket names


def read(path: Path) -> str:                                            # script text
    return path.read_text(encoding="utf-8")                             # UTF-8 source


# ── Window: SQL coverage and step order ───────────────────────
def test_window_references_every_t1b_sql_file():                        # nothing in the SQL folders is left unused
    text = read(WINDOW)                                                 # window source
    folders = ["sql/ddl", "sql/migrations", "sql/validation/t1b"]       # the T1b SQL folders
    files = [path for folder in folders for path in sorted((REPO / folder).glob("*.sql"))]  # every SQL file
    assert files                                                        # the folders are not empty
    missing = [path.relative_to(REPO).as_posix() for path in files if path.relative_to(REPO).as_posix() not in text]  # not named in the window
    assert missing == []                                                # every file is used


def test_window_section_headers_name_steps_1_to_18_in_order():          # spec section 4 sequence
    numbers = [int(found) for found in re.findall(r"^# ── Step (\d+)\b", read(WINDOW), re.MULTILINE)]  # step headers, in file order
    assert numbers == list(range(1, 19))                                # exactly 1..18, each once, ascending


def test_window_finishes_with_checks_and_masking():                     # evidence tooling at the end
    text = read(WINDOW)                                                 # window source
    assert "scripts/t1b_evidence.py checks" in text                     # pass/fail lines
    assert re.search(r"t1b_evidence\.py mask .*--visit-file", text)     # masking replaces the visit ID with the label
    assert "pick-visit" in text                                         # visit A is chosen by the seeded helper
    assert "t1b_erase_visit_from_bronze.py" in text                     # the Bronze erase runs in step 15


def test_window_run3_zero_files_prints_fallback_and_never_resets_bookmark():  # spec section 6 risk 1
    text = read(WINDOW)                                                 # window source
    assert "rerun only that month" in text                              # the documented fallback text
    assert not re.search(r"^\s*aws glue reset-job-bookmark", text, re.MULTILINE)  # never run as a command, only printed


def test_window_writes_evidence_only_through_the_masker():              # ruling 12: only masked files reach evidence/
    lines = read(WINDOW).splitlines()                                   # window lines
    assert not any("Copy-Item" in line for line in lines)               # no unmasked copies at all
    writes = [line for line in lines if "$evidence" in line and re.search(r"Set-Content|Out-File|\s>\s", line)]  # direct writes into evidence
    assert writes == []                                                 # nothing written there except by the masker
    assert re.search(r"\$work\s*=\s*Join-Path \$env:TEMP \"t1b-window-", read(WINDOW))  # raw output lives in TEMP


def test_window_never_prints_the_visit_id():                            # the console shows the label only
    lines = read(WINDOW).splitlines()                                   # window lines
    echoes = [line for line in lines if re.search(r"Write-(Host|Output)", line) and "$visitId" in line]  # printing the ID variable
    assert echoes == []                                                 # never


# ── Teardown: drops the three tables, then the T1a teardown ───
def test_teardown_drops_exactly_the_three_tables_before_the_t1a_teardown():  # spec section 6 risk 6
    text = read(TEARDOWN)                                               # teardown source
    table_list = re.search(r"\$icebergTables\s*=\s*@\(([^)]*)\)", text)  # the list the DROP loop walks
    assert table_list is not None                                       # the list exists
    assert set(re.findall(r"\"(\w+)\"", table_list.group(1))) == TABLES  # exactly the three tables
    assert re.search(r"foreach \(\$table in \$icebergTables\)\s*\{[^}]*DROP TABLE IF EXISTS \$\(\$out\.DatabaseName\)\.\$table", text)  # the only DROP walks that list
    assert text.count("DROP TABLE IF EXISTS") == 1                      # no other DROP statement anywhere
    assert "aws glue get-tables" in text                                # the database is checked afterwards
    assert text.index("DROP TABLE IF EXISTS") < text.index("aws glue get-tables") < text.index("t1a-teardown.ps1\"")  # drop, verify, then T1a teardown


# ── Both scripts: public-repo and guardrail hygiene ───────────
@pytest.mark.parametrize("script", [WINDOW, TEARDOWN], ids=["window", "teardown"])
def test_scripts_have_no_login_account_ids_or_bucket_literals(script):  # placeholders only
    text = read(script)                                                 # script source
    assert "aws login" not in text.lower()                              # the owner logs in by hand
    assert not re.search(r"(?<![0-9])[0-9]{12}(?![0-9])", text)         # no 12-digit account IDs
    assert not GENERATED_BUCKET.search(text)                            # no generated bucket names
    assert not re.search(r"s3://[A-Za-z0-9]", text)                     # every s3:// path starts from a variable


@pytest.mark.parametrize("script", [WINDOW, TEARDOWN], ids=["window", "teardown"])
def test_scripts_parse_with_the_powershell_parser(script):              # syntax check without running anything
    pwsh = shutil.which("pwsh")                                         # PowerShell 7 on PATH
    if pwsh is None:                                                    # CI images may not have it
        pytest.skip("pwsh is not on PATH")                              # skip, as the brief allows
    command = f"$e = $null; $null = [System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$null, [ref]$e); $e.Count"  # count parse errors
    result = subprocess.run([pwsh, "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=120)  # run the parser only
    assert result.stdout.strip() == "0", result.stdout + result.stderr  # no parse errors


# ── Window helpers run for real (extracted through the PowerShell AST, aws stubbed, no AWS) ─
HELPER_HARNESS = r"""
param([string]$WindowPath, [string]$Work, [string]$ResultPath)               # window file, fake TEMP folder, JSON answers
$ErrorActionPreference = "Stop"                                              # any harness error fails the test
$names = @("Hide-Visit", "Get-InputFileCount", "Remove-SqlCommentLines", "Read-AthenaRows", "Read-AthenaPairs", "Get-FormatVersions", "ConvertTo-TimeTravelFact", "Get-SilverClickObjectTimes", "Get-FilesStillInS3")  # helpers under test
$ast = [System.Management.Automation.Language.Parser]::ParseFile($WindowPath, [ref]$null, [ref]$null)  # parse only, never run the window
$found = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in $names }, $true)  # the function definitions
foreach ($function in $found) { . ([scriptblock]::Create($function.Extent.Text)) }  # define each one here
$day = "2026-01-01"                                                          # names the masked TEMP path
$script:visitId = 4321                                                       # fake visit ID
$out = @{ DatabaseName = "clickstream_t1"; SilverBucketName = "example" }    # fake stack outputs
$Region = "ap-south-1"                                                       # region argument
$answers = [ordered]@{ defined = @($found | ForEach-Object { $_.Name }) }      # what the test reads back
function Save-Result([string]$Name, $Rows) {                                 # one fake Athena result file
    $path = Join-Path $Work "$Name.json"                                     # under the fake TEMP
    $columns = @($Rows[0] | ForEach-Object { @{ Name = $_ } })               # header row gives the column names
    $data = @($Rows | ForEach-Object { @{ Data = @($_ | ForEach-Object { if ($null -eq $_) { @{} } else { @{ VarCharValue = $_ } } }) } })  # NULL = cell without VarCharValue
    @{ ResultSet = @{ ResultSetMetadata = @{ ColumnInfo = $columns }; Rows = $data } } | ConvertTo-Json -Depth 10 | Set-Content $path  # Athena's shape
    return @{ source = "sql/fixture/$Name.sql"; state = "SUCCEEDED"; result_path = $path }  # what the runner returns
}
function Get-Error([scriptblock]$Block) {                                    # the message a block throws, or "" when it does not
    try { & $Block | Out-Null; return "" } catch { return $_.Exception.Message }  # captured
}
# ── Read-AthenaRows / Read-AthenaPairs ──
$counts = Save-Result "counts" @(@("click_month", "clicks"), @("2008-04", "3"), @("2008-05", $null))  # header row, a value, a NULL
$rows = @(Read-AthenaRows $counts @("click_month", "clicks"))               # parsed
$answers.rows_count = $rows.Count                                            # header dropped -> 2
$answers.null_is_null = ($null -eq $rows[1].clicks)                          # NULL -> $null
$answers.missing_column = Get-Error { Read-AthenaRows $counts @("visits") }  # names the SQL file
$answers.pairs_null = Get-Error { Read-AthenaPairs $counts "click_month" "clicks" }  # NULL is never 0
# ── Hide-Visit / Get-InputFileCount / Remove-SqlCommentLines ──
$answers.hidden = Hide-Visit "visit 4321 at $Work/x, not 14321"              # ID and TEMP path masked
$answers.empty_months = Get-InputFileCount ('{"source_months": []}' | ConvertFrom-Json)  # [] -> 0
$answers.one_month = Get-InputFileCount ('{"source_months": ["2008-05"]}' | ConvertFrom-Json)  # one file
$answers.stripped = Remove-SqlCommentLines ("-- " + [char]0x2500 + " header`r`nSELECT '--x' AS a  -- trailing`r`n   -- indented`r`nFROM t")  # comment lines go
# ── ConvertTo-TimeTravelFact ──
$answers.travel_expired = ConvertTo-TimeTravelFact @{ state = "FAILED"; error = "Snapshot 99 not found" } "silver_clicks" "99"  # expected failure
$answers.travel_by_id = ConvertTo-TimeTravelFact @{ state = "FAILED"; error = "no version 99" } "silver_clicks" "99"  # names the ID only
$answers.travel_not_started = Get-Error { ConvertTo-TimeTravelFact @{ state = "NOT_STARTED"; error = "token expired" } "silver_clicks" "99" }  # stops
$answers.travel_other_failure = Get-Error { ConvertTo-TimeTravelFact @{ state = "FAILED"; error = "Access denied" } "silver_clicks" "99" }  # stops
$answers.travel_succeeded = ConvertTo-TimeTravelFact (Save-Result "travel" @(@("row_count"), @("0"))) "silver_clicks_rejected" "99"  # recorded
# ── Get-FormatVersions with the metadata.json fallback (aws and Invoke-AthenaFile stubbed) ──
New-Item -ItemType Directory -Force -Path (Join-Path $Work "s3") | Out-Null  # the window's S3 scratch folder
$script:awsCalls = @()                                                       # every stubbed aws call
function aws {                                                               # stands in for the AWS CLI
    $script:awsCalls += ($args -join " ")                                    # remember the call
    if ($args[0] -eq "glue" -and $args[1] -eq "get-table") { return "s3:" + "//example/clicks/metadata/00001.metadata.json" }  # fake metadata location
    if ($args[0] -eq "s3" -and $args[1] -eq "cp") { Set-Content -Path $args[3] -Value '{ "format-version" : 2, "table-uuid" : "x" }'; return }  # fake download
    if ($args[0] -eq "s3api") { return @("clicks/data/a.parquet`t2026-01-01T00:00:00.000Z", "clicks/metadata/v1.json`t2026-01-01T00:00:00.000Z") }  # fake listing
}
$script:showProperties = Save-Result "properties" @(@("prpt_name", "prpt_value"), @("write_compression", "snappy"))  # no format-version line
function Invoke-AthenaFile { return $script:showProperties }                 # SHOW TBLPROPERTIES stub
$answers.versions_fallback = Get-FormatVersions 1                            # every table through metadata.json
$script:showProperties = Save-Result "properties2" @(@("prpt_name", "prpt_value"), @("format-version", "2"))  # Athena lists it
$answers.versions_direct = Get-FormatVersions 14                             # read from SHOW TBLPROPERTIES
# ── Get-FilesStillInS3 ──
$answers.left = @(Get-FilesStillInS3 @("s3://example/clicks/data/a.parquet", "s3://example/clicks/data/b.parquet") "after_vacuum")  # a is still listed
$answers.aws_calls = $script:awsCalls                                        # for the call-shape asserts
$answers | ConvertTo-Json -Depth 10 | Set-Content $ResultPath                # answers for pytest
"""  # end of the PowerShell harness


def test_window_helpers_behave_on_fixtures(tmp_path):                   # the helpers run, not only parse
    pwsh = shutil.which("pwsh")                                         # PowerShell 7 on PATH
    if pwsh is None:                                                    # CI images may not have it
        pytest.skip("pwsh is not on PATH")                              # skip, as the brief allows
    harness = tmp_path / "harness.ps1"                                  # the harness script
    harness.write_text(HELPER_HARNESS, encoding="utf-8")                # written fresh each run
    work = tmp_path / "work"                                            # fake TEMP folder
    work.mkdir()                                                        # exists before the harness writes into it
    answers_path = tmp_path / "answers.json"                            # harness output
    result = subprocess.run([pwsh, "-NoProfile", "-File", str(harness), "-WindowPath", str(WINDOW), "-Work", str(work), "-ResultPath", str(answers_path)], capture_output=True, text=True, timeout=120)  # run it
    assert result.returncode == 0, result.stdout + result.stderr        # the harness itself ran
    answers = json.loads(answers_path.read_text(encoding="utf-8-sig"))  # answers (any BOM dropped)
    assert len(answers["defined"]) == 9                                 # every helper was found in the window
    assert answers["rows_count"] == 2 and answers["null_is_null"] is True  # header dropped, NULL kept as null
    assert "sql/fixture/counts.sql" in answers["missing_column"] and "visits" in answers["missing_column"]  # names the file and column
    assert "NULL" in answers["pairs_null"] and "sql/fixture/counts.sql" in answers["pairs_null"]  # NULL stops, naming the file
    assert answers["hidden"] == "visit visit A at %TEMP%/t1b-window-2026-01-01/x, not 14321"  # ID and TEMP path masked, whole numbers only
    assert answers["empty_months"] == 0 and answers["one_month"] == 1   # [] -> 0
    assert answers["stripped"] == "SELECT '--x' AS a  -- trailing\nFROM t"  # full-line comments gone, the rest unchanged
    assert answers["travel_expired"] == {"state": "FAILED", "error": "Snapshot 99 not found"}  # expected failure recorded
    assert answers["travel_by_id"]["state"] == "FAILED"                 # the snapshot ID alone also counts
    assert "step 14" in answers["travel_not_started"] and "step 14" in answers["travel_other_failure"]  # anything else stops, naming step 14
    assert answers["travel_succeeded"] == {"state": "SUCCEEDED", "row_count": 0}  # recorded with its state
    tables = ["silver_clicks", "silver_clicks_rejected", "silver_deleted_visits"]  # the three Iceberg tables
    assert answers["versions_fallback"] == {name: {"format_version": 2, "source": "metadata.json"} for name in tables}  # fallback used
    assert answers["versions_direct"] == {name: {"format_version": 2, "source": "show_tblproperties"} for name in tables}  # first try used
    assert "example" not in json.dumps(answers["versions_fallback"])    # no bucket name in the fact
    assert sum("glue get-table" in call for call in answers["aws_calls"]) == 3  # one metadata lookup per table, fallback only
    assert answers["left"] == ["s3://example/clicks/data/a.parquet"]    # only the still-listed step-8 file


# ── Makefile and README rows ──────────────────────────────────
def test_makefile_has_owner_only_t1b_targets():                         # as for T1a
    text = read(REPO / "Makefile")                                      # Makefile source
    for target, script in (("window-t1b", "t1b-window.ps1"), ("teardown-t1b", "t1b-teardown.ps1")):  # both targets
        block = re.search(rf"^{target}:\n\t(.+)$", text, re.MULTILINE)  # recipe line
        assert block is not None                                        # target exists
        assert "Owner-run only" in block.group(1) and script in block.group(1) and block.group(1).endswith("exit 1")  # prints and fails


def test_scripts_readme_lists_both_t1b_scripts():                       # discoverable
    text = read(REPO / "scripts" / "README.md")                         # README source
    assert "`t1b-window.ps1`" in text and "`t1b-teardown.ps1`" in text  # one row each
