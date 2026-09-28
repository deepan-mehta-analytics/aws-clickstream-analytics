"""Build build/glue/clickstream_libs.zip for the Glue job's --extra-py-files (tier T1a)."""  # module docstring

import argparse                                                         # command-line options
import zipfile                                                          # write the zip
from pathlib import Path                                                # file paths

REPO_ROOT = Path(__file__).resolve().parents[1]                         # repository root
PACKAGES = ["clickstream", "clickstream_spark"]                         # pandas reference (used by enrichment) + Spark code
SQL_DIR = REPO_ROOT / "sql" / "summaries"                               # dashboard SQL
DEFAULT_OUTPUT = REPO_ROOT / "build" / "glue" / "clickstream_libs.zip"  # gitignored output


def build_zip(output: Path = DEFAULT_OUTPUT) -> Path:                   # create the zip
    output = Path(output)                                               # accept str or Path
    output.parent.mkdir(parents=True, exist_ok=True)                    # make the folder
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:  # new zip
        for package in PACKAGES:                                        # each package
            for path in sorted((REPO_ROOT / "src" / package).rglob("*.py")):  # source files only (no caches)
                archive.write(path, path.relative_to(REPO_ROOT / "src").as_posix())  # e.g. clickstream_spark/silver.py
        for path in sorted(SQL_DIR.glob("*.sql")):                      # summary SQL
            archive.write(path, f"clickstream_spark/sql/{path.name}")   # read by sql_files.load_summary_sql in Glue
    return output                                                       # where it was written


def main() -> None:                                                     # command-line entry
    parser = argparse.ArgumentParser(description="Build the Glue library zip.")  # description
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)  # optional path
    print(build_zip(parser.parse_args().output))                        # print the path


if __name__ == "__main__":                                              # run as a script
    main()                                                              # start
