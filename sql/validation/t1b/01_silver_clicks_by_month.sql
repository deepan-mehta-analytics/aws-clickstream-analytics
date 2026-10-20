-- Clean clicks in the Iceberg Silver table per click month
SELECT click_month, COUNT(*) AS clicks  -- month and its clean clicks
FROM "clickstream_t1".silver_clicks     -- Iceberg Silver clicks table
GROUP BY click_month                    -- one row per month
ORDER BY click_month                    -- oldest first
