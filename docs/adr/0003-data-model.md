# ADR-0003: Data model: real UCI clickstream, labelled enrichment, two-grain star schema

- **Status:** Accepted (2026-09-25, by the project owner, after a
  section-by-section brainstorm and a review of this written ADR)
- **Deciders:** project owner
- **Related:** `docs/GAPS.md` G-08, G-09, G-14;
  [ADR-0001](0001-ingest-and-warehouse-stack.md) (hybrid stack, Mumbai);
  [ADR-0002](0002-dashboard-streamlit.md) (Streamlit, published snapshot);
  [`data-dictionary.md`](../data-dictionary.md);
  [`data/README.md`](../../data/README.md)

## Context

The brief's model was internally inconsistent (G-09):

- `fact_clicks` was loaded from `silver/sessions/`, so its name (a click)
  did not match what one row actually was (a session).
- `users` and `pages` tables appeared with no job to derive them.
- No Gold layer was defined.
- The simulated events carried a `session_id`, but a separate job was
  supposed to re-derive sessions from a 30-minute gap.

The data source had to be settled first. Candidates reviewed on
2026-09-25:

- **UCI #553, "Clickstream Data for Online Shopping"** (also mirrored on
  Kaggle as `tunguz/clickstream-data-for-online-shopping`): real clicks
  from a 2008 maternity-clothing e-shop, licensed **CC BY 4.0**.
- Every clickstream candidate in `awesomedata/awesome-public-datasets`:
  - The Coveo shopper-intent set is technically the richest, but its terms
    allow "only … non-commercial research and educational purposes" and
    forbid distributing "data contained therein", which rules out
    ADR-0002's public snapshot.
  - The Indiana University web-click data is restricted to research labs.
  - The Criteo and KDD Cup 2012 sets are advertising data, not
    clickstreams.

Measured from the real UCI file (see `data/README.md`):

- 165,474 clicks and 24,026 sessions, with 5,042 one-click sessions.
- 135 dates in April–August 2008, 47 country codes, 217 products.
- No nulls and no duplicate rows. Click order is complete in every
  session, and no session crosses midnight.
- Colour, price, above-average-price flag, photo position, photo angle
  and page number are fixed per product. Country is fixed per session.
  Exactly one product (A18) appears once under a second category.
- The data has **no time of day, no user ID, no checkout or purchase
  events, and no device**.

## Decision

1. **Source: UCI #553 is the real backbone, downloaded from UCI** (not the
   Kaggle mirror), with source, licence, citation and MD5 recorded in
   `data/README.md`.
2. **Labelled synthetic enrichment, only for what the data lacks.** It is
   seeded per visit, so it is reproducible:
   - `click_time_synthetic`: the real 2008 date is kept. The visit start
     comes from a documented hour-of-day profile in shop local time
     (Europe/Warsaw, UTC+2 for April–August), and later clicks follow at
     documented gaps (about 5 s to 5 min) in the real click order. The
     visit stays within its real date. Times are stored in UTC.
   - `device_type_synthetic`: one value per visit from documented,
     illustrative weights. Any chart that uses it is labelled synthetic.
   - `received_time`: the real time the event entered Kinesis or S3.
     Lateness is measured as `seconds_late` = received time minus click
     time.
3. **Visits use the real session ID.** Visits are aggregated by the real
   session ID (a stateful aggregation). The brief's 30-minute-gap
   sessionization is dropped: over synthetic times it would only
   reproduce sessions the generator created.
4. **Metrics are reframed honestly:**
   - daily **visits** replace daily active users, because there is no
     user ID;
   - a **browse-depth funnel** (visits reaching shop page ≥1 … ≥5:
     24,026 → 14,504 → 9,125 → 4,779 → 1,631) replaces the purchase
     funnel, because there are no checkout or purchase events;
   - bounce rate by product and category, and visits by country and
     (synthetic) device, stay as they are.
