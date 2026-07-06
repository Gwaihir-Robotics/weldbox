"""Feature planning: tabs, slots, dog-bones, rivet holes as pure data.

No CAD imports — geometry/ consumes these; dedupe canonicalizes them.

Member-local coordinates
    (x, y): cross-section plane, origin at the tube centerline. The mapping
    of local x/y to global axes is LOCAL_BASIS in frame.py.
    z: along the member, 0 at Member.origin, L at the far end.
    Faces are named by outward normal: "+x", "-x", "+y", "-y".

Tab/slot design (through_wall_tab, per PRD best practices)
    At a tee joint the tab member's end grows TWO tabs, one from each of
    the walls whose normals are parallel to the slot member's axis. Each
    tab is the wall's own material: `wall_A` thick, `tab_width` wide
    (tab_width_fraction x the receiving face's flat width, so it lands
    between the corner radii), protruding `wall_B` so it welds flush with
    the far side of the receiving wall. The receiving face gets one slot
    per tab: length = tab_width + clearance (along the direction
    perpendicular to both members), width = wall_A + clearance (along the
    slot member's axis), dog-bone relief circles at the corners.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .frame import AXIS_DIR, LOCAL_BASIS, Axis, FaceDir, FrameGraph, Joint, Member
from .spec import BoxSpec

LocalFace = Literal["+x", "-x", "+y", "-y"]

# outward normal of a local face in local (x, y)
_FACE_NORMAL: dict[LocalFace, tuple[float, float]] = {
    "+x": (1.0, 0.0),
    "-x": (-1.0, 0.0),
    "+y": (0.0, 1.0),
    "-y": (0.0, -1.0),
}
# lateral (in-face, cross-member) direction for each face: z_hat x normal
_FACE_LATERAL: dict[LocalFace, tuple[float, float]] = {
    "+x": (0.0, 1.0),
    "-x": (0.0, -1.0),
    "+y": (-1.0, 0.0),
    "-y": (1.0, 0.0),
}


@dataclass(frozen=True)
class TabFeature:
    """End tab: the wall named by `wall` keeps `protrusion` mm of extra
    length at member end `end`; the rest of the end face is trimmed back to
    nominal. Tab is centered on the wall, `width` mm across."""

    end: Literal[0, 1]
    wall: LocalFace
    width: float
    protrusion: float


@dataclass(frozen=True)
class SlotFeature:
    """Through-wall slot on face `face`, centered at (z, lateral) in face
    coordinates (lateral measured from the face center along _FACE_LATERAL).
    `length` runs along the lateral direction, `width` along the member
    axis. Dog-bone relief circles of `dogbone_r` at the four corners."""

    face: LocalFace
    z: float
    lateral: float
    length: float
    width: float
    dogbone_r: float


@dataclass(frozen=True)
class RivetHole:
    """Through-near-wall hole on face `face` at (z, lateral)."""

    face: LocalFace
    z: float
    lateral: float
    dia: float


Feature = TabFeature | SlotFeature | RivetHole

# face maps for the square-tube symmetry group (dihedral D4):
# rotation by +90 deg about local z, and end-for-end flip (180 about local x)
ROT_FACE: dict[LocalFace, LocalFace] = {"+x": "+y", "+y": "-x", "-x": "-y", "-y": "+x"}
FLIP_FACE: dict[LocalFace, LocalFace] = {"+x": "+x", "-x": "-x", "+y": "-y", "-y": "+y"}


def transform_feature(f: Feature, length: float, quarter_turns: int, flipped: bool) -> Feature:
    """Return `f` under a square-tube symmetry: flip first (ends swap,
    z -> L - z, lateral negates, +-y faces swap), then rotate about the
    member axis in 90 degree steps (faces cycle, z/lateral unchanged —
    a rotated face's lateral axis is the rotation of the original's)."""

    def rot(face: LocalFace) -> LocalFace:
        for _ in range(quarter_turns % 4):
            face = ROT_FACE[face]
        return face

    if isinstance(f, TabFeature):
        end, wall = f.end, f.wall
        if flipped:
            end, wall = 1 - end, FLIP_FACE[wall]
        return TabFeature(end=end, wall=rot(wall), width=f.width, protrusion=f.protrusion)

    face, z, lateral = f.face, f.z, f.lateral
    if flipped:
        face, z, lateral = FLIP_FACE[face], length - z, -lateral
    face = rot(face)
    if isinstance(f, SlotFeature):
        return SlotFeature(face=face, z=z, lateral=lateral, length=f.length,
                           width=f.width, dogbone_r=f.dogbone_r)
    return RivetHole(face=face, z=z, lateral=lateral, dia=f.dia)


def inverse_transform(quarter_turns: int, flipped: bool) -> tuple[int, bool]:
    """Inverse of (rotate after flip) in the dihedral group: with T = R^q F^s,
    T^-1 = R^(-q) if s == 0 else R^q F (since F R^a = R^-a F)."""
    if flipped:
        return quarter_turns % 4, True
    return (-quarter_turns) % 4, False


def feature_key(f: Feature, decimals: int = 2) -> tuple:
    """Hashable geometric identity of a feature (member-local frame)."""
    r = lambda v: round(v, decimals)
    if isinstance(f, TabFeature):
        return ("tab", f.end, f.wall, r(f.width), r(f.protrusion))
    if isinstance(f, SlotFeature):
        return ("slot", f.face, r(f.z), r(f.lateral), r(f.length), r(f.width), r(f.dogbone_r))
    return ("hole", f.face, r(f.z), r(f.lateral), r(f.dia))


def global_dir_to_local_face(member_axis: Axis, direction: tuple[float, float, float]) -> LocalFace:
    """Map a global unit direction (perpendicular to the member axis) to the
    member-local face whose outward normal points that way."""
    lx_axis, ly_axis = LOCAL_BASIS[member_axis]
    lx = AXIS_DIR[lx_axis]
    ly = AXIS_DIR[ly_axis]
    dot_x = sum(a * b for a, b in zip(direction, lx))
    dot_y = sum(a * b for a, b in zip(direction, ly))
    if abs(dot_x) > 0.5:
        return "+x" if dot_x > 0 else "-x"
    if abs(dot_y) > 0.5:
        return "+y" if dot_y > 0 else "-y"
    raise ValueError(f"direction {direction} is not perpendicular to axis {member_axis}")


def _face_dir_to_vec(face: FaceDir) -> tuple[float, float, float]:
    sign = 1.0 if face[0] == "+" else -1.0
    base = AXIS_DIR[face[1]]  # type: ignore[index]
    return (base[0] * sign, base[1] * sign, base[2] * sign)


def flat_width(profile) -> float:
    """Flat width of a tube face between the corner radii."""
    return profile.outer_w_mm - 2.0 * profile.corner_r_resolved_mm


def plan_joint_features(frame: FrameGraph, spec: BoxSpec) -> None:
    """Populate member.features with tabs and slots for all applicable joints."""
    if spec.joints.style == "plain_butt":
        return
    for joint in frame.joints:
        if joint.kind == "corner_butt" and not spec.joints.corner_tabs:
            continue
        _plan_tab_slot(frame, spec, joint)


def _plan_tab_slot(frame: FrameGraph, spec: BoxSpec, joint: Joint) -> None:
    a = frame.member(joint.tab_member)  # tab member
    b = frame.member(joint.slot_member)  # slot member
    if a.axis == b.axis:
        raise ValueError(f"joint {joint} connects parallel members; unsupported")

    cfg = spec.joints
    wall_a = a.profile.wall_mm
    wall_b = b.profile.wall_mm
    s_a = a.profile.outer_w_mm

    # direction perpendicular to both member axes ("cross direction"):
    # the tab width and slot length run along it.
    cross_axis: Axis = next(ax for ax in ("x", "y", "z") if ax not in (a.axis, b.axis))

    # tab width sized to the receiving face's flat region, also clamped to
    # the tab member's own flat width (same formula when profiles match)
    width_limit = min(flat_width(b.profile), flat_width(a.profile))
    tab_width = cfg.tab_width_fraction * width_limit

    # tab member: two tabs, on the walls whose normals are +/- b.axis
    b_dir = AXIS_DIR[b.axis]
    for sign in (1.0, -1.0):
        direction = (b_dir[0] * sign, b_dir[1] * sign, b_dir[2] * sign)
        wall = global_dir_to_local_face(a.axis, direction)
        a.features.append(
            TabFeature(end=joint.tab_end, wall=wall, width=tab_width, protrusion=wall_b)
        )

    # slot member: one slot per tab, offset along b's axis by the distance
    # from the joint center to each tab wall's mid-plane
    slot_face = global_dir_to_local_face(b.axis, _face_dir_to_vec(joint.slot_face))
    # lateral coordinate of the tab member's centerline on the receiving
    # face: the members' centerlines intersect for all frame joints -> 0.
    for sign in (1.0, -1.0):
        b.features.append(
            SlotFeature(
                face=slot_face,
                z=joint.position_mm + sign * (s_a - wall_a) / 2.0,
                lateral=0.0,
                length=tab_width + cfg.slot_clearance,
                width=wall_a + cfg.slot_clearance,
                dogbone_r=cfg.dogbone_radius,
            )
        )


def plan_rivet_holes(frame: FrameGraph, spec: BoxSpec) -> dict[str, list[tuple[Member, RivetHole]]]:
    """Add rivet holes to every member whose outward face is coplanar with a
    sided box face. Returns {box_face: [(member, hole), ...]} so the panel
    layout uses the *same* holes (single source of truth).
    """
    if spec.siding is None or not spec.siding.panels:
        return {}
    att = spec.siding.attachment
    dia = att.rivet + att.hole_clearance
    ext = spec.exterior

    # box face -> (outward normal, plane coordinate)
    planes: dict[str, tuple[tuple[float, float, float], float]] = {
        "left": ((-1, 0, 0), 0.0),
        "right": ((1, 0, 0), ext.width),
        "front": ((0, -1, 0), 0.0),
        "back": ((0, 1, 0), ext.depth),
        "bottom": ((0, 0, -1), 0.0),
        "top": ((0, 0, 1), ext.height),
    }
    sided = [f for p in spec.siding.panels for f in p.faces]

    result: dict[str, list[tuple[Member, RivetHole]]] = {f: [] for f in sided}
    for face_name in sided:
        normal, plane = planes[face_name]
        axis_i = next(i for i, c in enumerate(normal) if c != 0)
        for m in frame.members:
            if AXIS_DIR[m.axis][axis_i] != 0:
                continue  # member runs into the face, not along it
            # member's outer surface coordinate on this normal axis
            center = m.origin[axis_i]
            outer = center + normal[axis_i] * (m.profile.outer_w_mm / 2.0)
            if abs(outer - plane) > 0.01:
                continue
            local_face = global_dir_to_local_face(m.axis, normal)  # type: ignore[arg-type]
            for z in _hole_positions(m.length, att.spacing):
                hole = RivetHole(face=local_face, z=z, lateral=0.0, dia=dia)
                m.features.append(hole)
                result[face_name].append((m, hole))
    return result


def _hole_positions(length: float, spacing: float, min_edge: float = 20.0) -> list[float]:
    """Evenly pitched hole centers along a member, symmetric about its
    middle: as many holes at `spacing` pitch as fit with `min_edge` end
    margin; a single centered hole if the member is too short for two."""
    usable = length - 2.0 * min_edge
    if usable < spacing:
        return [length / 2.0]
    n = int(usable // spacing) + 1
    run = (n - 1) * spacing
    start = (length - run) / 2.0
    return [start + k * spacing for k in range(n)]


def plan_features(frame: FrameGraph, spec: BoxSpec) -> dict[str, list[tuple[Member, RivetHole]]]:
    """Run all feature planning. Returns the per-box-face rivet hole map
    (consumed by panels.layout)."""
    plan_joint_features(frame, spec)
    return plan_rivet_holes(frame, spec)
