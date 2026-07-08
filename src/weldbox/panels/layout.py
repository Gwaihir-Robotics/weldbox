"""Sheet panel outlines and hole coordinates — pure 2D data.

Panels sit proud (riveted) on the outside of the frame, flush with the
frame exterior minus `siding.panel_margin` on each edge. Panel holes are
derived from the SAME RivetHole features planned on the tubes
(features.plan_rivet_holes), so tube and panel holes can never drift apart.

Panel face frames (u = panel width direction, v = panel height direction):
    left/right: u = depth (Y),  v = height (Z)
    front/back: u = width (X),  v = height (Z)
    top/bottom: u = width (X),  v = depth (Y)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..features import _FACE_LATERAL, _FACE_NORMAL, RivetHole
from ..frame import AXIS_DIR, LOCAL_BASIS, FrameGraph, Member
from ..spec import BoxSpec

Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class Cutout:
    """Rectangular cutout in panel coordinates (material removed), clipped to
    the panel outline. A side lying on the outline (u0 <= 0, v0 <= 0,
    u1 >= width, v1 >= height) makes the cutout an open corner/edge notch;
    `radius` is the concave inside-corner relief radius."""

    u0: float
    v0: float
    u1: float
    v1: float
    radius: float

    def key(self, decimals: int = 2) -> tuple:
        return tuple(round(v, decimals) for v in (self.u0, self.v0, self.u1, self.v1, self.radius))


@dataclass
class Panel:
    name: str
    face: str
    width: float  # along u
    height: float  # along v
    thickness: float
    material: str
    qty: int
    corner_radius: float = 0.0
    holes: list[tuple[float, float, float]] = field(default_factory=list)  # (u, v, dia)
    cutouts: list[Cutout] = field(default_factory=list)  # plate notches/holes
    # 3D placement (frame exterior corner of the panel, before margin)
    origin3d: Vec3 = (0.0, 0.0, 0.0)
    u_dir: Vec3 = (1.0, 0.0, 0.0)
    v_dir: Vec3 = (0.0, 0.0, 1.0)
    normal: Vec3 = (0.0, -1.0, 0.0)


def _face_frames(spec: BoxSpec) -> dict[str, dict]:
    W, D, H = spec.exterior.width, spec.exterior.depth, spec.exterior.height
    return {
        "left":   dict(origin=(0, 0, 0), u=(0, 1, 0), v=(0, 0, 1), n=(-1, 0, 0), w=D, h=H),
        "right":  dict(origin=(W, 0, 0), u=(0, 1, 0), v=(0, 0, 1), n=(1, 0, 0), w=D, h=H),
        "front":  dict(origin=(0, 0, 0), u=(1, 0, 0), v=(0, 0, 1), n=(0, -1, 0), w=W, h=H),
        "back":   dict(origin=(0, D, 0), u=(1, 0, 0), v=(0, 0, 1), n=(0, 1, 0), w=W, h=H),
        "bottom": dict(origin=(0, 0, 0), u=(1, 0, 0), v=(0, 1, 0), n=(0, 0, -1), w=W, h=D),
        "top":    dict(origin=(0, 0, H), u=(1, 0, 0), v=(0, 1, 0), n=(0, 0, 1), w=W, h=D),
    }


def hole_global_position(member: Member, hole: RivetHole) -> Vec3:
    """Global coordinates of a rivet hole center on the member's outer face."""
    n2 = _FACE_NORMAL[hole.face]
    t2 = _FACE_LATERAL[hole.face]
    half = member.profile.outer_w_mm / 2 if n2[0] != 0 else member.profile.outer_h_mm / 2
    local_x = n2[0] * half + t2[0] * hole.lateral
    local_y = n2[1] * half + t2[1] * hole.lateral
    lx_axis, ly_axis = LOCAL_BASIS[member.axis]
    lx, ly, lz = AXIS_DIR[lx_axis], AXIS_DIR[ly_axis], AXIS_DIR[member.axis]
    return tuple(
        member.origin[i] + lx[i] * local_x + ly[i] * local_y + lz[i] * hole.z
        for i in range(3)
    )


