# ADR-0002: Dashboard layer — one Streamlit app, local on Athena and published on a snapshot

- **Status:** Accepted (2026-09-25, by the project owner)
- **Deciders:** project owner
- **Related:** [ADR-0001](0001-ingest-and-warehouse-stack.md) (tier T5 in its
  [annex](0001-hybrid-cost-tiers.md)); `docs/GAPS.md` G-07, G-08;
  `docs/exam-guide-map.md` skill 3.2.1

## Context

ADR-0001 left the BI layer open. Research on 2026-09-25 found:

- Amazon Quick Free and Plus plans cannot author dashboards. A QuickSight
  Author costs $24/user-month (≈ ₹2,718 including 18% GST). That one seat
  would be about 80% of the whole project's all-paid cost, and it renews
  monthly unless cancelled.
- The project goal is a published release with **₹0 sustained monthly
  cost** (ADR-0001 annex).
- A portfolio dashboard is most useful when a reviewer can open it from a
  link, without the author's laptop or AWS account being involved.

## Decision

Build **one Streamlit app** (Python, the same language as the pipeline)
with two data modes chosen by configuration:

1. **Local mode (evidence of the AWS integration).** It runs on the
   owner's laptop and queries the Gold tables through **Athena in Mumbai**
   with a read-only identity. Evidence is screenshots and a short
   recording, committed to the repo. Each Athena query is billed at the
   10 MB minimum, about ₹0.006 including GST.
2. **Published mode (the public link).** The final Gold aggregates are
   exported once, after a real run, into a small Parquet snapshot
   committed to the repo. The same app reads it with DuckDB and is
   deployed to **Streamlit Community Cloud**. The public app holds **no AWS
   credentials** and makes no AWS calls, so it costs ₹0 on AWS whoever
   opens it.

The data is synthetic clickstream, so publishing the snapshot exposes no
personal data.

## Consequences

- AWS cost after teardown remains **₹0/month**. The public dashboard stays
  online because it no longer depends on AWS.
- The published view is a **snapshot**, not live. It is labelled with its
  run date. That also resolves the brief's "last 1 hour" panel (G-08) for
  the public app: live views are shown only in local mode, during a
  streaming window.
- `.gitignore` currently ignores all `*.parquet` and `/data/*`. The build
  must add one narrow exception for the snapshot directory and keep the
  snapshot small (target: a few MB).
- Streamlit Community Cloud limits (docs.streamlit.io, fetched 2026-09-25):
  0.078–2 CPU cores, 690 MB–2.7 GB memory, up to 50 GB storage, and apps
  "without traffic for 12 hours go to sleep" (a visitor can wake one). The
  first visit after a quiet spell will be slow.
- Exam skill 3.2.1 names AWS tools (DataBrew, QuickSight) as examples.
  This design shows the skill (visualising data queried through an AWS
  service), but **not QuickSight itself**. That gap is recorded honestly
  in the exam map. A QuickSight trial stays an optional stretch.

## Alternatives rejected

- **QuickSight, paid:** ≈ ₹2,718 per Author-month, and the link dies when the
  seat is cancelled, which conflicts with the ₹0-sustained goal.
- **QuickSight trial only:** whether the Quick 30-day trial covers a
  QuickSight Author is unverified, and it has the same dead-link problem
  after the trial.
- **Static snapshot site only (Evidence.dev / Observable):** a public link at
  ₹0, but it never queries AWS, so it gives weaker evidence of the
  pipeline integration.
- **Power BI Desktop:** free on Windows and common in job posts, but a public
  link needs the separate Power BI service. It remains a possible later
  add-on.
- **Grafana / Metabase / Superset:** they connect to Athena, but they need
  a Docker runtime and have no comparable free public hosting.

## Still unverified

- Whether Streamlit Community Cloud is free with no paid tier needed, and
  whether it requires a public GitHub repo. The pages read did not say.
- How it handles secrets. This is not needed for published mode, which
  uses no credentials.
- The Athena client library for local mode (`pyathena` or the AWS SDK for
  pandas), to be checked against current docs at build time.
