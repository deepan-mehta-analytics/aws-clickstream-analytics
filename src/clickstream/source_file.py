"""Read the UCI #553 clickstream CSV and give its columns plain names."""  # module docstring

from pathlib import Path                                                # file paths

import pandas as pd                                                     # dataframes

# ── Source column → plain name (see docs/data-dictionary.md) ─
SOURCE_TO_PLAIN = {                                                     # mapping in source file order
    "year": "year",                                                     # kept as is
    "month": "month",                                                   # kept as is
    "day": "day",                                                       # kept as is
    "order": "click_number_in_visit",                                   # position of the click in its visit
    "country": "country_code",                                          # IP country code 1-47
    "session ID": "visit_id",                                           # the source calls a visit a session
    "page 1 (main category)": "category_code",                          # category 1-4
    "page 2 (clothing model)": "product_code",                          # product code such as A13
    "colour": "colour_code",                                            # colour 1-14
    "location": "photo_position_code",                                  # photo position 1-6
    "model photography": "photo_angle_code",                            # 1 front, 2 side
    "price": "price_usd",                                               # price in US dollars
    "price 2": "price_above_category_average_code",                     # 1 yes, 2 no
    "page": "page_number_in_shop",                                      # listing page 1-5
}
PLAIN_COLUMNS = list(SOURCE_TO_PLAIN.values())                          # plain names in a fixed order


class SourceFileError(ValueError):                                      # raised when the file is not the expected UCI file
    """The source file does not have the expected UCI #553 columns."""  # class docstring


def read_source_clicks(csv_path: str | Path) -> pd.DataFrame:          # read and rename
    raw = pd.read_csv(csv_path, sep=";")                                # the UCI file is semicolon-delimited
    missing = [name for name in SOURCE_TO_PLAIN if name not in raw.columns]  # expected columns that are absent
    if missing:                                                         # wrong delimiter or wrong file
        raise SourceFileError(f"{csv_path}: missing columns {missing}; expected the ';'-delimited UCI #553 file")  # clear message
    return raw[list(SOURCE_TO_PLAIN)].rename(columns=SOURCE_TO_PLAIN)   # keep only known columns, renamed
