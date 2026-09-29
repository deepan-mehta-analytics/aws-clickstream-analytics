# ── T1a proof window: ingest, Glue runs, Athena validation, masked evidence (owner-run, after `aws login`) ──
# The scripts rely on $PSNativeCommandUseErrorActionPreference (PowerShell 7.3 and later); refuse to run on older versions.
#Requires -Version 7.3

# ── Section 1: options, safety, folders ────────────────────────
param(                                                                   # options
    [string]$StackName = "clickstream-t1-lake",                        # SAM stack (infra/t1-lake/template.yaml)
    [string]$Region = "ap-south-1",                                     # Mumbai
    [string]$Python = ".venv/Scripts/python.exe"                        # project interpreter
)
$ErrorActionPreference = "Stop"                                         # stop on the first error
$PSNativeCommandUseErrorActionPreference = $true                        # a failing aws/python call stops the script too
$day = Get-Date -Format yyyy-MM-dd                                      # today's date, names the evidence folder
$work = Join-Path $env:TEMP "t1a-window-$day"                           # raw output never goes into the repo
if (Test-Path $work) { Remove-Item -Recurse -Force $work }              # a same-day rerun must never see the earlier run's Athena files
$evidence = "evidence/t1a/$day"                                         # masked evidence, safe to commit
New-Item -ItemType Directory -Force -Path $work | Out-Null              # scratch folder
New-Item -ItemType Directory -Force -Path "$work/athena" | Out-Null     # raw Athena JSON results
New-Item -ItemType Directory -Force -Path "$work/reports" | Out-Null    # raw Glue quality reports
New-Item -ItemType Directory -Force -Path $evidence | Out-Null          # masked evidence folder
New-Item -ItemType Directory -Force -Path "$evidence/athena" | Out-Null # masked Athena results
Get-ChildItem "$evidence/athena/*.json" -ErrorAction SilentlyContinue | Remove-Item -Force  # drop masked results left by an earlier same-day run
if (Test-Path "$evidence/comparison.json") { Remove-Item -Force "$evidence/comparison.json" }  # and its stale comparison

# ── Section 2: read the stack outputs ──────────────────────────
function Get-StackOutputs {                                             # stack outputs as a hashtable
    $raw = aws cloudformation describe-stacks --stack-name $StackName --region $Region --query "Stacks[0].Outputs" --output json | ConvertFrom-Json  # CloudFormation outputs
    $out = @{}                                                          # OutputKey -> OutputValue
    foreach ($item in $raw) { $out[$item.OutputKey] = $item.OutputValue }  # copy each pair
    return $out                                                         # hashtable form
}

# ── Section 3: invoke the ingest Lambda ────────────────────────
function Invoke-Ingest([string[]]$Months) {                             # invoke the ingest Lambda for these source months
    $first = $Months[0]                                                 # used to name the request/response files
    $payloadPath = "$work/payload-$first.json"                          # request body
    @{ months = $Months } | ConvertTo-Json -Compress | Set-Content $payloadPath  # months -> JSON payload
    $responsePath = "$work/ingest-$first.json"                          # Lambda response body, written by aws lambda invoke
    $invokeJson = aws lambda invoke --function-name $out.IngestFunctionName --payload "fileb://$payloadPath" --region $Region $responsePath  # invoke, capture invoke metadata from stdout
    $meta = $invokeJson | ConvertFrom-Json                              # invoke metadata (StatusCode, FunctionError)
    if ($meta.FunctionError) {                                          # the function itself raised
        $body = Get-Content $responsePath -Raw                         # error body from the response file
        throw "Lambda error: $body"                                    # stop the window
    }
    return Get-Content $responsePath -Raw                               # the response file content
}

# ── Section 4: start a Glue run and wait for it ────────────────
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
        throw "Glue run $runId ended $state : $($run.ErrorMessage). Logs: /aws-glue/$StackName/error (and /aws-glue/$StackName/output for stdout)."  # per the Task 9 custom-logGroup-prefix ruling
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

# ── Section 5: run one validation query and save its result ───
function Invoke-AthenaFile([string]$SqlPath) {                          # run one validation query and save its result
    $id = aws athena start-query-execution --query-string "file://$SqlPath" --work-group $out.WorkGroupName --query-execution-context "Database=$($out.DatabaseName)" --region $Region --query QueryExecutionId --output text  # start it
    $state = "RUNNING"                                                  # poll until it settles
    $exec = $null                                                       # last-seen execution description
    while ($state -in @("QUEUED", "RUNNING")) {                         # still executing
        Start-Sleep -Seconds 3                                          # small queries under the 1 GB cutoff finish fast
        $exec = aws athena get-query-execution --query-execution-id $id --region $Region --query QueryExecution --output json | ConvertFrom-Json  # current state
        $state = $exec.Status.State                                     # remember for the loop check
    }
    if ($state -ne "SUCCEEDED") {                                       # failed or cancelled
        throw "Athena query $id ($SqlPath) ended $state : $($exec.Status.StateChangeReason)"  # stop the window
    }
    $basename = [System.IO.Path]::GetFileNameWithoutExtension($SqlPath)  # e.g. 01_bronze_rows_by_month
    aws athena get-query-results --query-execution-id $id --region $Region --output json > "$work/athena/$basename.json"  # raw result, saved for masking
    return @{                                                           # the evidence recorded for this query
        file          = $basename                                       # which validation query this was
        scanned_bytes = $exec.Statistics.DataScannedInBytes             # cost proxy (workgroup cutoff is 1 GB)
        engine_ms     = $exec.Statistics.EngineExecutionTimeInMillis    # how long Athena spent on it
    }
}

