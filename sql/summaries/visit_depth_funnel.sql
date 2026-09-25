-- Browse-depth funnel: visits reaching at least each shop page (not a purchase funnel)
SELECT
    pages.shop_page,                                                   -- shop listing page 1-5
    COUNT(visits.visit_id) AS visits_reaching_page                     -- visits whose deepest page is at least this page
FROM (VALUES (1), (2), (3), (4), (5)) AS pages (shop_page)             -- every page, even if no visit reaches it
LEFT JOIN visits                                                       -- Gold visits table
    ON visits.deepest_page_reached >= pages.shop_page                  -- reached this page or deeper
GROUP BY pages.shop_page                                               -- one row per page
ORDER BY pages.shop_page                                               -- page 1 first
