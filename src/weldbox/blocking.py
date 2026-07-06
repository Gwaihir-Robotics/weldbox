"""Expand blocking primitives (level / supports / spanner) into frame members.

See frame.py module docstring for the placement conventions.
"""

from __future__ import annotations

from .frame import FrameBuilder, Layer, Member
from .spec import BlockingItem, LevelSpec, SpannerSpec, SupportsSpec


def expand_blocking(b: FrameBuilder, items: list[BlockingItem]) -> None:
    spanner_counts = {"top": 0, "bottom": 0}
    for item in items:
        if isinstance(item, LevelSpec):
            _expand_level(b, item)
        elif isinstance(item, SupportsSpec):
            _expand_supports(b, item)
        elif isinstance(item, SpannerSpec):
            _expand_spanner(b, item, spanner_counts)
        else:  # pragma: no cover
            raise TypeError(f"unknown blocking item {item!r}")


def _level_z_center(b: FrameBuilder, item: LevelSpec) -> float:
    half = b.s / 2
    if item.height_ref == "top_face":
        return item.height - half
    if item.height_ref == "bottom_face":
        return item.height + half
    return item.height  # centerline


def _validate_level_height(b: FrameBuilder, item: LevelSpec, name: str, z_center: float) -> None:
    """A level's rails must clear both the base and top layers. Report the
    violation in the user's own terms (their height + height_ref) with the
    valid range for this box."""
    lo_center, hi_center = 1.5 * b.s, b.H - 1.5 * b.s
    if lo_center <= z_center <= hi_center:
        return
    ref_offset = {"top_face": b.s / 2, "centerline": 0.0, "bottom_face": -b.s / 2}[
        item.height_ref
    ]
    lo, hi = lo_center + ref_offset, hi_center + ref_offset
    where = (
        f"is above the box (exterior height {b.H:g}mm)"
        if item.height > b.H
        else "collides with the base or top frame"
    )
    hint = (
        " The top frame already provides a surface at the exterior height."
        if z_center > hi_center
        else ""
    )
    raise ValueError(
        f"level {name!r}: height {item.height:g}mm ({item.height_ref}) {where}. "
        f"With {b.s:g}mm tube and a {b.H:g}mm tall box, a level's height "
        f"({item.height_ref}) must be between {lo:g}mm and {hi:g}mm.{hint}"
    )


def _expand_level(b: FrameBuilder, item: LevelSpec) -> None:
    name = item.name or f"level@{item.height:g}"
    z_center = _level_z_center(b, item)
    _validate_level_height(b, item, name, z_center)
    layer = b.build_layer(name, z_center, "tee")

    if item.cross_members is None:
        return
    n = item.cross_members.count
    s, wg = b.s, b.wg
    if item.cross_members.axis == "depth":
        # members along Y, butted between the layer's front and back rails,
        # evenly spaced across the exterior width
        for k in range(1, n + 1):
            x = b.W * k / (n + 1)
            m = b.add_member(
                Member(
                    id=f"{name}-cross-{k}",
                    role="cross",
                    profile=b.profile,
                    axis="y",
                    origin=(x, s + wg, z_center),
                    length=b.D - 2 * s - 2 * wg,
                )
            )
            b._butt("tee", m.id, 0, layer.rails["front"], "+y", x)
            b._butt("tee", m.id, 1, layer.rails["back"], "-y", x)
    else:  # axis == "width": members along X between left and right rails
        for k in range(1, n + 1):
            y = b.D * k / (n + 1)
            m = b.add_member(
                Member(
                    id=f"{name}-cross-{k}",
                    role="cross",
                    profile=b.profile,
                    axis="x",
                    origin=(s + wg, y, z_center),
                    length=b.W - 2 * s - 2 * wg,
                )
            )
            b._butt("tee", m.id, 0, layer.rails["left"], "+x", y)
            b._butt("tee", m.id, 1, layer.rails["right"], "-x", y)


def _resolve_layer(b: FrameBuilder, ref: str) -> Layer:
    if ref in b.layers:
        return b.layers[ref]
    raise LookupError(
        f"unknown layer {ref!r} in supports.between; "
        f"available: {', '.join(sorted(b.layers))}"
    )


def _expand_supports(b: FrameBuilder, item: SupportsSpec) -> None:
    lo, hi = sorted((_resolve_layer(b, r) for r in item.between), key=lambda l: l.z_center)
    s, wg = b.s, b.wg
    z0 = lo.z_center + s / 2 + wg  # top face of lower rails
    z1 = hi.z_center - s / 2 - wg  # bottom face of upper rails
    length = z1 - z0
    if length <= 0:
        raise ValueError(f"supports between {lo.name!r} and {hi.name!r} have no span")

    # one support at the midpoint of each of the 4 rail pairs
    half = s / 2
    positions = {
        "front": (b.W / 2, half),
        "back": (b.W / 2, b.D - half),
        "left": (half, b.D / 2),
        "right": (b.W - half, b.D / 2),
    }
    for key, (x, y) in positions.items():
        m = b.add_member(
            Member(
                id=f"support-{lo.name}-{hi.name}-{key}",
                role="support",
                profile=b.profile,
                axis="z",
                origin=(x, y, z0),
                length=length,
            )
        )
        mid = b.W / 2 if key in ("front", "back") else b.D / 2
        b._butt("tee", m.id, 0, lo.rails[key], "+z", mid)
        b._butt("tee", m.id, 1, hi.rails[key], "-z", mid)


def _expand_spanner(b: FrameBuilder, item: SpannerSpec, counts: dict[str, int]) -> None:
    s, wg = b.s, b.wg
    fractions = (
        [item.position]
        if item.count == 1
        else [k / (item.count + 1) for k in range(1, item.count + 1)]
    )
    for face in item.face:
        layer = _resolve_layer(b, {"top": "top", "bottom": "base"}[face])
        for fraction in fractions:
            counts[face] += 1
            name = f"{face}-spanner-{counts[face]}"
            if item.axis == "width":
                # along X at a fraction of the depth, between left/right rails
                y = b.D * fraction
                m = b.add_member(
                    Member(
                        id=name,
                        role="spanner",
                        profile=b.profile,
                        axis="x",
                        origin=(s + wg, y, layer.z_center),
                        length=b.W - 2 * s - 2 * wg,
                    )
                )
                b._butt("tee", m.id, 0, layer.rails["left"], "+x", y)
                b._butt("tee", m.id, 1, layer.rails["right"], "-x", y)
            else:  # axis == "depth": along Y between front/back rails
                x = b.W * fraction
                m = b.add_member(
                    Member(
                        id=name,
                        role="spanner",
                        profile=b.profile,
                        axis="y",
                        origin=(x, s + wg, layer.z_center),
                        length=b.D - 2 * s - 2 * wg,
                    )
                )
                b._butt("tee", m.id, 0, layer.rails["front"], "+y", x)
                b._butt("tee", m.id, 1, layer.rails["back"], "-y", x)
