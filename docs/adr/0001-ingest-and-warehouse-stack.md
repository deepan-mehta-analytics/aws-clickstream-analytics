# ADR-0001: Ingest and warehouse stack

- **Status:** Accepted (2026-09-25, by the project owner; proposed the same day)
- **Deciders:** project owner
- **Related:** `docs/GAPS.md` G-01, G-02, G-04, G-05, G-10; `docs/cost-model.md`;
  [annex: hybrid cost tiers, SWOT and move analysis](0001-hybrid-cost-tiers.md)
  (Mumbai, INR incl. GST: about ₹110 one-time for the full hybrid on trials,
  ₹0/month after teardown)

## Context

The original brief (`docs/00-initial-brief.md`) assumed that Kinesis Data
Streams, Firehose, Redshift, QuickSight and Glue ETL were all "Always Free".
Research on 2026-09-24/25 found otherwise:

- This account is on the **legacy Free Tier**, so it gets no new-plan
  credits. The only relevant Always Free allowances are Lambda (1M
  requests + 400,000 GB-s/month) and the Glue Data Catalog (1M objects +
  1M requests/month). S3's 12-month offer has likely lapsed.
- Kinesis Data Streams is "NOT currently available in AWS Free Tier". Neither
  Firehose, Glue ETL nor Athena has a free tier stated on its pricing page.
- Redshift Serverless has a separate **$300 / 90-day trial** for accounts
  that have never used Serverless. It is independent of the Free Tier, and
  its usage is not shown in the Billing console.

Estimated costs from list prices (see `docs/cost-model.md`): a 2-hour
streaming window costs about $1.56 (about $0.06 while the trial credit
lasts), and a daily batch run about $0.15. Streams left running cost
$0.36–0.96/day.

## Decision

Use a **hybrid** design in **Asia Pacific (Mumbai), `ap-south-1`**, built up
tier by tier along the recommended line in the
[annex](0001-hybrid-cost-tiers.md) §6: local twin, then batch, then
orchestration, then one combined streaming and Redshift window, then the
dashboard. Mumbai costs about ₹25 more per streaming and warehouse window
than us-east-1. GST applies in either region. Mumbai keeps the data in
India, which fits the portfolio's India focus.

1. **Baseline, always available: the batch path.** A Lambda event
   generator writes to S3 (Bronze), a Glue job builds Silver/Gold, and
   Athena serves queries. Nothing is billed while idle.
2. **Bounded demo windows: the streaming path.** Kinesis Data Streams
   (1 provisioned shard) → Firehose (Parquet) → S3, with Redshift
   Serverless at the 4-RPU base on the trial credit. Every window is
   created and torn down by IaC, and each one is logged in
   `docs/cost-model.md` §5.

This ADR does not decide the BI layer; see
[ADR-0002](0002-dashboard-streamlit.md) (one Streamlit app, local on
Athena and published on a snapshot, ₹0/month).

## Consequences

- The warehouse and streaming services the brief centres on are shown
  running in real, evidenced windows, and the idle cost stays near zero.
- There are two ingestion paths to build and document, which is more work
  than either path alone.
- The Redshift trial clock (90 days) starts at activation, so windows must be
  planned before it is switched on.
- Redshift trial burn has to be watched in the Redshift console or
  `SYS_SERVERLESS_USAGE`, because Budgets will not see it.
- Exam coverage, checked against guide v1.1 on 2026-09-25 in
  `docs/exam-guide-map.md`: 11 of the 120 skills (6 planned, 5 stretch)
  depend on the streaming and Redshift window, including reading streaming
  sources (1.1.1), loading and unloading between S3 and Redshift (2.3.1),
  Redshift schema design (2.4.1) and Spectrum or materialized views (2.1.5).
  A batch-only design would drop them. The window is therefore
  load-bearing for coverage, not decoration.

## Alternatives rejected

- **Streaming path only, always on:** a running shard alone costs about
  $10.80 per 30 days before any warehouse compute, and it has idle costs
  that the budget guardrail cannot fully see.
- **Batch path only:** the cheapest option, but it drops Kinesis, Firehose
  and Redshift entirely, which the project's portfolio goal needs to show.
- **Provisioned Redshift (dc2.large trial):** AWS offers it only "where
  Serverless [is] unavailable", and a cluster left running bills every hour.

## Preconditions carried forward

- **Before T4 (the Redshift window):** the account owner checks in the
  Redshift console that the Serverless free trial is offered to this
  India-billed account. If it is not, T4 runs as one scripted, paid hour
  (about ₹194 including GST) instead of several trial hours.
- **Before any resource:** an AWS Budgets alert, set by the account owner.
  IAM for each tier is applied by the owner as one reviewed IaC stack.
