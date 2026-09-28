"""Silver in Spark: the same hard rules as clickstream.silver, as DataFrame expressions (ADR-0003)."""  # module docstring

from dataclasses import dataclass                                       # result container
from datetime import datetime, timezone                                 # run time
from functools import reduce                                            # OR many conditions together

from pyspark.sql import Column, DataFrame, Window                       # Spark types
from pyspark.sql import functions as F                                  # column functions

from clickstream.codebook import CATEGORIES, COLOURS, PHOTO_ANGLES, PHOTO_POSITIONS  # decode tables (shared)
from clickstream.enrichment import SHOP_TIMEZONE                        # Europe/Warsaw
from clickstream.silver import REQUIRED_COLUMNS, SILVER_COLUMNS, VALID_CODE_RANGES  # rules and output shape (shared)
from clickstream_spark.bronze import BRONZE_COLUMNS                     # input columns

REJECTED_COLUMNS = BRONZE_COLUMNS + ["rejection_reason", "rejected_time", "source_month"]  # clicks_rejected columns (source_month = partition)


@dataclass
class SparkSilverResult:                                                # everything build_silver_spark returns
    clicks: DataFrame                                                   # rows that passed every hard rule
    rejected: DataFrame                                                 # rows that failed, with a reason
    duplicates_removed: int                                             # resent copies dropped


# ── Small column builders ─────────────────────────────────────
def decode(mapping: dict, column: str) -> Column:                       # code -> label, NULL if unknown
    pairs = [part for code, label in mapping.items() for part in (F.lit(code).cast("long"), F.lit(label))]  # key/value literals
    return F.try_element_at(F.create_map(*pairs), F.col(column))        # try_: no ANSI error on a missing key


def real_date_column() -> Column:                                       # the real 2008 date, NULL when impossible
    valid_month = F.col("year").between(1, 9999) & F.col("month").between(1, 12)  # make_date would fail outside these
    first_day = F.when(valid_month, F.make_date(F.col("year").cast("int"), F.col("month").cast("int"), F.lit(1)))  # first of that month
    valid_day = F.col("day").between(1, 31) & (F.col("day") <= F.dayofmonth(F.last_day(first_day)))  # day exists in that month
    return F.when(valid_day, F.date_add(first_day, (F.col("day") - 1).cast("int")))  # the date, or NULL (e.g. 31 April)


# ── Hard rules: the first failing rule is the recorded reason ─
def with_rejection_reason(frame: DataFrame) -> DataFrame:               # adds _real_date, _local_time, rejection_reason
    per_visit = Window.partitionBy("visit_id")                          # all clicks of a visit (NULL visit ids form one group, like pandas dropna=False)
    in_order = Window.partitionBy("visit_id").orderBy("click_number_in_visit")  # click order in a visit
    frame = frame.withColumn("_real_date", real_date_column()).withColumn("_local_time", F.from_utc_timestamp("click_time_synthetic", SHOP_TIMEZONE))  # helpers
    clicks_in_visit = F.count(F.lit(1)).over(per_visit)                 # rows in the visit
    contiguous = ((F.min("click_number_in_visit").over(per_visit) == 1)  # starts at 1
                  & (F.max("click_number_in_visit").over(per_visit) == clicks_in_visit)  # ends at n
                  & (F.size(F.collect_set("click_number_in_visit").over(per_visit)) == clicks_in_visit))  # no repeats, no gaps
    gap = F.coalesce(F.unix_seconds("click_time_synthetic") - F.unix_seconds(F.lag("click_time_synthetic").over(in_order)), F.lit(1))  # seconds since previous click (first click: 1)
    rules = [(reduce(lambda a, b: a | b, [F.col(c).isNull() for c in REQUIRED_COLUMNS]), "missing required field")]  # every required field present
    rules.append((F.col("_real_date").isNull(), "invalid real date"))   # e.g. month 13, 31 April
    rules += [(~F.col(c).between(low, high), f"{c} outside {low}-{high}") for c, (low, high) in VALID_CODE_RANGES.items()]  # codebook ranges
    rules.append((~contiguous, "click numbers not contiguous in visit"))  # the whole visit fails together
    rules.append((F.to_date("_local_time") != F.col("_real_date"), "synthetic time outside real date"))  # synthetic time on the real date
    rules.append((gap <= 0, "synthetic time not increasing"))           # times must increase
    reason = None                                                       # CASE WHEN chain
    for failed, text in rules:                                          # in rule order
        condition = F.coalesce(failed, F.lit(True))                     # an unknown result counts as failed (pandas fillna(True))
        reason = F.when(condition, F.lit(text)) if reason is None else reason.when(condition, F.lit(text))  # first match wins
    frame = frame.withColumn("_reason", reason)                         # own-row reason
    visit_failed = F.max(F.col("_reason").isNotNull().cast("int")).over(per_visit) == 1  # any failed click in the visit
    return frame.withColumn("rejection_reason", F.coalesce(F.col("_reason"), F.when(visit_failed, F.lit("other click in visit rejected")))).drop("_reason")  # never pass a partial visit


# ── Silver ────────────────────────────────────────────────────
def build_silver_spark(bronze: DataFrame, run_time: datetime) -> SparkSilverResult:  # Bronze -> Silver
    earliest = Window.partitionBy("click_id").orderBy(F.col("received_time").asc())  # earliest copy first
    ranked = bronze.withColumn("_copy", F.row_number().over(earliest)).cache()  # copy number per click
    duplicates_removed = ranked.filter(F.col("_copy") > 1).count()      # resends
    checked = with_rejection_reason(ranked.filter(F.col("_copy") == 1).drop("_copy")).cache()  # one row per click, with a reason or NULL
    rejected = (checked.filter(F.col("rejection_reason").isNotNull())   # failed rows
                .withColumn("rejected_time", F.lit(run_time.astimezone(timezone.utc)).cast("timestamp"))  # when this run rejected them
                .withColumn("source_month", F.format_string("%04d-%02d", F.col("year"), F.col("month")))  # the Bronze file month (always valid)
                .select(REJECTED_COLUMNS))                              # exact order
    clicks = checked.filter(F.col("rejection_reason").isNull()).select(  # clean rows, decoded
        "click_id", "visit_id", "click_number_in_visit",                # identity
        F.col("_real_date").alias("click_date"), "click_time_synthetic",  # dates and times
        F.hour("_local_time").cast("long").alias("click_hour_shop_time_synthetic"),  # shop-local hour 0-23
        "product_code", decode(CATEGORIES, "category_code").alias("category"), decode(COLOURS, "colour_code").alias("colour"),  # product
        "price_usd", (F.col("price_above_category_average_code") == 1).alias("priced_above_category_average"),  # price
        "page_number_in_shop", decode(PHOTO_POSITIONS, "photo_position_code").alias("photo_position_on_page"),  # placement
        decode(PHOTO_ANGLES, "photo_angle_code").alias("photo_angle"), "country_code", "device_type_synthetic",  # context
        "received_time", (F.unix_seconds("received_time") - F.unix_seconds("click_time_synthetic")).alias("seconds_late"),  # lateness
        F.date_format("_real_date", "yyyy-MM").alias("click_month"),    # partition value
    ).select(SILVER_COLUMNS)                                            # exact order
    return SparkSilverResult(clicks, rejected, duplicates_removed)      # all three outputs
