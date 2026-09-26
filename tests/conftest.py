# ── Shared test helpers: hand-made source rows in plain names ─
import os                                                               # environment variables
import re                                                               # parse "java -version"
import shutil                                                           # find java on PATH
import subprocess                                                       # run "java -version"
import sys                                                              # this Python, for the Spark workers

import pandas as pd                                                     # dataframes
import pytest                                                           # fixtures and skips

from clickstream.source_file import PLAIN_COLUMNS                       # the plain column order


def source_row(visit_id, click_number, product_code="A13", category_code=1, page=1, country=29, day=1, month=4):  # one hand-made click
    return {                                                            # dict keyed by plain column names
        "year": 2008,                                                   # all real data is from 2008
        "month": month,                                                 # month of the click
        "day": day,                                                     # day of the click
        "click_number_in_visit": click_number,                          # position in the visit
        "country_code": country,                                        # 29 = Poland
        "visit_id": visit_id,                                           # which visit
        "category_code": category_code,                                 # 1 = trousers
        "product_code": product_code,                                   # product clicked
        "colour_code": 1,                                               # 1 = beige
        "photo_position_code": 5,                                       # 5 = bottom in the middle
        "photo_angle_code": 1,                                          # 1 = front
        "price_usd": 28,                                                # price in dollars
        "price_above_category_average_code": 2,                         # 2 = no
        "page_number_in_shop": page,                                    # listing page 1-5
    }


def make_source(rows):                                                  # build a source-shaped dataframe
    return pd.DataFrame(rows, columns=PLAIN_COLUMNS)                    # same columns as read_source_clicks returns


# ── Local Spark session for the Glue job tests ────────────────
SUPPORTED_JAVA = {17, 21}                                               # Spark 4.1.1 runs on Java 17/21 (spark.apache.org/docs/4.1.1)


def _java_home():                                                       # JDK to use for Spark
    return os.environ.get("SPARK_JAVA_HOME") or os.environ.get("JAVA_HOME")  # a dedicated JDK wins over the default one


def _java_major(java_home):                                             # major version of that JDK, or None
    executable = os.path.join(java_home, "bin", "java") if java_home else shutil.which("java")  # java binary
    if not executable:                                                  # no Java at all
        return None                                                     # caller skips
    output = subprocess.run([executable, "-version"], capture_output=True, text=True).stderr  # java prints its version on stderr
    match = re.search(r'version "(\d+)', output)                        # e.g. version "21.0.4"
    return int(match.group(1)) if match else None                       # 21, or None if unreadable


@pytest.fixture(scope="session")                                        # one Spark session for the whole test run
def spark():                                                            # local Spark with the Glue settings
    pytest.importorskip("pyspark", reason="install the spark extra: pip install -e .[dev,spark]")  # optional dependency
    java_home = _java_home()                                            # chosen JDK
    major = _java_major(java_home)                                      # its version
    if major not in SUPPORTED_JAVA:                                     # Java 25 and others are not supported by Spark 4.1
        pytest.skip(f"Spark 4.1 needs Java 17 or 21 (found {major}); set SPARK_JAVA_HOME to a JDK 21")  # clear reason
    if java_home:                                                       # point Spark at that JDK
        os.environ["JAVA_HOME"] = java_home                             # used by the Spark launcher
    os.environ["PYSPARK_PYTHON"] = sys.executable                       # workers use this venv's Python
    os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable                # driver too
    from pyspark.sql import SparkSession                                # import only after the checks

    from clickstream_spark.settings import SPARK_SETTINGS               # shared settings
    builder = (SparkSession.builder.master("local[2]").appName("clickstream-tests")  # two local cores
               .config("spark.sql.shuffle.partitions", "4").config("spark.ui.enabled", "false")  # small shuffles, no web UI
               .config("spark.sql.execution.arrow.pyspark.enabled", "true"))  # toPandas via Arrow: timestamps in the UTC session zone
    for key, value in SPARK_SETTINGS.items():                           # same settings as Glue
        builder = builder.config(key, value)                            # apply each
    session = builder.getOrCreate()                                     # start Spark
    yield session                                                       # hand it to the tests
    session.stop()                                                      # shut down at the end
