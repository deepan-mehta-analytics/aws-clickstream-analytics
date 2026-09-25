# ── Tests: codebook decoding ──────────────────────────────────
from clickstream.codebook import CATEGORIES, COLOURS, COUNTRIES, PHOTO_ANGLES, PHOTO_POSITIONS, country_kind  # code under test


def test_codebook_sizes_match_description_file():                      # sizes from the UCI description
    assert len(COUNTRIES) == 47                                         # 47 country codes
    assert len(CATEGORIES) == 4                                         # 4 categories
    assert len(COLOURS) == 14                                           # 14 colours
    assert len(PHOTO_POSITIONS) == 6                                    # 6 screen positions
    assert PHOTO_ANGLES == {1: "front", 2: "side"}                      # en face / profile in plain words


def test_known_labels():                                                # spot-check decoded labels
    assert COUNTRIES[20] == "India"                                     # India is code 20
    assert COUNTRIES[29] == "Poland"                                    # Poland is code 29
    assert CATEGORIES[4] == "sale"                                      # category 4


def test_country_kind():                                                # country vs domain vs unknown
    assert country_kind(29) == "country"                                # a real country
    assert country_kind(12) == "unknown"                                # unidentified
    assert country_kind(44) == "web domain"                             # *.com
