# ADR-0005: Tier T1a batch lake design (Spark on Glue, one bucket per layer, projection tables)

- **Status:** Proposed (2026-09-29; the project owner flips this to Accepted)
- **Deciders:** project owner
- **Related:** [ADR-0001](0001-ingest-and-warehouse-stack.md) (hybrid stack,
  Mumbai); [ADR-0001 cost tiers](0001-hybrid-cost-tiers.md) (T1 about ₹12 a
  run); [ADR-0003](0003-data-model.md) (data model);
  [ADR-0004](0004-iac-sam-cloudformation.md) (SAM stack, security baseline,
  owner-run deploys); `docs/GAPS.md`; `infra/t1-lake/template.yaml`

## Context

Tier T1 (Lambda → S3 → Glue → Athena in `ap-south-1`) was split into four
slices on 2026-09-26 because 46 exam skills are too many for one plan. This
ADR covers the first slice, **T1a, the core lake**: ingest the UCI file into
Bronze, turn it into Silver and Gold with a Glue job, expose the results to
Athena, and tear everything down after a proof window.

Constraints that shaped the choices:

- **Exam coverage and portfolio value come first.** Glue with Spark, job
  bookmarks, the Glue Data Catalog and Athena are all named DEA-C01 topics.
- **The pandas pipeline from tier T0 already exists** and is verified against
  the real file, so it can serve as a known-right answer.
- **Every AWS command is run by the owner** (ADR-0004), so the design must
  make a window repeatable and hard to get wrong.
- **Cost stays small and capped.** The whole tier is estimated at about ₹12
  per proof run (annex to ADR-0001), so a runaway job is the main risk.

Nothing in this ADR has run on AWS yet. Items that only a real run can settle
are logged in `docs/GAPS.md`.

## Decision

The numbering follows the T1a design decisions D2–D7.

1. **D2: a native PySpark Glue job; the pandas code stays as the local
   reference.** The Silver and Gold stages are written in PySpark
   (`src/clickstream_spark/`, entry point `glue/build_silver_gold.py`). The
   pandas code stays as the checked reference, and a parity test asserts that
   Spark gives identical Silver `clicks` and Gold `visits` on all 165,474
   clicks.
2. **D3: the ingest Lambda fetches the UCI zip and lands raw CSV split by
   source month.** The Lambda checks the file's MD5, keeps rows for the
   requested months and writes `month=YYYY-MM/clicks.csv` unchanged. Raw data
   stays raw in Bronze, and landing months at different times is what lets the
   job-bookmark behaviour be proven.
3. **D4: one bucket per layer** (Bronze, Silver, Gold) **plus an Athena
   results bucket.** Versioning is a whole-bucket setting and only Bronze
   needs it. Separate buckets also keep access rules simple.
4. **D5: Glue Catalog tables are defined in the template, with Athena
   partition projection.** The schema is reviewed like code. There is no
   crawler bill, and no "repair table" step after each run.
5. **D6: Glue 6.0, G.1X with 2 workers, Flex execution class, a 15-minute
   timeout and the job's own temp directory.** Glue 6.0 is the newest runtime
   and has the lowest price per DPU in the annex; Flex is cheaper for
   non-urgent runs; the timeout caps a runaway bill; and our own temp
   directory (on the Silver bucket) avoids Glue creating a temp bucket of its
   own.
6. **D7: the Glue job writes months with dynamic partition overwrite.** A rerun
   replaces only the months it read. Job bookmarks do not track outputs, so
   this prevents duplicate rows.

## Consequences

- **Spark is used here for exam coverage and learning, not because the data
  volume needs it.** An enterprise team would size the tool to the data:
  165,474 rows would normally be Athena SQL or plain Python. It would write
  each transform once, in the engine it runs on (PySpark on Glue, EMR or
  Databricks, or SQL-first with dbt), with no pandas copy. It would test at
  three levels (local-Spark unit tests in CI, data-quality rules inside the
  pipeline, an integration run in a separate dev account) and deploy through
  CI/CD to dev, stage and prod accounts, adding Lake Formation permissions,
  orchestration and lineage. What matches an enterprise design: immutable raw
  Bronze, date-partitioned Parquet, least-privilege roles per service, IaC
  with reviewed change sets, and Athena over the Catalog. The duplicate
  pandas code is the price of the learning goal.
- **Iceberg is deferred to T1b.** Iceberg format version 3 is not readable by
  Athena, so the T1b design must pick a version Athena can query, or query
  through another engine. T1a uses plain Parquet.
- **Glue 6.0 in Mumbai is inferred, not verified.** It rests on a Price List
  SKU for `ap-south-1`. If the first deploy shows Glue 6.0 is not available
  there, the template's `GlueVersion` parameter (allowed values `6.0` and
  `5.1`) is set to `5.1` and the job is rerun. No code change is expected.
- **A Flex run can start late.** Flex uses spare capacity, so a run may wait
  before it starts. The 15-minute timeout and the window script's wait handle
  this, but the elapsed time of a run is not a stable number.
- **The Glue role's least-privilege set is unproven** until the first run. If
  the job fails on a missing permission, the owner reviews the change and
  redeploys; the role is never widened to `*`.
- **Minimum Glue workers are unverified.** Two are used; whether one would
  work is not checked (`docs/GAPS.md`).
- **The Catalog schema lives in the template.** A column change is a template
  change plus a redeploy, which is deliberate: the guardrail tests compare the
  table columns with the code.
- **Teardown must empty the versioned Bronze bucket, versions included,**
  before the stack can be deleted. The teardown script does this and verifies
  that the stack is gone.

## Alternatives rejected

- **A Glue Python shell job.** Cheaper, but it has no job bookmarks and no
  Spark evidence, so it would not show the exam's main Glue topics.
- **A Spark job that runs pandas inside.** Easier to write, but it proves less
  about Spark: the distributed engine would only be a wrapper around code that
  already exists.
- **A Glue crawler on every run.** Costs money on every run and creates a
  schema no one reviewed; a crawler can also guess wrong types.
- **One lake bucket with layer prefixes.** S3 versioning is a per-bucket
  setting, so Silver and Gold would carry versions they do not need, and one
  bucket policy would have to cover three different access patterns.
