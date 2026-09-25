-- Browse-depth funnel: visits reaching at least each shop page (not a purchase funnel)
-- Pages are listed with UNION ALL (no row-constructor list), so the same SQL runs in DuckDB, Athena and Redshift
SELECT
    pages.shop_page,                                                   -- shop listing page 1-5
    COUNT(visits.visit_id) AS visits_reaching_page                     -- visits whose deepest page is at least this page
FROM (                                                                 -- every page, even if no visit reaches it
    SELECT 1 AS shop_page                                              -- page 1
    UNION ALL SELECT 2                                                 -- page 2
    UNION ALL SELECT 3                                                 -- page 3
    UNION ALL SELECT 4                                                 -- page 4
    UNION ALL SELECT 5                                                 -- page 5
) AS pages                                                             -- the page list
LEFT JOIN visits                                                       -- Gold visits table
    ON visits.deepest_page_reached >= pages.shop_page                  -- reached this page or deeper
GROUP BY pages.shop_page                                               -- one row per page
ORDER BY pages.shop_page                                               -- page 1 first
