# ── T1b proof window: Iceberg Silver, a schema change, erasing visit A, masked evidence (owner-run, once signed in to AWS) ──
# Spec docs/superpowers/specs/2026-10-20-t1b-iceberg-silver-design.md section 4. The owner deploys the stack first (step 0)
# and runs scripts/t1b-teardown.ps1 afterwards (step 19); this script runs steps 1-18 and stops at the first failure.
# The scripts rely on $PSNativeCommandUseErrorActionPreference (PowerShell 7.3 and later); refuse to run on older versions.
#Requires -Version 7.3

# ── Setup: options, safety, folders ───────────────────────────
param(                                                                   # options
    [string]$StackName = "clickstream-t1-lake",                        # SAM stack (infra/t1-lake/template.yaml)
    [string]$Region = "ap-south-1",                                     # Mumbai
    [string]$Python = ".venv/Scripts/python.exe",                       # project interpreter
    [string]$SourceFile = "data/e-shop clothing 2008.csv"               # the UCI file the local twin reads
)
$ErrorActionPreference = "Stop"                                         # stop on the first error
$PSNativeCommandUseErrorActionPreference = $true                        # a failing aws/python call stops the script too
$day = Get-Date -Format yyyy-MM-dd                                      # today's date, names both folders
$evidence = "evidence/t1b/$day"                                         # masked evidence only, safe to commit
if (Test-Path $evidence) {                                              # an earlier run today already saved evidence
    throw "$evidence already exists from an earlier run today. Move it aside first (rename it or move it out of the repo; never delete it), then rerun."  # never overwrite or delete earlier evidence
}
$work = Join-Path $env:TEMP "t1b-window-$day"                           # raw output (visit ID, version IDs, bucket names) never enters the repo
if (Test-Path $work) { Remove-Item -Recurse -Force $work }              # a same-day rerun must never see the earlier run's raw files
foreach ($folder in @("athena", "sql", "reports", "facts", "s3")) {     # raw Athena results, filled-in SQL, Glue reports, check inputs, S3 listings
    New-Item -ItemType Directory -Force -Path "$work/$folder" | Out-Null  # one scratch subfolder each
}
foreach ($folder in @("", "athena", "facts")) {                         # masked evidence folders
    New-Item -ItemType Directory -Force -Path "$evidence/$folder" | Out-Null  # created empty, filled only by the masker
}
$visitFile = "$work/visit.json"                                         # private pick-visit file (holds the real visit ID), TEMP only
$visitId = $null                                                        # the real visit ID, set at step 8, never printed
$visitMonth = $null                                                     # visit A's source month, set at step 8
$currentStep = 0                                                        # the step running now, named in every failure
$firstMonths = @("2008-04", "2008-05", "2008-06", "2008-07")            # the months run 1 processes
$silverTables = @("silver_clicks", "silver_clicks_rejected")            # the two Silver tables visit A is deleted from (snapshots, time travel)

# ── Helpers: keep the visit ID out of messages and save small facts ─
function Hide-Visit([string]$Text) {                                    # replace the real visit ID (and the local TEMP path) in a message
    if ([string]::IsNullOrEmpty($Text)) { return $Text }                # nothing to hide
    $Text = $Text.Replace($work, "%TEMP%/t1b-window-$day")              # the TEMP path holds the local user name
    if ($null -eq $script:visitId) { return $Text }                     # no visit picked yet
    return [regex]::Replace($Text, "(?<![0-9])$($script:visitId)(?![0-9])", "visit A")  # whole numbers only
}

function Save-Fact([string]$Name, $Value) {                             # one small JSON file that t1b_evidence.py checks reads
    ConvertTo-Json -InputObject $Value -Depth 20 | Set-Content "$work/facts/$Name"  # -InputObject keeps a one-item list a list
}

function Complete-Step([int]$Number, [string]$Note) {                   # progress line and record entry
    $record.steps_completed += $Number                                  # kept in the masked window.json
    Write-Host "Step $Number done: $Note"                               # progress (never the visit ID)
}

# ── Helpers: stack outputs, ingest Lambda, Glue run (copied from t1a-window.ps1) ─
function Get-StackOutputs {                                             # stack outputs as a hashtable
    $raw = aws cloudformation describe-stacks --stack-name $StackName --region $Region --query "Stacks[0].Outputs" --output json | ConvertFrom-Json  # CloudFormation outputs
    $out = @{}                                                          # OutputKey -> OutputValue
    foreach ($item in $raw) { $out[$item.OutputKey] = $item.OutputValue }  # copy each pair
    return $out                                                         # hashtable form
}

function Invoke-Ingest([string[]]$Months) {                             # invoke the ingest Lambda for these source months
    $first = $Months[0]                                                 # used to name the request/response files
    $payloadPath = "$work/payload-$first.json"                          # request body
    @{ months = $Months } | ConvertTo-Json -Compress | Set-Content $payloadPath  # months -> JSON payload
    $responsePath = "$work/ingest-$first.json"                          # Lambda response body, written by aws lambda invoke
    $invokeJson = aws lambda invoke --function-name $out.IngestFunctionName --payload "fileb://$payloadPath" --region $Region $responsePath  # invoke, capture invoke metadata from stdout
    $meta = $invokeJson | ConvertFrom-Json                              # invoke metadata (StatusCode, FunctionError)
    if ($meta.FunctionError) {                                          # the function itself raised
        $body = Get-Content $responsePath -Raw                         # error body from the response file
        throw "Lambda error: $body. Logs: /aws/lambda/$($out.IngestFunctionName)"  # stop the window, naming the log group
    }
    return Get-Content $responsePath -Raw                               # the response file content
}

