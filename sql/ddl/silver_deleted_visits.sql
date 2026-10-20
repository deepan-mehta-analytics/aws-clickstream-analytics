-- Silver deleted visits: visits removed on request, so later runs skip them.
-- {silver_bucket} is replaced with the real Silver bucket name before running.

-- ── Table and columns ─────────────────────────────────────────────────────
CREATE TABLE clickstream_t1.silver_deleted_visits (         -- Iceberg table in the clickstream_t1 database
  visit_id bigint,                                          -- the deleted visit
  deleted_time timestamp,                                   -- when it was deleted, UTC
  reason string,                                            -- why it was deleted
  bronze_key string                                         -- Bronze file it came from
)                                                           -- end of the column list

-- ── Partition and location ────────────────────────────────────────────────
LOCATION 's3://{silver_bucket}/deleted_visits/'             -- table folder, never the bucket root

-- ── Table properties ──────────────────────────────────────────────────────
TBLPROPERTIES (                                             -- Athena allowed Iceberg properties, exactly these seven
  'table_type'='ICEBERG',                                   -- Iceberg table (format version 2, Athena default)
  'format'='parquet',                                       -- data file format
  'write_compression'='snappy',                             -- data file compression
  'vacuum_max_snapshot_age_seconds'='60',                   -- VACUUM expires snapshots older than 60 seconds
  'vacuum_min_snapshots_to_keep'='1',                       -- VACUUM always keeps the latest snapshot
  'optimize_rewrite_delete_file_threshold'='1',             -- OPTIMIZE rewrites data files that have even one delete file
  'optimize_rewrite_data_file_threshold'='1'                -- OPTIMIZE rewrites any data file
);                                                          -- end of the table definition
