# sql/

`summaries/` holds the four dashboard summaries as plain SQL, written to run
unchanged in DuckDB (local twin) and, in later tiers, in Athena and Redshift:
`daily_visits`, `visit_depth_funnel`, `bounce_rate_by_product`,
`visits_by_country_and_device`. They read the Gold `visits` and `countries` tables.

`ddl/` holds the three Iceberg Silver tables as Athena `CREATE TABLE` statements
(`silver_clicks`, `silver_clicks_rejected`, `silver_deleted_visits`). `{silver_bucket}`
in each `LOCATION` is replaced with the real bucket name before running. Iceberg
format version 2 only. `migrations/` holds numbered schema changes, applied in name
order: `001_add_weekend_click.sql` adds `weekend_click` to `silver_clicks`. The local
Spark tests read the same files through `clickstream_spark.sql_files`.
