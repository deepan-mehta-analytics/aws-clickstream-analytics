# infra/

Infrastructure as code for this project: AWS SAM-extended CloudFormation,
one stack per folder ([ADR-0004](../docs/adr/0004-iac-sam-cloudformation.md)).
**Only the account owner deploys.** No agent or CI job ever holds AWS
credentials; CI only lints and tests the templates.

| Folder | Stack name | What it creates | Status |
|---|---|---|---|
| `foundation/` | `clickstream-foundation` | One S3 bucket for packaged code (SSE-S3, private, TLS only, 30-day expiry) | Deployed 2026-10-05 (owner); kept between windows |
| `t1-lake/` | `clickstream-t1-lake` | Tier T1a (ingest Lambda, Bronze/Silver/Gold/Athena-results buckets, Glue job and catalog, Athena workgroup) | Two creation attempts on 2026-10-05 rolled back on account-level limits (GAPS G-18, G-19) and were deleted; waiting on AWS Support to enable Glue |

## Checks (no AWS credentials)

```bash
.venv/Scripts/cfn-lint                                       # validate templates for ap-south-1 (.cfnlintrc)
.venv/Scripts/python -m pytest -v tests/test_infra_templates.py  # guardrail tests
```

## Owner: one-time setup

1. Deploy as a **non-root IAM user with MFA and no access keys** (for example
   `owner-admin` in an `admins` group with `AdministratorAccess` and
   `SignInLocalDevelopmentAccess`). Keep the root user for root-only tasks.
2. Install **AWS CLI v2, version 2.32.0 or later** (needed for `aws login`) and
   the **AWS SAM CLI** from their official installers; check with
   `aws --version` and `sam --version`.
3. Install Docker Desktop (only needed for `sam local invoke`).
4. Create an AWS Budgets alert before the first deploy.

## Owner: sign in only for a deploy window

```bash
aws login --region ap-south-1        # browser sign-in as the IAM user; session lasts up to 12 hours
# ... deploy / work / tear down ...
aws logout                           # remove the cached session
```

Any program on this computer, including an AI agent's shell, can use a
cached CLI session. Sign out as soon as the window ends.

## Foundation stack (once)

```bash
aws cloudformation deploy --template-file infra/foundation/template.yaml --stack-name clickstream-foundation --region ap-south-1
aws cloudformation describe-stacks --stack-name clickstream-foundation --region ap-south-1 --query "Stacks[0].Outputs"
```

Copy the `ArtifactsBucketName` value into your local `infra/samconfig.toml`
(start from `samconfig.example.toml`; the real file is gitignored).

Teardown (the bucket must be empty first):

```bash
aws s3 rm s3://<ArtifactsBucketName> --recursive
aws cloudformation delete-stack --stack-name clickstream-foundation --region ap-south-1
```

## Tier stacks (every working window)

```bash
cd infra
sam build --template-file <tier>/template.yaml --build-dir .aws-sam/<tier>   # one build folder per tier (gitignored)
sam deploy --config-file (Resolve-Path samconfig.toml).Path --config-env <tier> --template-file .aws-sam/<tier>/template.yaml --no-execute-changeset  # change set only; SAM looks for samconfig.toml beside the built template, so pass its full path
# review the change set in the CloudFormation console: IAM resources first
# then execute THAT change set from the console; rerunning sam deploy would create a new, unreviewed one
sam delete --stack-name clickstream-<tier> --region ap-south-1     # teardown at the end of the window
```

Each tier gets its own build folder, so building one tier can never overwrite
the packaged template another tier is about to deploy.

The foundation bucket deletes packaged code after 30 days. Stacks here are torn
down after every window, so this never matters in practice; a stack kept longer
than 30 days would need a fresh `sam build` + `sam deploy` before any rollback.

Record every window (created, torn down, measured cost) in the teardown log
in [`docs/cost-model.md`](../docs/cost-model.md).

## Tier T1a window runbook (owner only)

