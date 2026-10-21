-- Silver rejected clicks: rows that failed a hard rule, with the reason.
-- {silver_bucket} is replaced with the real Silver bucket name before running.

-- ── Table and columns ─────────────────────────────────────────────────────
CREATE TABLE clickstream_t1.silver_clicks_rejected (        -- Iceberg table in the clickstream_t1 database
  year bigint,                                              -- year
  month bigint,                                             -- month
  day bigint,                                               -- day
  click_number_in_visit bigint,                             -- source order
  country_code bigint,                                      -- source country
  visit_id bigint,                                          -- source session ID
  category_code bigint,                                     -- page 1
  product_code string,                                      -- page 2
  colour_code bigint,                                       -- colour
  photo_position_code bigint,                               -- location
  photo_angle_code bigint,                                  -- model photography
  price_usd bigint,                                         -- price
  price_above_category_average_code bigint,                 -- price 2
  page_number_in_shop bigint,                               -- page
  click_id string,                                          -- uci553-<visit>-<click>
  click_time_synthetic timestamp,                           -- synthetic time, UTC
  device_type_synthetic string,                             -- synthetic device
  received_time timestamp,                                  -- arrival time, UTC
  data_source string,                                       -- uci553
  rejection_reason string,                                  -- why the click failed
  rejected_time timestamp,                                  -- when this run rejected it
  source_month string                                       -- partition: the Bronze file month
)                                                           -- end of the column list

-- ── Partition and location ────────────────────────────────────────────────
PARTITIONED BY (source_month)                               -- partition column (named without a type)
LOCATION 's3://{silver_bucket}/clicks_rejected/'            -- table folder, never the bucket root

-- ── Table properties ──────────────────────────────────────────────────────
TBLPROPERTIES (                                             -- Athena allowed Iceberg properties, exactly these eight
  'table_type'='ICEBERG',                                   -- Iceberg table (format version 2, Athena default)
  'format'='parquet',                                       -- data file format
  'write_compression'='snappy',                             -- data file compression
  'vacuum_max_snapshot_age_seconds'='60',                   -- VACUUM expires snapshots older than 60 seconds
  'vacuum_min_snapshots_to_keep'='1',                       -- VACUUM always keeps the latest snapshot
  'optimize_rewrite_delete_file_threshold'='1',             -- OPTIMIZE rewrites data files that have even one delete file
  'optimize_rewrite_data_file_threshold'='1',               -- OPTIMIZE rewrites any data file
  'write_data_path_enabled'='true'                          -- Athena writes write.data.path, not the old write.object-storage.path that Iceberg 1.9+ refuses
);                                                          -- end of the table definition
