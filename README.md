# 🖱️ AWS Clickstream Analytics

## ⚡ Quick Summary

This project turns raw website clicks into answers a shop owner can act on:
how many people visit each day, how deep they browse, and which products make
them leave after one click. It uses **real clickstream data** from a 2008
online clothing shop: 165,474 clicks across 24,026 visits. It is built as a
layered data pipeline (Bronze → Silver → Gold) with data-quality checks at
every step.

The pipeline runs fully on a laptop today (the "local twin"). The same code
and SQL are designed to move to AWS in the Mumbai region, in small priced
steps. Every cloud resource is torn down after use, so the project costs
nothing per month once it is published.

### Real data, honest labels, and a cloud path priced in rupees before a single resource is created

---

## 🏷️ Project Badges

[![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![pandas](https://img.shields.io/badge/pandas-2.3-150458?style=for-the-badge&logo=pandas&logoColor=white)](https://pandas.pydata.org/)
[![DuckDB](https://img.shields.io/badge/DuckDB-1.5-yellow?style=for-the-badge)](https://duckdb.org/)
[![Parquet](https://img.shields.io/badge/Storage-Parquet-50ABF1?style=for-the-badge)](https://parquet.apache.org/)
[![AWS](https://img.shields.io/badge/AWS-Mumbai_(planned)-FF9900?style=for-the-badge&logo=amazonwebservices&logoColor=white)](docs/adr/0001-ingest-and-warehouse-stack.md)
[![Status](https://img.shields.io/badge/Status-In_Development-yellow?style=for-the-badge)](PROJECT-STATUS.md)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

---

## 📌 Project Overview

This project implements **a medallion-architecture clickstream pipeline with a
two-grain star schema**, designed for AWS and built and tested locally first.

It uses the [UCI "Clickstream Data for Online Shopping" dataset](https://archive.ics.uci.edu/dataset/553/clickstream+data+for+online+shopping)
(CC BY 4.0).

Implemented today (local twin, no AWS):

- **Bronze `clicks_received`** — every click as it arrived, including simulated resends
- **Silver `clicks`** — one cleaned row per real click; hard quality rules send failures to `clicks_rejected` with a reason, never silently dropped
- **Gold star schema** — `clicks` (one row per click) and `visits` (one row per visit), plus reference tables `products`, `countries`, `calendar_days`, `devices`
- **Dashboard summaries in portable SQL** — daily visits, browse-depth funnel, bounce rate by product, visits by country and device
- **Labelled synthetic enrichment** — the source has dates but no time of day or device, so these are generated from a fixed seed in columns ending `_synthetic`
- **Reconciliation against measured facts** — a test runs the real file end to end and checks every count against the numbers measured from the source

Designed but not built yet: AWS ingestion (Kinesis → Firehose), Glue, Athena,
a Redshift Serverless window, and a Streamlit dashboard. See the Roadmap.

---

## ⚙️ Tech Stack

| Layer | Tool | Purpose |
|---|---|---|
| Language | Python 3.11 | Pipeline code |
| Data processing | pandas 2.3 + NumPy | Transformations and seeded enrichment |
| Storage format | Apache Parquet (pyarrow 16.1) | Columnar files, partitioned by month |
| Local SQL engine | DuckDB 1.5 | Runs the summary SQL (the same files are meant for Athena and Redshift) |
| Timezones | zoneinfo + tzdata | Shop local time (Europe/Warsaw), stored in UTC |
| Testing | pytest 9 | 70 tests, including full-file reconciliation and template guardrails |
| Linting | ruff (Python), cfn-lint (CloudFormation) | Static checks |
| CI | GitHub Actions | Hygiene, lint and tests; downloads the dataset and verifies its MD5 (runs once the repo has a remote) |
| Cloud (planned) | AWS Mumbai: Lambda, S3, Glue, Athena, Kinesis, Firehose, Redshift Serverless | See [ADR-0001](docs/adr/0001-ingest-and-warehouse-stack.md) |
| Infrastructure as code | AWS SAM + CloudFormation, `cfn-lint` | One stack per tier, owner-deployed through a reviewed change set ([ADR-0004](docs/adr/0004-iac-sam-cloudformation.md)) |
| Dashboard (planned) | Streamlit | Local on Athena, published on a data snapshot ([ADR-0002](docs/adr/0002-dashboard-streamlit.md)) |

---

## 🎯 Business Problem

An online shop sees thousands of clicks a day but cannot tell which products
pull visitors deeper into the catalogue and which ones make them leave
straight away. Raw click logs are also messy: events arrive late, arrive
twice, or carry invalid codes.

> **Which products and pages keep visitors browsing, where do visits stop, and
> can those numbers be trusted?**

---

## 🏗️ Architecture

```
UCI CSV (real 2008 clicks)
   ──►  Enrichment (seeded time of day + device, labelled _synthetic)
   ──►  Bronze  clicks_received      (as arrived, resends possible)
   ──►  Silver  clicks               (deduplicated, validated, decoded)
          └──►  clicks_rejected      (failed rows + reason)
   ──►  Gold    star schema          (clicks, visits + products, countries, calendar_days, devices)
   ──►  Summaries (SQL)              (daily_visits, visit_depth_funnel, bounce_rate_by_product, visits_by_country_and_device)
   ──►  quality_report.json          (reconciliation counts + reported findings)
```

| Component | Module | Role |
|---|---|---|
| Source reader | `src/clickstream/source_file.py` | Reads the `;`-delimited UCI file and applies plain column names |
| Enrichment | `src/clickstream/enrichment.py` | `click_id`, `click_time_synthetic`, `device_type_synthetic` |
| Bronze | `src/clickstream/bronze.py` | Adds `received_time`, `data_source`; optional resends |
| Silver | `src/clickstream/silver.py` | Deduplication, hard quality rules, decoding |
| Gold | `src/clickstream/gold.py` | Star schema with click and visit grains |
| Summaries | `sql/summaries/*.sql` + `summaries.py` | Dashboard queries run in DuckDB |
| Runner | `src/clickstream/local_run.py` | End-to-end local run writing Parquet and the report |

Design decisions are recorded as ADRs:
- [ADR-0001: hybrid stack in Mumbai](docs/adr/0001-ingest-and-warehouse-stack.md), with a [cost-tier and SWOT annex](docs/adr/0001-hybrid-cost-tiers.md)
- [ADR-0002: Streamlit dashboard](docs/adr/0002-dashboard-streamlit.md)
- [ADR-0003: data model](docs/adr/0003-data-model.md)
- [ADR-0004: infrastructure as code (SAM + CloudFormation) and security baseline](docs/adr/0004-iac-sam-cloudformation.md)

---

## 📁 Repository Structure

```
aws-clickstream-analytics/
├── src/clickstream/            ← the pipeline package, one module per stage
├── sql/summaries/              ← dashboard SQL, portable to Athena/Redshift
├── tests/                      ← 70 pytest tests incl. full-file reconciliation and template guardrails
├── data/README.md              ← dataset source, licence, MD5s, measured stats (data itself is gitignored)
├── docs/
│   ├── adr/                    ← architecture decision records (0001–0004 + cost annex)
│   ├── data-dictionary.md      ← every table and column in plain words
│   ├── cost-model.md           ← verified AWS prices and teardown log
│   ├── exam-guide-map.md       ← DEA-C01 skills-coverage matrix
│   ├── exam-guide-delta.md     ← exam guide re-check log
│   └── GAPS.md                 ← what is verified, open or accepted as a limitation
├── infra/                      ← CloudFormation/SAM stacks (foundation written; owner-deployed only)
├── glue/  dashboards/          ← placeholders for the cloud tiers (each has a README)
├── .github/workflows/ci.yml    ← hygiene, lint (ruff + cfn-lint), tests
├── Makefile                    ← working local targets; cloud targets say "owner-run only"
├── pyproject.toml              ← package and pinned dependencies
├── PROJECT-STATUS.md           ← phase-by-phase status
└── LICENSE                     ← MIT
```

---

## ▶️ How to Run

### 📌 Option 1 — Local (Windows shown; use `.venv/bin/python` on Linux/macOS)

#### 1. Clone and create a virtual environment
```bash
git clone <this-repo-url>
cd aws-clickstream-analytics
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

#### 2. Download the dataset from UCI (see `data/README.md`)
```bash
curl -L -o data/uci553.zip "https://archive.ics.uci.edu/static/public/553/clickstream+data+for+online+shopping.zip"
unzip -o data/uci553.zip -d data/
```

#### 3. Run the pipeline
```bash
.venv/Scripts/python -m clickstream.local_run --source "data/e-shop clothing 2008.csv" --output output/local
```
Output lands in `output/local/` (gitignored): `bronze/`, `silver/`, `gold/`
and `quality_report.json`.

### ☁️ Option 2 — GitHub Actions

`.github/workflows/ci.yml` runs the hygiene check, ruff, cfn-lint and the
full test suite on every push. It downloads the dataset and checks its MD5 first. It
has not run yet, because the repository has no remote.

---

## 🧪 Tests

```bash
.venv/Scripts/python -m ruff check src tests
.venv/Scripts/python -m pytest -v
.venv/Scripts/cfn-lint
```

70 tests. They cover:
- the reader and codebook;
- repeatable seeded enrichment, including a 195-click visit near midnight;
- Bronze resends;
- every Silver quality rule, plus out-of-order and empty input;
- Gold metrics, including the real A18 category anomaly;
- the SQL summaries;
- the end-to-end run;
- `test_full_file.py`, which checks the real file against the measured stats. It is skipped when the dataset is not downloaded;
- `test_infra_templates.py`, which checks every CloudFormation template for encryption, private buckets, TLS-only policies, safe IAM (no admin or public grants) and no account IDs in any committed file.

---

## 📊 Results / Performance

From a **local run (tier T0)** on the full UCI file, 2026-09-25:

| Measure | Value |
|---|---|
| Source clicks read | 165,474 |
| Clicks rejected by quality rules | 0 |
| Silver clicks | 165,474 |
| Visits | 24,026 |
| One-click visits (bounces) | 5,042 (≈ 21%) |
| Category mismatches reported | 1 (product A18: 937× trousers, 1× skirts) |

Browse-depth funnel (visits reaching at least each shop page):

| Page 1 | Page 2 | Page 3 | Page 4 | Page 5 |
|---|---|---|---|---|
| 24,026 | 14,504 | 9,125 | 4,779 | 1,631 |

When resends are simulated (every 1,000th click sent twice), Silver removes
exactly the 166 duplicates (checked by `test_full_file.py`).

**Cloud cost (estimate, not measured):** about ₹110 one-time for the full
hybrid build if the Redshift Serverless trial applies, and ₹0/month after
teardown. Details in the [cost-tier annex](docs/adr/0001-hybrid-cost-tiers.md).

---

## 🎓 Exam Alignment (AWS Certified Data Engineer – Associate)

A [skills-coverage matrix](docs/exam-guide-map.md) maps all 120 skills in exam
guide v1.1 to evidence in this repo. It is a coverage matrix, not exam prep.
**8 of 120 skills are shown** (by the local run and tests), **15 are designed**
in ADRs, and **97 are not started**. It is honest by construction: nothing
is marked shown without a real run behind it.

---

## ⚠️ Known Limitations

- **No user ID in the source:** the pipeline counts **visits**, not active users.
- **No checkout or purchase events:** the funnel is a **browse-depth** funnel, not a purchase funnel.
- **Time of day and device are synthetic:** generated from a fixed seed, and labelled `_synthetic` everywhere.
- **The data is from 2008** (April–August), mostly Polish traffic (≈ 81%).
- **No AWS resources exist yet:** the cloud tiers are designed and priced, not built.
- **Infrastructure as code is only partly written:** AWS SAM-extended CloudFormation, one stack per tier, deployed only by the account owner ([ADR-0004](docs/adr/0004-iac-sam-cloudformation.md)). Only the foundation (artifacts bucket) template exists; it has not been deployed.
- **Encryption uses S3-managed keys (SSE-S3), not a customer-managed KMS key**, to avoid a monthly key charge and a 7–30 day key-deletion wait ([ADR-0004](docs/adr/0004-iac-sam-cloudformation.md)).

## 🔜 Roadmap

- [x] T0: local twin (Bronze → Silver → Gold → summaries, 45 tests)
- [ ] T1: serverless batch on AWS Mumbai (Lambda → S3 → Glue → Athena)
- [ ] T2: orchestration, data-quality alerts, monitoring
- [ ] T3 + T4: one streaming window (Kinesis → Firehose) with a Redshift Serverless window
- [ ] T5: Streamlit dashboard, local on Athena and published on a snapshot

---

## 📂 Dataset

**Clickstream Data for Online Shopping**, UCI Machine Learning Repository
#553 (DOI 10.24432/C5QK7X), licensed CC BY 4.0.

Łapczyński M., Białowąs S. (2013). *Discovering Patterns of Users' Behaviour
in an E-shop – Comparison of Consumer Buying Behaviours in Poland and Other
European Countries.* Studia Ekonomiczne, nr 151, pp. 144–153.

Checksums and measured statistics are in [`data/README.md`](data/README.md).

---

## 📜 License

MIT. See [`LICENSE`](LICENSE). The dataset keeps its own licence (CC BY 4.0).

---

## 👤 Author

**Deepan Mehta**

- Data Analytics → Data Engineering → AI/ML Engineering
- Focused on building end-to-end data and ML systems combining analytics, automation, and deployment
- Experience in ETL pipelines, predictive modelling, and analytical databases

🔗 GitHub: [deepan-mehta-analytics](https://github.com/deepan-mehta-analytics)