function Invoke-GlueRun {                                               # start a Glue run and wait for it to finish
    $runId = aws glue start-job-run --job-name $out.GlueJobName --region $Region --query JobRunId --output text  # start it
    $state = "STARTING"                                                 # first poll always shows a running state
    $run = $null                                                        # last-seen run description
    while ($state -in @("STARTING", "RUNNING", "STOPPING", "WAITING")) {  # still in flight
        Start-Sleep -Seconds 30                                         # Glue runs take minutes, not seconds
        $run = aws glue get-job-run --job-name $out.GlueJobName --run-id $runId --region $Region --query JobRun --output json | ConvertFrom-Json  # current state
        $state = $run.JobRunState                                       # remember for the loop check
        Write-Host "Glue run $runId : $state"                           # progress
    }
    if ($state -ne "SUCCEEDED") {                                       # failed, timed out, or stopped
        throw "Glue run $runId ended $state : $(Hide-Visit $run.ErrorMessage). Logs: /aws-glue/$StackName/error (and /aws-glue/$StackName/output for stdout)."  # run ID and log groups
    }
    return @{                                                           # the evidence recorded for this run
        Id            = $run.Id                                        # Glue run id
        JobRunState   = $run.JobRunState                                # final state (SUCCEEDED here)
        ExecutionTime = $run.ExecutionTime                              # seconds spent running
        DPUSeconds    = $run.DPUSeconds                                 # cost proxy, when Glue reports it
        StartedOn     = $run.StartedOn                                  # start timestamp
        CompletedOn   = $run.CompletedOn                                # end timestamp
    }
}

function Get-RunReport([int]$RunNumber) {                               # the quality report the Glue job saved for this run
    aws s3 cp "s3://$($out.SilverBucketName)/_reports/" "$work/reports/" --recursive --region $Region | Out-Null  # every report so far, raw, to TEMP
    $files = @(Get-ChildItem "$work/reports/*.json" | Sort-Object Name) # report names are run timestamps, so oldest first
    if ($files.Count -ne $RunNumber) {                                  # exactly one report per Glue run
        throw "expected $RunNumber quality reports under the Silver bucket's _reports/, found $($files.Count)"  # a run did not report
    }
    return Get-Content $files[-1].FullName -Raw | ConvertFrom-Json      # the newest report is this run's
}

function Get-InputFileCount($Report) {                                  # Bronze files the run read (one file per source month, as in T1a)
    return @($Report.source_months | Where-Object { $_ }).Count         # an empty list (no new files) counts 0, never 1
}

# ── Helpers: Athena runner with placeholder filling ───────────
function Remove-SqlCommentLines([string]$Text) {                        # drop full-line -- comments (the repo SQL headers hold non-ASCII box-drawing characters)
    $kept = @($Text -split "\r?\n" | Where-Object { $_ -notmatch "^\s*--" })  # a line whose first non-space characters are -- ; a -- later in a line stays
    return ($kept -join "`n")                                           # the statement lines, unchanged
}

function Invoke-AthenaSql([string]$Name, [string]$Text, [hashtable]$Parameters = @{}, [string]$Source = "inline SQL", [switch]$AllowFailure) {  # run one statement, save its raw result to TEMP
    $Text = Remove-SqlCommentLines $Text                                # full-line comments never reach Athena
    foreach ($key in $Parameters.Keys) {                                # each {placeholder} the SQL uses
        $Text = $Text.Replace("{$key}", [string]$Parameters[$key])      # fill it in (TEMP copy only)
    }
    $unfilled = @([regex]::Matches($Text, "\{[a-z_]+\}") | ForEach-Object { $_.Value })  # placeholders nobody filled
    if ($unfilled.Count -gt 0) { throw "$Source still has unfilled placeholders: $($unfilled -join ', ')" }  # never send a half-filled query
    $Text = [regex]::Replace($Text, ";(\s*--[^\r\n]*)?\s*$", '$1')      # drop the one trailing semicolon, keep its comment
    $sqlPath = "$work/sql/$Name.sql"                                    # the filled-in SQL can hold the visit ID or bucket, so TEMP only
    Set-Content -Path $sqlPath -Value $Text -NoNewline                  # UTF-8 without BOM in PowerShell 7
    $PSNativeCommandUseErrorActionPreference = $false                   # read the start call's exit code by hand (scoped to this function)
    $previousEncoding = $env:AWS_CLI_FILE_ENCODING                      # the owner's own setting (usually unset), restored below
    $env:AWS_CLI_FILE_ENCODING = "UTF-8"                                # CLI v2 reads file:// with the locale encoding (cp1252 on Windows) unless told
    try {                                                               # restore the encoding setting whatever happens
        $startOutput = aws athena start-query-execution --query-string "file://$sqlPath" --work-group $out.WorkGroupName --query-execution-context "Database=$($out.DatabaseName)" --region $Region --query QueryExecutionId --output text 2>&1 | Out-String  # start it, keep stderr
        $startFailed = $LASTEXITCODE -ne 0                              # Athena refused the statement outright
    }
    finally {                                                           # runs after the start call, success or not
        $env:AWS_CLI_FILE_ENCODING = $previousEncoding                  # back to the owner's setting ($null removes it)
    }
    $PSNativeCommandUseErrorActionPreference = $true                    # strict again for the polling calls
    if ($startFailed) {                                                 # no query ID exists
        $reason = Hide-Visit $startOutput.Trim()                       # the CLI message, visit ID hidden
        if ($AllowFailure) { return @{ source = $Source; state = "NOT_STARTED"; error = $reason } }  # the caller expected a possible failure
        throw "Athena could not start $Source : $reason"               # stop the window
    }
    $id = @($startOutput -split "`r?`n" | Where-Object { $_.Trim() })[-1].Trim()  # the query ID is the last printed line
    $state = "RUNNING"                                                  # poll until it settles
    $exec = $null                                                       # last-seen execution description
    while ($state -in @("QUEUED", "RUNNING")) {                         # still executing
        Start-Sleep -Seconds 3                                          # small queries under the 1 GB cutoff finish fast
        $exec = aws athena get-query-execution --query-execution-id $id --region $Region --query QueryExecution --output json | ConvertFrom-Json  # current state
        $state = $exec.Status.State                                     # remember for the loop check
    }
    $summary = [ordered]@{                                              # the evidence recorded for this query
        name          = $Name                                           # result file name
        source        = $Source                                         # which SQL file (or inline SQL) this was
        query_id      = $id                                             # Athena query execution ID
        state         = $state                                          # SUCCEEDED, FAILED or CANCELLED
        scanned_bytes = $exec.Statistics.DataScannedInBytes             # cost proxy (workgroup cutoff is 1 GB)
        engine_ms     = $exec.Statistics.EngineExecutionTimeInMillis    # how long Athena spent on it
    }
    if ($state -ne "SUCCEEDED") {                                       # failed or cancelled
        $summary.error = Hide-Visit $exec.Status.StateChangeReason      # Athena's reason, visit ID hidden
        $record.athena += $summary                                      # kept even though it failed
        if ($AllowFailure) { return @{ source = $Source; state = $state; error = $summary.error } }  # the caller expected a possible failure
        throw "Athena query $id ($Source) ended $state : $($summary.error)"  # stop the window, naming the query ID
    }
    $resultPath = "$work/athena/$Name.json"                             # raw result, masked later
    aws athena get-query-results --query-execution-id $id --region $Region --output json > $resultPath  # save it before any parsing
    $result = Get-Content $resultPath -Raw | ConvertFrom-Json           # parsed for the optional row count below
    if ($result.PSObject.Properties["UpdateCount"]) { $summary.update_count = $result.UpdateCount }  # rows a DML statement changed, when Athena reports it
    $record.athena += $summary                                          # recorded as soon as the query finishes (no local paths in it)
    return @{ source = $Source; state = $state; result_path = $resultPath }  # what the parsers below need, kept out of the record
}

