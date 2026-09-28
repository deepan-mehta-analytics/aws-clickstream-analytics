-- Clean clicks in Silver per click month (rejects excluded)
SELECT click_month, COUNT(*) AS clicks        -- month and its clean clicks
FROM silver_clicks                            -- Silver clicks table
GROUP BY click_month                          -- one row per month
ORDER BY click_month                          -- oldest first
