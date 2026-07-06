"""Part-count consolidation: add sacrificial slots/holes so near-identical
members become the SAME stock part.

Members that share a profile and cut length often differ only in which
faces carry slots or rivet holes (e.g. the two front posts lack the
front-face rivet holes the back posts have). For each (profile, length)
group this pass aligns every member to a reference via the square-tube
symmetry group, unions the feature sets, and writes the union back to each
member — so all of them collapse to one part in dedupe. The extra features
are cosmetic through-wall cuts (unused slots or holes); they never remove a
tab and never overlap an existing feature.

Alignment is chosen greedily to minimize the union size. A member whose
best alignment would still create overlapping features is left out of the
group and keeps its own part.
"""

from __future__ import annotations

from .features import (
    Feature,
    RivetHole,
    SlotFeature,
    TabFeature,
    feature_key,
    inverse_transform,
    transform_feature,
)
from .frame import FrameGraph, Member

# minimum web of material left between neighboring features
_CLEARANCE = 0.5


def consolidate_parts(frame: FrameGraph) -> dict[str, int]:
    """Union features across same-profile/same-length members. Returns
    {member_id: number_of_added_features} for reporting."""
    from .dedupe import ALL_TRANSFORMS

    groups: dict[tuple, list[Member]] = {}
    for m in frame.members:
        groups.setdefault((m.profile.id, round(m.length, 2)), []).append(m)

    added: dict[str, int] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        # richest feature set first: it anchors the reference frame
        members = sorted(members, key=lambda m: len(m.features), reverse=True)
        ref = members[0]
        part_feats: dict[tuple, Feature] = {
            feature_key(f): f for f in ref.features
        }
        placements: list[tuple[Member, int, bool]] = [(ref, 0, False)]

        for m in members[1:]:
            best = None  # (union_size, q, flipped, mapped_feats)
            for q, flipped in ALL_TRANSFORMS:
                mapped = {
                    feature_key(tf): tf
                    for tf in (
                        transform_feature(f, m.length, q, flipped) for f in m.features
                    )
                }
                union = {**part_feats, **mapped}
                if _has_conflict(union.values()):
                    continue
                if best is None or len(union) < best[0]:
                    best = (len(union), q, flipped, union)
            if best is None:
                continue  # keeps its own part
            _, q, flipped, union = best
            part_feats = union
            placements.append((m, q, flipped))

        for m, q, flipped in placements:
            iq, iflip = inverse_transform(q, flipped)
            new_features = [
                transform_feature(f, m.length, iq, iflip) for f in part_feats.values()
            ]
            n_added = len(new_features) - len(m.features)
            if n_added:
                added[m.id] = n_added
            m.features = new_features
    return added


def _footprint(f: Feature) -> tuple[str, float, float, float, float] | None:
    """(face, z_min, z_max, lat_min, lat_max) of a cut feature, or None for
    tabs (tabs live on end planes; identical tabs merge by key)."""
    if isinstance(f, SlotFeature):
        dz = f.width / 2 + f.dogbone_r
        dl = f.length / 2 + f.dogbone_r
        return (f.face, f.z - dz, f.z + dz, f.lateral - dl, f.lateral + dl)
    if isinstance(f, RivetHole):
        r = f.dia / 2
        return (f.face, f.z - r, f.z + r, f.lateral - r, f.lateral + r)
    return None


def _has_conflict(features) -> bool:
    """True if any two distinct cut features on the same face overlap (with
    a small clearance web), or a cut crosses a tab's protruding wall."""
    boxes = [fp for f in features if (fp := _footprint(f)) is not None]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if a[0] != b[0]:
                continue
            if (
                a[1] < b[2] + _CLEARANCE
                and b[1] < a[2] + _CLEARANCE
                and a[3] < b[4] + _CLEARANCE
                and b[3] < a[4] + _CLEARANCE
            ):
                return True
    return False
