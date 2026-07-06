import pytest

from weldbox.units import parse_length


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (2000, 2000.0),
        (2000.5, 2000.5),
        ("2000mm", 2000.0),
        ("2000 mm", 2000.0),
        ("1.5in", 38.1),
        ("1.5 in", 38.1),
        ('0.038"', 0.9652),
        ("1/4in", 6.35),
        ("3 1/2 in", 88.9),
        ("2cm", 20.0),
        ("1m", 1000.0),
        (".5in", 12.7),
    ],
)
def test_parse_length(value, expected):
    assert parse_length(value) == pytest.approx(expected)


def test_default_unit_inches():
    assert parse_length(1.5, default_unit="in") == pytest.approx(38.1)


@pytest.mark.parametrize("bad", ["", "abc", "1.5ft", "--3mm"])
def test_parse_length_rejects(bad):
    with pytest.raises(ValueError):
        parse_length(bad)
