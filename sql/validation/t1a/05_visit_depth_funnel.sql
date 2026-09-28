-- Browse-depth funnel from the Gold summary table (not the local-twin SQL: no UNION ALL needed, the table already exists)
SELECT shop_page, visits_reaching_page        -- shop listing page and visits reaching it
FROM gold_summary_visit_depth_funnel          -- pre-built Gold summary table
ORDER BY shop_page                            -- page 1 first
