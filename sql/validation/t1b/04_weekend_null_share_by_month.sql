-- Share of clicks whose weekend_click is NULL per month (1.0 = every click, 0.0 = none)
SELECT click_month,                                                                      -- month
       CAST(SUM(CASE WHEN weekend_click IS NULL THEN 1 ELSE 0 END) AS double)            -- clicks with no value
         / COUNT(*) AS null_share                                                        -- divided by all clicks
FROM "clickstream_t1".silver_clicks                                                                       -- Iceberg Silver clicks table
GROUP BY click_month                                                                     -- one row per month
ORDER BY click_month                                                                     -- oldest first
