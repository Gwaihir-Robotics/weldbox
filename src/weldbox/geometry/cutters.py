"""Boolean cutter/trim solids for member features.

All solids are built in the member's local frame: cross-section centered on
the XY origin, member extruded 0..L along +Z (see features.py for the local
coordinate conventions). Cutters are grown EPS beyond the surfaces they cut
through so booleans never leave coplanar slivers.
"""

from __future__ import annotations

from build123d import Box, Cylinder, Pos, Rot, Part

from ..catalog import TubeProfile
from ..features import _FACE_LATERAL, _FACE_NORMAL, LocalFace, RivetHole, SlotFeature, TabFeature

EPS = 0.01


def _face_frame(profile: TubeProfile, face: LocalFace):
    """Returns (normal2d, lateral2d, half_size_along_normal, wall)."""
    n = _FACE_NORMAL[face]
    t = _FACE_LATERAL[face]
    half = profile.outer_w_mm / 2 if n[0] != 0 else profile.outer_h_mm / 2
    return n, t, half, profile.wall_mm


def _through_wall_prism(
    profile: TubeProfile, face: LocalFace, z: float, lateral: float,
    axial_size: float, lateral_size: float,
) -> Part:
    """Box passing through the near wall of `face`, centered at (z, lateral)
    in face coordinates; `axial_size` along the member axis, `lateral_size`
    across the face."""
    n, t, half, wall = _face_frame(profile, face)
    depth = wall + 2 * EPS
    center = (
        n[0] * (half - wall / 2) + t[0] * lateral,
        n[1] * (half - wall / 2) + t[1] * lateral,
        z,
    )
    if n[0] != 0:  # face normal along local x
        dims = (depth, lateral_size, axial_size)
    else:
        dims = (lateral_size, depth, axial_size)
    return Pos(*center) * Box(*dims)


def _through_wall_cylinder(
    profile: TubeProfile, face: LocalFace, z: float, lateral: float, radius: float
) -> Part:
    n, t, half, wall = _face_frame(profile, face)
    depth = wall + 2 * EPS
    center = (
        n[0] * (half - wall / 2) + t[0] * lateral,
        n[1] * (half - wall / 2) + t[1] * lateral,
        z,
    )
    rot = Rot(0, 90, 0) if n[0] != 0 else Rot(90, 0, 0)
    return Pos(*center) * rot * Cylinder(radius, depth)


def slot_cutter(profile: TubeProfile, slot: SlotFeature) -> Part:
    """Rectangular through-wall slot plus dog-bone relief cylinders at the
    four corners (PRD: corner relief prevents stress cracking)."""
    cutter = _through_wall_prism(
        profile, slot.face, slot.z, slot.lateral,
        axial_size=slot.width, lateral_size=slot.length,
    )
    if slot.dogbone_r > 0:
        for dz in (-slot.width / 2, slot.width / 2):
            for dl in (-slot.length / 2, slot.length / 2):
                cutter += _through_wall_cylinder(
                    profile, slot.face, slot.z + dz, slot.lateral + dl, slot.dogbone_r
                )
    return cutter


def rivet_hole_cutter(profile: TubeProfile, hole: RivetHole) -> Part:
    return _through_wall_cylinder(profile, hole.face, hole.z, hole.lateral, hole.dia / 2)


def end_trim(profile: TubeProfile, tabs: list[TabFeature], end: int, length: float) -> Part:
    """Trim solid for one member end: everything beyond the nominal end
    plane except the tab prisms. Subtracting this from an over-extruded
    member leaves a flush nominal end with only the tabs protruding —
    tabs are made by subtraction, never by union."""
    w, h = profile.outer_w_mm, profile.outer_h_mm
    extent = max((t.protrusion for t in tabs), default=0.0) + 1.0
    z_plane = length if end == 1 else 0.0
    sign = 1.0 if end == 1 else -1.0

    trim = Pos(0, 0, z_plane + sign * extent / 2) * Box(w + 4, h + 4, extent)
    for tab in tabs:
        n, t, half, wall = _face_frame(profile, tab.wall)
        depth = wall + 2 * EPS
        center = (
            n[0] * (half - wall / 2),
            n[1] * (half - wall / 2),
            z_plane + sign * tab.protrusion / 2,
        )
        if n[0] != 0:
            dims = (depth, tab.width, tab.protrusion)
        else:
            dims = (tab.width, depth, tab.protrusion)
        trim -= Pos(*center) * Box(*dims)
    return trim
