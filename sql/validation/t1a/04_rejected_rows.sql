-- Total rows Silver rejected across the whole window (one scope: "all")
SELECT 'all' AS scope, COUNT(*) AS rejected   -- fixed label and the total count
FROM silver_clicks_rejected                   -- Silver rejects table
