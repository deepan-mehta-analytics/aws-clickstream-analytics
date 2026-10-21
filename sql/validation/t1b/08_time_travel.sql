-- Rows of one visit in one Silver table as they were at an older snapshot (version travel). {table}, {snapshot_id} and {visit_id} are filled in by the window script.
SELECT COUNT(*) AS row_count                                         -- rows the old snapshot still holds
FROM "clickstream_t1"."{table}" FOR VERSION AS OF {snapshot_id}      -- read that table at that snapshot
WHERE visit_id = {visit_id}                                          -- only that visit
