# ── Tests: Glue library zip and entry point ───────────────────
import ast                                                              # read the Glue script without importing awsglue
import importlib.util                                                   # load the build script by path
import subprocess                                                       # import from the zip in a clean interpreter
import sys                                                              # this interpreter
import zipfile                                                          # inspect the zip
from pathlib import Path                                                # file paths

REPO = Path(__file__).resolve().parents[1]                              # repo root
spec = importlib.util.spec_from_file_location("build_glue_libs", REPO / "scripts" / "build_glue_libs.py")  # not a package
build_glue_libs = importlib.util.module_from_spec(spec)                 # empty module
spec.loader.exec_module(build_glue_libs)                                # run it


def test_zip_holds_both_packages_and_the_sql(tmp_path):                 # what Glue needs
    names = set(zipfile.ZipFile(build_glue_libs.build_zip(tmp_path / "libs.zip")).namelist())  # zip contents
    assert {"clickstream/enrichment.py", "clickstream_spark/silver.py", "clickstream_spark/storage.py", "clickstream_spark/sql/daily_visits.sql"} <= names  # key files
    assert not any("__pycache__" in name for name in names)             # no compiled caches


def test_summary_sql_loads_from_inside_the_zip(tmp_path):               # the zip path Glue uses
    archive = build_glue_libs.build_zip(tmp_path / "libs.zip")          # build it
    code = f"import sys; sys.path.insert(0, {str(archive)!r}); from clickstream_spark.sql_files import load_summary_sql; print(sorted(load_summary_sql()))"  # import from the zip only
    output = subprocess.run([sys.executable, "-S", "-c", code], capture_output=True, text=True, check=True).stdout  # -S: no site-packages, so the repo copy cannot be used
    assert "daily_visits" in output and "visit_depth_funnel" in output  # read from clickstream_spark/sql/ in the zip


def test_glue_entry_uses_bookmark_context_and_commits_last():           # bookmark wiring
    source = (REPO / "glue" / "build_silver_gold.py").read_text(encoding="utf-8")  # the script
    tree = ast.parse(source)                                            # parse only
    keywords = {kw.arg: kw.value for node in ast.walk(tree) if isinstance(node, ast.Call) for kw in node.keywords}  # every keyword argument
    assert isinstance(keywords.get("transformation_ctx"), ast.Constant) and keywords["transformation_ctx"].value == "bronze_source"  # bookmark key
    lines = {name: node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) for name in [node.func.attr]}  # last line of each method name
    assert lines["commit"] > lines["put_object"]                        # commit only after the report is saved (a failure keeps the bookmark)
