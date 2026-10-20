-- Table properties of one table; the result should include the Iceberg format version (expected 2). {table} is filled in by the window script.
-- Fallback if SHOW TBLPROPERTIES does not report it: read format-version from the table's current metadata.json in S3.
SHOW TBLPROPERTIES "clickstream_t1"."{table}"  -- all properties of that table