function Invoke-AthenaFile([string]$SqlPath, [string]$Name, [hashtable]$Parameters = @{}, [switch]$AllowFailure) {  # run one repo SQL file
    if (-not $Name) { $Name = [System.IO.Path]::GetFileNameWithoutExtension($SqlPath) }  # default result name: the file's base name
    $text = Get-Content $SqlPath -Raw                                   # the reviewed SQL
    return Invoke-AthenaSql -Name $Name -Text $text -Parameters $Parameters -Source $SqlPath -AllowFailure:$AllowFailure  # same runner as inline SQL
}

# ── Helpers: parse saved Athena results (column names are checked, never assumed) ─
function Read-AthenaRows($Query, [string[]]$Columns) {                  # rows of a saved result as objects keyed by column name
    $raw = Get-Content $Query.result_path -Raw | ConvertFrom-Json       # the raw result saved in TEMP
    $names = @($raw.ResultSet.ResultSetMetadata.ColumnInfo | ForEach-Object { $_.Name })  # column names Athena reported
    foreach ($column in $Columns) {                                     # each column the caller needs
        if ($column -notin $names) {                                    # the SQL returned something else
            throw "$($Query.source) result has no column '$column' (columns: $($names -join ', ')). Raw result: $($Query.result_path). Fix the SQL and rerun."  # names the query file
        }
    }
    $rows = @()                                                         # parsed rows
    foreach ($row in @($raw.ResultSet.Rows)) {                          # every row, header included for SELECTs
        $item = [ordered]@{}                                            # column -> value
        for ($i = 0; $i -lt $names.Count; $i++) {                       # each column position
            $cell = @($row.Data)[$i]                                    # the cell, or null when short
            $item[$names[$i]] = if ($cell -and $cell.PSObject.Properties["VarCharValue"]) { $cell.VarCharValue } else { $null }  # missing value = NULL
        }
        if ((@($item.Values) -join "`t") -eq ($names -join "`t")) { continue }  # the header row repeats the column names
        $rows += [pscustomobject]$item                                  # keep a data row
    }
    return $rows                                                        # data rows only
}

function Read-AthenaPairs($Query, [string]$KeyColumn, [string]$ValueColumn, [switch]$AsDouble) {  # first column -> number
    $pairs = [ordered]@{}                                               # e.g. 2008-04 -> 3
    foreach ($row in @(Read-AthenaRows $Query @($KeyColumn, $ValueColumn))) {  # each data row
        $value = $row.$ValueColumn                                      # the number as text, or $null for NULL
        if ($null -eq $value) { throw "$($Query.source) returned NULL in column '$ValueColumn' for '$($row.$KeyColumn)' (raw result: $($Query.result_path)); a NULL is never counted as 0" }  # stop instead of a silent 0
        $pairs[[string]$row.$KeyColumn] = if ($AsDouble) { [double]$value } else { [long]$value }  # invariant-culture number
    }
    return $pairs                                                       # a dictionary is returned whole, not enumerated
}

# ── Helpers: Iceberg format version (SHOW TBLPROPERTIES first, then metadata.json) ─
function Get-FormatVersions([int]$Step) {                               # Iceberg format version of the three tables, with where it was read
    $versions = [ordered]@{}                                            # table -> {format_version, source}
    foreach ($table in @("silver_clicks", "silver_clicks_rejected", "silver_deleted_visits")) {  # every Iceberg table
        $version = $null                                                # not known yet
        $source = $null                                                 # where the version was read
        $query = Invoke-AthenaFile "sql/validation/t1b/09_format_version.sql" -Name "09_format_version_step$($Step)_$table" -Parameters @{ table = $table } -AllowFailure  # SHOW TBLPROPERTIES, first try
        if ($query.state -eq "SUCCEEDED") {                             # the statement ran
            $raw = Get-Content $query.result_path -Raw | ConvertFrom-Json  # its saved raw result (shape unverified, so read as text)
            $lines = @($raw.ResultSet.Rows | ForEach-Object { (@($_.Data) | ForEach-Object { $_.VarCharValue }) -join "`t" })  # every row as tab-separated text
            $found = [regex]::Match(($lines -join "`n"), "format-version\W*(\d+)")  # e.g. "format-version<tab>2"
            if ($found.Success) {                                       # Athena listed the property
                $version = [int]$found.Groups[1].Value                  # the reported version
                $source = "show_tblproperties"                          # recorded in the fact
            }
        }
        if ($null -eq $version) {                                       # Athena shows only its supported properties, which may leave format-version out
            Write-Host "Step $($Step): SHOW TBLPROPERTIES did not report format-version for $table; reading the table's current metadata.json instead."  # progress (no bucket name)
            $location = [string](aws glue get-table --database-name $out.DatabaseName --name $table --region $Region --query Table.Parameters.metadata_location --output text)  # current metadata file (an S3 URI with the bucket name), TEMP use only
            $location = $location.Trim()                                # drop the trailing newline
            if (-not $location -or $location -eq "None") { throw "step $($Step): the Glue table $table has no metadata_location parameter, so its format version cannot be read" }  # no fallback left
            $metadataPath = "$work/s3/$table-metadata-step$Step.json"   # the downloaded metadata file, TEMP only
            aws s3 cp $location $metadataPath --region $Region | Out-Null  # copy it down (the console line would name the bucket)
            $found = [regex]::Match((Get-Content $metadataPath -Raw), '"format-version"\s*:\s*(\d+)')  # e.g. "format-version" : 2
            if (-not $found.Success) { throw "step $($Step): the metadata.json of $table has no format-version (saved under %TEMP%, s3 folder)" }  # unexpected file
            $version = [int]$found.Groups[1].Value                      # the version Iceberg itself recorded
            $source = "metadata.json"                                   # recorded in the fact
        }
        $versions[$table] = [ordered]@{ format_version = $version; source = $source }  # no URI or bucket name in the fact
    }
    return $versions                                                    # {"silver_clicks": {"format_version": 2, "source": "..."}, ...}
}

