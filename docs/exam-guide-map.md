# Skills-Coverage Map: AWS Certified Data Engineer – Associate

A skills-coverage matrix, not exam prep. Each skill in the official exam
guide is mapped to the evidence in this repo that demonstrates it. Skill
wording below is **paraphrased**; the official guide is the authority.

- **Source:** [DEA-C01 exam guide](https://docs.aws.amazon.com/aws-certification/latest/data-engineer-associate-01/data-engineer-associate-01.html),
  **version 1.1** (published 2025-12-12), fetched 2026-09-25.
- **Re-check log:** [`exam-guide-delta.md`](exam-guide-delta.md).

**Coverage: 0 of 120 skills shown · 2 designed · 118 not started**
(as of 2026-09-25; no code or cloud run exists yet).

**Plan: 58 planned · 36 stretch · 26 not planned.** Planned skills by
domain: D1 21/37, D2 11/26, D3 17/28, D4 9/29. Security and governance
(D4) is the thinnest area, because several of its skills need AWS
Organizations, multiple accounts or paid services outside this project's
scope. Eleven skills (6 planned, 5 stretch) depend on the streaming and
Redshift window in ADR-0001, and would be lost with a batch-only design.

Status legend:
- ✅ **shown**: runnable and exercised in a real run, with evidence linked.
- 🟡 **designed**: covered by an ADR, doc or IaC stub, but not yet run.
- ⬜ **not started**.

Plan column (from [ADR-0001](adr/0001-ingest-and-warehouse-stack.md),
Proposed):
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
| 1.1.4 | Consume data APIs | Stretch | Generator pulling reference data from a public API | ⬜ |
| 1.1.5 | Schedule jobs and crawlers | Planned | EventBridge schedule for the batch job | ⬜ |
| 1.1.6 | Trigger on events | Planned | S3 event notification → Lambda | ⬜ |
| 1.1.7 | Invoke Lambda from Kinesis | Stretch | Lambda consumer on the stream | ⬜ |
| 1.1.8 | IP allowlists for data-source access | Not planned | No private data sources | ⬜ |
| 1.1.9 | Handle throttling and rate limits | Stretch | Producer retry and backoff on Kinesis | ⬜ |
| 1.1.10 | Fan-in / fan-out for streams | Stretch | Second consumer (enhanced fan-out is extra cost) | ⬜ |
| 1.1.11 | Replayable ingestion | Planned | Immutable raw Bronze in S3 plus stream retention | ⬜ |
| 1.1.12 | Stateful vs stateless processing | Planned | Sessionization (stateful) vs per-event cleaning (stateless) | ⬜ |

### Task 1.2: Transform and process data

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 1.2.1 | Tune container workloads | Not planned | No containers in the design | ⬜ |
| 1.2.2 | Connect via JDBC/ODBC | Stretch | Redshift JDBC connection from a client | ⬜ |
| 1.2.3 | Integrate multiple sources | Stretch | Join clickstream with page and user reference data | ⬜ |
| 1.2.4 | Keep processing costs down | Planned | [`cost-model.md`](cost-model.md), ADR-0001 | 🟡 |
| 1.2.5 | Pick transformation services to fit requirements | Planned | Glue, Lambda, Redshift SQL | ⬜ |
| 1.2.6 | Convert between formats | Planned | Firehose JSON → Parquet; Glue | ⬜ |
| 1.2.7 | Debug transformation failures and slowness | Planned | Runbook entries from real failures | ⬜ |
| 1.2.8 | Expose data to other systems as APIs | Not planned | — | ⬜ |
| 1.2.9 | Characterise data volume, velocity and variety | Planned | Data dictionary | ⬜ |
| 1.2.10 | Use LLMs in data processing | Not planned | — | ⬜ |

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
| 1.4.1 | Reduce ingest/transform runtime | Stretch | Before/after job timing | ⬜ |
| 1.4.2 | Tune Lambda concurrency and performance | Stretch | Generator concurrency settings | ⬜ |
| 1.4.3 | Use data-engineering languages | Planned | Python, SQL | ⬜ |
| 1.4.4 | Apply software engineering practice | Planned | Git, tests, CI, logging | ⬜ |
| 1.4.5 | Deploy with IaC | Planned | IaC for every resource (tool choice open, G-13) | ⬜ |
| 1.4.6 | Package serverless pipelines with SAM | Stretch | Depends on the IaC choice | ⬜ |
| 1.4.7 | Mount storage in Lambda | Not planned | — | ⬜ |
| 1.4.8 | Repeatable deploys with CloudFormation/CDK | Stretch | Depends on the IaC choice (G-13) | ⬜ |
| 1.4.9 | CI/CD for data pipelines | Planned | GitHub Actions | ⬜ |
| 1.4.10 | Distributed computing concepts | Planned | Spark in Glue, with a concept note | ⬜ |
| 1.4.11 | Data structures and algorithms | Not planned | — | ⬜ |

---

## Domain 2: Data Store Management (26%)

### Task 2.1: Choose a data store

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 2.1.1 | Match storage services to cost and performance needs | Planned | S3 vs Redshift vs Kinesis, per ADR-0001 | ⬜ |
| 2.1.2 | Configure stores for access patterns | Planned | Redshift sort/distribution keys; S3 partitioning | ⬜ |
| 2.1.3 | Specialised stores (vector index, key/value) | Not planned | — | ⬜ |
| 2.1.4 | Migration tools such as Transfer Family | Not planned | — | ⬜ |
| 2.1.5 | Federated queries, materialized views, Spectrum | Planned | Redshift Spectrum over S3 or a materialized view | ⬜ |
| 2.1.6 | Manage locks | Not planned | — | ⬜ |
| 2.1.7 | Open table formats (Iceberg) | Stretch | Iceberg table for Silver | ⬜ |
| 2.1.8 | Vector index types | Not planned | — | ⬜ |

### Task 2.2: Data cataloging

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 2.2.1 | Query source data through a catalog | Planned | Athena via Glue Data Catalog | ⬜ |
| 2.2.2 | Build a technical catalog | Planned | Glue Data Catalog | ⬜ |
| 2.2.3 | Discover schemas with crawlers | Stretch | Crawler vs IaC-defined tables (crawler cost) | ⬜ |
| 2.2.4 | Keep partitions in sync with the catalog | Planned | Partition projection or partition loads | ⬜ |
| 2.2.5 | Create catalog connections | Stretch | — | ⬜ |
| 2.2.6 | Business data catalogs | Not planned | — | ⬜ |

### Task 2.3: Data lifecycle

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 2.3.1 | Load and unload between S3 and Redshift | Planned | `COPY` / `UNLOAD` in a streaming window | ⬜ |
| 2.3.2 | Move data between tiers with Lifecycle rules | Planned | S3 Lifecycle on Bronze | ⬜ |
| 2.3.3 | Expire aged data with Lifecycle rules | Planned | S3 Lifecycle expiry | ⬜ |
| 2.3.4 | Versioning and TTL | Stretch | S3 versioning on Bronze | ⬜ |
| 2.3.5 | Delete data for legal or business reasons | Stretch | User-deletion walkthrough | ⬜ |
| 2.3.6 | Resiliency and availability | Stretch | — | ⬜ |

### Task 2.4: Data models and schema evolution

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 2.4.1 | Design Redshift / DynamoDB / Lake Formation schemas | Planned | Redshift star schema | ⬜ |
| 2.4.2 | Handle changing data characteristics | Stretch | Schema-evolution test | ⬜ |
| 2.4.3 | Schema conversion tools | Not planned | — | ⬜ |
| 2.4.4 | Data lineage tooling | Not planned | — | ⬜ |
| 2.4.5 | Partitioning, compression and indexing practice | Planned | Parquet, date partitions, sort keys | ⬜ |
| 2.4.6 | Vectorization concepts | Not planned | — | ⬜ |

---

## Domain 3: Data Operations and Support (22%)

### Task 3.1: Automate processing

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 3.1.1 | Orchestrate pipelines | Planned | Step Functions | ⬜ |
| 3.1.2 | Troubleshoot managed workflows | Planned | Runbook entries | ⬜ |
| 3.1.3 | Call AWS SDKs from code | Planned | boto3 event generator | ⬜ |
| 3.1.4 | Use service features to process data | Planned | Glue, Redshift | ⬜ |
| 3.1.5 | Consume and maintain data APIs | Not planned | — | ⬜ |
| 3.1.6 | Prepare data with DataBrew / Unified Studio | Not planned | — | ⬜ |
| 3.1.7 | Query data with Athena | Planned | Athena queries on Silver/Gold | ⬜ |
| 3.1.8 | Automate processing with Lambda | Planned | Generator and trigger functions | ⬜ |
| 3.1.9 | Manage events and schedules | Planned | EventBridge | ⬜ |

### Task 3.2: Analyze data

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 3.2.1 | Visualize data | Planned | Dashboard (BI option undecided, G-07) | ⬜ |
| 3.2.2 | Verify and clean data | Planned | Athena validation queries | ⬜ |
| 3.2.3 | Query and create views with SQL in Redshift and Athena | Planned | Views in both engines | ⬜ |
| 3.2.4 | Explore data with Athena Spark notebooks | Not planned | — | ⬜ |
| 3.2.5 | Weigh provisioned vs serverless | Planned | [ADR-0001](adr/0001-ingest-and-warehouse-stack.md), `cost-model.md` | 🟡 |
| 3.2.6 | Aggregation, rolling averages, grouping, pivoting | Planned | Gold-layer metrics SQL | ⬜ |

### Task 3.3: Maintain and monitor pipelines

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 3.3.1 | Pull logs for audit | Stretch | — | ⬜ |
| 3.3.2 | Logging and monitoring for traceability | Planned | CloudWatch metrics and logs | ⬜ |
| 3.3.3 | Alert from monitoring | Planned | CloudWatch alarm → SNS | ⬜ |
| 3.3.4 | Troubleshoot performance | Stretch | — | ⬜ |
| 3.3.5 | Track API calls with CloudTrail | Stretch | — | ⬜ |
| 3.3.6 | Troubleshoot and maintain Glue/EMR pipelines | Planned | Glue job runbook | ⬜ |
| 3.3.7 | Log application data to CloudWatch Logs | Planned | Structured Lambda/Glue logs | ⬜ |
| 3.3.8 | Analyze logs with AWS services | Stretch | CloudWatch Logs Insights queries | ⬜ |

### Task 3.4: Data quality

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 3.4.1 | Check quality during processing | Planned | Null/range checks in the Glue job | ⬜ |
| 3.4.2 | Define quality rules | Stretch | Rule set (DataBrew or Glue Data Quality) | ⬜ |
| 3.4.3 | Investigate consistency | Stretch | Bronze vs Silver row reconciliation | ⬜ |
| 3.4.4 | Sampling techniques | Stretch | — | ⬜ |
| 3.4.5 | Handle data skew | Stretch | — | ⬜ |

---

## Domain 4: Data Security and Governance (18%)

IAM changes are run by the account owner, never by an agent. IaC in this
repo defines roles and policies; the owner applies them.

### Task 4.1: Authentication

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 4.1.1 | Update VPC security groups | Stretch | Redshift Serverless workgroup security group | ⬜ |
| 4.1.2 | Manage IAM groups, roles and endpoints | Planned | IaC-defined roles | ⬜ |
| 4.1.3 | Create and rotate credentials in Secrets Manager | Stretch | Secrets Manager cost not yet verified | ⬜ |
| 4.1.4 | Roles for service access | Planned | Lambda, Glue, Firehose, Redshift roles | ⬜ |
| 4.1.5 | Policies on access points and endpoints | Stretch | — | ⬜ |
| 4.1.6 | Managed vs unmanaged services | Planned | ADR discussion | ⬜ |
| 4.1.7 | SageMaker Unified Studio domains/projects | Not planned | — | ⬜ |

### Task 4.2: Authorization

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 4.2.1 | Write custom IAM policies | Planned | Scoped IaC policies | ⬜ |
| 4.2.2 | Store app and database credentials | Stretch | Parameter Store or Secrets Manager | ⬜ |
| 4.2.3 | Database users, groups and roles | Planned | Redshift read-only analyst role | ⬜ |
| 4.2.4 | Permissions via Lake Formation | Stretch | — | ⬜ |
| 4.2.5 | Role-, tag- and attribute-based access | Stretch | — | ⬜ |
| 4.2.6 | Least-privilege policies | Planned | Per-service scoped policies | ⬜ |

### Task 4.3: Encryption and masking

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 4.3.1 | Mask and anonymise data | Planned | Hashed user IDs | ⬜ |
| 4.3.2 | Encrypt with KMS keys | Stretch | KMS vs SSE-S3 decision (G-13) | ⬜ |
| 4.3.3 | Cross-account encryption | Not planned | Single account | ⬜ |
| 4.3.4 | Encryption in transit | Planned | TLS-only bucket policy | ⬜ |

### Task 4.4: Logs for audit

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 4.4.1 | Track API calls with CloudTrail | Stretch | — | ⬜ |
| 4.4.2 | Store app logs in CloudWatch Logs | Planned | Same as 3.3.7 | ⬜ |
| 4.4.3 | Centralised queries with CloudTrail Lake | Not planned | — | ⬜ |
| 4.4.4 | Analyze logs with AWS services | Stretch | Same as 3.3.8 | ⬜ |
| 4.4.5 | Large-volume logging integrations | Not planned | — | ⬜ |

### Task 4.5: Privacy and governance

| Skill | Paraphrase | Plan | Intended evidence | Status |
|---|---|---|---|---|
| 4.5.1 | Grant data-sharing permissions | Not planned | Needs a second Redshift namespace | ⬜ |
| 4.5.2 | Identify PII | Not planned | Synthetic data only | ⬜ |
| 4.5.3 | Block replication to disallowed Regions | Not planned | Needs AWS Organizations (owner-only area) | ⬜ |
| 4.5.4 | View account configuration changes | Not planned | — | ⬜ |
| 4.5.5 | Data sovereignty | Stretch | Region decision record (G-14) | ⬜ |
| 4.5.6 | Access via SageMaker Catalog projects | Not planned | — | ⬜ |
| 4.5.7 | Governance frameworks and sharing patterns | Stretch | Concept note | ⬜ |
