# ── Helpers for the Iceberg tests: build the Silver tables in the local catalog from the real DDL ─
from clickstream_spark.settings import CATALOG                          # catalog name (glue_catalog locally and in Glue)
from clickstream_spark.sql_files import ddl_columns, ddl_partition, load_ddl, load_migrations, strip_comments  # the real SQL files

DATABASE = "clickstream_t1"                                             # the Glue database name, reused locally
SPARK_TYPES = {                                                         # Athena DDL type -> Spark SQL type for the local table
    "bigint": "BIGINT",                                                 # 64-bit integer
    "int": "INT",                                                       # 32-bit integer
    "string": "STRING",                                                 # text
    "double": "DOUBLE",                                                 # floating point
    "boolean": "BOOLEAN",                                               # true / false
    "date": "DATE",                                                     # calendar date
    "timestamp": "TIMESTAMP_NTZ",                                       # Athena Iceberg "timestamp" has no time zone (Task 2 Step 1 finding)
}


def table_ddl(full_name: str, sql: str, properties: str) -> str:        # Athena DDL -> Spark CREATE TABLE for the local catalog
    columns = ", ".join(f"{name} {SPARK_TYPES[kind]}" for name, kind in ddl_columns(sql))  # same names and order, Spark types
    partition = ddl_partition(sql)                                      # partition column or None
    partition_clause = f" PARTITIONED BY ({partition})" if partition else ""  # identity partition, as in Athena
    return f"CREATE TABLE {full_name} ({columns}) USING iceberg{partition_clause} TBLPROPERTIES ({properties})"  # no LOCATION: the folder catalog picks it


def create_silver_tables(spark, database=DATABASE, properties="'format-version'='2'"):  # fresh, empty Silver tables -> SilverTables
    from clickstream_spark.iceberg_tables import SilverTables           # code under test
    tables = SilverTables(CATALOG, database)                            # fully qualified names
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {CATALOG}.{database}")   # database folder
    for name, sql in load_ddl().items():                                # the three DDL files
        full_name = f"{CATALOG}.{database}.{name}"                      # e.g. glue_catalog.clickstream_t1.silver_clicks
        spark.sql(f"DROP TABLE IF EXISTS {full_name} PURGE")            # leftovers from an earlier test
        spark.sql(table_ddl(full_name, sql, properties))                # create it empty, v2 like Athena
    return tables                                                       # names for the code under test


def apply_migrations(spark, database=DATABASE):                         # run sql/migrations/*.sql against the local catalog
    for _, sql in load_migrations():                                    # oldest first
        statement = strip_comments(sql).strip().rstrip(";")             # one statement, no comments
        spark.sql(statement.replace(f"{DATABASE}.", f"{CATALOG}.{database}.", 1))  # point the table name at the local catalog
