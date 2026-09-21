# Initial Brief — AWS Real-Time Clickstream Analytics (DRAFT, NOT BINDING)

> Captured 2026-09-21 from the user's original prompt, verbatim. This is a
> starting draft. All tech-stack, architecture, and engineering decisions are
> open to re-research and change in the working sessions.

---

Build a production-grade real-time clickstream analytics pipeline on AWS that demonstrates AWS Certified Data Engineer – Associate (DEA-C01) skills. The pipeline must ingest streaming click events, perform serverless ETL, load into a data warehouse, and power BI dashboards.

## Tech Stack Requirements

### Ingestion Layer
- Use **Amazon Kinesis Data Streams** (Always Free tier: 500,000 PUT records/month, 500,000 GET records/month).
- Create stream: `clickstream_raw` with 2 shards (1 MB/s write, 2 MB/s read per shard).
- Simulate click events: user_id, event_type, page_url, timestamp, device_type, geo_location, session_id.
- Target throughput: 1M clicks/day (≈30M/month, exceeds free tier — use Firehose to reduce costs).

### Streaming ETL
- Use **Amazon Kinesis Data Firehose** (Always Free tier: 5 GB/day ingestion, 150 GB/month).
- Configure Firehose to:
  - Transform JSON → Parquet (using built-in data transformation).
  - Write to S3 bucket: `s3://clickstream-analytics/bronze/` (partitioned by date/hour).
  - Enable server-side encryption (SSE-S3).
- Set buffer size: 64 MB, buffer interval: 300 seconds.

### Batch ETL
- Use **AWS Glue** (Free tier: 1M DPU-seconds/month ≈ 277 DPU-hours).
- Create Glue Data Catalog database: `clickstream_analytics`.
- Build Glue Spark job: `sessionization_job` (daily, runs at 1 AM IST):
  - Read Parquet from S3 Bronze.
  - Group clicks into sessions (30-min timeout).
  - Compute: session_duration, pages_per_session, bounce_rate, conversion_flag.
  - Write to S3 Silver: `s3://clickstream-analytics/silver/sessions/` (partitioned by date).
- Register Silver tables in Glue Catalog: `sessions`, `users`, `pages`.

### Data Warehouse
- Use **Amazon Redshift** (Free tier: 750 hours/month dc2.large single-node cluster, 160 GB SSD).
- Create Redshift cluster: `clickstream-warehouse` (dc2.large, 2 vCPU, 15 GB RAM, 160 GB SSD).
- Use COPY command to load Silver data from S3:
  ```sql
  COPY fact_clicks FROM 's3://clickstream-analytics/silver/sessions/'
  IAM_ROLE 'arn:aws:iam::ACCOUNT_ID:role/RedshiftS3Access'
  FORMAT AS PARQUET;
  ```
- Build dimension tables: `dim_users`, `dim_pages`, `dim_devices`.
- Create materialized views:
  - `mv_daily_active_users` (DAU by date).
  - `mv_funnel_conversion` (landing → product → checkout → purchase).
  - `mv_top_pages_by_bounce` (top 10 pages by bounce rate).

### BI Dashboards
- Use **Amazon QuickSight** (Standard edition: 1 user free, 1 GB SPICE).
- Create analysis: `Clickstream Analytics Dashboard`.
- Build 3 dashboards:
  1. **Real-Time Traffic:** DAU, sessions, avg session duration (last 1 hour).
  2. **Funnel Analysis:** Landing → Product → Checkout → Purchase conversion.
  3. **Device/Geo Breakdown:** Mobile vs. Desktop, top 10 countries by sessions.
- Enable auto-refresh (every 5 mins) for real-time visibility.
- Use SPICE for in-memory acceleration (1 GB free limit).

### Cost Optimization & Monitoring
- Use **S3 Intelligent-Tiering** for Bronze data (saves 40% storage cost).
- Enable **Redshift Concurrency Scaling** for peak BI loads (auto-scales read replicas).
- Set up **Amazon CloudWatch** (Basic monitoring free: 10 custom metrics, 1M API requests):
  - Alarm: Kinesis throughput >80% of shard limit.
  - Alarm: Glue job failures >2/day.
  - Alarm: Redshift query latency >5 seconds.
- Use **AWS Budgets** (free) to set monthly cost alert at ₹500.

## Vendor & Pricing Strategy

