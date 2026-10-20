-- Rows of one visit in every table that can hold it. {visit_id} is filled in by the window script (never committed).
SELECT 'silver_clicks' AS table_name, COUNT(*) AS row_count               -- clean clicks of the visit
FROM "clickstream_t1".silver_clicks WHERE visit_id = {visit_id}           -- only that visit
UNION ALL                                                                 -- stack the next table underneath
SELECT 'silver_clicks_rejected', COUNT(*)                                 -- rejected rows of the visit
FROM "clickstream_t1".silver_clicks_rejected WHERE visit_id = {visit_id}  -- only that visit
UNION ALL                                                                 -- stack the next table underneath
SELECT 'gold_visits', COUNT(*)                                            -- Gold row of the visit
FROM "clickstream_t1".gold_visits WHERE visit_id = {visit_id}             -- only that visit
