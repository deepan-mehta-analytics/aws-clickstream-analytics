-- Current data files of one month (metadata table $files). {month} is like 2008-04.
SELECT file_path, file_size_in_bytes, record_count              -- file, size, rows inside
FROM "clickstream_t1"."silver_clicks$files"                     -- Iceberg metadata table
WHERE partition.click_month = '{month}'                         -- only that month's partition
ORDER BY file_path                                              -- stable order for comparing lists