### AWS Free Tier (Always Free)
- **Kinesis Data Streams:** 500,000 PUT/GET records/month (free).
- **Kinesis Data Firehose:** 5 GB/day ingestion (150 GB/month free).
- **S3 Storage:** 5 GB/month storage, 20,000 GET requests, 2,000 PUT requests (free).
- **AWS Glue:** 1M DPU-seconds/month (≈277 DPU-hours free).
- **Redshift:** 750 hours/month dc2.large cluster (free).
- **QuickSight:** 1 user Standard edition (free, 1 GB SPICE).
- **CloudWatch:** 10 custom metrics, 1M API requests (free).

### AWS Activate Credits
- Apply for **AWS Activate Founders** ($1,000 credits + $350 Developer Support credits, valid 2 years).
- Eligibility: Self-funded, bootstrapped, or pre-seed without VC backing.
- Application process:
  1. Go to aws.amazon.com/activate → "Apply Now".
  2. Sign in with AWS Builder ID (use professional email, not Gmail).
  3. Fill company details: name, website, product description, funding stage.
  4. Link AWS account ID for credit application.
  5. Submit → approval in 5–10 business days.
- Credits cover: EC2, S3, RDS, Lambda, Kinesis, Glue, Redshift, QuickSight, Bedrock, SageMaker.
- For 1M clicks/day (≈30M/month), estimated monthly cost: **₹620–1,200** (Redshift + S3 overage).
- With $1,000 credits (≈₹83,000), covers **2–3 months** of full usage.

### Total Monthly Cost
- **Without credits:** ₹620–1,200/month (Redshift dc2.large + S3 overage).
- **With AWS Activate:** ₹0 for 2–3 months (covered by $1,000 credits).
- **After credits expire:** ₹620–1,200/month (optimize with S3 Intelligent-Tiering, Redshift pause/resume).

## Implementation Notes
- Use Kinesis Data Firehose for JSON → Parquet transformation (reduces Kinesis costs).
- Run Glue jobs daily (10 mins/day × 30 days = 300 mins = 5 DPU-hours, well within 1M DPU-seconds free tier).
- Use Redshift COPY with `FORMAT AS PARQUET` for 10x faster loading vs. CSV.
- For QuickSight, use SPICE for in-memory acceleration (1 GB free limit).
- Monitor costs with AWS Budgets → set alert at ₹500/month.

---

## Open questions to verify in the working session (added by Claude, unverified)

These are things I'd check against current AWS docs and pricing pages before committing to the brief, not settled facts. Full tracking lives in `GAPS.md`.

- **Free Tier claims** — several "Always Free" items (Kinesis Data Streams, Firehose, Redshift, QuickSight, Glue ETL) may not be always-free or may have changed; AWS restructured the Free Tier for new accounts in 2025. Confirm the current structure and what applies to this account.
- **Cost estimate vs. a running cluster** — a dc2.large left running continuously looks inconsistent with ₹620–1,200/month; recompute, and plan pause/teardown.
- **Latency mismatch** — the "last 1 hour" real-time dashboard cannot be served by a daily 1 AM batch → Silver → COPY path.
- **Data model mismatch** — `fact_clicks` is loaded from `silver/sessions/` (session grain, not click grain); `users` / `pages` tables are not derived by the described job; there is no Gold layer.
- **Firehose Parquet conversion** — record format conversion normally relies on a Glue Data Catalog schema, and Firehose has been renamed Amazon Data Firehose; check partitioning, UTC-vs-IST prefixes, and buffer limits.
- **Redshift Concurrency Scaling on a single node** — confirm it is supported at all; also decide dc2 (older generation) vs. RA3 vs. Redshift Serverless.
- **QuickSight** — confirm the current edition, free-trial/pricing terms, product naming, and SPICE refresh limits against the "auto-refresh every 5 minutes" requirement.
- **AWS Activate eligibility** — a personal portfolio project may not meet the startup criteria; verify before applying, and never misstate company details. That is the user's decision, not an automated step.
- **Exam alignment** — confirm the current DEA-C01 exam guide version and domain weights, then check which brief items map to it and which exam topics (e.g. governance, orchestration, IaC, data quality) the brief leaves uncovered.
- **Region and timezone** — pick the region deliberately (service availability, data residency) and reconcile UTC-based Firehose prefixes with the "1 AM IST" schedule.
