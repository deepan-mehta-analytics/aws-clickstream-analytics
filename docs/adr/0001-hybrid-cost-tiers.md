# ADR-0001 Annex: Hybrid Cost Tiers, SWOT and Move Analysis

Supporting analysis for [ADR-0001](0001-ingest-and-warehouse-stack.md)
(Accepted 2026-09-25 with Mumbai and the recommended line in §6). It
answers one question:

> How far up the hybrid design can this project go, in small priced steps,
> and still publish a release that carries **no sustained monthly AWS
> cost**?

**Bottom line (estimates, not measured):** the full hybrid release (batch
baseline, orchestration, one streaming window, one Redshift window, and a
dashboard) costs about **₹110 one-time** in Mumbai if the Redshift
Serverless trial applies and the dashboard runs locally. It costs about
**₹3,400** if every item is paid at list price. It leaves **₹0/month** after
teardown in both cases. The largest single cost is a paid BI Author seat;
the largest risk is a resource left running.

---

## 1. Pricing basis

| Input | Value | Source (fetched 2026-09-25) |
|---|---|---|
| Region priced | Asia Pacific (Mumbai), `ap-south-1` | AWS Price List API offer files (publication dates 2026-09-11 to 2026-09-24) |
| Exchange rate | ₹95.96 per USD (2026-09-24) | ECB reference rate via api.frankfurter.dev |
| Tax | IGST 18% (or CGST 9% + SGST 9% in Delhi), billed by Amazon Web Services India Private Limited | aws.amazon.com/tax-help/india/ |
| Conversion factor used | **₹113.23 per list-price USD** (95.96 × 1.18) | derived |
| Workload | 100,000 synthetic events of ~1 KB per run (~0.1 GB) | assumption, same as `cost-model.md` |

AWS India invoices in INR at its own exchange rate, which may differ from
the ECB rate (unverified). All rupee figures here are rounded estimates.

### Mumbai unit prices used

| Service | Price | vs us-east-1 |
|---|---|---|
| Kinesis Data Streams, provisioned shard-hour | $0.0175 | +17% |
| Kinesis Data Streams, per 1M PUT payload units | $0.0185 | +32% |
| Kinesis Data Streams, on-demand stream-hour | $0.0517 | +29% |
| Firehose ingest, first tier (5 KB billing floor per record) | $0.034/GB | +17% |
| Firehose format conversion | $0.021/GB | +17% |
| Redshift Serverless compute (4 RPU minimum base) | $0.4275/RPU-hour | +14% |
| Redshift managed storage | $0.0261/GB-month | +9% |
| Glue ETL, Glue 6.0+ ("Gen2") · Flex Gen2 · Glue 4/5 | $0.308 · $0.203 · $0.44 per DPU-hour | same |
| Athena | $5/TB scanned, 10 MB minimum per query | same |
| S3 Standard storage · PUT | $0.025/GB-month · $0.005 per 1,000 | +9% · same |
| Lambda | 1M requests + 400,000 GB-s/month free (global) | same |
| Step Functions | first 4,000 state transitions free, then $0.0000285 each | — |
| CloudWatch standard alarm · log ingest · log storage | $0.10/alarm-month · $0.67/GB · $0.03/GB-month | — |
| SNS email | first 1,000 notifications/month free | — |
| KMS customer-managed key · Secrets Manager secret | $1/key-month · $0.40/secret-month | — |
| QuickSight Author (BI) | $24/user-month (pricing page; Mumbai SKU not found in the Price List) | — |

**New finding:** Glue 6.0+ jobs are priced at $0.308 per DPU-hour, 30% below
the $0.44 used in `cost-model.md`. The tier estimates below use Glue 6.0+.

---

## 2. The tier ladder

Each tier adds to the one below. "Per proof run" is one clean run.
"Budget" allows for development re-runs (×5 batch, ×3 streaming, ×3
Redshift hours). Every tier ends torn down, so sustained cost is ₹0 unless
noted.

