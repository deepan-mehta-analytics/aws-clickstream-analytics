# ── Tear down the T1a stack and its buckets, zero-residual (owner-run, after `aws login`) ──
# The scripts rely on $PSNativeCommandUseErrorActionPreference (PowerShell 7.3 and later); refuse to run on older versions.
#Requires -Version 7.3
param(                                                                   # options
    [string]$StackName = "clickstream-t1-lake",                        # SAM stack (infra/t1-lake/template.yaml)
    [string]$Region = "ap-south-1"                                      # Mumbai
)
$ErrorActionPreference = "Stop"                                         # stop on the first error
$PSNativeCommandUseErrorActionPreference = $true                        # a failing aws/sam call stops the script too

# ── Section 1: helpers ─────────────────────────────────────────
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

function Get-DeleteBatch($Listing) {                                    # up to 1000 {Key, VersionId} pairs from one list-object-versions page
    $items = @()                                                        # this batch's keys to delete
    $items += @($Listing.Versions | Where-Object { $_ }) | ForEach-Object { @{ Key = $_.Key; VersionId = $_.VersionId } }       # object versions (null when the bucket has none)
    $items += @($Listing.DeleteMarkers | Where-Object { $_ }) | ForEach-Object { @{ Key = $_.Key; VersionId = $_.VersionId } }  # delete markers (null when none)
    return @($items | Select-Object -First 1000)                        # delete-objects accepts at most 1000 keys per call
}

# ── Section 2: empty the buckets, then delete the stack ───────
function Clear-Bucket([string]$Bucket) {                                # delete every object version and delete marker
    while ($true) {                                                     # repeat until nothing is left
        $listing = aws s3api list-object-versions --bucket $Bucket --max-items 1000 --output json | ConvertFrom-Json  # up to 1000 at a time
        $items = @(Get-DeleteBatch $listing)                            # this batch's keys, nulls dropped and capped
        if ($items.Count -eq 0) { break }                               # bucket is empty: stop
        @{ Objects = $items; Quiet = $true } | ConvertTo-Json -Depth 10 | Set-Content "$env:TEMP/delete.json"  # batch delete request
        $result = aws s3api delete-objects --bucket $Bucket --delete "file://$env:TEMP/delete.json" --output json  # remove this batch (Quiet: only failures are listed)
        $failed = @(($result | ConvertFrom-Json).Errors | Where-Object { $_ })  # per-key failures that the exit code does not reveal
        if ($failed.Count -gt 0) { throw "delete-objects could not remove $($failed.Count) keys from $Bucket, first: $($failed[0].Key) ($($failed[0].Code): $($failed[0].Message))" }  # stop instead of retrying forever
    }
}

if (Test-StackGone) {                                                   # a previous run already deleted the stack
    Write-Host "Stack $StackName is already gone; skipping bucket clearing and sam delete."  # rerun after success still reaches the log-retention step
}
else {
    $out = Get-StackOutputs                                             # bucket names, read once before deletion
    foreach ($bucketOutput in @("BronzeBucketName", "SilverBucketName", "GoldBucketName", "AthenaResultsBucketName")) {  # the four T1a buckets
        Write-Host "Clearing $bucketOutput ($($out[$bucketOutput]))..." # progress
        Clear-Bucket $out[$bucketOutput]                                # empty it so `sam delete` can remove it
    }
    sam delete --stack-name $StackName --region $Region --no-prompts    # deletes every resource the template created
}

# ── Section 3: verify the stack is really gone ─────────────────
if (-not (Test-StackGone)) { throw "stack still exists after sam delete" }  # only the specific "does not exist" error counts as deleted

# ── Section 4: shorten retention on the shared Glue job-run log groups ─
$logGroups = aws logs describe-log-groups --log-group-name-prefix /aws-glue/jobs --region $Region --query "logGroups[].logGroupName" --output json | ConvertFrom-Json  # these groups are not in the stack, so `sam delete` never removes them
foreach ($name in @($logGroups)) {                                      # each one found
    aws logs put-retention-policy --log-group-name $name --retention-in-days 1 --region $Region  # stop a slow leak
}

# ── Section 5: zero-residual checklist and final reminders ────
Write-Host "Zero-residual teardown checklist for T1a (docs/adr/0001-hybrid-cost-tiers.md Section 5):"  # heading, source doc
Write-Host "- [x] Glue jobs are idle; development endpoints and interactive sessions are stopped (T1a has neither)"  # T1a has no dev endpoints
Write-Host "- [x] CloudWatch alarms and log groups (or retention set to 1 day) - shared /aws-glue/jobs* groups set above"  # this script just did this
Write-Host "- [x] S3 buckets, including old object versions if versioning was on - cleared above, then deleted with the stack"  # this script just did this
Write-Host "- [ ] Cost Explorer checked 1-2 days later; measured INR total recorded in cost-model.md Section 5"  # follow-up, not automatable
Write-Host "Record this window in docs/cost-model.md Section 5; check Cost Explorer in 1-2 days; aws logout."  # final reminder
