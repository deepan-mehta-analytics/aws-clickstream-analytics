# Cost Model

Estimated AWS cost for this project, built only from list prices on AWS
pricing pages. **Every figure is an estimate until a real run's bill replaces
it.** No number here is a measured cost.

- **Account:** legacy AWS Free Tier (pre-2025 account, confirmed by AWS
  support 2026-09-24). No new-plan credits. **No free credits of any kind
  (owner-confirmed 2026-10-05, GAPS G-11), so every figure below is out of
  pocket at list price.** The 12-month offers have likely
  lapsed. See `GAPS.md` G-01.
- **Region priced here:** US East (N. Virginia), `us-east-1`, as a baseline.
  The chosen region is **Mumbai, `ap-south-1`** (ADR-0001, Accepted
  2026-09-25). Mumbai prices are in the annex linked below.
- **Currency:** USD. For Mumbai prices in INR including 18% GST, and the
  progressive tier ladder, see
  [`adr/0001-hybrid-cost-tiers.md`](adr/0001-hybrid-cost-tiers.md). That
  annex also found Glue 6.0+ at $0.308 per DPU-hour, below the $0.44 used
  below.

---

## 1. Verified inputs

All figures fetched 2026-09-25 from the page listed. Prices are for us-east-1.

| Service | Price component | List price | Free allowance on this account | Source |
|---|---|---|---|---|
| Kinesis Data Streams | Provisioned shard-hour | $0.015 | None ("NOT currently available in AWS Free Tier") | aws.amazon.com/kinesis/data-streams/pricing/ |
| Kinesis Data Streams | PUT payload units (25 KB each) | $0.014 per million | None | same |
| Kinesis Data Streams | On-demand standard: stream-hour / GB in / GB retrieved | $0.040 / $0.08 / $0.040 | None | same |
| Amazon Data Firehose | Ingest, first 500 TB/month (billed in 5 KB increments per record) | $0.029/GB | None stated | aws.amazon.com/firehose/pricing/ |
| Amazon Data Firehose | JSON → Parquet format conversion | $0.018 per ingested GB | None stated | same |
| Amazon Data Firehose | Dynamic partitioning: per GB / per 1,000 S3 objects | $0.020 / $0.005 | None stated | same |
| Redshift Serverless | Compute (4 RPU minimum base) | $0.375 per RPU-hour, per second, 60 s minimum | $300 trial credit within 90 days, if the account has never used Serverless (eligibility unverified) | aws.amazon.com/redshift/pricing/ + /redshift/free-trial/ |
| Redshift Serverless | Managed storage | $0.024/GB-month | Not stated whether the trial covers it | same |
| S3 Standard | Storage (first 50 TB) | $0.023/GB-month | 12-month offer, likely lapsed | aws.amazon.com/s3/pricing/ |
| S3 Standard | PUT/COPY/POST/LIST · GET | $0.005 · $0.0004 per 1,000 | 12-month offer, likely lapsed | same |
| Lambda (x86) | Requests · duration | $0.20 per 1M · $0.0000166667 per GB-s | **Always Free:** 1M requests + 400,000 GB-s/month | aws.amazon.com/lambda/pricing/ |
| Glue | ETL job (Spark / Python shell) · Flex | $0.44 · $0.29 per DPU-hour, per second, 1 min minimum | None for ETL | aws.amazon.com/glue/pricing/ |
| Glue | Crawler | $0.44 per DPU-hour, 1 min minimum | None | same |
| Glue | Data Catalog | $1.00 per 100k objects over 1M | First 1M objects + 1M requests/month free | same |
| Athena | SQL query | $5 per TB scanned, 10 MB minimum per query, rounded up to the MB | None stated | aws.amazon.com/athena/pricing/ |
| Amazon Quick / QuickSight | BI Author · Reader | $24 · $3 per user/month | None; a Quick 30-day trial waives fees for up to 25 users (whether it covers a BI Author is unverified) | aws.amazon.com/quicksight/pricing/ + /quick/pricing/ |
| Amazon Quick | Free · Plus plans | $0 · $20–25 per user/month | Neither can author dashboards | aws.amazon.com/quick/pricing/ |

**Encryption choice (ADR-0004, 2026-09-26):** every bucket uses SSE-S3,
which has no key charge. A customer managed KMS key was rejected: $1 per
key version per month in Mumbai, plus $0.03 per 10,000 requests beyond the
free tier (Price List API `awskms` `ap-south-1`, published 2026-09-11), and
deletion needs a 7–30 day waiting period. The IaC artifacts bucket
(foundation stack) holds only small packaged-code objects with a short
expiry; its cost is expected to be negligible (not yet measured).

**Not yet verified:** Glue minimum DPUs per Spark job and the Python-shell
DPU size; provisioned Redshift dc2/ra3 hourly prices (the table did not
render); whether Firehose format conversion uses the same 5 KB rounding
as ingest; the costs of the T2 add-ons promoted on 2026-09-26 (Glue Data
Quality, Lake Formation, CloudTrail, CloudWatch Logs Insights, SSM
Parameter Store). Kinesis per-shard limits were verified on 2026-09-26
(GAPS G-02).

