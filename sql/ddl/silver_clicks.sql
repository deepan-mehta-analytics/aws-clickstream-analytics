-- Silver clicks: one row per clean click.
-- {silver_bucket} is replaced with the real Silver bucket name before running.

-- ── Table and columns ─────────────────────────────────────────────────────
CREATE TABLE clickstream_t1.silver_clicks (                 -- Iceberg table in the clickstream_t1 database
  click_id string,                                          -- uci553-<visit>-<click>
  visit_id bigint,                                          -- visit
  click_number_in_visit bigint,                             -- position in the visit
  click_date date,                                          -- real date
  click_time_synthetic timestamp,                           -- synthetic time, UTC
  click_hour_shop_time_synthetic bigint,                    -- shop-local hour 0-23
  product_code string,                                      -- product
  category string,                                          -- decoded category
  colour string,                                            -- decoded colour
  price_usd bigint,                                         -- price
  priced_above_category_average boolean,                    -- price flag
  page_number_in_shop bigint,                               -- listing page
  photo_position_on_page string,                            -- placement
  photo_angle string,                                       -- angle
  country_code bigint,                                      -- country
  device_type_synthetic string,                             -- synthetic device
  received_time timestamp,                                  -- arrival time, UTC
  seconds_late bigint,                                      -- seconds between click and arrival
  click_month string                                        -- partition: 2008-04 ... 2008-08
)                                                           -- end of the column list

-- ── Partition and location ────────────────────────────────────────────────
PARTITIONED BY (click_month)                                -- partition column (named without a type)
LOCATION 's3://{silver_bucket}/clicks/'                     -- table folder, never the bucket root

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
