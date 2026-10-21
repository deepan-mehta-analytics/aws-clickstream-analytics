-- Latest snapshot ID of one Silver table (metadata table $snapshots). {table} is filled in by the window script.
SELECT snapshot_id, committed_at, operation      -- snapshot number, when, what kind of commit
FROM "clickstream_t1"."{table}$snapshots"        -- Iceberg metadata table of that table
ORDER BY committed_at DESC                       -- newest first
LIMIT 1                                          -- only the latest
