# ── Shared test helpers: hand-made source rows in plain names ─
import pandas as pd                                                     # dataframes

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
