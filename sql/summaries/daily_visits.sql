-- One row per date: visits, clicks and bounce rate (Gold visits)
SELECT
    visit_date,                                                        -- calendar date of the visits
    COUNT(*) AS visits,                                                -- visits that day
    SUM(clicks_in_visit) AS clicks,                                    -- clicks that day
    ROUND(AVG(CASE WHEN bounced THEN 1.0 ELSE 0.0 END), 4) AS bounce_rate  -- share of one-click visits
FROM visits                                                            -- Gold visits table
GROUP BY visit_date                                                    -- one row per date
ORDER BY visit_date                                                    -- oldest first
