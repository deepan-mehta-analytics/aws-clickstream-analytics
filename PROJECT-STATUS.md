# AWS Clickstream Analytics — Project Status

Ecosystem snapshot for this repo. Updated after every meaningful session.
Tracked in git (same convention as `gridpulse-gcp`), so it must stay
public-safe: no AWS account IDs, ARNs, access keys, or personal emails —
placeholders only.

## Current phase
Phase 0 in progress (updated 2026-09-29): pricing research and cost model done (G-10), and
ADR-0001 (hybrid stack in Mumbai) accepted; ADR-0002 (Streamlit dashboard: local on Athena, published on a snapshot) accepted; ADR-0003 (data model: real UCI #553 clickstream + labelled synthetic time/device, two-grain star schema) accepted. **Phase 1 local twin (tier T0) built:** the full UCI file runs Bronze → Silver → Gold → summaries locally, with 45 tests passing at T0 ship (local run: 165,474 clicks, 24,026 visits, 5,042 bounces, 0 rejects, 1 reported category mismatch). ADR-0004 (infrastructure as code: AWS SAM-extended CloudFormation, one stack per tier, owner-deployed via a reviewed change set; SSE-S3, TLS-only, least-privilege roles) accepted 2026-09-26, resolving G-13. IaC foundation built (not deployed). Tier T1 designed on 2026-09-26 and split into four slices (T1a core lake: Lambda → S3 Bronze → Glue 6.0 Spark → Glue Catalog → Athena; T1b Iceberg Silver; T1c ingest extras; T1d evidence pass). T1a update 2026-09-28: Tasks 1–9 built locally (Spark harness, ingest Lambda, Spark Silver/Gold, summaries and quality, full-file pandas-vs-Spark parity, Glue job entry point and library zip, and the T1a SAM stack with guardrail tests; Glue 6.0 logging moved to `--custom-logGroup-prefix` after the review found the older continuous-log arguments are ignored since Glue 5.0); Task 10 (2026-09-29): owner window, verified-teardown and evidence-masking tooling built and reviewed (never run against AWS); Task 11: DST-safe shop-time conversion and microsecond Parquet timestamps; next, docs and ADR-0005, then an owner-run deploy window. Public GitHub repo created 2026-09-28 with CI green; no AWS resources provisioned; the local twin code is built and tested. The original brief is captured in
`docs/00-initial-brief.md` and is a **non-binding draft**; every stack and
architecture decision is to be re-researched before it is adopted (see
`docs/GAPS.md`).

## Phase status

Provisional — to be replaced by the real plan once Phase 0 research lands.

| Phase | Status | Notes |
|---|---|---|
| 0 — Research & decisions (verify Free Tier, cost, latency, data model; write ADRs) | 🔄 In progress | Account confirmed on the legacy Free Tier (2026-09-24). 2026-09-25: list prices verified for Kinesis, Firehose, Redshift Serverless, S3, Lambda, Glue, Athena and Quick; `docs/cost-model.md` estimates about $1.56 per streaming demo window and about $0.15 per batch run (estimates only, nothing measured); ADR-0001 (hybrid batch baseline + bounded streaming windows, region Mumbai `ap-south-1`) **Accepted** 2026-09-25, with an annex that prices a 7-tier ladder in Mumbai (INR incl. GST) with SWOT: ≈ ₹110 one-time on trials, ₹0/month after teardown. DEA-C01 guide v1.1 mapped in `docs/exam-guide-map.md`: 8 of 120 skills shown (local run), 15 designed; 86 planned, 8 stretch, 26 not planned (26 stretch skills promoted to low-cost tier add-ons on 2026-09-26); drives `docs/GAPS.md`. 2026-09-26: ADR-0004 (IaC + security baseline) **Accepted**, G-13 resolved |
| 1 — Scaffolding (git repo, CI, Makefile, IaC skeleton, per-directory READMEs) | ✅ Done | Package, pinned tooling, hygiene/lint/test CI (green on GitHub Actions since 2026-09-28), honest Makefile, directory READMEs, root README, and the local twin pipeline (tier T0). IaC foundation built 2026-09-26: artifacts-bucket stack, guardrail tests, cfn-lint in CI (not deployed) |
| 2 — Ingest → Bronze (streaming path to S3) | ⏳ Pending | |
| 3 — Batch ETL → Silver and Gold on AWS (Glue) | ⏳ Pending | Logic built and verified locally (tier T0); the Glue 6.0 Spark job, SAM stack and owner window/teardown tooling are built and tested locally (T1a, not deployed); visits come from real session IDs, not gap-based sessionization (ADR-0003) |
| 4 — Warehouse + modelling | ⏳ Pending | |
| 5 — BI dashboards | ⏳ Pending | |
| 6 — Monitoring, security & cost guardrails | ⏳ Pending | |
| 7 — Live demo window + teardown | ⏳ Pending | |

## Last commit
See `git log` on `main` (hashes are not repeated here). Latest milestone: T1a Task 11 (T1-prep fixes), pushed with CI green (136 passed) on 2026-09-29.

## Metrics
From a **local run (tier T0)** on the full UCI file, 2026-09-25: 165,474 source clicks, 0 rejected, 165,474 Silver clicks, 24,026 visits, 5,042 one-click visits, 1 reported category mismatch (A18); browse-depth funnel 24,026 / 14,504 / 9,125 / 4,779 / 1,631. As of 2026-09-29, 136 tests pass on Linux CI (132 on Windows, where 4 lake-storage tests are skipped); the full-file pandas-vs-Spark check matches on all 165,474 clicks. No AWS metric exists yet; none is reported until measured from a real cloud run.

## Known gaps
See `docs/GAPS.md` — the brief-versus-reality register and the exam-coverage
gap map.