# ── Helpers: time travel after VACUUM and files left in S3 ────
function ConvertTo-TimeTravelFact($Attempt, [string]$Table, [string]$SnapshotId) {  # step-14 time travel result -> fact, or stop
    if ($Attempt.state -eq "SUCCEEDED") {                               # the old snapshot still answers
        return [ordered]@{ state = "SUCCEEDED"; row_count = [long]@(Read-AthenaRows $Attempt @("row_count"))[0].row_count }  # recorded honestly; t1b_evidence.py checks judges it
    }
    $reason = [string]$Attempt.error                                    # Athena's or the CLI's message, visit ID already hidden
    $namesSnapshot = ($reason -match "snapshot") -or ($SnapshotId -and $reason.Contains($SnapshotId))  # case-insensitive "snapshot", or the snapshot ID itself
    if ($Attempt.state -eq "FAILED" -and $namesSnapshot) {              # the expected failure: the snapshot is gone
        return [ordered]@{ state = "FAILED"; error = $reason }          # the fact checks reads
    }
    throw "step 14: time travel on $Table ended $($Attempt.state) for a reason other than a missing or expired snapshot: $reason"  # expired login, throttling, permissions: never counted as proof
}

function Assert-FilesListedInS3([string[]]$Paths, [string]$Label) {    # before VACUUM: every step-8 path must match a key in the S3 listing
    $times = Get-SilverClickObjectTimes $Label                          # every current Silver clicks object
    $unmatched = @($Paths | Where-Object { -not $times.ContainsKey($_) }).Count  # paths whose form the listing does not share
    if ($unmatched -gt 0) {                                             # the after-VACUUM check could pass falsely
        throw "step 13: $unmatched of $(@($Paths).Count) step-8 data files are not in the S3 listing before VACUUM, so the after-VACUUM file check cannot be trusted (listing saved under %TEMP%, s3 folder)"  # counts only: the paths hold the bucket name
    }
}

function Get-FilesStillInS3([string[]]$Paths, [string]$Label) {        # which of these data files S3 still holds
    $times = Get-SilverClickObjectTimes $Label                          # every current Silver clicks object
    return @($Paths | Where-Object { $times.ContainsKey($_) })          # paths still present (none expected after VACUUM)
}

function Get-MonthFiles([string]$Month, [string]$Label) {               # current data files of one month (SQL 07)
    $query = Invoke-AthenaFile "sql/validation/t1b/07_data_files_for_month.sql" -Name "07_data_files_$($Label)_$Month" -Parameters @{ month = $Month }  # $files metadata table
    return @(Read-AthenaRows $query @("file_path", "file_size_in_bytes") | ForEach-Object { [ordered]@{ path = $_.file_path; size = [long]$_.file_size_in_bytes } })  # path and size per file
}

function Get-SilverClickObjectTimes([string]$Label) {                   # S3 last-modified time of every Silver clicks object
    $listingPath = "$work/s3/silver-clicks-objects-$Label.txt"          # raw listing, TEMP only
    aws s3api list-objects-v2 --bucket $out.SilverBucketName --prefix clicks/ --region $Region --query "Contents[].[Key,LastModified]" --output text > $listingPath  # text output keeps the time as written
    $times = @{}                                                        # s3 path -> last-modified text
    foreach ($line in @(Get-Content $listingPath)) {                    # one object per line
        $parts = $line -split "`t"                                      # key, time
        if ($parts.Count -ge 2) { $times["s3://$($out.SilverBucketName)/$($parts[0])"] = $parts[1] }  # same form as $files file_path
    }
    return $times                                                       # lookup table
}

function Get-DataFileFacts([string]$Label) {                            # April-July data files with path, size, last-modified time
    $times = Get-SilverClickObjectTimes $Label                          # S3 times for every clicks object
    $files = @()                                                        # result list
    foreach ($month in $firstMonths) {                                  # April-July only
        foreach ($file in @(Get-MonthFiles $month $Label)) {            # each current data file
            if (-not $times.ContainsKey($file.path)) { throw "data file listed by sql/validation/t1b/07_data_files_for_month.sql is not in the S3 listing (see $work/s3/)" }  # $files and S3 disagree
            $files += [ordered]@{ path = $file.path; size = $file.size; last_modified = $times[$file.path] }  # the shape checks expects
        }
    }
    if ($files.Count -eq 0) { throw "no April-July data files found by sql/validation/t1b/07_data_files_for_month.sql" }  # nothing to compare
    return $files                                                       # list of files
}

function Test-VisitInCsv([string]$Path) {                               # does a Bronze CSV still hold a row of visit A?
    $lines = @(Get-Content $Path)                                       # lines, CR/LF stripped
    if ($lines.Count -lt 2) { return $false }                           # header only (or empty): no visit rows at all
    $header = $lines[0].TrimStart([char]0xFEFF).Split(";")              # column names, any BOM dropped
    $position = [Array]::IndexOf($header, "session ID")                 # where the visit ID sits
    if ($position -lt 0) { throw "the Bronze file has no 'session ID' column" }  # unexpected file
    foreach ($line in $lines[1..($lines.Count - 1)]) {                  # every data line
        $fields = $line.Split(";")                                      # its values
        if ($fields.Count -gt $position -and $fields[$position] -eq [string]$script:visitId) { return $true }  # found the visit
    }
    return $false                                                       # the visit is gone
}

