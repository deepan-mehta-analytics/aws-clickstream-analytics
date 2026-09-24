# Gaps Register

Two views of "what we don't know or don't cover yet". Both feed the README's
Known Limitations section, so nothing here gets quietly dropped.

Status legend: `⏳ Open` · `🔎 Researching` · `✅ Resolved` · `⚠️ Accepted limitation`

---

## 1. Brief-versus-reality register

Claims in `docs/00-initial-brief.md` checked against current AWS docs,
pricing pages, or a real run. Seeded 2026-09-21 from open questions raised
when the brief was captured (none verified yet).

| ID | Brief claim / assumption | What to verify | How | Decision | Status |
|---|---|---|---|---|---|
| G-01 | Kinesis Data Streams, Firehose, Redshift, QuickSight and Glue ETL are all "Always Free" at the stated quotas | Current Free Tier structure for this account (AWS restructured it for new accounts in 2025); which items are always-free, time-limited, or credit-based | AWS Free Tier pages + Billing console | **Brief claim not supported (docs half, 2026-09-24).** New customers choose a Free plan or a Paid plan. Free plan: $100 credits at sign-up plus up to $100 more by exploring services (up to $200). The account "closes on its own 6 months after you open it or when your credits run out, whichever comes first"; data is kept 90 days after expiry, then erased unless upgraded. No charges on the Free plan unless you convert to Paid. The Free plan is "limited from accessing a subset of AWS services" that would use up the credits at once; the exact list was not on the pages read. "30+ services are always free within monthly usage limits". The overview page names EC2, S3, Aurora, RDS, DynamoDB and SageMaker AI, and does **not** name Kinesis Data Streams, Firehose, Redshift, QuickSight, Glue, Lambda or Athena. Existing customers keep the legacy Free Tier unchanged and get no credits. The FAQ says credits expire 12 months after account creation, while the overview says the free plan lasts 6 months. Sources: aws.amazon.com/free and /free/free-tier-faqs, fetched 2026-09-24. **Still open:** (a) which plan or legacy tier this account is on (Billing console, user-only); (b) whether Kinesis, Firehose, Redshift Serverless, QuickSight and Glue are usable on the Free plan (the restricted-services list); (c) per-service Always Free quotas | 🔎 Researching |
| G-02 | 2 Kinesis shards run inside the free tier | Shard-hour and PUT-payload billing; on-demand vs provisioned mode; whether 1 shard suffices | AWS pricing page | — | ⏳ Open |
| G-03 | Firehose converts JSON → Parquet via "built-in data transformation", partitioned by date/hour | Record format conversion requirements (Glue Catalog schema), dynamic partitioning, buffer limits, UTC vs IST prefixes, current product name (Amazon Data Firehose) | Firehose docs + a real test | — | ⏳ Open |
| G-04 | Glue ETL has a 1M DPU-seconds/month free tier | Real Glue pricing and free-tier terms (Data Catalog vs ETL jobs); job runtime and DPU choice | Glue pricing page | — | ⏳ Open |
| G-05 | Redshift dc2.large single node is free at 750 h/month | Current trial terms and duration; dc2 vs RA3 vs Serverless; cost of a cluster left running; pause/resume behaviour | Redshift pricing page | — | ⏳ Open |
| G-06 | Concurrency Scaling on the single-node cluster ("auto-scales read replicas") | Whether Concurrency Scaling is supported on single-node clusters; correct description of the feature | Redshift docs | — | ⏳ Open |
| G-07 | QuickSight Standard, 1 free user, 1 GB SPICE, auto-refresh every 5 min | Current edition and free-trial terms, product naming, SPICE refresh limits vs direct query | QuickSight docs + pricing | — | ⏳ Open |
| G-08 | Dashboard 1 shows "last 1 hour" from a pipeline with a daily 1 AM batch | Latency mismatch: need a near-real-time serving path (e.g. query Bronze directly, streaming ingestion) or reframe the dashboard | Design + research | — | ⏳ Open |
| G-09 | `fact_clicks` loads from `silver/sessions/`; `users` / `pages` tables appear from the same job | Grain mismatch (session vs click); how `users`, `pages`, `dim_*` are derived; no Gold layer defined | Design | — | ⏳ Open |
| G-10 | Cost ₹620–1,200/month for a running Redshift dc2.large plus S3 overage | Recompute from verified prices and the USD/INR rate; plan pause/teardown between sessions | Pricing pages | — | ⏳ Open |
| G-11 | AWS Activate Founders credits ($1,000 + $350 support) are obtainable for this project | Whether a personal portfolio project meets the startup eligibility criteria; program terms. This is the user's decision and application, not an automated step | AWS Activate terms | — | ⏳ Open |
| G-12 | S3 Intelligent-Tiering saves 40% on Bronze | Small Parquet objects and monitoring fees; whether tiering helps at this data volume | S3 pricing page | — | ⏳ Open |
| G-13 | Security and IaC are unspecified | Least-privilege IAM, KMS vs SSE-S3, encryption in transit, IaC choice (Terraform vs CDK), placeholder discipline for account IDs | Design | — | ⏳ Open |
| G-14 | Region and timezone are unspecified | Region choice (service availability, data residency, latency); UTC-based Firehose prefixes vs the "1 AM IST" Glue schedule | Design | — | ⏳ Open |

Add a row whenever research contradicts the brief. Resolved rows stay in the
table with their decision, so the reasoning remains auditable.

---

## 2. Exam-coverage gap map

AWS Certified Data Engineer – Associate (DEA-C01) syllabus versus what this
project actually demonstrates.

**Not populated yet.** In the working session, fetch the current official
exam guide first (do not fill this from memory), record its version, domain
weights and fetch date here, then add one row per official task statement:

| § | Task statement | Module in this repo | Status |
|---|---|---|---|
| — | — | — | ⏳ Open |

Rows with no module are the gaps. Decide for each: build it, or record it
under Known Limitations. Likely candidates to check: governance and data
cataloguing, orchestration, data quality, IaC, and security controls.

---

## 3. Accepted limitations

Items promoted from sections 1–2 that we decided to live with. Each becomes
a bullet in the README's Known Limitations.

| ID | Limitation | Why accepted |
|---|---|---|
| — | — | — |
