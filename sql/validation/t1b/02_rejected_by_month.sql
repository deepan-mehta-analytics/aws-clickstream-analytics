-- Rejected rows in the Iceberg rejects table per source month (the real data has none)
SELECT source_month, COUNT(*) AS rejected     -- month and its rejected rows
FROM silver_clicks_rejected                   -- Iceberg Silver rejects table
GROUP BY source_month                         -- one row per month
ORDER BY source_month                         -- oldest first