# ── Main sequence ─────────────────────────────────────────────
$out = Get-StackOutputs                                                 # stack outputs, used by every helper above
if ($out.DatabaseName -ne "clickstream_t1") { throw "the DDL names database clickstream_t1 but the stack output is $($out.DatabaseName)" }  # the SQL hard-codes the name
$record = [ordered]@{ steps_completed = @(); athena = @() }             # everything this window did, raw (masked before it reaches evidence/)
try {                                                                   # the main sequence; any failure is recorded below
    & $Python scripts/t1b_evidence.py expected --source $SourceFile --output "$work/expected_before.json"  # local counts with every visit

# ── Step 1: create the three Iceberg tables and capture their format version ─
    $currentStep = 1                                                    # named in any failure
    foreach ($ddl in @("sql/ddl/silver_clicks.sql", "sql/ddl/silver_clicks_rejected.sql", "sql/ddl/silver_deleted_visits.sql")) {  # Athena creates Iceberg format version 2
        Invoke-AthenaFile $ddl -Parameters @{ silver_bucket = $out.SilverBucketName } | Out-Null  # bucket filled in from the stack output
    }
    Save-Fact "format_version_step1.json" (Get-FormatVersions 1)       # expected 2 on all three
    Complete-Step 1 "three Iceberg tables created"                      # progress

# ── Step 2: land April-July in Bronze ─────────────────────────
    $currentStep = 2                                                    # named in any failure
    $record.ingest_1 = Invoke-Ingest $firstMonths                       # the first four months
    Complete-Step 2 "April-July landed"                                 # progress

# ── Step 3: run 1, then a first Athena read of what Glue wrote ─
    $currentStep = 3                                                    # named in any failure
    $record.glue_run_1 = Invoke-GlueRun                                 # writes four months without weekend_click
    $record.report_run_1 = Get-RunReport 1                              # its quality report
    $months = @($record.report_run_1.source_months | Sort-Object)       # months the run processed
    if (($months -join ",") -ne ($firstMonths -join ",")) { throw "run 1 should process exactly $($firstMonths -join ','), found: $($months -join ',')" }  # bookmark start state wrong
    $readCheck = Read-AthenaPairs (Invoke-AthenaFile "sql/validation/t1b/01_silver_clicks_by_month.sql" -Name "01_silver_clicks_by_month_after_run1") "click_month" "clicks"  # Athena reads the Glue-written table (spec risk 2)
    if ((@($readCheck.Keys) -join ",") -ne ($firstMonths -join ",")) { throw "Athena read months $(@($readCheck.Keys) -join ',') from silver_clicks after run 1, expected $($firstMonths -join ',')" }  # reader problem caught early
    Complete-Step 3 "run 1 succeeded and Athena reads the table"        # progress

# ── Step 4: capture the April-July data files, then apply migration 001 ─
    $currentStep = 4                                                    # named in any failure
    Save-Fact "files_before_migration.json" @(Get-DataFileFacts "before_migration")  # path, size, last-modified before the change
    Invoke-AthenaFile "sql/migrations/001_add_weekend_click.sql" | Out-Null  # ALTER TABLE ... ADD COLUMNS (weekend_click boolean)
    Complete-Step 4 "migration 001 applied"                             # progress

# ── Step 5: land August ───────────────────────────────────────
    $currentStep = 5                                                    # named in any failure
    $record.ingest_2 = Invoke-Ingest @("2008-08")                       # the fifth month, on its own
    Complete-Step 5 "August landed"                                     # progress

# ── Step 6: run 2 (the bookmark reads only August) ────────────
    $currentStep = 6                                                    # named in any failure
    $record.glue_run_2 = Invoke-GlueRun                                 # writes August with weekend_click
    $record.report_run_2 = Get-RunReport 2                              # its quality report
    Save-Fact "run2_input_files.json" ([ordered]@{ input_files = (Get-InputFileCount $record.report_run_2); source_months = @($record.report_run_2.source_months) })  # expected 1 (checked by t1b_evidence.py)
    Complete-Step 6 "run 2 succeeded"                                   # progress

# ── Step 7: schema-change evidence (NULL share, files untouched, August values) ─
    $currentStep = 7                                                    # named in any failure
    Save-Fact "weekend_null_share.json" (Read-AthenaPairs (Invoke-AthenaFile "sql/validation/t1b/04_weekend_null_share_by_month.sql") "click_month" "null_share" -AsDouble)  # 1.0 for April-July, 0.0 for August
    Save-Fact "files_after_migration.json" @(Get-DataFileFacts "after_migration")  # must equal the step 4 list
    $weekendSql = "SELECT CAST(click_date AS varchar) AS click_date, CAST(weekend_click AS varchar) AS weekend_click, COUNT(*) AS clicks FROM `"clickstream_t1`".silver_clicks WHERE click_month = '2008-08' GROUP BY click_date, weekend_click"  # August values per day
    $mismatched = 0                                                     # August rows whose value breaks the local twin's rule
    $checked = 0                                                        # August rows looked at
    foreach ($row in @(Read-AthenaRows (Invoke-AthenaSql -Name "weekend_values_august" -Text $weekendSql) @("click_date", "weekend_click", "clicks"))) {  # one row per (day, value)
        $date = [datetime]::ParseExact($row.click_date, "yyyy-MM-dd", [cultureinfo]::InvariantCulture)  # the real click date
        $expected = if ($date.DayOfWeek -in @([DayOfWeek]::Saturday, [DayOfWeek]::Sunday)) { "true" } else { "false" }  # the twin's rule (clickstream.silver.add_weekend_click)
        $checked += [long]$row.clicks                                   # count every row
        if ($row.weekend_click -ne $expected) { $mismatched += [long]$row.clicks }  # a NULL or wrong value is a mismatch
    }
    Save-Fact "weekend_mismatches.json" ([ordered]@{ mismatched_rows = $mismatched; august_rows_checked = $checked })  # expected 0 mismatches
    Complete-Step 7 "schema-change evidence saved"                      # progress

# ── Step 8: pick visit A; record counts, the snapshot and the month's data files ─
    $currentStep = 8                                                    # named in any failure
    $pickPrinted = & $Python scripts/t1b_evidence.py pick-visit --source $SourceFile --output $visitFile  # the private file gets the real ID; the console line holds the label only
    Write-Host "Picked: $pickPrinted"                                   # label and month, no ID
    $visit = Get-Content $visitFile -Raw | ConvertFrom-Json             # private pick, read back
    $script:visitId = [long]$visit.visit_id                             # the real ID, used only in SQL text and Python arguments
    $script:visitMonth = [string]$visit.month                           # visit A's source month
    $record.visit = [ordered]@{ label = "visit A"; month = $visitMonth } # public part of the pick
    & $Python scripts/t1b_evidence.py expected --source $SourceFile --without-visit $visitId --output "$work/expected_after.json"  # local counts minus visit A
    Save-Fact "before_delete_counts.json" ([ordered]@{ silver_clicks_by_month = (Read-AthenaPairs (Invoke-AthenaFile "sql/validation/t1b/01_silver_clicks_by_month.sql" -Name "01_silver_clicks_by_month_step8") "click_month" "clicks") })  # pre-delete counts
    $visitRowsBefore = Read-AthenaPairs (Invoke-AthenaFile "sql/validation/t1b/05_visit_row_counts.sql" -Name "05_visit_row_counts_step8" -Parameters @{ visit_id = $visitId }) "table_name" "row_count"  # visit A per table
    $record.visit_rows_step8 = $visitRowsBefore                         # counts only
    if ($visitRowsBefore["silver_clicks"] -le 0) { throw "visit A has no rows in silver_clicks before the delete" }  # nothing to erase
    $snapshotsStep8 = [ordered]@{}                                      # table -> the pre-delete snapshot ID for time travel
    $record.snapshots_step8 = [ordered]@{}                              # table -> snapshot ID, commit time, operation
    foreach ($table in $silverTables) {                                 # both Silver tables visit A is deleted from
        $snapshotSource = "sql/validation/t1b/06_latest_snapshot.sql ($table)"  # named in any failure
        $snapshot = @(Read-AthenaRows (Invoke-AthenaFile "sql/validation/t1b/06_latest_snapshot.sql" -Name "06_latest_snapshot_step8_$table" -Parameters @{ table = $table }) @("snapshot_id", "committed_at", "operation"))  # $snapshots metadata table of that table
        if ($snapshot.Count -eq 0) { throw "step 8: $snapshotSource returned no snapshot for $table (run 1 should have committed one)" }  # nothing to time travel to
        if ($snapshot.Count -ne 1) { throw "step 8: $snapshotSource returned $($snapshot.Count) rows for $table, expected 1" }  # one latest snapshot
        $snapshotsStep8[$table] = [string]$snapshot[0].snapshot_id      # the pre-delete snapshot
        $record.snapshots_step8[$table] = $snapshot[0]                  # kept in the masked window.json
    }
    $filesStep8 = @(Get-MonthFiles $visitMonth "step8" | ForEach-Object { $_.path })  # data files of visit A's month
    if ($filesStep8.Count -eq 0) { throw "sql/validation/t1b/07_data_files_for_month.sql found no data files for visit A's month" }  # nothing to compare later
    Save-Fact "files_step8.json" $filesStep8                            # plain list of paths
    Complete-Step 8 "visit A picked ($visitMonth)"                      # progress (month only)

# ── Step 9: DELETE visit A from both Silver tables; add it to the deleted-visits list ─
    $currentStep = 9                                                    # named in any failure
    $visitParameters = @{ visit_id = $visitId; month = $visitMonth }    # placeholders for the inline statements
    Invoke-AthenaSql -Name "delete_silver_clicks" -Text "DELETE FROM clickstream_t1.silver_clicks WHERE visit_id = {visit_id}" -Parameters $visitParameters | Out-Null  # merge-on-read delete
    Invoke-AthenaSql -Name "delete_silver_clicks_rejected" -Text "DELETE FROM clickstream_t1.silver_clicks_rejected WHERE visit_id = {visit_id}" -Parameters $visitParameters | Out-Null  # 0 rows expected (no rejects in the real data)
    Invoke-AthenaSql -Name "insert_silver_deleted_visits" -Text "INSERT INTO clickstream_t1.silver_deleted_visits (visit_id, deleted_time, reason, bronze_key) VALUES ({visit_id}, CAST(current_timestamp AS timestamp(6)), 'erasure request (T1b proof window)', 'source_month={month}/clicks.csv')" -Parameters $visitParameters | Out-Null  # keeps later runs from bringing it back
    $afterCounts = Read-AthenaPairs (Invoke-AthenaFile "sql/validation/t1b/01_silver_clicks_by_month.sql" -Name "01_silver_clicks_by_month_step9") "click_month" "clicks"  # per-month counts after the delete
    $visitRowsAfter = Read-AthenaPairs (Invoke-AthenaFile "sql/validation/t1b/05_visit_row_counts.sql" -Name "05_visit_row_counts_step9" -Parameters @{ visit_id = $visitId }) "table_name" "row_count"  # visit A per table
    Save-Fact "after_delete_counts.json" ([ordered]@{ silver_clicks_by_month = $afterCounts; visit_rows_in_silver_clicks = $visitRowsAfter["silver_clicks"]; rejects_rows_deleted = ($visitRowsBefore["silver_clicks_rejected"] - $visitRowsAfter["silver_clicks_rejected"]) })  # measured before/after, not assumed
    Complete-Step 9 "visit A deleted from Silver"                       # progress

# ── Step 10: time travel to the step-8 snapshot (merge-on-read only hides) ─
    $currentStep = 10                                                   # named in any failure
    $travel10 = [ordered]@{}                                            # table -> {row_count}
    foreach ($table in $silverTables) {                                 # both Silver tables
        $travelParameters = @{ table = $table; snapshot_id = $snapshotsStep8[$table]; visit_id = $visitId }  # placeholders for SQL 08
        $travelRows = @(Read-AthenaRows (Invoke-AthenaFile "sql/validation/t1b/08_time_travel.sql" -Name "08_time_travel_step10_$table" -Parameters $travelParameters) @("row_count"))  # the old snapshot still answers
        if ($travelRows.Count -ne 1) { throw "step 10: sql/validation/t1b/08_time_travel.sql ($table) returned $($travelRows.Count) rows, expected 1" }  # COUNT(*) gives one row
        $travel10[$table] = [ordered]@{ row_count = [long]$travelRows[0].row_count }  # silver_clicks more than 0; rejects 0 (visit A is clean)
    }
    Save-Fact "time_travel_step10.json" $travel10                       # per-table counts
    Complete-Step 10 "time travel still returns visit A"                # progress

# ── Step 11: OPTIMIZE visit A's month on both Silver tables ───
    $currentStep = 11                                                   # named in any failure
    Invoke-AthenaSql -Name "optimize_silver_clicks" -Text "OPTIMIZE clickstream_t1.silver_clicks REWRITE DATA USING BIN_PACK WHERE click_month = '{month}'" -Parameters $visitParameters | Out-Null  # rewrite data files that have delete files
    Invoke-AthenaSql -Name "optimize_silver_clicks_rejected" -Text "OPTIMIZE clickstream_t1.silver_clicks_rejected REWRITE DATA USING BIN_PACK WHERE source_month = '{month}'" -Parameters $visitParameters | Out-Null  # same on the rejects table
    Complete-Step 11 "OPTIMIZE done"                                    # progress

# ── Step 12: the month's data files after OPTIMIZE ────────────
    $currentStep = 12                                                   # named in any failure
    Save-Fact "files_step12.json" @(Get-MonthFiles $visitMonth "step12" | ForEach-Object { $_.path })  # must share no path with step 8
    Complete-Step 12 "data files listed after OPTIMIZE"                 # progress

# ── Step 13: VACUUM all three tables ──────────────────────────
    $currentStep = 13                                                   # named in any failure
    Assert-FilesListedInS3 $filesStep8 "before_vacuum"                  # the same listing helper must see every step-8 file now, or [] later proves nothing
    Start-Sleep -Seconds 65                                             # every pre-delete snapshot is now older than vacuum_max_snapshot_age_seconds (60)
    foreach ($table in @("silver_clicks", "silver_clicks_rejected", "silver_deleted_visits")) {  # every Iceberg table
        Invoke-AthenaSql -Name "vacuum_$table" -Text "VACUUM clickstream_t1.$table" | Out-Null  # expire old snapshots, remove unused files
    }
    Save-Fact "files_step8_left_after_vacuum.json" @(Get-FilesStillInS3 $filesStep8 "after_vacuum")  # spec risk 3: VACUUM can succeed without deleting; the S3 listing decides (expected [])
    Complete-Step 13 "VACUUM done"                                      # progress

# ── Step 14: time travel again (now expected to fail) and format version again ─
    $currentStep = 14                                                   # named in any failure
    $travel14 = [ordered]@{}                                            # table -> {state, error} or {state, row_count}
    foreach ($table in $silverTables) {                                 # both Silver tables
        $travelParameters = @{ table = $table; snapshot_id = $snapshotsStep8[$table]; visit_id = $visitId }  # placeholders for SQL 08
        $attempt = Invoke-AthenaFile "sql/validation/t1b/08_time_travel.sql" -Name "08_time_travel_step14_$table" -Parameters $travelParameters -AllowFailure  # a snapshot failure is the expected result
        $travel14[$table] = ConvertTo-TimeTravelFact $attempt $table $snapshotsStep8[$table]  # only a FAILED state naming the snapshot counts; anything else stops here
    }
    Save-Fact "time_travel_step14.json" $travel14                       # per-table results
    Save-Fact "format_version_step14.json" (Get-FormatVersions 14)     # still 2 on all three
    Complete-Step 14 "time travel after VACUUM recorded"                # progress

# ── Step 15: erase visit A from the versioned Bronze object ───
    $currentStep = 15                                                   # named in any failure
    $bronzeKey = "source_month=$visitMonth/clicks.csv"                  # the ingest Lambda's key for that month
    $eraseOutput = & $Python scripts/t1b_erase_visit_from_bronze.py --bucket $out.BronzeBucketName --key $bronzeKey --visit-file $visitFile  # counts JSON; exits 1 on a refusal
    $record.bronze_erase = $eraseOutput | ConvertFrom-Json              # rows removed, versions before and after (no IDs)
    aws s3api list-object-versions --bucket $out.BronzeBucketName --prefix $bronzeKey --region $Region --output json > "$work/s3/bronze-versions-after.json"  # raw listing with version IDs, TEMP only
    $listing = Get-Content "$work/s3/bronze-versions-after.json" -Raw | ConvertFrom-Json  # parsed listing
    $versionCount = @($listing.Versions | Where-Object { $_ -and $_.Key -eq $bronzeKey }).Count  # versions of exactly this key
    $markerCount = @($listing.DeleteMarkers | Where-Object { $_ -and $_.Key -eq $bronzeKey }).Count  # delete markers of exactly this key
    aws s3 cp "s3://$($out.BronzeBucketName)/$bronzeKey" "$work/s3/bronze-after.csv" --region $Region | Out-Null  # the current object, TEMP only
    Save-Fact "bronze_versions_after.json" ([ordered]@{ version_count = ($versionCount + $markerCount); contains_visit = (Test-VisitInCsv "$work/s3/bronze-after.csv") })  # a marker also counts, so it fails the check
    Complete-Step 15 "Bronze rewritten without visit A"                 # progress

# ── Step 16: run 3 (the bookmark reprocesses the rewritten file) ─
    $currentStep = 16                                                   # named in any failure
    $record.glue_run_3 = Invoke-GlueRun                                 # rebuilds that month's Silver and Gold
    $record.report_run_3 = Get-RunReport 3                              # its quality report
    $inputFiles = Get-InputFileCount $record.report_run_3               # Bronze files run 3 read
    Save-Fact "run3_input_files.json" ([ordered]@{ input_files = $inputFiles; source_months = @($record.report_run_3.source_months) })  # expected 1
    if ($inputFiles -eq 0) {                                            # spec section 6 risk 1 happened
        throw "run 3 read 0 input files: the job bookmark did not reprocess the rewritten Bronze file (spec section 6, risk 1). Documented fallback, the owner's call, not automatic: reset the bookmark and rerun only that month ($visitMonth). It is safe because of the bookmark reset, the dynamic partition overwrite and the deleted-visits filter. Reset command: aws glue reset-job-bookmark --job-name $($out.GlueJobName) --region $Region"  # stop; never reset here
    }
    Complete-Step 16 "run 3 succeeded"                                  # progress

# ── Step 17: final evidence (visit A absent everywhere; Gold = run 2 minus visit A) ─
    $currentStep = 17                                                   # named in any failure
    Save-Fact "visit_rows_final.json" (Read-AthenaPairs (Invoke-AthenaFile "sql/validation/t1b/05_visit_row_counts.sql" -Name "05_visit_row_counts_final" -Parameters @{ visit_id = $visitId }) "table_name" "row_count")  # expected 0 in every table
    $goldVisits = Read-AthenaPairs (Invoke-AthenaFile "sql/validation/t1b/03_gold_visits_by_month.sql") "visit_month" "visits"  # Gold visits per month
    $goldClicks = Read-AthenaPairs (Invoke-AthenaSql -Name "gold_clicks_by_month" -Text "SELECT click_month, COUNT(*) AS clicks FROM `"clickstream_t1`".gold_clicks GROUP BY click_month ORDER BY click_month") "click_month" "clicks"  # Gold clicks per month
    Save-Fact "gold_after_run3.json" ([ordered]@{ visits_by_month = $goldVisits; clicks_by_month = $goldClicks })  # compared with the local run minus visit A
    Complete-Step 17 "final Silver and Gold evidence saved"             # progress

# ── Step 18: validation SQL as in T1a (final per-month counts) ─
    $currentStep = 18                                                   # named in any failure
    $bronzeRows = Read-AthenaPairs (Invoke-AthenaFile "sql/validation/t1a/01_bronze_rows_by_month.sql" -Name "t1a_01_bronze_rows_by_month") "source_month" "row_count"  # Bronze rows after the erase
    $silverFinal = Read-AthenaPairs (Invoke-AthenaFile "sql/validation/t1b/01_silver_clicks_by_month.sql" -Name "01_silver_clicks_by_month_final") "click_month" "clicks"  # Silver clicks after run 3
    $rejectedFinal = Read-AthenaPairs (Invoke-AthenaFile "sql/validation/t1b/02_rejected_by_month.sql") "source_month" "rejected"  # rejects per month (none expected)
    $rejectedTotal = 0                                                  # all rejected rows
    foreach ($count in @($rejectedFinal.Values)) { $rejectedTotal += $count }  # summed over months
    Save-Fact "final_counts.json" ([ordered]@{ bronze_rows_by_month = $bronzeRows; silver_clicks_by_month = $silverFinal; gold_visits_by_month = $goldVisits; rejected_rows = [ordered]@{ all = $rejectedTotal } })  # same keys as expected_counts
    Complete-Step 18 "validation SQL done"                              # progress
}
catch {                                                                 # a step failed
    $record.failure = "step $($currentStep): $(Hide-Visit $_.Exception.Message)"  # what went wrong, kept in the masked evidence
    throw "Step $currentStep failed: $(Hide-Visit $_.Exception.Message)"  # still fail the script (visit ID hidden), once the finally block below has run
}
finally {                                                               # always save evidence, also after an early stop
    # ── Finish: checks, then mask every file into evidence/ (also after an early stop) ─
    $PSNativeCommandUseErrorActionPreference = $false                   # from here every exit code is read by hand so nothing masks the real failure
    $finishProblems = @()                                               # problems found while saving evidence
    $record | ConvertTo-Json -Depth 20 | Set-Content "$work/window-raw.json"  # everything captured so far, raw, TEMP only
    $checksMismatch = $false                                            # set only when checks ran and reported a failed line
    if ((Test-Path "$work/expected_before.json") -and (Test-Path "$work/expected_after.json")) {  # both local count sets exist (step 8 reached)
        & $Python scripts/t1b_evidence.py checks --evidence-dir "$work/facts" --expected-before "$work/expected_before.json" --expected-after "$work/expected_after.json" --output "$work/comparison.json"  # one pass/fail line per spec section 5 check
        if ($LASTEXITCODE -ne 0) { $checksMismatch = $true }            # remembered, thrown below only if nothing else failed
    }
    else {                                                              # stopped before step 8
        Write-Host "Checks skipped: the window stopped before visit A was picked."  # nothing to compare yet
    }
    $haveVisit = Test-Path $visitFile                                   # the masker can replace the visit ID only once it is known
    $toMask = @(@{ from = "$work/window-raw.json"; to = "$evidence/window.json" })  # source -> masked target pairs
    foreach ($name in @("expected_before.json", "expected_after.json", "comparison.json")) {  # local counts and the check results
        if (Test-Path "$work/$name") { $toMask += @{ from = "$work/$name"; to = "$evidence/$name" } }  # only files that exist
    }
    Get-ChildItem "$work/athena/*.json" -ErrorAction SilentlyContinue | ForEach-Object { $toMask += @{ from = $_.FullName; to = "$evidence/athena/$($_.Name)" } }  # every Athena result that landed
    Get-ChildItem "$work/facts/*.json" -ErrorAction SilentlyContinue | ForEach-Object { $toMask += @{ from = $_.FullName; to = "$evidence/facts/$($_.Name)" } }  # every fact the checks read
    foreach ($pair in $toMask) {                                        # each file
        if ($haveVisit) { & $Python scripts/t1b_evidence.py mask $pair.from $pair.to --visit-file $visitFile }  # visit ID -> "visit A", plus account, bucket, version masking
        else { & $Python scripts/t1b_evidence.py mask $pair.from $pair.to }  # no visit picked yet: account, bucket, version masking only
        if ($LASTEXITCODE -ne 0) { $finishProblems += "masking $([System.IO.Path]::GetFileName($pair.from)) failed" }  # note it, keep going
    }
    if ($finishProblems.Count -gt 0) { Write-Host "Evidence saving problems: $($finishProblems -join '; ')" }  # shown even when an earlier step's error is the one thrown
    $PSNativeCommandUseErrorActionPreference = $true                    # restore the strict setting
}
if ($finishProblems.Count -gt 0) { throw "evidence saving problems: $($finishProblems -join '; ')" }  # only reached when the main sequence succeeded
if ($checksMismatch) { throw "at least one T1b check failed: see $evidence/comparison.json" }  # a real mismatch, reported only when no earlier step failed
Write-Host "Window complete. Masked evidence in $evidence. Next: run scripts/t1b-teardown.ps1, then aws logout."  # only reached once nothing above threw
