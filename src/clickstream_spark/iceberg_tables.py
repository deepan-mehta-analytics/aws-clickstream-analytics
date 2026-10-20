"""Silver Iceberg tables: names, the format-version guard, the column-following writer and the deleted-visits filter."""  # module docstring

from dataclasses import dataclass                                       # table-name container

from pyspark.sql import DataFrame, SparkSession                         # Spark types
from pyspark.sql import functions as F                                  # column functions
from pyspark.sql.types import TimestampNTZType, TimestampType           # the two timestamp kinds

ALLOWED_FORMAT_VERSION = "2"                                            # Athena reads v2 only, and v2 -> v3 cannot be undone (decision A2)


# ── Table names ───────────────────────────────────────────────
@dataclass(frozen=True)
class SilverTables:                                                     # where the Silver Iceberg tables live
    catalog: str                                                        # Spark catalog name, e.g. glue_catalog
    database: str                                                       # Glue database, e.g. clickstream_t1

    @property
    def clicks(self) -> str:                                            # clean clicks table
        return f"{self.catalog}.{self.database}.silver_clicks"          # fully qualified name

    @property
    def rejected(self) -> str:                                          # rejected clicks table
        return f"{self.catalog}.{self.database}.silver_clicks_rejected"  # fully qualified name

    @property
    def deleted_visits(self) -> str:                                    # deleted-visits list
        return f"{self.catalog}.{self.database}.silver_deleted_visits"  # fully qualified name


# ── Errors ────────────────────────────────────────────────────
class FormatVersionError(RuntimeError):                                 # a table that is not Iceberg format version 2
    pass                                                                # the message names the table and the value


class MissingColumnError(ValueError):                                   # the table has a column the frame does not
    pass                                                                # the message names the column and the table


# ── Guard and table shape ─────────────────────────────────────
def check_format_version(spark: SparkSession, table: str) -> None:      # stop before writing to anything but v2
    properties = {row["key"]: row["value"] for row in spark.sql(f"SHOW TBLPROPERTIES {table}").collect()}  # every table property
    version = properties.get("format-version")                          # Iceberg reports its format version here (None if missing)
    if version != ALLOWED_FORMAT_VERSION:                               # v1, v3 or unknown
        raise FormatVersionError(f"{table} has format-version {version!r}; only {ALLOWED_FORMAT_VERSION!r} is allowed")  # name both


def table_columns(spark: SparkSession, table: str) -> list[str]:        # the table's current columns, in table order
    return spark.table(table).columns                                   # read from the catalog, so a migrated column shows up


# ── Writer: follow the table's columns (decision D2) ──────────
def write_months_to_table(spark: SparkSession, frame: DataFrame, table: str) -> None:  # replace only the months (partitions) in the frame
    table_schema = spark.table(table).schema                            # current columns and types
    missing = [field.name for field in table_schema if field.name not in frame.columns]  # table columns the frame lacks
    if missing:                                                         # never write NULL silently into a table column
        raise MissingColumnError(f"{table} has column(s) {missing} that the frame does not")  # name them
    frame_types = {field.name: field.dataType for field in frame.schema}  # frame column -> Spark type
    selected = []                                                       # columns to write, in table order
    for field in table_schema:                                          # each table column (extra frame columns are dropped)
        column = F.col(field.name)                                      # the frame's column
        if isinstance(frame_types[field.name], TimestampType) and isinstance(field.dataType, TimestampNTZType):  # Athena "timestamp" is Iceberg timestamp without zone
            column = column.cast(TimestampNTZType())                    # UTC wall-clock, because the session time zone is UTC
        selected.append(column.alias(field.name))                       # keep the table's name
    frame.select(selected).writeTo(table).overwritePartitions()         # Iceberg dynamic overwrite: only these months are replaced


# ── Deleted visits ────────────────────────────────────────────
def deleted_visit_ids(spark: SparkSession, tables: SilverTables) -> DataFrame:  # visits that must never come back
    return spark.table(tables.deleted_visits).select("visit_id").distinct()  # one column, one row per visit


def remove_deleted_visits(frame: DataFrame, deleted: DataFrame) -> DataFrame:  # drop every row of a listed visit
    return frame.join(deleted, on="visit_id", how="left_anti")          # keep rows whose visit is not in the list
