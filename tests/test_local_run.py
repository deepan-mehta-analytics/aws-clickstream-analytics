# ── Tests: end-to-end local run ───────────────────────────────
import json                                                             # read the report

import pandas as pd                                                     # dataframes

from clickstream.local_run import run_local_pipeline                    # code under test

UCI_HEADER = "year;month;day;order;country;session ID;page 1 (main category);page 2 (clothing model);colour;location;model photography;price;price 2;page"  # real header
RECEIVED = pd.Timestamp("2026-09-25 12:00:00", tz="UTC")                # fixed arrival time


def write_csv(path, lines):                                             # helper: write a UCI-shaped file
    path.write_text(UCI_HEADER + "\n" + "".join(line + "\n" for line in lines))  # header + rows
    return path                                                         # for chaining


def test_writes_every_layer_and_report(tmp_path):                       # happy path
    source = write_csv(tmp_path / "in.csv", ["2008;4;1;1;29;1;1;A13;1;5;1;28;2;1", "2008;4;1;2;29;1;1;A16;1;6;1;33;2;2", "2008;5;2;1;20;2;4;P1;2;1;2;40;1;1"])  # 3 clicks, 2 visits
    report = run_local_pipeline(source, tmp_path / "out", RECEIVED)     # run
    out = tmp_path / "out"                                              # output root
    assert (out / "bronze" / "clicks_received" / "clicks_received.parquet").exists()  # Bronze written
    assert (out / "silver" / "clicks" / "click_month=2008-04").is_dir()  # Silver partitioned by month
    assert (out / "gold" / "visits" / "visit_month=2008-05").is_dir()   # Gold visits partitioned by month
    assert (out / "gold" / "summaries" / "visit_depth_funnel.parquet").exists()  # summaries written
    saved = json.loads((out / "quality_report.json").read_text())       # report on disk
    assert saved == report                                              # same as returned
    assert report["silver_clicks"] == 3 and report["visits"] == 2       # counts
    assert report["one_click_visits"] == 1                              # visit 2 bounced


def test_empty_source_completes_with_zero_counts(tmp_path):             # Review Focus 4
    report = run_local_pipeline(write_csv(tmp_path / "empty.csv", []), tmp_path / "out", RECEIVED)  # header only
    assert report["source_rows"] == 0 and report["silver_clicks"] == 0 and report["visits"] == 0  # all zero
    assert (tmp_path / "out" / "quality_report.json").exists()          # report still written


def test_rerun_replaces_output_instead_of_appending(tmp_path):         # idempotent output
    source = write_csv(tmp_path / "in.csv", ["2008;4;1;1;29;1;1;A13;1;5;1;28;2;1"])  # one click
    run_local_pipeline(source, tmp_path / "out", RECEIVED)              # first run
    run_local_pipeline(source, tmp_path / "out", RECEIVED)              # second run
    clicks = pd.read_parquet(tmp_path / "out" / "gold" / "clicks")      # read back all partitions
    assert len(clicks) == 1                                             # not duplicated


def test_parquet_timestamps_are_microseconds(tmp_path):                 # T1-prep: Athena-friendly timestamp unit
    import pyarrow.parquet as pq                                        # read the schema
    from clickstream.local_run import write_table                       # code under test
    frame = pd.DataFrame({"t": pd.to_datetime(["2008-04-01 10:00:00"]).tz_localize("UTC")})  # one timestamp
    write_table(frame, tmp_path / "table")                              # write it
    unit = pq.read_schema(tmp_path / "table" / "table.parquet").field("t").type.unit  # stored unit
    assert unit == "us"                                                 # microseconds, not nanoseconds
