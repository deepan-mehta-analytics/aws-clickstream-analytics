# ADR-0006: Tier T1b Iceberg Silver (Athena-created v2 tables, erasure across all layers)

- **Status:** Proposed (2026-10-20)
- **Deciders:** project owner
- **Related:** [ADR-0005](0005-t1-batch-lake-design.md) (T1a batch lake);
  [ADR-0004](0004-iac-sam-cloudformation.md) (SAM stack, owner-run deploys);
  [ADR-0003](0003-data-model.md) (data model); `docs/GAPS.md`;
  `infra/t1-lake/template.yaml`

## Context

Tier T1a proved the batch lake on AWS with plain Parquet (2026-10-19).
ADR-0005 deferred Iceberg to T1b because Athena cannot read Iceberg format
version 3. T1b turns Silver into Apache Iceberg tables and proves three exam
skills on real AWS: open table formats (2.1.7), schema change without
rewriting data (2.4.2) and deleting data for legal or business reasons
(2.3.5). The deletion also exercises Bronze's S3 versioning (2.3.4), which
T1a only configured.

Facts that shaped the choices (AWS docs, read 2026-10-20):

- Glue 6.0 creates Iceberg **v2** tables by default and ships Iceberg 1.11.0.
  Tables set to `'format-version'='3'` cannot be read by Athena, and a v2 to
  v3 upgrade cannot be undone.
- Athena's `CREATE TABLE` creates **only v2** Iceberg tables.
- Athena's Iceberg `DELETE` is merge-on-read: it writes position delete files
  and leaves the data file in place. `OPTIMIZE` rewrites files; `VACUUM`
  expires snapshots (default retention 5 days) and removes unreachable files,
  and it quietly removes nothing if the caller lacks `s3:DeleteObject`.
- Athena's `OPTIMIZE` skips a data file with fewer than 2 delete files and a
  partition with fewer than 5 data files, unless the table properties lower
  those thresholds.
- The CloudFormation Iceberg table input can only create a table.
- Deleting a Glue database removes its tables asynchronously.

## Decision

1. **Both Silver tables (`silver_clicks`, `silver_clicks_rejected`) become
   Iceberg v2; Gold stays Parquet.** A rejected visit's rows live only in
   the rejects table, so the deletion must reach both. The real file has no
   rejected rows, so the rejects path is proven by a local test with a
   made-up rejected visit; on AWS its `DELETE` runs and affects 0 rows.
2. **Athena creates the tables** from reviewed SQL files (`sql/ddl/`) during
   the window; the Silver table resources leave the template, and the Glue
   database stays in it. Athena can only create v2, which makes the
   wrong version impossible at creation. A repo test and a pre-write check in
   the job add two more guards against v3.
3. **The job writes with Iceberg dynamic partition overwrite** through the
   Glue Data Catalog. It keeps T1a's identity partitions by month and T1a's
   rerun safety.
4. **Erasure covers every layer.** Athena `DELETE` on Silver, then `OPTIMIZE`
   and `VACUUM`, with table properties set so both act on a small table and
   time travel to pre-delete snapshots ends. The Bronze month file is
   rewritten without the visits and its previous version deleted by version
   ID. The job bookmark then reprocesses that month and rebuilds Gold. A
   deleted-visits table (`silver_deleted_visits`) is filtered by every job
   run, so reprocessing cannot bring a deleted visit back.
5. **Schema change is a reviewed migration** (`ALTER TABLE … ADD COLUMNS`)
   applied between two job runs. The job computes the new column but writes
   only the columns the table currently has.

## Consequences

- **The Iceberg schema lives in the table's metadata, not in the template.**
  The SQL files and a repo test that compares them with the code take over
  the review role that the template tests had for Parquet tables.
- **Bronze is no longer strictly immutable.** A legal erasure is the one
  documented exception, recorded in the deleted-visits table. An enterprise
  team at scale would rather keep personal data out of raw storage or use
  crypto-shredding (a per-person encryption key that is deleted on request).
- **The deleted-visits table keeps the visit IDs** that were erased. That is
  the minimum needed to keep them erased, and it is standard suppression-list
  practice.
- **Teardown drops the Iceberg tables in Athena first** (this also deletes
  their data), because the database delete would only remove them
  asynchronously.
- **Two risks are checked during the window rather than assumed:** that
  Athena reads v2 tables written by Glue 6.0's newer Iceberg library, and
  that the bookmark reprocesses a rewritten Bronze object. The window script
  stops at either failure, and a bookmark reset is the documented fallback.
- **Cost:** one more window, estimated at no more than ₹6 (T1a measured about
  ₹3.33).

## Alternatives rejected

- **Iceberg tables defined in CloudFormation.** Create-only; the template's
  schema goes stale after the first `ALTER TABLE`, and a later stack update
  could try to replace the table.
- **Spark creates the tables in the Glue job.** It needs create rights, and
  a single catalog setting (`table-default.format-version=3`) would produce
  tables Athena cannot read.
- **Hidden partitioning (`month(click_date)`).** The better design for a new
  table, but it would change every query and test at once for no gain at
  165,474 rows.
- **`MERGE INTO` for every run.** It suits row-level change feeds; our unit
  of change is a whole month.
- **Automatic schema merging on write.** A code bug could silently add a
  column to a shared table.
- **Deleting from Silver only, with Gold and Bronze documented.** Honest,
  but it leaves the visit in two layers and shows less.
