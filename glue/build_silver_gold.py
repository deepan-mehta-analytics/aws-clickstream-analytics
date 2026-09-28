"""AWS Glue job (tier T1a): new Bronze files -> Silver and Gold Parquet, with job bookmarks."""  # module docstring

# ── Imports (awsglue exists only inside Glue) ─────────────────
import json                                                             # quality report
import sys                                                              # job arguments
from datetime import datetime, timezone                                 # run time

import boto3                                                            # save the report (boto3 ships with Glue 6.0)
from awsglue.context import GlueContext                                 # Glue wrapper around Spark
from awsglue.job import Job                                             # bookmarks: init and commit
from awsglue.utils import getResolvedOptions                            # read --arguments
from pyspark.context import SparkContext                                # Spark entry

from clickstream_spark.settings import SPARK_SETTINGS                   # same settings as the tests
from clickstream_spark.sql_files import load_summary_sql                # summary SQL from the zip
from clickstream_spark.storage import LakePaths, run_increment          # the work

# ── Arguments and session ─────────────────────────────────────
args = getResolvedOptions(sys.argv, ["JOB_NAME", "JOB_RUN_ID", "bronze_path", "silver_path", "gold_path", "reports_bucket"])  # full names (Glue 6.0: no prefix matching)
glue = GlueContext(SparkContext.getOrCreate())                          # Glue context
spark = glue.spark_session                                              # Spark session
for key, value in SPARK_SETTINGS.items():                               # UTC, ANSI, dynamic overwrite...
    spark.conf.set(key, value)                                          # apply each
job = Job(glue)                                                         # bookmark holder
job.init(args["JOB_NAME"], args)                                        # loads the bookmark state
run_time = datetime.now(timezone.utc)                                   # this run's time (arrival and rejection time)

# ── Read only new Bronze files (job bookmark) ─────────────────
bronze = glue.create_dynamic_frame.from_options(                        # S3 CSV source
    connection_type="s3",                                               # Amazon S3
    connection_options={"paths": [args["bronze_path"]], "recurse": True},  # every source_month=... folder
    format="csv",                                                       # raw UCI rows
    format_options={"withHeader": True, "separator": ";"},              # header row, semicolons
    transformation_ctx="bronze_source",                                 # bookmark key: files seen by this source are skipped next time
)

# ── Build, write, report ──────────────────────────────────────
report = run_increment(spark, bronze.toDF(), LakePaths(args["silver_path"], args["gold_path"]), run_time, load_summary_sql())  # the work
report.update({"job_run_id": args["JOB_RUN_ID"], "run_time": run_time.isoformat()})  # identify the run
body = json.dumps(report, indent=2, default=str)                        # JSON text
print(body)                                                             # to CloudWatch Logs
boto3.client("s3").put_object(Bucket=args["reports_bucket"], Key=f"_reports/{run_time:%Y%m%dT%H%M%SZ}.json", Body=body.encode("utf-8"), ContentType="application/json", ServerSideEncryption="AES256")  # saved for the evidence
job.commit()                                                            # only now does the bookmark move forward
