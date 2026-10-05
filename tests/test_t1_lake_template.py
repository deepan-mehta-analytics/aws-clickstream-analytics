# ── Tests: tier T1a template specifics and its link to the code ─
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
    from clickstream.silver import SILVER_COLUMNS                       # Silver shape
    def names(table_name):                                              # data + partition columns
        table_input = table(table_name)                                 # definition
        return [c["Name"] for c in table_input["StorageDescriptor"]["Columns"]] + [c["Name"] for c in table_input.get("PartitionKeys", [])]  # in order
    assert names("silver_clicks") == SILVER_COLUMNS                     # partition column last, as Spark writes it
    assert names("gold_clicks") == GOLD_CLICK_COLUMNS                   # same
    assert names("gold_visits") == VISIT_COLUMNS                        # same
    assert names("gold_products") == PRODUCT_COLUMNS                    # whole table
    assert names("gold_calendar_days") == CALENDAR_COLUMNS              # whole table


# ── Fix round 1 (Task 9 review) ────────────────────────────────
def test_more_table_columns_match_the_code():                           # minor 1: rejected/countries/devices too
    pytest.importorskip("pyspark", reason="install the spark extra: pip install -e .[dev,spark]")  # these constants live in a pyspark-importing module
    from clickstream_spark.gold import COUNTRY_SCHEMA, DEVICE_SCHEMA     # static reference table shapes
    from clickstream_spark.silver import REJECTED_COLUMNS               # clicks_rejected shape
    def names(table_name):                                              # data + partition columns
        table_input = table(table_name)                                 # definition
        return [c["Name"] for c in table_input["StorageDescriptor"]["Columns"]] + [c["Name"] for c in table_input.get("PartitionKeys", [])]  # in order
    assert names("silver_clicks_rejected") == REJECTED_COLUMNS          # partition column last, as Spark writes it
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
