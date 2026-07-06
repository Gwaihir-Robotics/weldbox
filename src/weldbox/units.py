"""Length parsing. All internal math is float millimetres.

Accepted input forms (str or number):
    2000        -> 2000.0 mm (bare numbers use default_unit)
    "2000mm"    -> 2000.0
    "1.5in"     -> 38.1
    '0.038"'    -> 0.9652
    "1/4in"     -> 6.35  (simple fractions)
    "3 1/2 in"  -> 88.9  (mixed numbers)
"""

from __future__ import annotations

import re
from typing import Literal

MM_PER_INCH = 25.4

_UNIT_FACTORS = {
    "mm": 1.0,
    "millimeter": 1.0,
    "millimeters": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": MM_PER_INCH,
    "inch": MM_PER_INCH,
    "inches": MM_PER_INCH,
    '"': MM_PER_INCH,
}

_LENGTH_RE = re.compile(
    r"""^\s*
    (?P<whole>\d+(?:\.\d+)?|\.\d+)          # whole/decimal part
    (?:\s+(?P<num>\d+)\s*/\s*(?P<den>\d+))? # optional mixed fraction
    \s*(?P<unit>[a-zA-Z"]+)?\s*$""",
    re.VERBOSE,
)

_FRACTION_RE = re.compile(
    r'^\s*(?P<num>\d+)\s*/\s*(?P<den>\d+)\s*(?P<unit>[a-zA-Z"]+)?\s*$'
)


def parse_length(
    value: str | int | float, default_unit: Literal["mm", "in"] = "mm"
) -> float:
    """Parse a length into millimetres."""
    if isinstance(value, (int, float)):
        return float(value) * _UNIT_FACTORS[default_unit]

    text = str(value).strip()
    m = _FRACTION_RE.match(text)
    if m:
        magnitude = int(m.group("num")) / int(m.group("den"))
    else:
        m = _LENGTH_RE.match(text)
        if not m:
            raise ValueError(f"cannot parse length: {value!r}")
        magnitude = float(m.group("whole"))
        if m.group("num"):
            magnitude += int(m.group("num")) / int(m.group("den"))

    unit = (m.group("unit") or default_unit).lower().rstrip(".")
    if unit == '"'.lower() or m.group("unit") == '"':
        unit = '"'
    if unit not in _UNIT_FACTORS:
        raise ValueError(f"unknown unit {unit!r} in length {value!r}")
    return magnitude * _UNIT_FACTORS[unit]


def fmt_mm(mm: float, places: int = 1) -> str:
    """Format a mm value for manifests, trimming trailing zeros."""
    s = f"{mm:.{places}f}"
    return s


def inches(mm: float) -> float:
    return mm / MM_PER_INCH
