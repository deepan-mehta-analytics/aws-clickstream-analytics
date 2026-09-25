# ── Full-file reconciliation against the measured stats (data/README.md) ─
from pathlib import Path                                                # file paths

import pandas as pd                                                     # dataframes
import pytest                                                           # test framework

from clickstream.local_run import run_local_pipeline                    # code under test

SOURCE = Path(__file__).resolve().parents[1] / "data" / "e-shop clothing 2008.csv"  # real UCI file location
RECEIVED = pd.Timestamp("2026-09-25 12:00:00", tz="UTC")                # fixed arrival time

pytestmark = [                                                          # applies to every test here
    pytest.mark.full_file,                                              # marker declared in pyproject.toml
    pytest.mark.skipif(not SOURCE.exists(), reason="UCI file not downloaded; see data/README.md"),  # skip without the file
]


@pytest.fixture(scope="module")                                         # run the pipeline once for all checks
def full_run(tmp_path_factory):                                         # shared result
    output = tmp_path_factory.mktemp("full")                            # temp output folder
    report = run_local_pipeline(SOURCE, output, RECEIVED, resend_every=1000)  # resend every 1000th click to exercise dedup
    return report, output                                               # report and folder


def test_counts_match_measured_stats(full_run):                         # reconciliation
    report, _ = full_run                                                # unpack
    assert report["source_rows"] == 165_474                             # measured rows
    assert report["duplicates_removed"] == 166                          # ceil(165,474 / 1000) resends removed
    assert report["rejected_rows"] == 0                                 # clean real data passes every hard rule
    assert report["silver_clicks"] == 165_474                           # one row per real click
    assert report["visits"] == 24_026                                   # measured sessions
    assert report["one_click_visits"] == 5_042                          # measured bounces


def test_known_category_mismatch_is_a18_only(full_run):                 # reported finding
    report, _ = full_run                                                # unpack
    assert [finding["product_code"] for finding in report["category_mismatches"]] == ["A18"]  # exactly one, A18


def test_funnel_and_dates_match(full_run):                              # summaries
    _, output = full_run                                                # unpack
    funnel = pd.read_parquet(output / "gold" / "summaries" / "visit_depth_funnel.parquet")  # funnel summary
    assert funnel["visits_reaching_page"].tolist() == [24_026, 14_504, 9_125, 4_779, 1_631]  # measured funnel
    daily = pd.read_parquet(output / "gold" / "summaries" / "daily_visits.parquet")  # daily summary
    assert len(daily) == 135                                            # measured distinct dates