| Tier | Adds | Per proof run | Budget with re-runs | Cumulative, best case¹ | Cumulative, all paid² | Left running after teardown | Planned skills first shown (cumulative of 58) |
|---|---|---|---|---|---|---|---|
| **T0 Local twin** | Generator, transforms and SQL run on the laptop (local files, local Spark/DuckDB); tests and CI | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | 8 (8) |
| **T1 Serverless batch** | Lambda generator → S3 Bronze → Glue 6.0+ job (2 DPU³ × 10 min) → Glue Catalog → Athena | ₹12 | ₹61 | ₹61 | ₹61 | ₹0 (delete bucket) | 29 (37) |
| **T2 Orchestrated and monitored** | Step Functions + EventBridge schedule, data-quality checks, CloudWatch logs and alarms, SNS email | ₹23 upper bound⁴ | ₹23 | ₹84 | ₹84 | ₹0 (delete alarms, log groups) | 15 (52) |
| **T3 Streaming window** | Kinesis (1 provisioned shard) → Firehose → Parquet in S3, for 2 hours | ₹7 | ₹22 | ₹106 | ₹106 | ₹0 (delete stream) | 1 + 3 stretch (53) |
| **T4 Warehouse window** | Redshift Serverless at 4 RPU: `COPY`/`UNLOAD`, star schema, Spectrum or a materialized view | ₹194 per active hour | ₹581 | ₹106 (trial) | ₹687 | ₹0 (delete workgroup and namespace, no snapshots) | 4 + 2 stretch (57) |
| **T5 Dashboard** | Either a local open-source dashboard over Athena, or QuickSight | local ≈ ₹0; QuickSight ₹2,718/Author-month | same | ≈ ₹110 (local) | ≈ ₹3,405 (QuickSight) | ₹0 (cancel seat) | 1 (58) |
| **T6 Hardening (optional)** | Customer-managed KMS key, Secrets Manager, CloudTrail analysis | ₹113 per key-month; ₹45 per secret-month | depends on hours held | +₹0 if skipped | + ₹160 for one month | **Recurring unless deleted** | Stretch only |

1. Best case: the Redshift Serverless $300 / 90-day trial applies, and the
   dashboard runs locally.
2. All paid: no trials; one QuickSight Author month.
3. The Glue minimum worker count was not found in the docs read; 2 DPU is
   an assumption.
4. Two standard alarms for a full month. Step Functions stays inside the
   4,000 free transitions. EventBridge Scheduler pricing was not in the
   Price List file read, and is expected to be negligible (unverified).

Skill counts are a planning split of the 58 "Planned" rows in
[`exam-guide-map.md`](../exam-guide-map.md), grouped by the first tier
where each can be exercised. They are not yet shown.

Update 2026-09-26: [ADR-0004](0004-iac-sam-cloudformation.md) moved 1.4.6
(SAM) and 1.4.8 (CloudFormation) from stretch to planned, so there are now
60 planned rows. Both first land in T1, which takes T1 to 31 (39) and each
later cumulative figure up by 2 (T5: 60). The table above keeps the
figures as they were accepted.

---

## 3. SWOT per tier

| Tier | Strengths | Weaknesses | Opportunities | Threats |
|---|---|---|---|---|
| **T0 Local twin** | Free; fast iteration; every later tier reuses the code; CI can run it on each push | Shows no AWS service; "works on my laptop" is weak evidence for a cloud role | Tests written here become the regression suite for every cloud run | Local behaviour drifts from AWS (IAM, S3 consistency, Glue runtime versions) |
| **T1 Serverless batch** | Real AWS evidence for about ₹12 a run; nothing bills while idle; covers the most skills per rupee | No streaming, no warehouse, so it looks like a generic data-lake demo | Glue 6.0+ and Flex cut compute further; Athena on Parquet shows scan-cost thinking | First IAM roles are needed, and they must be applied by the account owner; a leftover bucket accrues small charges |
| **T2 Orchestrated** | Shows production habits: scheduling, retries, alerts, data quality | Adds moving parts to debug; alarms bill monthly while they exist | Failure alerts and runbooks are strong interview material | Forgotten alarms and log groups are the classic slow leak |
| **T3 Streaming window** | Shows the real-time path the clickstream story needs, for about ₹7 a window | Only 1 planned skill added; a demo window is not a live pipeline | Producer batching (≥5 KB records) cuts Firehose cost about fivefold, and shows cost engineering | A shard left running costs about ₹48/day (on-demand about ₹140/day); easy to forget |
| **T4 Warehouse window** | Unlocks the Redshift skills (load/unload, schema, Spectrum) that the exam guide names directly | The most expensive compute: ₹194 per active hour without the trial | The $300 trial covers about 175 active hours at 4 RPU in Mumbai; that is enough for the whole project | Trial burn is invisible to AWS Budgets; the 90-day clock starts at activation; eligibility of this India-billed account is unverified |
| **T5 Dashboard** | Completes the story: event → insight | QuickSight costs more than every other tier combined | A local dashboard over Athena is free and fully reproducible; the Quick 30-day trial may cover QuickSight (unverified) | A seat left subscribed renews at ₹2,718 a month |
| **T6 Hardening** | Adds to Domain 4 (security), the thinnest area of the exam map | Recurring charges by design (keys, secrets) | SSE-S3 and IAM authentication show the same principles at ₹0 | A KMS key or secret left in place breaks the "no sustained cost" goal |

---

## 4. Move analysis ("chess board")