5. **Layers and tables.** The Bronze/Silver/Gold layer names are fixed.
   Everything inside them has plain, full-word names.
   - **Bronze** `clicks_received`: one row per click as it arrived, which
     may include resends.
   - **Silver** `clicks`: one row per real click, deduplicated on
     `click_id`, with types enforced and codes decoded; rejected rows go
     to `clicks_rejected` with a `rejection_reason`.
   - **Gold** is a star schema with two grains:
     - reference tables `products` (217), `countries` (47),
       `calendar_days` and `devices`;
     - event tables `clicks` (one per click) and `visits` (one per
       visit);
     - dashboard summaries `daily_visits`, `visit_depth_funnel`,
       `bounce_rate_by_product` and `visits_by_country_and_device`.
   - Joins use the real codes (`product_code`, `country_code`,
     `calendar_date`, `device_type`); no surrogate IDs are added.
   - Product A18 keeps its most frequent category (trousers). The one
     mismatched click is a reported data-quality finding.
6. **Storage.**
   - Bronze uses Firehose's UTC hourly folders.
   - Silver and Gold are Parquet partitioned by **month**, avoiding about
     135 tiny daily folders. Athena finds them through partition
     projection (no crawler).
   - In the Redshift window:
     - reference tables are copied to every node (`DISTSTYLE ALL`);
     - `clicks` and `visits` are sorted by date;
     - the Gold tables are loaded with `COPY`;
     - the summaries are exported with `UNLOAD` to feed the published
       Streamlit snapshot.
7. **Data quality.**
   - Hard rules (rows go to `clicks_rejected`):
     - `click_id` is unique;
     - required fields are present;
     - the real date is a valid calendar date;
     - codes are within the codebook's ranges;
     - click numbers are contiguous within each visit;
     - synthetic times increase with click number and stay within the
       real date;
     - if any click in a visit fails, every click in that visit is
       rejected ("other click in visit rejected"), so no partial visit
       reaches Gold (added after the whole-branch review, 2026-09-25).
   - Reported, not failed: category mismatches (exactly 1 expected),
     duplicates removed from Bronze, and reconciliation counts (165,474
     clicks / 24,026 visits / 5,042 one-click visits).
8. **Testing, on the local twin first:**
   - unit tests on hand-made visits (one-click, A18, a resend, a gap in
     click numbers, out-of-order arrival);
   - a test that the same seed gives identical synthetic columns;
   - full-file reconciliation of the counts and the funnel;
   - checks that the summaries match across the local run, Athena and
     Redshift.

## Consequences

- G-09's grain mismatch is resolved with real data at both grains: clicks
  and visits.
- The dashboard can make only true claims:
  - dates are real;
  - times and devices are labelled synthetic;
  - "visits" and "browse depth" are named for what they measure.
- The brief's DAU and purchase-funnel dashboards are **not** reproduced.
  This is recorded as a known limitation, not hidden.
- The volume is 165,474 events, about 1.65× the 100,000 assumed in the
  cost model. The per-GB lines scale accordingly; totals stay in single
  rupees per run.
- Exam coverage (the local twin now shows several of these; see `docs/exam-guide-map.md` for the current status):
  - 2.4.1 schema design;
  - 2.4.5 partitioning and compression;
  - 2.2.4 partition sync;
  - 3.4.1 data-quality checks;
  - 1.1.12 stateful processing;
  - 1.2.9 data characteristics.
- **Still to verify when building:** whether Redshift Serverless honours
  explicit `DISTSTYLE`/`SORTKEY` settings, and the Firehose record-format
  settings (G-03).

## Alternatives rejected

- **Pure synthetic generator:** it supports every brief metric, but none
  of the data would be real.
- **Coveo shopper-intent data:** its non-commercial and no-redistribution
  terms conflict with a public repo and a published snapshot.
- **One wide table plus views:** weak evidence of schema design (exam
  2.4.1).
- **Apache Iceberg for Silver:** kept as a stretch goal (2.1.7), not the
  baseline.
- **Re-dating 2008 to the present:** it misrepresents a real historical
  dataset.
- **30-minute-gap sessionization:** circular over synthetic timestamps.
- **Product-engagement funnel:** its thresholds would be arbitrary.
