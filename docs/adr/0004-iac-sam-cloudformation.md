# ADR-0004: Infrastructure as code with SAM-extended CloudFormation, one stack per tier

- **Status:** Accepted (2026-09-26, by the project owner, after a
  section-by-section brainstorm and a review of this written ADR)
- **Deciders:** project owner
- **Related:** `docs/GAPS.md` G-13;
  [ADR-0001](0001-ingest-and-warehouse-stack.md) (hybrid stack, Mumbai);
  [ADR-0001 cost tiers](0001-hybrid-cost-tiers.md) (IAM applied per tier by
  the owner); [`exam-guide-map.md`](../exam-guide-map.md) skills 1.4.5,
  1.4.6, 1.4.8, 4.1.2, 4.1.4, 4.2.1, 4.2.6

## Context

G-13 recorded that the brief named no infrastructure-as-code (IaC) tool and
no security baseline. Tier T1 (Lambda → S3 → Glue → Athena in
`ap-south-1`) cannot be built until both are settled.

Constraints that shaped the choice:

- **Exam coverage comes first.** The DEA-C01 guide names three IaC skills:
  1.4.5 (deploy with IaC), 1.4.6 (package serverless pipelines with AWS SAM)
  and 1.4.8 (repeatable deploys with CloudFormation or CDK). Terraform is not
  named.
- **The owner applies every IAM change.** Project guardrail: no agent runs
  IAM, billing or account changes. Each tier's IAM is applied by the owner
  as one reviewed stack (ADR-0001 cost tiers, section 4).
- **This repo is public.** No account ID, ARN or email may be committed.
- **Every tier is torn down after each working window** (cost rule), so a
  tier must be removable in one command.
- **Terraform is already shown** in the sibling repo `gridpulse-gcp`, so
  choosing it here adds little portfolio breadth.

Facts checked on 2026-09-26:

- The AWS SAM CLI can run Lambda functions from a CDK-synthesised template
  (`sam local invoke -t ./cdk.out/<Stack>.template.json`), after `cdk synth`
  ([CDK guide: testing locally with SAM](https://docs.aws.amazon.com/cdk/v2/guide/testing-locally-with-sam-cli.html)).
- `cdk bootstrap` deploys a `CDKToolkit` stack containing an S3 bucket, an
  ECR repository **and IAM roles**
  ([CDK guide: bootstrapping](https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping.html)).
- `sam deploy --resolve-s3` creates an S3 bucket automatically; `--s3-bucket`
  uses a named bucket instead; `--no-execute-changeset` creates a change set
  and exits without applying it
  ([`sam deploy` reference](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-cli-command-reference-sam-deploy.html)).
- `cfn-lint` is a local linting tool; `sam validate --lint` wraps it
  ([`sam validate` reference](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-cli-command-reference-sam-validate.html)).
- AWS KMS in Mumbai: **$1 per customer managed key version per month**;
  $0.03 per 10,000 requests beyond the free tier (Price List API, `awskms`
  `ap-south-1`, publication date 2026-09-11).

## Decision

1. **Tool: AWS SAM-extended CloudFormation.** Each tier is one YAML template
   with `Transform: AWS::Serverless-2016-10-31`. SAM resource types are used
   for serverless pieces (Lambda functions and their events); plain
   CloudFormation types are used for everything else (S3, Glue, Athena,
   IAM). A SAM template is a CloudFormation template, so this single tool
   shows 1.4.5, 1.4.6 and 1.4.8.

2. **Layout: one stack per tier.**

   ```
   infra/
     README.md                  ← lint, local test, owner deploy/teardown steps
     foundation/template.yaml   ← artifacts bucket for packaged code (deployed once)
     t1-lake/template.yaml      ← ingest Lambda, Bronze/Silver/Gold buckets,
                                   Glue database/tables/job, Athena workgroup,
                                   one IAM role per service
     samconfig.example.toml     ← placeholders only; real samconfig.toml is gitignored
   ```

   Later tiers (T2–T4) each get their own folder when they are designed.
   `sam delete --stack-name <tier>` removes a tier in one command.

3. **Deploy flow: the owner runs every deploy.**

   | Step | Who | AWS credentials |
   |---|---|---|
   | Write templates; `cfn-lint`; `sam build`; `sam local invoke` (Docker) | Agent or CI | None |
   | `aws cloudformation deploy` of the foundation stack | Owner | Yes |
   | `sam deploy --s3-bucket <artifacts bucket> --no-execute-changeset --capabilities CAPABILITY_IAM` | Owner | Yes |
   | Review the change set in the console, IAM resources first | Owner | Yes |
   | Execute the change set; later `sam delete` and log the teardown in `cost-model.md` | Owner | Yes |

   Passing `--s3-bucket` to the project's own artifacts bucket avoids the
   SAM-managed default stack, so no resource exists that no template in this
   repo describes.

4. **Security baseline (closes the security half of G-13).**
   - **Encryption at rest:** SSE-S3 on every bucket.
   - **Encryption in transit:** every bucket policy denies requests where
     `aws:SecureTransport` is `false`.
   - **No public access:** all four S3 Block Public Access settings on every
     bucket.
   - **Least privilege:** one IAM role per service, scoped to specific
     bucket and prefix ARNs built from `AWS::AccountId` / `AWS::Region`
     pseudo-parameters. No `Action: "*"`. `Resource: "*"` only where an
     action supports no resource-level permission, with a comment on that
     line naming the action.
   - **No IAM users or access keys** are created by any template.
   - **No identifiers in the repo:** no 12-digit account IDs, ARNs or emails
     in committed files; names use `!Sub` with the stack name.

5. **Checks without AWS credentials.**
   - `cfn-lint` (pinned in the dev dependencies) runs on every template in CI.
   - `tests/test_infra_templates.py` parses the templates and fails on: any
     12-digit number; a bucket missing encryption, Block Public Access or the
     TLS-only deny; any statement with both `Action: "*"` and
     `Resource: "*"`; any `AWS::IAM::User` or `AWS::IAM::AccessKey`; a
     resource name not built from the stack name.
   - `sam build` + `sam local invoke` of the ingest Lambda is a documented
     manual step (needs Docker), not a CI job.

## Consequences

- Exam skills 1.4.5, 1.4.6 and 1.4.8 move to **designed**, and 4.1.2,
  4.1.4, 4.2.1 and 4.2.6 gain a concrete home (IaC-defined, scoped roles).
  They become **shown** only after a real deploy.
- The owner reviews exactly the YAML that is applied; no generated layer and
  no bootstrap roles sit in between.
- Templates are more verbose than CDK code, and there is no unit-testable
  construct layer; the guardrail tests partly compensate.
- The owner must install AWS CLI v2 and the AWS SAM CLI before the first
  deploy. `sam local invoke` also needs Docker.
- KMS customer-managed keys are not used, so exam skills on key management
  (Task 4.3) stay stretch skills.
- Any machine where the owner is signed in to the AWS CLI exposes those
  credentials to any agent shell on the same machine. The owner signs in only
  for the deploy window and signs out afterwards (documented in
  `infra/README.md`, written with the IaC foundation).
- The owner deploys as a non-root admin identity, not the root user.
  Creating that identity is an owner-only IAM action, done once before the
  first deploy.

## Alternatives rejected

- **AWS CDK (Python) as the main tool, SAM CLI only for local tests.**
  Strongest industry signal and pytest-friendly assertions, but 1.4.6 would
  only be partly shown (SAM would test, not package), and `cdk bootstrap`
  creates IAM roles outside this repo's templates. Kept as a possible later
  upgrade.
- **Plain CloudFormation without SAM.** Simplest, but leaves 1.4.6 as an
  accepted limitation.
- **Terraform.** Not named in DEA-C01 and already shown in `gridpulse-gcp`;
  also needs a remote state backend (an extra bucket and lock) or local state
  that is easy to lose between sessions.
- **SSE-KMS with a customer managed key.** $1 per key version per month in
  Mumbai for as long as the key exists, and key deletion needs a 7–30 day
  waiting period
  ([KMS key deletion](https://docs.aws.amazon.com/kms/latest/cryptographic-details/key-deletion.html)),
  which does not fit tearing everything down after each working window.
  Whether a key is billed during that wait is unverified. Stretch goal for
  Task 4.3.
- **`sam deploy --resolve-s3`.** Creates a SAM-managed stack that no template
  in this repo describes; replaced by the foundation artifacts bucket.