---

## 2. Workload assumptions

Illustrative demo volumes, not measured. The chosen dataset (ADR-0003) has
**165,474 events**, about 1.65× the 100,000 below. The per-GB and per-request
lines scale by that factor, and totals stay at single rupees per run:

- **Events:** 100,000 synthetic clickstream events of about 1 KB each per
  window or day (~0.1 GB raw).
- **Streaming demo window:** 2 hours of ingest, 1 hour of active Redshift
  Serverless query time at the 4-RPU base.
- **Batch run:** one Glue Spark job of 10 minutes at 2 DPU (the DPU minimum
  is unverified), plus 100 Athena queries at the 10 MB minimum.

---

## 3. Scenario estimates

### A. Streaming path, one 2-hour demo window

Kinesis Data Streams (1 provisioned shard) → Firehose (→ Parquet) → S3 →
Redshift Serverless.

| Line item | Calculation | Estimate |
|---|---|---|
| Kinesis shard-hours | 2 h × $0.015 | $0.030 |
| Kinesis PUT units | 0.1M × $0.014 | $0.001 |
| Firehose ingest | 100k records × 5 KB billing floor ≈ 0.5 GB × $0.029 | $0.015 |
| Firehose Parquet conversion | ≈ 0.5 GB × $0.018 (assumes the same rounding) | $0.009 |
| Redshift Serverless compute | 4 RPU × 1 h × $0.375 | $1.500 |
| S3 storage + requests | < 0.1 GB, a few hundred PUTs | < $0.01 |
| **Total at list price** | | **≈ $1.56** |
| **Out of pocket while the Serverless trial credit lasts** | Redshift compute covered | **≈ $0.06** |

The trial credit of $300 covers about 200 active hours at the 4-RPU base,
but only within 90 days of activation. Batching records up to 5 KB before
they reach Firehose would cut the ingest line roughly fivefold.

### B. Batch path, one daily run

Lambda generator → S3 → Glue job → Athena.

| Line item | Calculation | Estimate |
|---|---|---|
| Lambda | well under 1M requests / 400k GB-s | $0.00 (Always Free) |
| S3 PUTs | ~120 objects × $0.005 per 1,000 | < $0.001 |
| S3 storage | 0.1 GB × $0.023/GB-month | < $0.01/month |
| Glue Spark job | 2 DPU × 10 min × $0.44/DPU-hour | $0.147 |
| Athena | 100 queries × 10 MB minimum = 1 GB × $5/TB | $0.005 |
| **Total per run** | | **≈ $0.15** |

Running B every day for 30 days comes to about $4.50/month. Glue Flex
($0.29) would cut the Glue line by about a third.

### B2. Tier T1a proof run, Mumbai (estimate)

| Line item | Calculation | Estimate |
|---|---|---|
| T1a proof run (Lambda, S3, Glue 6.0 job on 2 workers, Athena) | From the tier ladder in the [ADR-0001 annex](adr/0001-hybrid-cost-tiers.md), Mumbai, INR incl. GST | about ₹12 per run (estimate, not measured) |

The annex prices T1 at 2 DPU for 10 minutes on Glue 6.0+; the Flex execution
class and the 15-minute timeout in [ADR-0005](adr/0005-t1-batch-lake-design.md)
are not separately priced here. The measured cost replaces this line after
the first window.

### C. BI layer (either path)

| Option | Estimate |
|---|---|
| QuickSight BI Author, 1 user | $24/month (no free Author tier found) |
| Amazon Quick 30-day trial | $0 for 30 days if it covers a BI Author (unverified) |
| Amazon Quick Free / Plus | Cannot author dashboards |
| Local open-source dashboard over Athena | $0 AWS BI cost (Athena scans still billed) |

---

## 4. Leak risks (what costs money while idle)

| Resource left running | Idle cost | Guardrail |
|---|---|---|
| Kinesis stream, 1 provisioned shard | ≈ $0.36/day (≈ $10.80 per 30 days) | Delete the stream at the end of every window |
| Kinesis stream, on-demand | ≈ $0.96/day (≈ $28.80 per 30 days) | Prefer provisioned 1-shard for demos |
| Redshift Serverless workgroup | $0 compute when idle; storage $0.024/GB-month | Set an RPU-hour usage limit. Trial burn is **not visible in the Billing console**, so watch `SYS_SERVERLESS_USAGE` |
| Quick/QuickSight Author seat | $24/month | Unsubscribe after the demo month |
| Firehose, Glue, Athena, Lambda | No idle charge (usage-billed) | None needed |

An AWS Budgets alert (about $1, set by the account owner) must exist before
any resource is created. It does not cover Redshift trial usage.

---

## 5. Teardown log

One row per working window with cost-bearing resources. Empty until the
first cloud run.

| Date | Resources created | Torn down / paused | Verified by | Measured cost |
|---|---|---|---|---|
| 2026-09-25 | None: tier T0 local twin ran on a laptop | Nothing to tear down | — | ₹0 AWS cost |
| _pending_ | _T1a window (Task 13): fill in when run_ | | | |
