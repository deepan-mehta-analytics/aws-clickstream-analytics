# infra/

Infrastructure as code for this project: AWS SAM-extended CloudFormation,
one stack per folder ([ADR-0004](../docs/adr/0004-iac-sam-cloudformation.md)).
**Only the account owner deploys.** No agent or CI job ever holds AWS
credentials; CI only lints and tests the templates.

| Folder | Stack name | What it creates | Status |
|---|---|---|---|
| `foundation/` | `clickstream-foundation` | One S3 bucket for packaged code (SSE-S3, private, TLS only, 30-day expiry) | Written, not deployed |
| `t1-lake/` | `clickstream-t1-lake` | Tier T1 (Lambda, Bronze/Silver/Gold buckets, Glue, Athena) | Not written yet |

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
sam build --template-file <tier>/template.yaml                     # package code into .aws-sam/ (gitignored)
sam deploy --config-env <tier> --no-execute-changeset              # create a change set only
# review the change set in the CloudFormation console: IAM resources first
# then execute it from the console (or rerun sam deploy without --no-execute-changeset)
sam delete --stack-name clickstream-<tier> --region ap-south-1     # teardown at the end of the window
```

Record every window (created, torn down, measured cost) in the teardown log
in [`docs/cost-model.md`](../docs/cost-model.md).
