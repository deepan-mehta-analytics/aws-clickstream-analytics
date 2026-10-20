# ── Tests: tiers T1a/T1b template specifics and its link to the code ─
import ast                                                              # read the Glue script's argument list
from pathlib import Path                                                # file paths

import pytest                                                           # skip pyspark-only checks when it is absent

from infra_rules import load_template                                   # CloudFormation-aware YAML loader

REPO = Path(__file__).resolve().parents[1]                              # repo root
TEMPLATE = load_template(REPO / "infra" / "t1-lake" / "template.yaml")  # parsed template
RESOURCES = TEMPLATE["Resources"]                                       # its resources


def of_type(kind):                                                      # resources of one type
    return {name: body for name, body in RESOURCES.items() if body["Type"] == kind}  # name -> body


def table(name):                                                        # a catalog table by its Athena name
    return next(body["Properties"]["TableInput"] for body in of_type("AWS::Glue::Table").values() if body["Properties"]["TableInput"]["Name"] == name)  # its TableInput


def _sub_text(value):                                                   # raw !Sub text, or a plain string
    text = value.get("Fn::Sub") if isinstance(value, dict) else value    # !Sub text or a plain string
    return text[0] if isinstance(text, list) else text                  # list form: first item is the text


def _ddl_names(schema: str) -> list[str]:                               # column names from a Spark DDL-format schema string
    return [part.strip().split(" ", 1)[0] for part in schema.split(",")]  # "name type, name type" -> ["name", "name"]


def test_only_bronze_is_versioned():                                    # versioning is per bucket
    versioned = [name for name, body in of_type("AWS::S3::Bucket").items() if body["Properties"].get("VersioningConfiguration", {}).get("Status") == "Enabled"]  # versioned buckets
    assert versioned == ["BronzeBucket"]                                # only raw data keeps history


def test_athena_results_expire_after_one_day():                         # no pile-up of query results
    rules = RESOURCES["AthenaResultsBucket"]["Properties"]["LifecycleConfiguration"]["Rules"]  # lifecycle rules
    assert any(rule.get("ExpirationInDays") == 1 for rule in rules)     # 1-day expiry


def test_glue_job_settings():                                           # the cost-bounded job
    job = RESOURCES["BuildSilverGoldJob"]["Properties"]                 # job settings
    assert (job["WorkerType"], job["NumberOfWorkers"], job["ExecutionClass"], job["Timeout"], job["MaxRetries"]) == ("G.1X", 2, "FLEX", 15, 0)  # as the spec says
    assert job["DefaultArguments"]["--job-bookmark-option"] == "job-bookmark-enable"  # bookmarks on


def test_glue_arguments_match_the_script():                             # template and script agree
    script = ast.parse((REPO / "glue" / "build_silver_gold.py").read_text(encoding="utf-8"))  # the Glue script
    names = next(node.args[1] for node in ast.walk(script) if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "getResolvedOptions")  # its argument list
    wanted = {element.value for element in names.elts} - {"JOB_NAME", "JOB_RUN_ID"}  # our own arguments
    given = {key[2:] for key in RESOURCES["BuildSilverGoldJob"]["Properties"]["DefaultArguments"]} & wanted  # template provides them
    assert given == wanted                                              # nothing missing
    assert "silver_path" not in wanted and "catalog_database" in wanted  # Silver is addressed through the catalog, not a path


def test_glue_script_asks_for_no_reserved_argument():                   # awsglue registers these itself; asking again crashes argparse
    script = ast.parse((REPO / "glue" / "build_silver_gold.py").read_text(encoding="utf-8"))  # the Glue script
    names = next(node.args[1] for node in ast.walk(script) if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "getResolvedOptions")  # its argument list
    reserved = {"JOB_ID", "JOB_RUN_ID", "SECURITY_CONFIGURATION", "job-bookmark-option", "continuation-option", "encryption-type", "TempDir", "RedshiftTempDir"}  # awsglue/utils.py getResolvedOptions, aws-glue-libs master, read 2026-10-19
    assert {element.value for element in names.elts} & reserved == set()  # "conflicting option string: --JOB_RUN_ID" on the first real run, 2026-10-19


