# AWS Clickstream Analytics — Project Status

Ecosystem snapshot for this repo. Updated after every meaningful session.
Tracked in git (same convention as `gridpulse-gcp`), so it must stay
public-safe: no AWS account IDs, ARNs, access keys, or personal emails —
placeholders only.

## Current phase
Phase 0 in progress (updated 2026-09-25): pricing research and cost model done (G-10), and
ADR-0001 (hybrid stack in Mumbai) accepted; ADR-0002 (Streamlit dashboard: local on Athena, published on a snapshot) accepted; ADR-0003 (data model: real UCI #553 clickstream + labelled synthetic time/device, two-grain star schema) accepted. **Phase 1 local twin (tier T0) built:** the full UCI file runs Bronze → Silver → Gold → summaries locally, with 38 tests passing (local run: 165,474 clicks, 24,026 visits, 5,042 bounces, 0 rejects, 1 reported category mismatch). Next: tier T1 on AWS, which needs the IaC decision (G-13) first. Local git repo initialised (no
remote yet), no AWS resources provisioned, no code written. The original brief is captured in
`docs/00-initial-brief.md` and is a **non-binding draft**; every stack and
architecture decision is to be re-researched before it is adopted (see
`docs/GAPS.md`).

## Phase status

Provisional — to be replaced by the real plan once Phase 0 research lands.

| Phase | Status | Notes |
|---|---|---|
| 0 — Research & decisions (verify Free Tier, cost, latency, data model; write ADRs) | 🔄 In progress | Account confirmed on the legacy Free Tier (2026-09-24). 2026-09-25: list prices verified for Kinesis, Firehose, Redshift Serverless, S3, Lambda, Glue, Athena and Quick; `docs/cost-model.md` estimates about $1.56 per streaming demo window and about $0.15 per batch run (estimates only, nothing measured); ADR-0001 (hybrid batch baseline + bounded streaming windows, region Mumbai `ap-south-1`) **Accepted** 2026-09-25, with an annex that prices a 7-tier ladder in Mumbai (INR incl. GST) with SWOT: ≈ ₹110 one-time on trials, ₹0/month after teardown. DEA-C01 guide v1.1 mapped in `docs/exam-guide-map.md`: 8 of 120 skills shown (local run), 8 designed; 58 planned, 36 stretch, 26 not planned; drives `docs/GAPS.md` |
| 1 — Scaffolding (git repo, CI, Makefile, IaC skeleton, per-directory READMEs) | ✅ Done (local) | Package, pinned tooling, hygiene/lint/test CI (defined, not yet run: no remote), honest Makefile, directory READMEs, root README, and the local twin pipeline (tier T0). IaC skeleton excluded, pending G-13 |
| 2 — Ingest → Bronze (streaming path to S3) | ⏳ Pending | |
| 3 — Batch ETL → Silver (sessionization) | ⏳ Pending | |
| 4 — Warehouse + modelling | ⏳ Pending | |
| 5 — BI dashboards | ⏳ Pending | |
| 6 — Monitoring, security & cost guardrails | ⏳ Pending | |
| 7 — Live demo window + teardown | ⏳ Pending | |

## Last commit
See `git log` on `main` (local twin docs commit); no remote configured yet.

## Metrics
No results yet. No number is reported until it is measured from a real run.

## Known gaps
See `docs/GAPS.md` — the brief-versus-reality register and the exam-coverage
gap map.
