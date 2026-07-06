"""DXF flat patterns for sheet panels (ezdxf).

Written the way flat-laser vendors expect uploads: DXF R2000, millimetre
units ($INSUNITS = 4), a closed LWPOLYLINE outline and CIRCLE holes on
layer 0.
"""

from __future__ import annotations

import math
from pathlib import Path

import ezdxf

from .layout import Panel

# bulge for a 90 degree arc segment
_BULGE_90 = math.tan(math.pi / 8)


def _outline_points(w: float, h: float, r: float):
    """LWPOLYLINE vertices (x, y, bulge) for a rectangle with radius-r
    corners. The bulge on a vertex applies to the segment leaving it."""
    if r <= 0:
        return [(0, 0, 0), (w, 0, 0), (w, h, 0), (0, h, 0)]
    return [
        (r, 0, 0), (w - r, 0, _BULGE_90),
        (w, r, 0), (w, h - r, _BULGE_90),
        (w - r, h, 0), (r, h, _BULGE_90),
        (0, h - r, 0), (0, r, _BULGE_90),
    ]


def write_panel_dxf(panel: Panel, path: Path) -> None:
    doc = ezdxf.new("R2000", setup=False)
    doc.header["$INSUNITS"] = 4  # millimetres
    msp = doc.modelspace()

    msp.add_lwpolyline(
        _outline_points(panel.width, panel.height, panel.corner_radius),
        format="xyb",
        close=True,
    )
    for u, v, dia in panel.holes:
        msp.add_circle((u, v), dia / 2)

    doc.saveas(path)
