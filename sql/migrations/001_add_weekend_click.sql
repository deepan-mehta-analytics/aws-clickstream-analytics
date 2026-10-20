-- Migration 001: add weekend_click (true when click_date is a Saturday or Sunday) to Silver clicks.
ALTER TABLE clickstream_t1.silver_clicks ADD COLUMNS (weekend_click boolean)  -- new column, existing rows read NULL until rewritten