Run the commands in this order from the repository root, in PowerShell 7.3 or
later. Values in angle brackets are placeholders; the real values come from
your stack outputs and stay out of the repository. The scripts are described
in [`scripts/README.md`](../scripts/README.md). Steps 1–5 were run on 2026-10-05; step 5's stack creation stopped on account-level limits (see below), so steps 6–7 have not run yet.

**Pre-flight: do not start the window until every box is ticked.**

- [ ] An **AWS Budgets alert exists** (Billing and Cost Management → Budgets;
      the *Zero spend budget* template, or a monthly cost budget of about $1,
      emailing you). Billing pages show the Region as "Global", which is
      expected.
- [ ] Each budget's email recipient shows **Active** on the budget's detail
      page. AWS Budgets now sends nothing to an unverified address: confirm
      the link in the email from an `@aws.com` sender while signed in to this
      account (links expire after 12 hours; use *Resend verification* or
      *Send Notification* if the status is Pending, Expiring or Inactive).
      Source: [Budgets email recipients](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-email-recipients.html),
      fetched 2026-10-05. Budgets data is not real-time and cannot see Redshift trial
      usage, so it is a backstop, not a live meter.
- [ ] The console's Region selector is on **Asia Pacific (Mumbai)
      `ap-south-1`** for every service page you open during the window.
- [ ] No screenshot or copied output that shows the account ID, ARNs or your
      sign-in name will be saved inside the repository; evidence goes through
      the masking script only.

```powershell
# 1. Sign in for this window only
aws login --region ap-south-1

# 2. Foundation stack (once); note the ArtifactsBucketName output
aws cloudformation deploy --template-file infra/foundation/template.yaml --stack-name clickstream-foundation --region ap-south-1
aws cloudformation describe-stacks --stack-name clickstream-foundation --region ap-south-1 --query "Stacks[0].Outputs"

# 2b. Copy the ArtifactsBucketName value into your local, gitignored infra/samconfig.toml
#     (start from infra/samconfig.example.toml); `sam deploy --config-env t1-lake` in step 4 reads it.

# 3. Upload the Glue script and library zip to the artifacts bucket
pwsh scripts/t1a-upload-glue-code.ps1 -ArtifactsBucket <ArtifactsBucketName>

# 4. Build, then create a change set only (does not apply it)
cd infra
sam build --template-file t1-lake/template.yaml --build-dir .aws-sam/t1-lake
sam deploy --config-file (Resolve-Path samconfig.toml).Path --config-env t1-lake --template-file .aws-sam/t1-lake/template.yaml --no-execute-changeset
# (without --config-file, SAM looks beside the built template and stops with "Missing option '--stack-name'")
cd ..

# 5. Review the change set in the CloudFormation console (IAM resources first),
#    then execute that same change set from the console.

# 6. Run the proof window: ingest, Glue twice (bookmark proof), Athena checks, masked evidence
#    (uses the repo's .venv interpreter: its -Python parameter defaults to .venv/Scripts/python.exe, so the venv must exist first)
pwsh scripts/t1a-window.ps1

# 7. Tear down: empties the four buckets, deletes the stack, verifies it is gone
pwsh scripts/t1a-teardown.ps1

# 8. Remove the cached session, then log the window in docs/cost-model.md
aws logout
```

If the first deploy fails with "decreases account's UnreservedConcurrentExecution
below its minimum value", the account's Lambda concurrency quota is reduced
(10 on this account, GAPS G-18). The template's `IngestReservedConcurrency`
parameter defaults to 0 (no reservation) for that reason. A stack left in
`ROLLBACK_COMPLETE` must be deleted (`aws cloudformation delete-stack`, then
`aws cloudformation wait stack-delete-complete`) before deploying again.

If Glue 6.0 is not available in `ap-south-1`, redeploy with the template's
`GlueVersion` parameter set to `5.1` (see
[ADR-0005](../docs/adr/0005-t1-batch-lake-design.md)). Masked evidence lands in
`evidence/t1a/<date>/`; check it for account IDs before committing.
