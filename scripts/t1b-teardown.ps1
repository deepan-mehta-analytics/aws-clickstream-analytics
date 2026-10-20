# ── Tear down T1b: drop the three Iceberg tables, check the database, then run the T1a teardown (owner-run, once signed in to AWS) ──
# Athena created the Iceberg tables, so the stack does not own them; Glue's DeleteDatabase would only remove them
# asynchronously (spec section 6, risk 6). They are dropped explicitly first, through the stack's Athena workgroup.
# The scripts rely on $PSNativeCommandUseErrorActionPreference (PowerShell 7.3 and later); refuse to run on older versions.
#Requires -Version 7.3
param(                                                                   # options
    [string]$StackName = "clickstream-t1-lake",                        # SAM stack (infra/t1-lake/template.yaml)
    [string]$Region = "ap-south-1"                                      # Mumbai
)
$ErrorActionPreference = "Stop"                                         # stop on the first error
$PSNativeCommandUseErrorActionPreference = $true                        # a failing aws call stops the script too
$icebergTables = @("silver_clicks", "silver_clicks_rejected", "silver_deleted_visits")  # the three tables the window created in Athena

# ── Section 1: helpers (copied from t1a-teardown.ps1, plus one Athena runner) ─
function Get-StackOutputs {                                             # stack outputs as a hashtable
    $raw = aws cloudformation describe-stacks --stack-name $StackName --region $Region --query "Stacks[0].Outputs" --output json | ConvertFrom-Json  # CloudFormation outputs
    $out = @{}                                                          # OutputKey -> OutputValue
    foreach ($item in $raw) { $out[$item.OutputKey] = $item.OutputValue }  # copy each pair
    return $out                                                         # hashtable form
}

function Test-StackGone {                                               # $true only when CloudFormation says the stack does not exist
    $PSNativeCommandUseErrorActionPreference = $false                   # this function reads the exit code itself (scoped to the function)
    $text = aws cloudformation describe-stacks --stack-name $StackName --region $Region 2>&1 | Out-String  # keep stderr so the message can be checked
    if ($LASTEXITCODE -eq 0) { return $false }                          # lookup succeeded: the stack is still there
    if ($text -match "does not exist") { return $true }                 # the specific "not found" error: really deleted
    throw "describe-stacks failed for a reason other than 'does not exist': $text"  # expired login, wrong region, throttling: never mistaken for deleted
}

function Invoke-AthenaStatement([string]$Text) {                        # run one statement in the stack's workgroup and wait for it
    $id = aws athena start-query-execution --query-string $Text --work-group $out.WorkGroupName --query-execution-context "Database=$($out.DatabaseName)" --region $Region --query QueryExecutionId --output text  # start it
    $state = "RUNNING"                                                  # poll until it settles
    $exec = $null                                                       # last-seen execution description
    while ($state -in @("QUEUED", "RUNNING")) {                         # still executing
        Start-Sleep -Seconds 3                                          # DROP TABLE finishes in seconds
        $exec = aws athena get-query-execution --query-execution-id $id --region $Region --query QueryExecution --output json | ConvertFrom-Json  # current state
        $state = $exec.Status.State                                     # remember for the loop check
    }
    if ($state -ne "SUCCEEDED") {                                       # failed or cancelled
        throw "Athena query $id ($Text) ended $state : $($exec.Status.StateChangeReason)"  # stop before the stack is deleted
    }
    Write-Host "$Text : $state"                                         # progress
}

if (Test-StackGone) {                                                   # a previous run already deleted the stack (and its workgroup)
    Write-Host "Stack $StackName is already gone; skipping the Iceberg table drops."  # the T1a teardown below still runs its checks
}
else {
    $out = Get-StackOutputs                                             # workgroup and database names, read once

    # ── Section 2: drop the three Iceberg tables through the workgroup ─
    foreach ($table in $icebergTables) {                                # each Athena-created table
        Invoke-AthenaStatement "DROP TABLE IF EXISTS $($out.DatabaseName).$table"  # removes it from the Glue catalog now, not asynchronously
    }

    # ── Section 3: confirm the database holds nothing the stack will not delete ─
    $remaining = @(aws glue get-tables --database-name $out.DatabaseName --region $Region --query "TableList[].Name" --output json | ConvertFrom-Json)  # every table still in the database
    $leftIceberg = @($remaining | Where-Object { $_ -in $icebergTables }) # any Iceberg table that survived the drop
    if ($leftIceberg.Count -gt 0) { throw "Iceberg tables still in $($out.DatabaseName) after DROP TABLE: $($leftIceberg -join ', ')" }  # stop before sam delete
    $stackTables = @(aws cloudformation list-stack-resources --stack-name $StackName --region $Region --query "StackResourceSummaries[?ResourceType=='AWS::Glue::Table'].PhysicalResourceId" --output json | ConvertFrom-Json)  # tables the template owns (Bronze and Gold)
    $unowned = @($remaining | Where-Object { $_ -notin $stackTables })  # tables sam delete would leave behind
    if ($unowned.Count -gt 0) { throw "tables not owned by the stack remain in $($out.DatabaseName): $($unowned -join ', '). Drop them before deleting the stack." }  # never leave orphans
    Write-Host "Database $($out.DatabaseName) is empty apart from the $($remaining.Count) tables the stack itself deletes."  # progress
}

# ── Section 4: the T1a teardown (buckets, stack, verification, log retention) ─
& (Join-Path $PSScriptRoot "t1a-teardown.ps1") -StackName $StackName -Region $Region  # empties all versions, sam delete, verifies the stack is gone
Write-Host "T1b teardown finished. Record the window in docs/cost-model.md (daily Cost Explorer export), then aws logout."  # final reminder
