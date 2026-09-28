-- Rows landed in Bronze per source month (raw CSV, header skipped)
SELECT source_month, COUNT(*) AS row_count   -- month and its rows
FROM bronze_source_clicks                     -- raw table (partition projection)
GROUP BY source_month                         -- one row per month
ORDER BY source_month                         -- oldest first