def test_lambda_settings():                                             # runtime and cap
    function = RESOURCES["IngestFunction"]["Properties"]                # function settings
    assert (function["Runtime"], function["Architectures"], function["MemorySize"], function["Timeout"]) == ("python3.13", ["arm64"], 512, 60)  # as the spec says
    assert function["ReservedConcurrentExecutions"] == {"Fn::If": ["CapIngestConcurrency", {"Ref": "IngestReservedConcurrency"}, {"Ref": "AWS::NoValue"}]}  # cap only when the parameter is above 0


def test_ingest_concurrency_cap_is_a_parameter_off_by_default():        # accounts with a reduced Lambda quota (10) cannot reserve any
    parameter = TEMPLATE["Parameters"]["IngestReservedConcurrency"]     # deploy-time setting
    assert (parameter["Type"], parameter["Default"], parameter["MinValue"], parameter["MaxValue"]) == ("Number", 0, 0, 1)  # 0 = no reservation, 1 = one run at a time
    assert TEMPLATE["Conditions"]["CapIngestConcurrency"] == {"Fn::Not": [{"Fn::Equals": [{"Ref": "IngestReservedConcurrency"}, "0"]}]}  # Ref of a Number compares as text


def test_workgroup_enforces_scan_limit():                               # cost fuse on queries
    config = RESOURCES["AthenaWorkGroup"]["Properties"]["WorkGroupConfiguration"]  # workgroup settings
    assert config["EnforceWorkGroupConfiguration"] is True and config["BytesScannedCutoffPerQuery"] == 1073741824  # enforced, 1 GB


def test_partitioned_tables_use_projection():                           # no crawler, no MSCK REPAIR
    for body in of_type("AWS::Glue::Table").values():                   # every table
        table_input = body["Properties"]["TableInput"]                  # its definition
        if table_input.get("PartitionKeys"):                            # partitioned tables only
            parameters = table_input["Parameters"]                      # table properties
            key = table_input["PartitionKeys"][0]["Name"]               # e.g. click_month
            assert parameters["projection.enabled"] == "true" and parameters[f"projection.{key}.format"] == "yyyy-MM"  # monthly projection
            assert "storage.location.template" in parameters            # where each month lives
            location = _sub_text(table_input["StorageDescriptor"]["Location"])  # table root, as written
            template = _sub_text(parameters["storage.location.template"])  # per-partition path, as written
            assert template.startswith(location)                       # each month lives under the table root
            assert f"${{!{key}}}" in template                          # keyed by the partition value (${!name} escapes Athena's own ${...})


def test_table_columns_match_the_code():                                # template stays in step with the Spark output
    from clickstream.gold import CALENDAR_COLUMNS, GOLD_CLICK_COLUMNS, PRODUCT_COLUMNS, VISIT_COLUMNS  # Gold shapes
    def names(table_name):                                              # data + partition columns
        table_input = table(table_name)                                 # definition
        return [c["Name"] for c in table_input["StorageDescriptor"]["Columns"]] + [c["Name"] for c in table_input.get("PartitionKeys", [])]  # in order
    assert names("gold_clicks") == GOLD_CLICK_COLUMNS                   # same
    assert names("gold_visits") == VISIT_COLUMNS                        # same
    assert names("gold_products") == PRODUCT_COLUMNS                    # whole table
    assert names("gold_calendar_days") == CALENDAR_COLUMNS              # whole table


# ── Fix round 1 (Task 9 review) ────────────────────────────────
def test_more_table_columns_match_the_code():                           # minor 1: countries/devices too (Silver tables are Athena Iceberg now: test_iceberg_sql.py)
    pytest.importorskip("pyspark", reason="install the spark extra: pip install -e .[dev,spark]")  # these constants live in a pyspark-importing module
    from clickstream_spark.gold import COUNTRY_SCHEMA, DEVICE_SCHEMA     # static reference table shapes
    def names(table_name):                                              # data + partition columns
        table_input = table(table_name)                                 # definition
        return [c["Name"] for c in table_input["StorageDescriptor"]["Columns"]] + [c["Name"] for c in table_input.get("PartitionKeys", [])]  # in order
    assert names("gold_countries") == _ddl_names(COUNTRY_SCHEMA)        # static reference table
    assert names("gold_devices") == _ddl_names(DEVICE_SCHEMA)           # static reference table


