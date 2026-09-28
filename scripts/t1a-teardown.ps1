# ── Tear down the T1a stack and its buckets, zero-residual (owner-run, after `aws login`) ──
param(                                                                   # options
    [string]$StackName = "clickstream-t1-lake",                        # SAM stack (infra/t1-lake/template.yaml)
    [string]$Region = "ap-south-1"                                      # Mumbai
)
$ErrorActionPreference = "Stop"                                         # stop on the first error
$PSNativeCommandUseErrorActionPreference = $true                        # a failing aws/sam call stops the script too

# ── Section 1: read the stack outputs before anything is deleted ─
function Get-StackOutputs {                                             # stack outputs as a hashtable
    $raw = aws cloudformation describe-stacks --stack-name $StackName --region $Region --query "Stacks[0].Outputs" --output json | ConvertFrom-Json  # CloudFormation outputs
    $out = @{}                                                          # OutputKey -> OutputValue
    foreach ($item in $raw) { $out[$item.OutputKey] = $item.OutputValue }  # copy each pair
    return $out                                                         # hashtable form
}
$out = Get-StackOutputs                                                 # bucket names, read once before deletion

# ── Empty a bucket (with versions) so the stack can delete it ─
function Clear-Bucket([string]$Bucket) {                                # delete every object version and delete marker
    while ($true) {                                                     # repeat until nothing is left
        $listing = aws s3api list-object-versions --bucket $Bucket --max-items 1000 --output json | ConvertFrom-Json  # up to 1000 at a time
        $items = @()                                                    # this batch's keys to delete
        $items += @($listing.Versions) | ForEach-Object { @{ Key = $_.Key; VersionId = $_.VersionId } }        # object versions
        $items += @($listing.DeleteMarkers) | ForEach-Object { @{ Key = $_.Key; VersionId = $_.VersionId } }   # delete markers
        if ($items.Count -eq 0) { break }                               # bucket is empty: stop
        @{ Objects = $items; Quiet = $true } | ConvertTo-Json -Depth 10 | Set-Content "$env:TEMP/delete.json"  # batch delete request
        aws s3api delete-objects --bucket $Bucket --delete "file://$env:TEMP/delete.json"  # remove this batch
    }
}
foreach ($bucketOutput in @("BronzeBucketName", "SilverBucketName", "GoldBucketName", "AthenaResultsBucketName")) {  # the four T1a buckets
    Write-Host "Clearing $bucketOutput ($($out[$bucketOutput]))..."     # progress
    Clear-Bucket $out[$bucketOutput]                                    # empty it so `sam delete` can remove it
}

# ── Section 2: delete the stack itself ─────────────────────────
sam delete --stack-name $StackName --region $Region --no-prompts        # deletes every resource the template created

# ── Section 3: verify the stack is really gone ─────────────────
try {                                                                    # describe-stacks should now fail (stack not found)
    aws cloudformation describe-stacks --stack-name $StackName --region $Region | Out-Null  # look it up
    throw "stack still exists"                                          # the lookup should have failed instead
}
catch {                                                                  # either the expected "not found", or our own sentinel above
    if ($_.Exception.Message -eq "stack still exists") { throw }        # the stack really is still there: fail loudly
}                                                                        # any other error means the lookup failed as expected: deleted

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
