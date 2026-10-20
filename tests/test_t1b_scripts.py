# ── Tests: T1b owner window and teardown scripts (static text checks, no AWS) ─
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
    dropped = re.findall(r"DROP TABLE IF EXISTS [`\"]?clickstream_t1[`\"]?\.[`\"]?(\w+)", text)  # tables named in DROP statements
    table_list = re.search(r"\$icebergTables\s*=\s*@\(([^)]*)\)", text)  # the list the DROP loop walks
    assert table_list is not None                                       # the list exists
    assert set(re.findall(r"\"(\w+)\"", table_list.group(1))) == TABLES  # exactly the three tables
    assert dropped == [] or set(dropped) <= TABLES                      # any literal DROP names only those tables
    assert "DROP TABLE IF EXISTS" in text                               # the drop statement is present
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
