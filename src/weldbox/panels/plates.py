"""Deck plates: laser-cut sheet resting on top of a horizontal layer.

Pure 2D/3D math, no CAD imports. A plate covers the layer's footprint
(exterior minus `margin` per edge) and sits on the top faces of the layer's
horizontal members. Two feature families come out of it:

- Cutouts: every vertical member (post, support) whose z-extent passes
  through the plate slab gets a rectangular cutout of its tube footprint
  plus `post_clearance`, clipped to the outline — a corner notch at the
  posts, an edge notch at perimeter supports, a rounded interior hole for
  anything mid-plate. The concave relief radius matches the tube's outer
  corner radius so the notch wraps the tube profile.

- Rivet holes into the top face of every member whose top surface is
  coplanar with the plate underside (rails, cross members, spanners on the
  layer). Hole positions that fall inside a cutout, or closer to it than a
  minimum web, are skipped on the tube too so the pair never drifts apart.

Must run BEFORE consolidate_parts so the planned tube holes participate in
part consolidation.
"""

from __future__ import annotations

from ..features import RivetHole, _hole_positions, global_dir_to_local_face
from ..frame import FrameGraph
from ..spec import BoxSpec, PlateSpec
from .layout import Cutout, Panel, hole_global_position

_UP = (0.0, 0.0, 1.0)
_EPS = 0.01
_MIN_WEB = 2.0  # minimum sheet web between a hole edge and a cutout


def plan_plates(frame: FrameGraph, spec: BoxSpec) -> list[Panel]:
    return [_plan_plate(frame, spec, p) for p in spec.plates]


def _plan_plate(frame: FrameGraph, spec: BoxSpec, plate: PlateSpec) -> Panel:
    try:
        layer = frame.layers[plate.layer]
    except KeyError:
        raise LookupError(
            f"plate 'layer: {plate.layer}' does not name a layer; "
            f"available: {', '.join(sorted(frame.layers))}"
        ) from None

    s = frame.profile.outer_w_mm
    z_plate = layer.z_center + s / 2.0  # plate underside = layer top face
    t = plate.material.thickness
    m0 = plate.margin
    w = spec.exterior.width - 2.0 * m0
    h = spec.exterior.depth - 2.0 * m0
    if w <= 0 or h <= 0:
        raise ValueError(
            f"plate on {plate.layer!r}: margin {m0:g}mm leaves no material "
            f"({spec.exterior.width:g} x {spec.exterior.depth:g}mm exterior)"
        )
    origin = (m0, m0, z_plate)

    cutouts = _plate_cutouts(frame, plate, origin, w, h, z_plate, t)

    panel = Panel(
        name=f"{plate.layer}-plate",
        face=f"plate:{plate.layer}",
        width=w,
        height=h,
        thickness=t,
        material=plate.material.alloy,
        qty=1,
        corner_radius=plate.corner_radius,
        cutouts=cutouts,
        origin3d=origin,
        u_dir=(1.0, 0.0, 0.0),
        v_dir=(0.0, 1.0, 0.0),
        normal=_UP,
    )

    att = plate.attachment
    dia = att.rivet + att.hole_clearance
    edge_keepout = dia / 2.0 + _MIN_WEB
    for m in frame.members:
        if m.axis == "z":
            continue
        top = m.origin[2] + m.profile.outer_w_mm / 2.0
        if abs(top - z_plate) > _EPS:
            continue  # not supporting this plate
        local_face = global_dir_to_local_face(m.axis, _UP)
        for z in _hole_positions(m.length, att.spacing):
            hole = RivetHole(face=local_face, z=z, lateral=0.0, dia=dia)
            g = hole_global_position(m, hole)
            u, v = g[0] - origin[0], g[1] - origin[1]
            if not (edge_keepout <= u <= w - edge_keepout
                    and edge_keepout <= v <= h - edge_keepout):
                continue
            if any(_hole_hits_cutout(u, v, dia, c) for c in cutouts):
                continue
            m.features.append(hole)
            panel.holes.append((u, v, dia))
    return panel


def _plate_cutouts(
    frame: FrameGraph,
    plate: PlateSpec,
    origin: tuple[float, float, float],
    w: float,
    h: float,
    z_plate: float,
    thickness: float,
) -> list[Cutout]:
    gap = plate.post_clearance
    cutouts: list[Cutout] = []
    for m in frame.members:
        if m.axis != "z":
            continue
        z0, z1 = m.origin[2], m.origin[2] + m.length
        if z0 >= z_plate + thickness - _EPS or z1 <= z_plate + _EPS:
            continue  # does not pass through the plate slab
        hw = m.profile.outer_w_mm / 2.0 + gap
        hh = m.profile.outer_h_mm / 2.0 + gap
        cu, cv = m.origin[0] - origin[0], m.origin[1] - origin[1]
        u0, v0 = max(cu - hw, 0.0), max(cv - hh, 0.0)
        u1, v1 = min(cu + hw, w), min(cv + hh, h)
        if u1 - u0 < _EPS or v1 - v0 < _EPS:
            continue  # entirely outside the plate (large margin)
        cutouts.append(
            Cutout(u0=u0, v0=v0, u1=u1, v1=v1, radius=m.profile.corner_r_resolved_mm)
        )
    return sorted(cutouts, key=lambda c: (c.u0, c.v0))


def _hole_hits_cutout(u: float, v: float, dia: float, c: Cutout) -> bool:
    margin = dia / 2.0 + _MIN_WEB
    return (
        c.u0 - margin <= u <= c.u1 + margin
        and c.v0 - margin <= v <= c.v1 + margin
    )
