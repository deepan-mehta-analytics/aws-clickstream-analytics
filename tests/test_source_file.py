# ── Tests: reading the UCI source file ────────────────────────
import pytest                                                           # test framework

from clickstream.source_file import PLAIN_COLUMNS, SourceFileError, read_source_clicks  # code under test

UCI_HEADER = "year;month;day;order;country;session ID;page 1 (main category);page 2 (clothing model);colour;location;model photography;price;price 2;page"  # real header


def test_reads_semicolon_file_with_plain_names(tmp_path):              # happy path
    csv_path = tmp_path / "clicks.csv"                                  # temporary file
    csv_path.write_text(UCI_HEADER + "\n2008;4;1;1;29;1;1;A13;1;5;1;28;2;1\n2008;4;1;2;29;1;1;A16;1;6;1;33;2;1\n")  # two real rows
    clicks = read_source_clicks(csv_path)                               # read it
    assert list(clicks.columns) == PLAIN_COLUMNS                        # plain names, fixed order
    assert clicks["visit_id"].tolist() == [1, 1]                        # session ID became visit_id
    assert clicks["product_code"].tolist() == ["A13", "A16"]            # product codes kept as text


def test_wrong_delimiter_raises_clear_error(tmp_path):                  # Review Focus 1
    csv_path = tmp_path / "comma.csv"                                   # temporary file
    csv_path.write_text(UCI_HEADER.replace(";", ",") + "\n2008,4,1,1,29,1,1,A13,1,5,1,28,2,1\n")  # comma-delimited copy
    with pytest.raises(SourceFileError, match="missing columns"):      # must fail clearly
        read_source_clicks(csv_path)                                    # read it
