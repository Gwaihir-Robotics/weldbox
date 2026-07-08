"""Caster / leveling-foot plates — pure 2D/3D math, no CAD imports.

Square plates welded to the UNDERSIDE of the bottom frame (they occupy
z in [-thickness, 0]), flush with the box exterior: one in each corner by
default, plus optional pairs spaced along an axis for long spans
(`feet.mid`). Each plate carries the caster/foot mounting pattern centered
on the plate — 4 holes on a square pattern, or a single stem hole. The
plates are welded gussets: no rivet holes are cut into the tubes.

All plates are identical, so panel consolidation collapses them into one
flat part ("foot", qty N) for the vendor's multiples pricing.
"""

from __future__ import annotations

from ..spec import BoxSpec
from .layout import Panel

_DOWN = (0.0, 0.0, -1.0)
_MIN_EDGE = 4.0  # minimum web between a pattern hole edge and the plate edge


def plan_feet(spec: BoxSpec) -> list[Panel]:
    if spec.feet is None:
        return []
    feet = spec.feet
    W, D = spec.exterior.width, spec.exterior.depth
    a = feet.size

    if feet.corners and (2 * a > W or 2 * a > D):
        raise ValueError(
            f"feet: corner plates of {a:g}mm overlap on a "
            f"{W:g} x {D:g}mm footprint; use size <= {min(W, D) / 2:g}mm"
        )
    if not feet.corners and feet.mid is None:
        raise ValueError("feet: nothing to place (corners: false and no mid)")

    holes = _pattern_holes(feet, a)

    # plate min-corner positions (box coordinates, flush with the exterior)
    positions: list[tuple[float, float]] = []
    if feet.corners:
        positions += [(0.0, 0.0), (W - a, 0.0), (0.0, D - a), (W - a, D - a)]
    if feet.mid is not None:
        n = feet.mid.count
        for k in range(1, n + 1):
            if feet.mid.axis == "width":
                x = W * k / (n + 1) - a / 2
                positions += [(x, 0.0), (x, D - a)]
            else:  # along depth: pairs on the left/right edges
                y = D * k / (n + 1) - a / 2
                positions += [(0.0, y), (W - a, y)]

    panels = []
    for i, (x, y) in enumerate(sorted(positions), start=1):
        panels.append(
            Panel(
                name=f"foot-{i}",
                face="foot",
                width=a,
                height=a,
                thickness=feet.material.thickness,
                material=feet.material.alloy,
                qty=1,
                corner_radius=feet.corner_radius,
                holes=list(holes),
                origin3d=(x, y, 0.0),
                u_dir=(1.0, 0.0, 0.0),
                v_dir=(0.0, 1.0, 0.0),
                normal=_DOWN,
            )
        )
    return panels


def _pattern_holes(feet, a: float) -> list[tuple[float, float, float]]:
    p = feet.pattern
    if p.type == "single":
        return [(a / 2, a / 2, p.hole)]
    if p.spacing + p.hole + 2 * _MIN_EDGE > a:
        raise ValueError(
            f"feet.pattern: {p.spacing:g}mm square pattern with {p.hole:g}mm "
            f"holes does not fit a {a:g}mm plate (needs "
            f">= {p.spacing + p.hole + 2 * _MIN_EDGE:g}mm)"
        )
    c, s = a / 2, p.spacing / 2
    holes = [(c - s, c - s, p.hole), (c + s, c - s, p.hole),
             (c - s, c + s, p.hole), (c + s, c + s, p.hole)]
    if p.center_hole > 0:
        # default center hole so the same plate takes a bolt-on caster OR a
        # stem/leveling foot; corner-to-center distance must keep a web
        web = s * 2**0.5 - p.center_hole / 2 - p.hole / 2
        if web < _MIN_EDGE:
            raise ValueError(
                f"feet.pattern: {p.center_hole:g}mm center hole leaves only "
                f"{web:g}mm web to the {p.spacing:g}mm square pattern "
                f"(needs >= {_MIN_EDGE:g}mm); shrink it or set center_hole: 0"
            )
        holes.append((c, c, p.center_hole))
    return holes
