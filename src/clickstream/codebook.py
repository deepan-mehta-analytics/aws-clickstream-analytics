"""Decode tables copied from the UCI #553 description file (e-shop clothing 2008 data description.txt)."""  # module docstring

# ── Categories, colours and photo placement ───────────────────
CATEGORIES = {1: "trousers", 2: "skirts", 3: "blouses", 4: "sale"}      # main category codes
COLOURS = {                                                             # colour codes 1-14
    1: "beige", 2: "black", 3: "blue", 4: "brown", 5: "burgundy", 6: "gray", 7: "green",  # codes 1-7
    8: "navy blue", 9: "of many colors", 10: "olive", 11: "pink", 12: "red", 13: "violet", 14: "white",  # codes 8-14
}
PHOTO_POSITIONS = {                                                     # where the photo sat on the screen
    1: "top left", 2: "top in the middle", 3: "top right",              # top row
    4: "bottom left", 5: "bottom in the middle", 6: "bottom right",     # bottom row
}
PHOTO_ANGLES = {1: "front", 2: "side"}                                  # source says "en face" and "profile"

# ── Countries (IP origin) ─────────────────────────────────────
COUNTRIES = {                                                           # country codes 1-47
    1: "Australia", 2: "Austria", 3: "Belgium", 4: "British Virgin Islands", 5: "Cayman Islands",  # 1-5
    6: "Christmas Island", 7: "Croatia", 8: "Cyprus", 9: "Czech Republic", 10: "Denmark",  # 6-10
    11: "Estonia", 12: "unidentified", 13: "Faroe Islands", 14: "Finland", 15: "France",  # 11-15
    16: "Germany", 17: "Greece", 18: "Hungary", 19: "Iceland", 20: "India",  # 16-20
    21: "Ireland", 22: "Italy", 23: "Latvia", 24: "Lithuania", 25: "Luxembourg",  # 21-25
    26: "Mexico", 27: "Netherlands", 28: "Norway", 29: "Poland", 30: "Portugal",  # 26-30
    31: "Romania", 32: "Russia", 33: "San Marino", 34: "Slovakia", 35: "Slovenia",  # 31-35
    36: "Spain", 37: "Sweden", 38: "Switzerland", 39: "Ukraine", 40: "United Arab Emirates",  # 36-40
    41: "United Kingdom", 42: "USA", 43: "biz (*.biz)", 44: "com (*.com)", 45: "int (*.int)",  # 41-45
    46: "net (*.net)", 47: "org (*.org)",                               # 46-47
}
UNKNOWN_COUNTRY_CODES = {12}                                            # "unidentified"
WEB_DOMAIN_COUNTRY_CODES = {43, 44, 45, 46, 47}                         # generic domains, not countries


def country_kind(code: int) -> str:                                     # classify a country code
    if code in UNKNOWN_COUNTRY_CODES:                                   # unidentified origin
        return "unknown"                                                # plain label
    if code in WEB_DOMAIN_COUNTRY_CODES:                                # .biz/.com/.int/.net/.org
        return "web domain"                                             # plain label
    return "country"                                                    # everything else is a real country
