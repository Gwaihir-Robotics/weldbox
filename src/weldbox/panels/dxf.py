"""DXF flat patterns for sheet panels (ezdxf).

Written the way flat-laser vendors expect uploads: DXF R2000, millimetre
units ($INSUNITS = 4), a closed LWPOLYLINE outline and CIRCLE holes on
layer 0. Plate cutouts that touch the outline become notches in the
outline polyline; interior cutouts become their own closed polylines.
"""

from __future__ import annotations

import math
from pathlib import Path

import ezdxf

from .layout import Cutout, Panel

# bulge for a 90 degree arc segment; concave (material-side) fillets are
# clockwise while traversing the outline CCW, so they carry -_BULGE_90
_BULGE_90 = math.tan(math.pi / 8)

_TOL = 1e-6

# CCW edge frames: (start corner, travel dir, inward dir, length key)
# point(edge, t, d) = start + t * travel + d * inward
# edge order: 0 bottom, 1 right, 2 top, 3 left; corner k joins edge k-1 -> k


def _edges(w: float, h: float):
    return [
        ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), w),
        ((w, 0.0), (0.0, 1.0), (-1.0, 0.0), h),
        ((w, h), (-1.0, 0.0), (0.0, -1.0), w),
        ((0.0, h), (0.0, -1.0), (1.0, 0.0), h),
    ]


def _classify(w: float, h: float, cutouts: list[Cutout]):
    """Split cutouts into corner notches {corner_index: (p, q, r)}, edge
    notches {edge_index: [(a, b, depth, r)]}, and interior cutouts.

    p = notch extent along the corner's incoming edge, q along its outgoing
    edge; (a, b) is the notch interval in the edge's travel parameter.
    """
    corners: dict[int, tuple] = {}
    edges: dict[int, list[tuple]] = {0: [], 1: [], 2: [], 3: []}
    interior: list[Cutout] = []
    for c in cutouts:
        left, right = c.u0 <= _TOL, c.u1 >= w - _TOL
        bottom, top = c.v0 <= _TOL, c.v1 >= h - _TOL
        if (left and right) or (bottom and top):
            raise ValueError(f"plate cutout {c} spans the whole plate")
        n_touch = sum((left, right, bottom, top))
        if n_touch == 0:
            interior.append(c)
        elif n_touch == 1:
            if bottom:
                edges[0].append((c.u0, c.u1, c.v1, c.radius))
            elif right:
                edges[1].append((c.v0, c.v1, w - c.u0, c.radius))
            elif top:
                edges[2].append((w - c.u1, w - c.u0, h - c.v0, c.radius))
            else:  # left
                edges[3].append((h - c.v1, h - c.v0, c.u1, c.radius))
        else:  # corner notch: extents along incoming (p) and outgoing (q) edge
            if bottom and left:
                corners[0] = (c.v1, c.u1, c.radius)
            elif bottom and right:
                corners[1] = (w - c.u0, c.v1, c.radius)
            elif top and right:
                corners[2] = (h - c.v0, w - c.u0, c.radius)
            else:  # top and left
                corners[3] = (c.u1, h - c.v0, c.radius)
    return corners, edges, interior


def _plate_outline_points(w: float, h: float, rc: float, cutouts: list[Cutout]):
    """Closed LWPOLYLINE (x, y, bulge) vertices for the panel outline with
    rounded outer corners and cutout notches. The bulge on a vertex applies
    to the segment leaving it."""
    corners, edge_notches, interior = _classify(w, h, cutouts)
    edges = _edges(w, h)
    pts: list[tuple[float, float, float]] = []

    def P(edge: int, t: float, d: float, bulge: float) -> None:
        (sx, sy), (tx, ty), (dx, dy), _ = edges[edge]
        pts.append((sx + t * tx + d * dx, sy + t * ty + d * dy, bulge))

    # per-edge bounds occupied by the corner treatments, for overlap checks
    def start_extent(edge: int) -> float:
        return corners[edge][1] if edge in corners else rc

    def end_extent(edge: int) -> float:
        nxt = (edge + 1) % 4
        return corners[nxt][0] if nxt in corners else rc

    for k in range(4):
        incoming = (k - 1) % 4
        length_in = edges[incoming][3]
        if k in corners:
            p, q, r = corners[k]
            r = max(0.0, min(r, p, q))
            P(incoming, length_in - p, 0.0, 0.0)
            if r > _TOL:
                P(incoming, length_in - p, q - r, -_BULGE_90)
                P(incoming, length_in - p + r, q, 0.0)
            else:
                P(incoming, length_in - p, q, 0.0)
            P(k, q, 0.0, 0.0)
        elif rc > 0:
            P(incoming, length_in - rc, 0.0, _BULGE_90)
            P(k, rc, 0.0, 0.0)
        else:
            P(k, 0.0, 0.0, 0.0)

        t_min, t_max = start_extent(k), edges[k][3] - end_extent(k)
        prev_b = t_min
        for a, b, depth, r in sorted(edge_notches[k]):
            if a < prev_b - _TOL or b > t_max + _TOL:
                raise ValueError(
                    f"plate cutouts overlap on the outline (edge {k}, "
                    f"interval {a:.1f}..{b:.1f})"
                )
            prev_b = b
            r = max(0.0, min(r, depth, (b - a) / 2.0))
            P(k, a, 0.0, 0.0)
            if r > _TOL:
                P(k, a, depth - r, -_BULGE_90)
                P(k, a + r, depth, 0.0)
                P(k, b - r, depth, -_BULGE_90)
                P(k, b, depth - r, 0.0)
            else:
                P(k, a, depth, 0.0)
                P(k, b, depth, 0.0)
            P(k, b, 0.0, 0.0)

    return pts, interior


def _rounded_rect_points(u0: float, v0: float, u1: float, v1: float, r: float):
    w, h = u1 - u0, v1 - v0
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    if r <= _TOL:
        return [(u0, v0, 0), (u1, v0, 0), (u1, v1, 0), (u0, v1, 0)]
    return [
        (u0 + r, v0, 0), (u1 - r, v0, _BULGE_90),
        (u1, v0 + r, 0), (u1, v1 - r, _BULGE_90),
        (u1 - r, v1, 0), (u0 + r, v1, _BULGE_90),
        (u0, v1 - r, 0), (u0, v0 + r, _BULGE_90),
    ]


def write_panel_dxf(panel: Panel, path: Path) -> None:
    doc = ezdxf.new("R2000", setup=False)
    doc.header["$INSUNITS"] = 4  # millimetres
    msp = doc.modelspace()

    outline, interior = _plate_outline_points(
        panel.width, panel.height, panel.corner_radius, panel.cutouts
    )
    msp.add_lwpolyline(outline, format="xyb", close=True)
    for c in interior:
        msp.add_lwpolyline(
            _rounded_rect_points(c.u0, c.v0, c.u1, c.v1, c.radius),
            format="xyb",
            close=True,
        )
    for u, v, dia in panel.holes:
        msp.add_circle((u, v), dia / 2)

    doc.saveas(path)
