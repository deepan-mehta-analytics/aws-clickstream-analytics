# ── Helpers for the Spark tests ───────────────────────────────
import pandas as pd                                                     # dataframes

from clickstream.source_file import SOURCE_TO_PLAIN                     # source name -> plain name

PLAIN_TO_SOURCE = {plain: source for source, plain in SOURCE_TO_PLAIN.items()}  # plain name -> source name


def raw_frame(spark, rows):                                             # rows (plain dicts) -> DataFrame shaped like Glue's CSV read
    from pyspark.sql.types import StringType, StructField, StructType   # Spark schema types
    columns = list(SOURCE_TO_PLAIN)                                     # source column names, file order
    schema = StructType([StructField(name, StringType(), True) for name in columns])  # every column is text
    values = [[None if row[SOURCE_TO_PLAIN[name]] is None else str(row[SOURCE_TO_PLAIN[name]]) for name in columns] for row in rows]  # text values in file order
    return spark.createDataFrame(values, schema=schema)                 # DataFrame with source names


def sorted_pandas(frame, keys):                                         # Spark or pandas frame -> comparable pandas frame
    table = frame.toPandas() if hasattr(frame, "toPandas") else frame.copy()  # Spark -> pandas via Arrow (session time zone UTC)
    for column in table.columns:                                        # normalise types column by column
        series = table[column]                                          # one column
        if pd.api.types.is_datetime64_any_dtype(series):                # timestamps (pandas: UTC-aware; Spark: naive UTC)
            table[column] = pd.to_datetime(series, utc=True).astype("datetime64[us, UTC]")  # UTC, microseconds
        elif pd.api.types.is_bool_dtype(series):                        # booleans
            table[column] = series.astype(bool)                         # plain bool
        elif pd.api.types.is_integer_dtype(series):                     # int32 / int64 / Int64
            table[column] = series.astype("int64")                      # one integer type
        elif pd.api.types.is_float_dtype(series):                       # doubles
            table[column] = series.astype("float64").round(4)           # compare to 4 decimals
        elif series.dtype == object and series.notna().any() and hasattr(series.dropna().iloc[0], "isoformat"):  # datetime.date objects (Spark DateType round trip)
            table[column] = pd.to_datetime(series, utc=True).astype("datetime64[us, UTC]")  # same canonical form as a native datetime64 column (e.g. DuckDB's DATE round trip)
    return table.sort_values(keys).reset_index(drop=True)               # stable order


def text_of(frame, column, pattern="yyyy-MM-dd HH:mm"):                 # first row's timestamp as UTC text
    from pyspark.sql import functions as F                              # column functions
    return frame.select(F.date_format(column, pattern)).first()[0]      # formatted in Spark's UTC session, not the laptop's time zone
