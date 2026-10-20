-- Rows of one visit as they were at an older snapshot (version travel). {snapshot_id} and {visit_id} are filled in by the window script.
SELECT COUNT(*) AS row_count                                    -- rows the old snapshot still holds
FROM "clickstream_t1".silver_clicks FOR VERSION AS OF {snapshot_id}              -- read the table at that snapshot
WHERE visit_id = {visit_id}                                     -- only that visit
