-- Visits in Gold per visit month (Gold stays plain Parquet)
SELECT visit_month, COUNT(*) AS visits        -- month and its visits
FROM gold_visits                              -- Gold visits table
GROUP BY visit_month                          -- one row per month
ORDER BY visit_month                          -- oldest first
