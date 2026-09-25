# sql/

`summaries/` holds the four dashboard summaries as plain SQL, written to run
unchanged in DuckDB (local twin) and, in later tiers, in Athena and Redshift:
`daily_visits`, `visit_depth_funnel`, `bounce_rate_by_product`,
`visits_by_country_and_device`. They read the Gold `visits` and `countries` tables.
