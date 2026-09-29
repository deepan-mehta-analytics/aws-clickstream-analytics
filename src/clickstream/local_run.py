"""Run the whole pipeline locally: UCI CSV -> Bronze -> Silver -> Gold -> summaries (tier T0, no AWS)."""  # module docstring

import argparse                                                         # command-line options
import json                                                             # write the report
import shutil                                                           # clear old output
from pathlib import Path                                                # file paths

import pandas as pd                                                     # dataframes

from clickstream.bronze import build_bronze                             # Bronze step
from clickstream.enrichment import DEFAULT_SEED, add_synthetic_fields   # enrichment step
from clickstream.gold import (                                          # Gold step
    build_calendar_days, build_countries, build_devices, build_gold_clicks, build_products, build_visits, category_mismatches,
)
from clickstream.quality import build_quality_report                   # report
from clickstream.silver import build_silver                             # Silver step
from clickstream.source_file import read_source_clicks                  # source reader
from clickstream.summaries import run_summaries                         # summaries


def write_table(frame: pd.DataFrame, folder: Path, partition_column: str | None = None) -> None:  # write one table as Parquet
    if folder.exists():                                                 # old output from a previous run
        shutil.rmtree(folder)                                           # replace, never append
    folder.mkdir(parents=True)                                          # create the table folder
    if partition_column and not frame.empty:                            # partitioned tables (monthly)
        frame.to_parquet(folder, partition_cols=[partition_column], index=False, coerce_timestamps="us", allow_truncated_timestamps=True)  # microseconds: what Athena and Spark read natively
    else:                                                               # small or empty tables
        frame.to_parquet(folder / f"{folder.name}.parquet", index=False, coerce_timestamps="us", allow_truncated_timestamps=True)  # microseconds: what Athena and Spark read natively


def run_local_pipeline(source_csv: Path, output_dir: Path, received_time: pd.Timestamp, seed: int = DEFAULT_SEED, resend_every: int = 0) -> dict:  # end to end
    # ── Build every layer in memory ───────────────────────────
    source = read_source_clicks(source_csv)                             # real clicks, plain names
    bronze = build_bronze(add_synthetic_fields(source, seed), received_time, resend_every)  # Bronze
    silver = build_silver(bronze, run_time=received_time)               # Silver + rejects
    products = build_products(silver.clicks)                            # Gold reference: products
    visits = build_visits(silver.clicks)                                # Gold event table: visits
    countries = build_countries()                                       # Gold reference: countries
    summaries = run_summaries({"visits": visits, "countries": countries})  # dashboard summaries

    # ── Write Parquet, layer by layer ─────────────────────────
    output_dir = Path(output_dir)                                       # accept str or Path
    write_table(bronze, output_dir / "bronze" / "clicks_received")      # Bronze, single file locally
    write_table(silver.clicks, output_dir / "silver" / "clicks", "click_month")  # Silver by month
    write_table(silver.rejected, output_dir / "silver" / "clicks_rejected")  # rejects
    write_table(products, output_dir / "gold" / "products")             # reference table
    write_table(countries, output_dir / "gold" / "countries")           # reference table
    write_table(build_calendar_days(silver.clicks), output_dir / "gold" / "calendar_days")  # reference table
    write_table(build_devices(), output_dir / "gold" / "devices")       # reference table
    write_table(build_gold_clicks(silver.clicks), output_dir / "gold" / "clicks", "click_month")  # event table by month
    write_table(visits, output_dir / "gold" / "visits", "visit_month")  # event table by month
    summaries_folder = output_dir / "gold" / "summaries"                # summaries folder
    if summaries_folder.exists():                                       # old summaries
        shutil.rmtree(summaries_folder)                                 # replace, never append
    summaries_folder.mkdir(parents=True)                                # create it
    for name, frame in summaries.items():                               # each summary
        frame.to_parquet(summaries_folder / f"{name}.parquet", index=False)  # one file each

    # ── Quality report ────────────────────────────────────────
    report = build_quality_report(len(source), len(bronze), silver, visits, category_mismatches(silver.clicks, products))  # counts and findings
    (output_dir / "quality_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")  # save next to the data
    return json.loads(json.dumps(report, default=str))                  # same JSON-safe values as on disk


def main() -> None:                                                     # command-line entry point
    parser = argparse.ArgumentParser(description="Run the clickstream pipeline locally (no AWS).")  # CLI description
    parser.add_argument("--source", required=True, type=Path, help="Path to 'e-shop clothing 2008.csv'")  # input file
    parser.add_argument("--output", required=True, type=Path, help="Output folder, e.g. output/local")  # output folder
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Seed for synthetic fields")  # reproducibility
    parser.add_argument("--resend-every", type=int, default=0, help="Resend every Nth click to exercise deduplication")  # dedup demo
    arguments = parser.parse_args()                                     # read the options
    received_time = pd.Timestamp.now(tz="UTC")                          # real arrival time for this run
    report = run_local_pipeline(arguments.source, arguments.output, received_time, arguments.seed, arguments.resend_every)  # run
    print(json.dumps({key: value for key, value in report.items() if key != "category_mismatches"}, indent=2))  # counts to the console
    print(f"category_mismatches: {len(report['category_mismatches'])}")  # findings count


if __name__ == "__main__":                                              # run as `python -m clickstream.local_run`
    main()                                                              # start
