# Skills-Coverage Map: AWS Certified Data Engineer – Associate

A skills-coverage matrix, not exam prep. Each skill in the official exam
guide is mapped to the evidence in this repo that demonstrates it. Skill
wording below is **paraphrased**; the official guide is the authority.

- **Source:** [DEA-C01 exam guide](https://docs.aws.amazon.com/aws-certification/latest/data-engineer-associate-01/data-engineer-associate-01.html),
  **version 1.1** (published 2025-12-12), fetched 2026-09-25.
- **Re-check log:** [`exam-guide-delta.md`](exam-guide-delta.md).

**Coverage: 8 of 120 skills shown (local run, tier T0; no AWS yet) · 15 designed · 97 not started**
(as of 2026-10-05; the local twin, tier T0, is built and run; ADR-0004 designs the IaC and IAM; no cloud run exists yet).

**Plan: 104 planned · 8 stretch · 8 not planned.** Planned skills by
domain: D1 37/37, D2 20/26, D3 27/28, D4 20/29. On 2026-09-26, 26 stretch
skills were promoted to planned as low-cost add-ons to tiers T1–T4 (each row
names its tier); the costs of Glue Data Quality, Lake Formation, CloudTrail,
Logs Insights and Parameter Store are to be verified before T2 is built. On
2026-10-05, with no free credits available, 18 of the 26 not-planned skills
were promoted after pricing each one in Mumbai from the AWS Price List API
(about ₹170 in total, estimates, not measured); each row names its tier and
estimate, and each one adds a line to that tier's teardown. The 8 left are
accepted limitations (see `GAPS.md` §3): unpriced SageMaker services, a
Transfer Family leak risk, a schema-conversion source database, and two
skills that need AWS Organizations. Twelve skills (11 planned, 1 stretch)
depend on the streaming and Redshift windows in ADR-0001, and would be lost with a
batch-only design.

Status legend:
- ✅ **shown**: runnable and exercised in a real run, with evidence linked.
- 🟡 **designed**: covered by an ADR, doc or IaC stub, but not yet run.
- ⬜ **not started**.

Plan column (from [ADR-0001](adr/0001-ingest-and-warehouse-stack.md),
Accepted 2026-09-25):
- **Planned**: in the intended build.
- **Stretch**: fits the design if time and cost allow.
- **Not planned**: outside this project's scope; a Known Limitations
  candidate.

---

## Domain 1: Data Ingestion and Transformation (34%)

### Task 1.1: Ingest data

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 1.1.1 | Consume from streaming sources | Planned | Kinesis Data Streams → Firehose in a streaming window | ⬜ |
| 1.1.2 | Consume from batch sources | Planned | S3 Bronze read by Glue | ⬜ |
| 1.1.3 | Configure batch ingestion options | Planned | Glue job bookmarks and partition pruning | ⬜ |
| 1.1.4 | Consume data APIs | Planned | T1: Lambda pulls reference data (for example currency rates) from a free public API into Bronze | ⬜ |
| 1.1.5 | Schedule jobs and crawlers | Planned | EventBridge schedule for the batch job | ⬜ |
| 1.1.6 | Trigger on events | Planned | S3 event notification → Lambda | ⬜ |
| 1.1.7 | Invoke Lambda from Kinesis | Planned | T3: Lambda consumer on the Kinesis stream (event source mapping) | ⬜ |
| 1.1.8 | IP allowlists for data-source access | Planned | T1c: S3 bucket policy with an `aws:SourceIp` allowlist on a demo bucket (shows why AWS-service callers such as Glue fall outside it). Est. ₹0 | ⬜ |
| 1.1.9 | Handle throttling and rate limits | Planned | T1: producer retries with exponential backoff on throttling, tested locally first | ⬜ |
| 1.1.10 | Fan-in / fan-out for streams | Planned | T3: two standard consumers on one stream (Firehose + Lambda); enhanced fan-out explained, not bought | ⬜ |
| 1.1.11 | Replayable ingestion | Planned | Immutable raw Bronze in S3 plus stream retention | ⬜ |
| 1.1.12 | Stateful vs stateless processing | Planned | `build_visits` aggregates clicks per real visit (stateful), Silver cleans per click (stateless): `src/clickstream/gold.py`, `tests/test_gold.py` (local run, tier T0) | ✅ |

### Task 1.2: Transform and process data

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 1.2.1 | Tune container workloads | Planned | T1c: a small Lambda packaged as a container image (partial: no ECS/EKS tuning). Est. < ₹10, ECR storage price to verify | ⬜ |
| 1.2.2 | Connect via JDBC/ODBC | Planned | T4: JDBC connection from a local SQL client to Redshift Serverless | ⬜ |
| 1.2.3 | Integrate multiple sources | Planned | T1: clickstream joined with the public-API reference data (1.1.4) in Gold | ⬜ |
| 1.2.4 | Keep processing costs down | Planned | [`cost-model.md`](cost-model.md), ADR-0001 | 🟡 |
| 1.2.5 | Pick transformation services to fit requirements | Planned | Glue, Lambda, Redshift SQL | ⬜ |
| 1.2.6 | Convert between formats | Planned | CSV → Parquet at every layer: `src/clickstream/local_run.py` (local run, tier T0); Firehose JSON → Parquet still to come | ✅ |
| 1.2.7 | Debug transformation failures and slowness | Planned | Runbook entries from real failures | ⬜ |
| 1.2.8 | Expose data to other systems as APIs | Planned | T2: HTTP API (API Gateway + Lambda) serving one Athena summary; the workgroup's 1 GB scan cutoff caps abuse. Est. ₹0 | ⬜ |
| 1.2.9 | Characterise data volume, velocity and variety | Planned | Measured profile in [`data/README.md`](../data/README.md); [data dictionary](data-dictionary.md) | 🟡 |
| 1.2.10 | Use LLMs in data processing | Planned | T1c: an LLM (Amazon Bedrock) labels the 217 product codes; model availability in Mumbai to verify. Est. < ₹5 | ⬜ |

### Task 1.3: Orchestrate pipelines

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 1.3.1 | Build ETL workflows with orchestration services | Planned | Step Functions or Glue workflow plus EventBridge | ⬜ |
| 1.3.2 | Design for resilience and fault tolerance | Planned | Retries and a dead-letter queue | ⬜ |
| 1.3.3 | Run serverless workflows | Planned | Serverless orchestration of the batch path | ⬜ |
| 1.3.4 | Send alerts via notification services | Planned | SNS alert on job failure | ⬜ |

### Task 1.4: Apply programming concepts

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 1.4.1 | Reduce ingest/transform runtime | Planned | T1: measured before/after runtime and bytes scanned (CSV vs Parquet, partition pruning) | ⬜ |
| 1.4.2 | Tune Lambda concurrency and performance | Planned | T1: reserved concurrency and memory settings on the ingest Lambda, in the SAM template | ⬜ |
| 1.4.3 | Use data-engineering languages | Planned | Python package `src/clickstream/` plus SQL in `sql/summaries/` (local run, tier T0) | ✅ |
| 1.4.4 | Apply software engineering practice | Planned | Git history, 45 pytest tests (TDD), ruff, a quality report; CI defined but not yet run (local run, tier T0) | ✅ |
| 1.4.5 | Deploy with IaC | Planned | One SAM-extended CloudFormation stack per tier, owner-deployed via a reviewed change set ([ADR-0004](adr/0004-iac-sam-cloudformation.md)) | 🟡 |
| 1.4.6 | Package serverless pipelines with SAM | Planned | `sam build` / `sam deploy` of the tier templates; `sam local invoke` of the ingest Lambda ([ADR-0004](adr/0004-iac-sam-cloudformation.md)) | 🟡 |
| 1.4.7 | Mount storage in Lambda | Planned | T1c: a separate small Lambda in a VPC mounts EFS (S3 gateway endpoint, no NAT gateway). Est. ≈ ₹2 | ⬜ |
| 1.4.8 | Repeatable deploys with CloudFormation/CDK | Planned | CloudFormation stacks (SAM transform), deployed and deleted per working window ([ADR-0004](adr/0004-iac-sam-cloudformation.md)); CDK rejected | 🟡 |
| 1.4.9 | CI/CD for data pipelines | Planned | GitHub Actions | ⬜ |
| 1.4.10 | Distributed computing concepts | Planned | Spark in Glue, with a concept note | ⬜ |
| 1.4.11 | Data structures and algorithms | Planned | T1d: concept note linking the code that uses hash-based dedup, sorting and window functions. ₹0 | ⬜ |

---

## Domain 2: Data Store Management (26%)

### Task 2.1: Choose a data store

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 2.1.1 | Match storage services to cost and performance needs | Planned | S3 vs Redshift vs Kinesis: [ADR-0001](adr/0001-ingest-and-warehouse-stack.md) and its [cost-tier annex](adr/0001-hybrid-cost-tiers.md) | 🟡 |
| 2.1.2 | Configure stores for access patterns | Planned | Redshift sort/distribution keys; S3 partitioning | ⬜ |
| 2.1.3 | Specialised stores (vector index, key/value) | Planned | T1d: S3 Vectors index of product embeddings for a "similar products" lookup. Est. < ₹5 | ⬜ |
| 2.1.4 | Migration tools such as Transfer Family | Not planned | Accepted limitation: a Transfer Family endpoint costs ≈ ₹34/hour while it exists (≈ ₹25,000/month if left running) | ⬜ |
| 2.1.5 | Federated queries, materialized views, Spectrum | Planned | Redshift Spectrum over S3 or a materialized view | ⬜ |
| 2.1.6 | Manage locks | Planned | T2: DynamoDB conditional-write lock so only one batch run executes at a time. Est. ₹0 | ⬜ |
| 2.1.7 | Open table formats (Iceberg) | Planned | T1: Silver as an Apache Iceberg table queried by Athena | ⬜ |
| 2.1.8 | Vector index types | Planned | T1d: same S3 Vectors demo (partial: S3 Vectors does not expose HNSW/IVF index types; concept note covers them) | ⬜ |

### Task 2.2: Data cataloging

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 2.2.1 | Query source data through a catalog | Planned | Athena via Glue Data Catalog | ⬜ |
| 2.2.2 | Build a technical catalog | Planned | Glue Data Catalog | ⬜ |
| 2.2.3 | Discover schemas with crawlers | Planned | T1: one crawler run on Bronze compared with IaC-defined tables (crawler cost noted) | ⬜ |
| 2.2.4 | Keep partitions in sync with the catalog | Planned | Athena partition projection on monthly partitions, [ADR-0003](adr/0003-data-model.md) | 🟡 |
| 2.2.5 | Create catalog connections | Stretch | — | ⬜ |
| 2.2.6 | Business data catalogs | Not planned | Accepted limitation: SageMaker Unified Studio / DataZone has no Mumbai price in the Price List API (2026-10-05) | ⬜ |

### Task 2.3: Data lifecycle

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 2.3.1 | Load and unload between S3 and Redshift | Planned | `COPY` / `UNLOAD` in a streaming window | ⬜ |
| 2.3.2 | Move data between tiers with Lifecycle rules | Planned | S3 Lifecycle on Bronze | ⬜ |
| 2.3.3 | Expire aged data with Lifecycle rules | Planned | S3 Lifecycle expiry | ⬜ |
| 2.3.4 | Versioning and TTL | Planned | T1: S3 versioning on Bronze with a lifecycle rule expiring old versions | ⬜ |
| 2.3.5 | Delete data for legal or business reasons | Planned | T1: delete one visit's rows from the Iceberg Silver table, with before/after counts | ⬜ |
| 2.3.6 | Resiliency and availability | Stretch | — | ⬜ |

### Task 2.4: Data models and schema evolution

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 2.4.1 | Design Redshift / DynamoDB / Lake Formation schemas | Planned | Two-grain star schema (clicks, visits), [ADR-0003](adr/0003-data-model.md) | 🟡 |
| 2.4.2 | Handle changing data characteristics | Planned | T1: add a column to the Iceberg Silver table (schema evolution) without rewriting data | ⬜ |
| 2.4.3 | Schema conversion tools | Not planned | Accepted limitation: needs a paid source database; no migration in this project | ⬜ |
| 2.4.4 | Data lineage tooling | Not planned | Accepted limitation: lineage tooling (SageMaker Catalog) is unpriced for Mumbai (2026-10-05) | ⬜ |
| 2.4.5 | Partitioning, compression and indexing practice | Planned | Parquet partitioned by month (`click_month`, `visit_month`) in `local_run.py` (local run, tier T0); Redshift sort and distribution keys still designed only, [ADR-0003](adr/0003-data-model.md) | ✅ |
| 2.4.6 | Vectorization concepts | Planned | T1d: same S3 Vectors demo (embeddings generated with Bedrock) | ⬜ |

---

## Domain 3: Data Operations and Support (22%)

### Task 3.1: Automate processing

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 3.1.1 | Orchestrate pipelines | Planned | Step Functions | ⬜ |
| 3.1.2 | Troubleshoot managed workflows | Planned | Runbook entries | ⬜ |
| 3.1.3 | Call AWS SDKs from code | Planned | boto3 event generator | ⬜ |
| 3.1.4 | Use service features to process data | Planned | Glue, Redshift | ⬜ |
| 3.1.5 | Consume and maintain data APIs | Planned | T2: same HTTP API as 1.2.8, called from a script | ⬜ |
| 3.1.6 | Prepare data with DataBrew / Unified Studio | Planned | T1d: one AWS Glue DataBrew recipe job (jobs only; interactive sessions cost about ₹114 each). Est. ≈ ₹10, minimum billing to verify | ⬜ |
| 3.1.7 | Query data with Athena | Planned | Athena queries on Silver/Gold | ⬜ |
| 3.1.8 | Automate processing with Lambda | Planned | Generator and trigger functions | ⬜ |
| 3.1.9 | Manage events and schedules | Planned | EventBridge | ⬜ |

### Task 3.2: Analyze data

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 3.2.1 | Visualize data | Planned | Streamlit app on Athena plus a published snapshot ([ADR-0002](adr/0002-dashboard-streamlit.md)); QuickSight itself not shown | 🟡 |
| 3.2.2 | Verify and clean data | Planned | Athena validation queries | ⬜ |
| 3.2.3 | Query and create views with SQL in Redshift and Athena | Planned | Views in both engines | ⬜ |
| 3.2.4 | Explore data with Athena Spark notebooks | Planned | T1d: one Athena Spark notebook session of about 20 minutes. Est. ≈ ₹50, minimum DPUs to verify | ⬜ |
| 3.2.5 | Weigh provisioned vs serverless | Planned | [ADR-0001](adr/0001-ingest-and-warehouse-stack.md), `cost-model.md` | 🟡 |
| 3.2.6 | Aggregation, rolling averages, grouping, pivoting | Planned | Grouping and aggregation in `sql/summaries/*.sql`, `tests/test_summaries.py` (local run, tier T0) | ✅ |

### Task 3.3: Maintain and monitor pipelines

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 3.3.1 | Pull logs for audit | Planned | T2: export CloudTrail event history for a working window | ⬜ |
| 3.3.2 | Logging and monitoring for traceability | Planned | CloudWatch metrics and logs | ⬜ |
| 3.3.3 | Alert from monitoring | Planned | CloudWatch alarm → SNS | ⬜ |
| 3.3.4 | Troubleshoot performance | Planned | T1: diagnose a slow Athena query from its statistics and fix it (partitions, Parquet) | ⬜ |
| 3.3.5 | Track API calls with CloudTrail | Planned | T2: CloudTrail event history for the pipeline's API calls | ⬜ |
| 3.3.6 | Troubleshoot and maintain Glue/EMR pipelines | Planned | Glue job runbook | ⬜ |
| 3.3.7 | Log application data to CloudWatch Logs | Planned | Structured Lambda/Glue logs | ⬜ |
| 3.3.8 | Analyze logs with AWS services | Planned | T2: CloudWatch Logs Insights queries over Lambda and Glue logs | ⬜ |

### Task 3.4: Data quality

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 3.4.1 | Check quality during processing | Planned | Hard rules route failures to `clicks_rejected` with a reason: `src/clickstream/silver.py`, `tests/test_silver.py` (local run, tier T0) | ✅ |
| 3.4.2 | Define quality rules | Planned | T2: AWS Glue Data Quality ruleset (DQDL) on Silver | ⬜ |
| 3.4.3 | Investigate consistency | Stretch | Bronze → Silver → Gold counts reconciled with measured stats: `tests/test_full_file.py`, `quality_report.json` (local run, tier T0) | ✅ |
| 3.4.4 | Sampling techniques | Planned | T1: Athena TABLESAMPLE compared with a full scan | ⬜ |
| 3.4.5 | Handle data skew | Planned | T1: country skew (Poland ≈ 81% of clicks) measured and handled in Spark | ⬜ |

---

## Domain 4: Data Security and Governance (18%)

IAM changes are run by the account owner, never by an agent. IaC in this
repo defines roles and policies; the owner applies them.

### Task 4.1: Authentication

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 4.1.1 | Update VPC security groups | Stretch | Redshift Serverless workgroup security group | ⬜ |
| 4.1.2 | Manage IAM groups, roles and endpoints | Planned | IaC-defined roles ([ADR-0004](adr/0004-iac-sam-cloudformation.md)) | 🟡 |
| 4.1.3 | Create and rotate credentials in Secrets Manager | Stretch | Secrets Manager cost not yet verified | ⬜ |
| 4.1.4 | Roles for service access | Planned | Lambda, Glue, Firehose, Redshift roles, one per service ([ADR-0004](adr/0004-iac-sam-cloudformation.md)) | 🟡 |
| 4.1.5 | Policies on access points and endpoints | Planned | T1: S3 access point for read-only analyst access to Gold | ⬜ |
| 4.1.6 | Managed vs unmanaged services | Planned | ADR discussion | ⬜ |
| 4.1.7 | SageMaker Unified Studio domains/projects | Not planned | Accepted limitation: SageMaker Unified Studio is unpriced for Mumbai (2026-10-05) | ⬜ |

### Task 4.2: Authorization

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 4.2.1 | Write custom IAM policies | Planned | Scoped IaC policies ([ADR-0004](adr/0004-iac-sam-cloudformation.md)) | 🟡 |
| 4.2.2 | Store app and database credentials | Planned | T1: pipeline configuration in SSM Parameter Store (standard parameters) | ⬜ |
| 4.2.3 | Database users, groups and roles | Planned | Redshift read-only analyst role | ⬜ |
| 4.2.4 | Permissions via Lake Formation | Planned | T2: Lake Formation grants for a read-only analyst role | ⬜ |
| 4.2.5 | Role-, tag- and attribute-based access | Planned | T2: Lake Formation tag-based access control (LF-Tags) | ⬜ |
| 4.2.6 | Least-privilege policies | Planned | Per-service policies scoped to bucket/prefix ARNs, enforced by template tests ([ADR-0004](adr/0004-iac-sam-cloudformation.md)) | 🟡 |

### Task 4.3: Encryption and masking

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 4.3.1 | Mask and anonymise data | Planned | Hashed user IDs | ⬜ |
| 4.3.2 | Encrypt with KMS keys | Stretch | SSE-S3 chosen; KMS key rejected for cost and deletion wait ([ADR-0004](adr/0004-iac-sam-cloudformation.md)) | ⬜ |
| 4.3.3 | Cross-account encryption | Not planned | Accepted limitation: needs AWS Organizations and a second account, an owner-only governance change (cost is not the blocker) | ⬜ |
| 4.3.4 | Encryption in transit | Planned | TLS-only bucket policy | ⬜ |

### Task 4.4: Logs for audit

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 4.4.1 | Track API calls with CloudTrail | Planned | T2: same evidence as 3.3.5 (CloudTrail) | ⬜ |
| 4.4.2 | Store app logs in CloudWatch Logs | Planned | Same as 3.3.7 | ⬜ |
| 4.4.3 | Centralised queries with CloudTrail Lake | Planned | T2: CloudTrail Lake event data store for one window, then ingestion stopped and the store deleted (7-day wait). Est. ≈ ₹5 | ⬜ |
| 4.4.4 | Analyze logs with AWS services | Planned | T2: same evidence as 3.3.8 (Logs Insights) | ⬜ |
| 4.4.5 | Large-volume logging integrations | Planned | T3: CloudWatch Logs subscription filter into the existing Firehose stream. Est. ≈ ₹1 | ⬜ |

### Task 4.5: Privacy and governance

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 4.5.1 | Grant data-sharing permissions | Planned | T4: Redshift data share to a second Serverless namespace in the same account, inside the T4 window. Est. ₹20–50 extra | ⬜ |
| 4.5.2 | Identify PII | Planned | T2: Amazon Macie scan of a labelled file of made-up personal data; Macie disabled the same day. Est. < ₹10 | ⬜ |
| 4.5.3 | Block replication to disallowed Regions | Not planned | Accepted limitation: needs AWS Organizations (SCPs), an owner-only governance change (cost is not the blocker) | ⬜ |
| 4.5.4 | View account configuration changes | Planned | T2: AWS Config recorder for one window, then stopped. Est. ≈ ₹35 | ⬜ |
| 4.5.5 | Data sovereignty | Stretch | Mumbai region choice for data residency in [ADR-0001](adr/0001-ingest-and-warehouse-stack.md) | 🟡 |
| 4.5.6 | Access via SageMaker Catalog projects | Not planned | Accepted limitation: SageMaker Catalog is unpriced for Mumbai (2026-10-05) | ⬜ |
| 4.5.7 | Governance frameworks and sharing patterns | Stretch | Concept note | ⬜ |
