-- Bounce rate by the product a visit started on
SELECT
    first_product_viewed AS product_code,                              -- entry product
    COUNT(*) AS visits_started,                                        -- visits that started here
    SUM(CASE WHEN bounced THEN 1 ELSE 0 END) AS visits_bounced,        -- of those, one-click visits
    ROUND(SUM(CASE WHEN bounced THEN 1.0 ELSE 0.0 END) / COUNT(*), 4) AS bounce_rate  -- share that bounced
FROM visits                                                            -- Gold visits table
GROUP BY first_product_viewed                                          -- one row per entry product
ORDER BY visits_started DESC, product_code                             -- busiest first, then by code
