# ── Upload the Glue script and library zip (owner-run, after `aws login`) ──
param(                                                                   # options
    [Parameter(Mandatory)] [string]$ArtifactsBucket,                    # ArtifactsBucketName output of clickstream-foundation
    [string]$Region = "ap-south-1",                                     # Mumbai
    [string]$Python = ".venv/Scripts/python.exe"                        # project interpreter
)
$ErrorActionPreference = "Stop"                                         # stop on the first error
$PSNativeCommandUseErrorActionPreference = $true                        # a failing aws/python call stops the script too
& $Python scripts/build_glue_libs.py                                    # build build/glue/clickstream_libs.zip
aws s3 cp glue/build_silver_gold.py "s3://$ArtifactsBucket/t1-lake/glue/build_silver_gold.py" --sse AES256 --region $Region   # the script
aws s3 cp build/glue/clickstream_libs.zip "s3://$ArtifactsBucket/t1-lake/glue-libs/clickstream_libs.zip" --sse AES256 --region $Region   # the libraries
Write-Host "Uploaded. The Glue job picks these up on its next run (no redeploy needed)."   # reminder