def test_glue_job_uses_custom_logging_not_deprecated_continuous_log():  # Finding A: Glue 5.0+ deprecates continuous logging
    arguments = RESOURCES["BuildSilverGoldJob"]["Properties"]["DefaultArguments"]  # job arguments
    assert "--enable-continuous-cloudwatch-log" not in arguments        # deprecated on Glue 5.0+ (custom logging replaces it)
    assert "--continuous-log-logGroup" not in arguments                 # deprecated on Glue 5.0+
    assert _sub_text(arguments["--custom-logGroup-prefix"]) == "/aws-glue/${AWS::StackName}"  # its replacement
    for suffix in ("error", "output"):                                  # both halves of custom logging
        group = RESOURCES[f"Glue{suffix.capitalize()}LogGroup"]["Properties"]  # the log group
        assert _sub_text(group["LogGroupName"]) == f"/aws-glue/${{AWS::StackName}}/{suffix}"  # matches the prefix
        assert group["RetentionInDays"] == 7                            # no slow storage leak


# ── Task 5: Iceberg Silver (Athena creates the tables, the job writes through the Glue catalog) ──
GLUE_ACTIONS = {"glue:GetDatabase", "glue:GetTable", "glue:UpdateTable"}  # Iceberg GlueCatalog refresh + commit (ledger: Task 5 Step 1)
ICEBERG_CONF = [                                                        # the five settings from the AWS Glue Iceberg guide
    "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",  # SQL extensions
    "spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog",  # the catalog
    "spark.sql.catalog.glue_catalog.warehouse=s3://${SilverBucket}/",   # warehouse = the Silver bucket
    "spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog",  # Glue Data Catalog
    "spark.sql.catalog.glue_catalog.io-impl=org.apache.iceberg.aws.s3.S3FileIO",  # S3 file access
]                                                                       # end of the five settings


def test_silver_tables_are_not_in_the_template():                       # Athena creates them from sql/ddl/
    names = {body["Properties"]["TableInput"]["Name"] for body in of_type("AWS::Glue::Table").values()}  # catalog table names
    assert not names & {"silver_clicks", "silver_clicks_rejected", "silver_deleted_visits"}  # no Silver table resources
    assert {"gold_clicks", "gold_visits", "gold_products", "gold_calendar_days"} <= names  # Gold stays
    assert not [key for key in RESOURCES if key.startswith("Silver") and key.endswith("Table")]  # no Silver table resource names either


def test_glue_job_enables_iceberg():                                    # --datalake-formats and the --conf chain
    arguments = RESOURCES["BuildSilverGoldJob"]["Properties"]["DefaultArguments"]  # job arguments
    assert arguments["--datalake-formats"] == "iceberg"                 # Glue-provided Iceberg jars
    conf = _sub_text(arguments["--conf"])                               # one --conf key, chained with " --conf "
    assert conf == " --conf ".join(ICEBERG_CONF)                        # exactly the five settings, in order
    assert "format-version" not in conf                                 # the table version is Athena's (v2) choice
    assert arguments["--catalog_database"] == {"Ref": "ClickstreamDatabase"}  # clickstream_t1, from the database resource
    assert "--silver_path" not in arguments                             # Silver has no path argument any more


def test_glue_role_catalog_access_is_scoped():                          # least privilege on the Data Catalog
    glue = []                                                           # every statement with a glue: action, across all inline policies
    for policy in RESOURCES["GlueJobRole"]["Properties"]["Policies"]:   # each inline policy on the role
        for s in policy["PolicyDocument"]["Statement"]:                 # each statement in it
            actions = [s["Action"]] if isinstance(s["Action"], str) else s["Action"]  # action list, whatever its shape
            if any(a.startswith("glue:") for a in actions):             # touches the Data Catalog
                glue.append(s)                                          # keep it
    assert len(glue) == 1 and glue[0]["Effect"] == "Allow"              # one Allow statement for the catalog
    assert sorted(glue[0]["Action"]) == sorted(GLUE_ACTIONS)            # exactly those actions, no duplicates
    prefix = "arn:${AWS::Partition}:glue:${AWS::Region}:${AWS::AccountId}:"  # built, never a literal account
    resources = [_sub_text(r) for r in glue[0]["Resource"]]             # ARN templates as written
    assert resources == [prefix + "catalog", prefix + "database/clickstream_t1", prefix + "table/clickstream_t1/silver_*"]  # catalog, database, Silver tables only
