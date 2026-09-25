# AWS Clickstream Analytics — Project Status

Ecosystem snapshot for this repo. Updated after every meaningful session.
Tracked in git (same convention as `gridpulse-gcp`), so it must stay
public-safe: no AWS account IDs, ARNs, access keys, or personal emails —
placeholders only.

## Current phase
Phase 0 in progress (updated 2026-09-25): pricing research and cost model done (G-10), and
ADR-0001 (stack) proposed and awaiting the owner's decision. Local git repo initialised (no
remote yet), no AWS resources provisioned, no code written. The original brief is captured in
`docs/00-initial-brief.md` and is a **non-binding draft**; every stack and
architecture decision is to be re-researched before it is adopted (see
`docs/GAPS.md`).

## Phase status

Provisional — to be replaced by the real plan once Phase 0 research lands.

| Phase | Status | Notes |
|---|---|---|
| 0 — Research & decisions (verify Free Tier, cost, latency, data model; write ADRs) | 🔄 In progress | Account confirmed on the legacy Free Tier (2026-09-24). 2026-09-25: list prices verified for Kinesis, Firehose, Redshift Serverless, S3, Lambda, Glue, Athena and Quick; `docs/cost-model.md` estimates about $1.56 per streaming demo window and about $0.15 per batch run (estimates only, nothing measured); ADR-0001 (hybrid batch baseline + bounded streaming windows) Proposed. DEA-C01 guide v1.1 mapped in `docs/exam-guide-map.md`: 0 of 120 skills shown, 2 designed; 58 planned, 36 stretch, 26 not planned; drives `docs/GAPS.md` |
| 1 — Scaffolding (git repo, CI, Makefile, IaC skeleton, per-directory READMEs) | ⏳ Pending | |
| 2 — Ingest → Bronze (streaming path to S3) | ⏳ Pending | |
| 3 — Batch ETL → Silver (sessionization) | ⏳ Pending | |
| 4 — Warehouse + modelling | ⏳ Pending | |
| 5 — BI dashboards | ⏳ Pending | |
| 6 — Monitoring, security & cost guardrails | ⏳ Pending | |
| 7 — Live demo window + teardown | ⏳ Pending | |

## Last commit
Local scaffold commit only (`git log`); no remote configured yet.

## Metrics
No results yet. No number is reported until it is measured from a real run.

## Known gaps
See `docs/GAPS.md` — the brief-versus-reality register and the exam-coverage
gap map.