Each tier is a move. The best line is the one that keeps every later option
open at the lowest cost, and never leaves a piece that keeps costing money.

### Opening (T0 → T1): develop pieces cheaply

- Build and test all transforms locally first. Every bug found at T0 costs
  ₹0 instead of a Glue run.
- Apply IAM for T1 as **one reviewed IaC stack**, applied by the account
  owner (project guardrail). Batching IAM per tier avoids stop-start
  sessions.
- Create the ₹-denominated AWS Budgets alert before the first resource.

### Middlegame (T2 → T4): control the clock

- **Do not activate the Redshift trial early.** Its 90 days start at
  activation. Finish the T4 SQL (star schema, `COPY`, `UNLOAD`) against the
  local twin first, then activate and run the Redshift window in one or two
  sittings.
- Run T3 and T4 in the **same working window**: the stream feeds S3, and
  Redshift loads from it. That means one setup and one teardown.
- Before activation, set a Redshift usage limit (RPU-hours per day) and
  cap the maximum capacity at the 4-RPU base. Budgets cannot see trial
  usage.

### Threats and counters

| Threat | Cost if missed | Counter |
|---|---|---|
| Kinesis shard left running | ≈ ₹48/day (≈ ₹1,430 per 30 days) | Teardown script plus a checklist row in the teardown log; provisioned mode, not on-demand |
| Redshift trial burn unseen | Up to $300 of credit, then ₹194/hour | Usage limit + `SYS_SERVERLESS_USAGE` check at the end of each window |
| This account is not eligible for the trial | ₹581 for 3 active hours | Fall back to one scripted 1-hour window (₹194) |
| QuickSight seat renews | ₹2,718/month | Choose the local dashboard; if QuickSight is used, cancel on the same day the evidence is captured |
| Leftover alarms, log groups, snapshots, KMS keys | ₹11–113 per item per month | "Zero-residual" teardown checklist (§5), verified by a Cost Explorer check 2 days later |
| INR invoice rate differs from ECB rate | A few percent on every figure | Record the invoice's actual INR total in the teardown log; replace estimates with measured values |

### Endgame: the published release

The release is complete when the repo holds the evidence and the account
holds nothing:

- Screenshots, query outputs, run logs and the measured bill for each
  tier go into the repo. The **only** proof of the cloud runs is in git.
- A scripted `demo window` target can recreate T1–T4 on demand for an
  interviewer, then tear it down again.
- Sustained monthly cost: **₹0**. Keeping a 1 GB evidence bucket would
  cost about ₹3/month; the recommendation is to delete it and rely on the
  repo.

### Region move: Mumbai vs N. Virginia

A full T3 + T4 run costs about ₹25 more in Mumbai than in us-east-1
($1.77 vs $1.56 before tax). GST applies either way, because the seller is
AWS India, not the region. For an India-focused portfolio, Mumbai's
data-residency and latency story is worth about ₹25. This input is for
G-14; the owner chose Mumbai on 2026-09-25.

---

## 5. Zero-residual teardown checklist

After every window, delete and verify each of these:

- [ ] Kinesis streams (zero listed)
- [ ] Firehose delivery streams
- [ ] Redshift Serverless workgroups and namespaces, with **no manual
      snapshots** kept ($0.025/GB-month)
- [ ] Glue jobs are idle; development endpoints and interactive sessions are
      stopped
- [ ] CloudWatch alarms and log groups (or retention set to 1 day)
- [ ] S3 buckets, including old object versions if versioning was on
- [ ] Step Functions and EventBridge schedules disabled or deleted
- [ ] QuickSight subscription cancelled (if used)
- [ ] KMS keys scheduled for deletion; Secrets Manager secrets deleted (if T6 was used)
- [ ] Cost Explorer checked 1–2 days later; measured INR total recorded in
      `cost-model.md` §5

---

## 6. Recommended line

**T0 → T1 → T2 → (T3 + T4 in one window, on the trial) → T5 local
dashboard.** That shows 58 of the 58 planned skills for about ₹110 in
total, with ₹0/month after teardown. Add a QuickSight month (₹2,718) only if
the BI skill needs AWS-native evidence and the Quick trial does not cover
it. Skip T6 or keep it to ₹0 options (SSE-S3, IAM authentication).

## 7. Still unverified

- Whether this India-billed legacy account can use the Redshift Serverless
  trial.
- The Glue minimum worker count per Spark job.
- Whether Firehose format conversion uses the same 5 KB rounding as ingest.
- Whether the Quick 30-day trial covers a QuickSight Author.
- Whether a KMS key is billed pro-rata, and whether charges continue during
  its pending-deletion wait.
- EventBridge Scheduler pricing.
- The INR rate AWS India applies on invoices.
