-- Latest snapshot ID of Silver clicks (metadata table $snapshots)
SELECT snapshot_id, committed_at, operation      -- snapshot number, when, what kind of commit
FROM "clickstream_t1"."silver_clicks$snapshots"  -- Iceberg metadata table
ORDER BY committed_at DESC                       -- newest first
LIMIT 1                                          -- only the latest