def consolidate_panels(panels: list[Panel], enabled: bool = True) -> list[Panel]:
    """Group congruent panels into unique flat parts (multiples discount).

    A flat sheet with through-holes can be flipped over or rotated 180 in
    plane, so two panels are the same part under any of the four transforms
    (u, v) -> (w - u | u, h - v | v). Panels of the same size/material are
    aligned under the transform that minimizes the union of their hole
    patterns; missing holes are added to each panel (sacrificial, riveted
    only where the tube behind has a matching hole) so the group collapses
    to one part. With `enabled` False only exactly-congruent panels merge.

    Returns unique panels (qty summed); the input panels' hole lists are
    updated in place so the assembly solids show the real cut pattern.

    Cutouts (plate notches) are structural, so they are never unioned: two
    plates only merge under a transform that maps one's cutouts exactly onto
    the other's.
    """

    def cutout_set(cutouts, w, h, mu, mv):
        out = set()
        for c in cutouts:
            u0, u1 = (w - c.u1, w - c.u0) if mu else (c.u0, c.u1)
            v0, v1 = (h - c.v1, h - c.v0) if mv else (c.v0, c.v1)
            out.add(tuple(round(x, 2) for x in (u0, v0, u1, v1, c.radius)))
        return out

    transforms = [(False, False), (True, False), (False, True), (True, True)]

    groups: dict[tuple, list[Panel]] = {}
    for p in panels:
        canonical = min(
            tuple(sorted(cutout_set(p.cutouts, p.width, p.height, mu, mv)))
            for mu, mv in transforms
        )
        key = (
            round(p.width, 2), round(p.height, 2), round(p.thickness, 3),
            p.material, round(p.corner_radius, 2), canonical,
        )
        groups.setdefault(key, []).append(p)

    def apply(holes, w, h, mu, mv):
        return {
            (round(w - u if mu else u, 2), round(h - v if mv else v, 2), round(d, 2))
            for u, v, d in holes
        }

    unique: list[Panel] = []
    for group in groups.values():
        group = sorted(group, key=lambda p: len(p.holes), reverse=True)
        ref = group[0]
        w, h = ref.width, ref.height
        ref_cutouts = cutout_set(ref.cutouts, w, h, False, False)
        part_holes = apply(ref.holes, w, h, False, False)
        placements = [(ref, False, False)]
        for p in group[1:]:
            best = None
            for mu, mv in transforms:
                if cutout_set(p.cutouts, w, h, mu, mv) != ref_cutouts:
                    continue  # cutouts must coincide exactly
                mapped = apply(p.holes, w, h, mu, mv)
                union = part_holes | mapped
                if not enabled and len(union) > max(len(part_holes), len(mapped)):
                    continue  # only exact merges allowed
                if _holes_conflict(union):
                    continue
                if best is None or len(union) < best[0]:
                    best = (len(union), mu, mv, union)
            if best is None:
                unique.append(p)
                continue
            _, mu, mv, part_holes = best
            placements.append((p, mu, mv))

        for p, mu, mv in placements:  # transforms are involutions
            p.holes = sorted(apply(part_holes, w, h, mu, mv))
        ref.qty = len(placements)
        names = [p.name for p, _, _ in placements]
        # numbered twins ("foot-1".."foot-6") collapse to their stem
        stems = {n.rsplit("-", 1)[0] for n in names
                 if "-" in n and n.rsplit("-", 1)[1].isdigit()}
        if len(names) > 1 and len(stems) == 1 and all(
            "-" in n and n.rsplit("-", 1)[1].isdigit() for n in names
        ):
            ref.name = stems.pop()
        else:
            ref.name = "-".join(names)
        unique.append(ref)
    return sorted(unique, key=lambda p: p.name)


def _holes_conflict(holes, min_web: float = 2.0) -> bool:
    hs = sorted(holes)
    for i, (u1, v1, d1) in enumerate(hs):
        for u2, v2, d2 in hs[i + 1:]:
            if u2 - u1 > d1 / 2 + d2 / 2 + min_web:
                break
            if ((u1 - u2) ** 2 + (v1 - v2) ** 2) ** 0.5 < d1 / 2 + d2 / 2 + min_web:
                return True
    return False


def panel_layouts(
    frame: FrameGraph,
    spec: BoxSpec,
    hole_map: dict[str, list[tuple[Member, RivetHole]]],
) -> list[Panel]:
    assert spec.siding is not None
    margin = spec.siding.panel_margin
    frames = _face_frames(spec)
    panels: list[Panel] = []
    for pspec in spec.siding.panels:
        for face in pspec.faces:
            f = frames[face]
            origin = tuple(
                f["origin"][i] + f["u"][i] * margin + f["v"][i] * margin for i in range(3)
            )
            panel = Panel(
                name=face,
                face=face,
                width=f["w"] - 2 * margin,
                height=f["h"] - 2 * margin,
                thickness=pspec.material.thickness,
                material=pspec.material.alloy,
                qty=1,
                corner_radius=spec.siding.corner_radius,
                origin3d=origin,
                u_dir=f["u"],
                v_dir=f["v"],
                normal=f["n"],
            )
            for member, hole in hole_map.get(face, []):
                p = hole_global_position(member, hole)
                u = sum((p[i] - origin[i]) * f["u"][i] for i in range(3))
                v = sum((p[i] - origin[i]) * f["v"][i] for i in range(3))
                panel.holes.append((u, v, hole.dia))
            panels.append(panel)
    return panels
