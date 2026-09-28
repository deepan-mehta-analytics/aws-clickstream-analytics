"""Read raw UCI rows (Bronze CSV as Glue reads it) into plain-named, typed Spark columns."""  # module docstring

from pyspark.sql import DataFrame                                       # Spark table type
from pyspark.sql import functions as F                                  # column functions
from pyspark.sql.types import LongType, StringType, StructField, StructType  # schema types

from clickstream.source_file import SOURCE_TO_PLAIN                     # source name -> plain name (shared with pandas)

TEXT_COLUMNS = {"product_code"}                                         # the only text column; every other is a whole number
SOURCE_SCHEMA = StructType([                                            # plain columns and types, source file order
    StructField(plain, StringType() if plain in TEXT_COLUMNS else LongType(), True) for plain in SOURCE_TO_PLAIN.values()  # bigint except product code
])


class SourceColumnsError(ValueError):                                   # wrong file or wrong delimiter
    """The raw frame does not have the UCI #553 columns."""             # class docstring


def to_plain_columns(raw: DataFrame) -> DataFrame:                      # rename and type every column
    missing = [name for name in SOURCE_TO_PLAIN if name not in raw.columns]  # expected columns that are absent
    if missing:                                                         # not the UCI file
        raise SourceColumnsError(f"missing columns {missing}; expected the ';'-delimited UCI #553 file")  # clear message
    return raw.select([                                                 # one expression per column
        (F.col(f"`{source}`").cast("string") if plain in TEXT_COLUMNS    # product code stays text
         else F.expr(f"try_cast(cast(`{source}` AS STRING) AS BIGINT)")).alias(plain)  # numbers: text first, bad values -> NULL (ANSI-safe)
        for source, plain in SOURCE_TO_PLAIN.items()                    # source file order
    ])