# ── Section 6: main sequence ────────────────────────────────────
$out = Get-StackOutputs                                                 # stack outputs, used by every helper above
$record = [ordered]@{}                                                  # everything this window did, raw (unmasked)
try {
    & $Python scripts/t1a_evidence.py expected --source "data/e-shop clothing 2008.csv" --output "$work/expected.json"  # local numbers the cloud run must match
    $record.ingest_1 = Invoke-Ingest @("2008-04", "2008-05", "2008-06", "2008-07")  # the first four months
    $record.glue_run_1 = Invoke-GlueRun                                 # process them
    $record.ingest_2 = Invoke-Ingest @("2008-08")                       # the fifth month, on its own
    $record.glue_run_2 = Invoke-GlueRun                                 # process only it (this is the bookmark proof)

    aws s3 cp "s3://$($out.SilverBucketName)/_reports/" "$work/reports/" --recursive --region $Region  # both quality reports
    $reportFiles = Get-ChildItem "$work/reports/*.json" | Sort-Object Name  # oldest report first
    $record.quality_reports = @($reportFiles | ForEach-Object { Get-Content $_.FullName -Raw | ConvertFrom-Json })  # parsed reports, forced to an array
    if ($record.quality_reports.Count -ne 2) {                          # exactly one report per Glue run
        throw "expected 2 quality reports in $($out.SilverBucketName)/_reports/, found $($record.quality_reports.Count)"  # something did not land
    }
    $firstMonths = @($record.quality_reports[0].source_months | Sort-Object)  # months the first (bulk) run processed
    if (($firstMonths -join ",") -ne "2008-04,2008-05,2008-06,2008-07") {  # exactly April-July, not just any four months
        throw "first quality report source_months should be exactly 2008-04,2008-05,2008-06,2008-07, found: $($firstMonths -join ',')"  # bookmark not honoured
    }
    $secondMonths = @($record.quality_reports[1].source_months)         # months the second (bookmark) run processed
    if ($secondMonths.Count -ne 1 -or $secondMonths[0] -ne "2008-08") { # only the new month, nothing reprocessed
        throw "second quality report source_months should be exactly ['2008-08'], found: $($secondMonths -join ',')"  # this is the bookmark proof
    }

    $record.athena = @()                                                # filled one query at a time so a failure keeps what already ran
    foreach ($sqlFile in (Get-ChildItem sql/validation/t1a/*.sql | Sort-Object Name)) {  # every validation query, in file order
        $record.athena += Invoke-AthenaFile $sqlFile.FullName           # summary recorded as soon as the query finishes
    }
}
catch {
    $record.failure = $_.Exception.Message                              # what went wrong, kept in the masked evidence
    throw                                                                # still fail the script, once the finally block below has run
}
finally {
    $PSNativeCommandUseErrorActionPreference = $false                   # from here every exit code is read by hand so nothing masks the real failure
    $finishProblems = @()                                               # problems found while saving evidence
    $record | ConvertTo-Json -Depth 20 | Set-Content "$work/window-raw.json"  # everything captured so far, even on failure
    & $Python scripts/t1a_evidence.py mask "$work/window-raw.json" "$evidence/window.json"  # masked copy, safe to commit
    if ($LASTEXITCODE -ne 0) { $finishProblems += "masking window-raw.json failed" }  # note it, keep going
    Get-ChildItem "$work/athena/*.json" -ErrorAction SilentlyContinue | ForEach-Object {  # mask every Athena result that landed
        & $Python scripts/t1a_evidence.py mask $_.FullName "$evidence/athena/$($_.Name)"  # one masked file per query
        if ($LASTEXITCODE -ne 0) { $finishProblems += "masking $($_.Name) failed" }  # note it, keep going
    }
    $comparisonMismatch = $false                                        # set only when compare ran and reported a difference
    if (Test-Path "$work/expected.json") {                              # only possible once the first step ran
        Copy-Item "$work/expected.json" "$evidence/expected.json" -Force  # keep the local numbers first, whatever happens next
        if (@(Get-ChildItem "$work/athena/*.json" -ErrorAction SilentlyContinue).Count -gt 0) {  # nothing to compare when no query ran
            & $Python scripts/t1a_evidence.py compare --expected "$work/expected.json" --athena-dir "$work/athena" --output "$evidence/comparison.json"  # local vs Athena (exits 1 on any mismatch)
            if ($LASTEXITCODE -ne 0) { $comparisonMismatch = $true }    # remembered, thrown below only if nothing else failed
        }
    }
    $PSNativeCommandUseErrorActionPreference = $true                    # restore the strict setting
}
if ($finishProblems.Count -gt 0) { throw "evidence saving problems: $($finishProblems -join '; ')" }  # only reached when the main sequence succeeded
if ($comparisonMismatch) { throw "Athena results do not match the local twin: see $evidence/comparison.json" }  # a real mismatch, reported only when no earlier step failed
Write-Host "Window complete. Evidence in $evidence. Next: run scripts/t1a-teardown.ps1, then aws logout."  # only reached once nothing above threw
