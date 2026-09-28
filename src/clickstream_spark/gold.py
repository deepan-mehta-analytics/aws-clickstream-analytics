"""Gold in Spark: two-grain star schema (clicks, visits) plus reference tables, same shapes as clickstream.gold."""  # module docstring

from pyspark.sql import DataFrame, SparkSession, Window                 # Spark types
from pyspark.sql import functions as F                                  # column functions

from clickstream.gold import CALENDAR_COLUMNS, GOLD_CLICK_COLUMNS, PRODUCT_COLUMNS, VISIT_COLUMNS, build_countries, build_devices  # shared shapes and static tables

COUNTRY_SCHEMA = "country_code bigint, country_name string, kind string"  # countries table types
DEVICE_SCHEMA = "device_type string"                                    # devices table type


def build_products_spark(clicks: DataFrame) -> DataFrame:               # one row per product
    first_click = Window.partitionBy("product_code").orderBy("visit_id", "click_number_in_visit")  # pandas "first" = first row in Silver order
    firsts = clicks.withColumn("_n", F.row_number().over(first_click)).filter(F.col("_n") == 1).select("product_code", *PRODUCT_COLUMNS[2:])  # attributes fixed per product
    most_common = Window.partitionBy("product_code").orderBy(F.col("clicks").desc(), F.col("category").asc())  # pandas mode: most frequent, ties -> smallest
    modes = (clicks.groupBy("product_code", "category").agg(F.count(F.lit(1)).alias("clicks"))  # clicks per product and category
             .withColumn("_n", F.row_number().over(most_common)).filter(F.col("_n") == 1).select("product_code", "category"))  # the winner
    return firsts.join(modes, "product_code").select(PRODUCT_COLUMNS)   # exact column order


def build_countries_spark(spark: SparkSession) -> DataFrame:            # 47 country codes from the codebook
    return spark.createDataFrame(build_countries(), schema=COUNTRY_SCHEMA)  # same rows as pandas


def build_devices_spark(spark: SparkSession) -> DataFrame:              # desktop, mobile, tablet
    return spark.createDataFrame(build_devices(), schema=DEVICE_SCHEMA)  # same rows as pandas


def build_calendar_days_spark(clicks: DataFrame) -> DataFrame:          # one row per date with clicks
    dates = clicks.select(F.col("click_date").alias("calendar_date")).distinct()  # distinct dates
    return dates.select(                                                # calendar attributes
        "calendar_date",                                                # the date
        F.date_format("calendar_date", "EEEE").alias("day_of_week"),    # e.g. Saturday
        F.weekofyear("calendar_date").cast("long").alias("week_number"),  # ISO week (Monday start)
        F.date_format("calendar_date", "MMMM").alias("month_name"),     # e.g. April
    ).select(CALENDAR_COLUMNS)                                          # exact order


def build_gold_clicks_spark(clicks: DataFrame) -> DataFrame:            # event table, click grain
    return clicks.select(GOLD_CLICK_COLUMNS)                            # keys and measures only


def build_visits_spark(clicks: DataFrame) -> DataFrame:                 # event table, visit grain
    by_click = "click_number_in_visit"                                  # order within a visit
    visits = clicks.groupBy("visit_id").agg(                            # one row per visit
        F.min_by("click_date", by_click).alias("visit_date"),           # visits never cross midnight
        F.min_by("country_code", by_click).alias("country_code"),       # fixed per visit (measured)
        F.min_by("device_type_synthetic", by_click).alias("device_type_synthetic"),  # fixed per visit by design
        F.min("click_time_synthetic").alias("visit_start_time_synthetic"),  # first click time
        F.max("click_time_synthetic").alias("visit_end_time_synthetic"),  # last click time
        F.count(F.lit(1)).alias("clicks_in_visit"),                     # number of clicks
        F.count_distinct("product_code").alias("products_viewed"),      # distinct products
        F.count_distinct("category").alias("categories_viewed"),        # distinct categories
        F.max("page_number_in_shop").alias("deepest_page_reached"),     # browse-depth funnel stage
        F.min_by("product_code", by_click).alias("first_product_viewed"),  # entry product
        F.max_by("product_code", by_click).alias("last_product_viewed"),  # exit product
    )
    return (visits                                                      # derived columns
            .withColumn("visit_length_seconds_synthetic", F.unix_seconds("visit_end_time_synthetic") - F.unix_seconds("visit_start_time_synthetic"))  # duration
            .withColumn("bounced", F.col("clicks_in_visit") == 1)       # one click = bounce
            .withColumn("visit_month", F.date_format("visit_date", "yyyy-MM"))  # partition value
            .select(VISIT_COLUMNS))                                     # exact order
