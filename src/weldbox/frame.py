"""BoxSpec -> FrameGraph: members (centerline + length) and joints.

Pure math — no CAD imports. All coordinates in mm.

Box coordinate frame
    X = width  (0 .. W), "left" face at x=0, "right" at x=W
    Y = depth  (0 .. D), "front" face at y=0, "back" at y=D
    Z = height (0 .. H), "bottom" at z=0, "top" at z=H
Origin is the bottom-front-left *outer* corner of the box.

Placement conventions (these resolve the PRD's ambiguities)
    - full_height_posts: the 4 vertical posts run the full height; all
      horizontal rails butt between posts (rail length = span - 2 x tube).
    - top_bottom_frames: the top and bottom frames' front/back rails run
      solid across the full exterior WIDTH; the depth rails butt between
      them, and the posts butt up into the frames (post length =
      height - 2 x tube), tabbing into the full-width rails.
    - A "layer" is a horizontal perimeter frame: base, top, or a blocking
      level. Every layer has front/back rails (along X) and left/right
      rails (along Y) butted between the posts.
    - level height_ref=top_face: the level's top surface sits at the given
      height (it is a work surface).
    - Cross members butt between a layer's front and back rails, at
      positions k/(count+1) across the exterior width.
    - Supports stand at the midpoint of each of the 4 rail pairs of the
      two layers they connect, butting between the lower rails' top faces
      and the upper rails' bottom faces.
    - Spanners butt between the two rails of a face that are perpendicular
      to the spanner's axis, at `position` (fraction) across the face.
    - weld_gap (default 0) shortens every butting end by that amount.

Member local frame (used later for feature/geometry placement): the member
is extruded along its global `axis` from `origin`; local +Z = axis
direction, and local (x, y) map to the remaining global axes right-handed:
    axis x: local x -> +Y, local y -> +Z
    axis y: local x -> +Z, local y -> +X
    axis z: local x -> +X, local y -> +Y
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .catalog import Catalog, TubeProfile
from .spec import BoxSpec

Axis = Literal["x", "y", "z"]
FaceDir = Literal["+x", "-x", "+y", "-y", "+z", "-z"]

AXIS_INDEX: dict[Axis, int] = {"x": 0, "y": 1, "z": 2}
AXIS_DIR: dict[Axis, tuple[float, float, float]] = {
    "x": (1.0, 0.0, 0.0),
    "y": (0.0, 1.0, 0.0),
    "z": (0.0, 0.0, 1.0),
}
# member local basis (local_x, local_y) expressed as global axes
LOCAL_BASIS: dict[Axis, tuple[Axis, Axis]] = {
    "x": ("y", "z"),
    "y": ("z", "x"),
    "z": ("x", "y"),
}


@dataclass
class Member:
    id: str
    role: str  # post | rail | level_rail | cross | support | spanner
    profile: TubeProfile
    axis: Axis
    origin: tuple[float, float, float]  # centerline start (min-coordinate end)
    length: float
    features: list = field(default_factory=list)  # populated by features.plan_features

    @property
    def end(self) -> tuple[float, float, float]:
        d = AXIS_DIR[self.axis]
        return (
            self.origin[0] + d[0] * self.length,
            self.origin[1] + d[1] * self.length,
            self.origin[2] + d[2] * self.length,
        )

    def axis_coord(self, point_on_axis: float) -> float:
        """Distance along the member from its origin for a global coordinate."""
        return point_on_axis - self.origin[AXIS_INDEX[self.axis]]


@dataclass
class Joint:
    """A butting connection: `tab_member`'s end lands on `slot_member`'s face.

    kind "tee" gets tab/slot features when joints.style == through_wall_tab;
    "corner_butt" only when joints.corner_tabs is enabled.
    slot_face: outward normal of the receiving face, in global directions.
    position_mm: centerline distance along slot_member (from its origin) of
    the joint center.
    """

    kind: Literal["tee", "corner_butt"]
    tab_member: str
    tab_end: Literal[0, 1]
    slot_member: str
    slot_face: FaceDir
    position_mm: float


@dataclass
class Layer:
    name: str
    z_center: float
    rails: dict[str, str]  # "front"|"back"|"left"|"right" -> member id


@dataclass
class FrameGraph:
    spec: BoxSpec
    profile: TubeProfile
    members: list[Member]
    joints: list[Joint]
    layers: dict[str, Layer]

    def member(self, member_id: str) -> Member:
        for m in self.members:
            if m.id == member_id:
                return m
        raise KeyError(member_id)


class FrameBuilder:
    def __init__(self, spec: BoxSpec, profile: TubeProfile):
        if profile.shape != "square":
            raise NotImplementedError(
                f"frame topology math currently supports square tube only, got {profile.shape}"
            )
        self.spec = spec
        self.profile = profile
        self.s = profile.outer_w_mm  # tube outer size
        self.W = spec.exterior.width
        self.D = spec.exterior.depth
        self.H = spec.exterior.height
        self.wg = spec.joints.weld_gap
        self.members: list[Member] = []
        self.joints: list[Joint] = []
        self.layers: dict[str, Layer] = {}
        self.posts: dict[str, str] = {}  # "fl"|"fr"|"bl"|"br" -> member id

    def add_member(self, member: Member) -> Member:
        if any(m.id == member.id for m in self.members):
            raise ValueError(f"duplicate member id {member.id!r}")
        self.members.append(member)
        return member

    # -- posts ------------------------------------------------------------

    def _corners(self) -> dict[str, tuple[float, float]]:
        half = self.s / 2
        return {
            "fl": (half, half),
            "fr": (self.W - half, half),
            "bl": (half, self.D - half),
            "br": (self.W - half, self.D - half),
        }

    def build_posts(self) -> None:
        """full_height_posts: 4 posts run the full exterior height."""
        for key, (x, y) in self._corners().items():
            m = self.add_member(
                Member(
                    id=f"post-{key}",
                    role="post",
                    profile=self.profile,
                    axis="z",
                    origin=(x, y, 0.0),
                    length=self.H,
                )
            )
            self.posts[key] = m.id

    def build_posts_between_frames(self) -> None:
        """top_bottom_frames: posts butt up into the frames — they span
        between the bottom frame's top face and the top frame's bottom face,
        tabbing into the full-width rails above and below each corner."""
        s, wg = self.s, self.wg
        for key, (x, y) in self._corners().items():
            m = self.add_member(
                Member(
                    id=f"post-{key}",
                    role="post",
                    profile=self.profile,
                    axis="z",
                    origin=(x, y, s + wg),
                    length=self.H - 2 * s - 2 * wg,
                )
            )
            self.posts[key] = m.id
            rail_key = "front" if key in ("fl", "fr") else "back"
            self._butt("corner_butt", m.id, 0, self.layers["base"].rails[rail_key], "+z", x)
            self._butt("corner_butt", m.id, 1, self.layers["top"].rails[rail_key], "-z", x)

    # -- layers (perimeter frames) ----------------------------------------

    def build_layer(self, name: str, z_center: float, kind: Literal["tee", "corner_butt"]) -> Layer:
        if name in self.layers:
            raise ValueError(f"duplicate layer name {name!r}")
        s, W, D, wg = self.s, self.W, self.D, self.wg
        half = s / 2
        role = "rail" if kind == "corner_butt" else "level_rail"
        rails: dict[str, str] = {}

        # front/back rails along X, butted between the left and right posts
        for rail_key, y, posts in (
            ("front", half, ("fl", "fr")),
            ("back", D - half, ("bl", "br")),
        ):
            m = self.add_member(
                Member(
                    id=f"{name}-{rail_key}-rail",
                    role=role,
                    profile=self.profile,
                    axis="x",
                    origin=(s + wg, y, z_center),
                    length=W - 2 * s - 2 * wg,
                )
            )
            rails[rail_key] = m.id
            self._butt(kind, m.id, 0, self.posts[posts[0]], "+x", z_center)
            self._butt(kind, m.id, 1, self.posts[posts[1]], "-x", z_center)

        # left/right rails along Y, butted between the front and back posts
        for rail_key, x, posts in (
            ("left", half, ("fl", "bl")),
            ("right", W - half, ("fr", "br")),
        ):
            m = self.add_member(
                Member(
                    id=f"{name}-{rail_key}-rail",
                    role=role,
                    profile=self.profile,
                    axis="y",
                    origin=(x, s + wg, z_center),
                    length=D - 2 * s - 2 * wg,
                )
            )
            rails[rail_key] = m.id
            self._butt(kind, m.id, 0, self.posts[posts[0]], "+y", z_center)
            self._butt(kind, m.id, 1, self.posts[posts[1]], "-y", z_center)

        layer = Layer(name=name, z_center=z_center, rails=rails)
        self.layers[name] = layer
        return layer

    def build_ladder_layer(self, name: str, z_center: float) -> Layer:
        """top_bottom_frames horizontal frame: the front/back rails run the
        FULL exterior width (solid across); the left/right depth rails butt
        between them."""
        if name in self.layers:
            raise ValueError(f"duplicate layer name {name!r}")
        s, W, D, wg = self.s, self.W, self.D, self.wg
        half = s / 2
        rails: dict[str, str] = {}

        for rail_key, y in (("front", half), ("back", D - half)):
            m = self.add_member(
                Member(
                    id=f"{name}-{rail_key}-rail",
                    role="rail",
                    profile=self.profile,
                    axis="x",
                    origin=(0.0, y, z_center),
                    length=W,
                )
            )
            rails[rail_key] = m.id

        for rail_key, x in (("left", half), ("right", W - half)):
            m = self.add_member(
                Member(
                    id=f"{name}-{rail_key}-rail",
                    role="rail",
                    profile=self.profile,
                    axis="y",
                    origin=(x, s + wg, z_center),
                    length=D - 2 * s - 2 * wg,
                )
            )
            rails[rail_key] = m.id
            self._butt("corner_butt", m.id, 0, rails["front"], "+y", x)
            self._butt("corner_butt", m.id, 1, rails["back"], "-y", x)

        layer = Layer(name=name, z_center=z_center, rails=rails)
        self.layers[name] = layer
        return layer

    # -- joints ------------------------------------------------------------

    def _butt(
        self,
        kind: Literal["tee", "corner_butt"],
        tab_member: str,
        tab_end: Literal[0, 1],
        slot_member: str,
        slot_face: FaceDir,
        position_global: float,
    ) -> None:
        """Record a butt joint. position_global is the joint-center coordinate
        along the slot member's global axis."""
        slot = next(m for m in self.members if m.id == slot_member)
        self.joints.append(
            Joint(
                kind=kind,
                tab_member=tab_member,
                tab_end=tab_end,
                slot_member=slot_member,
                slot_face=slot_face,
                position_mm=slot.axis_coord(position_global),
            )
        )

    def graph(self) -> FrameGraph:
        return FrameGraph(
            spec=self.spec,
            profile=self.profile,
            members=self.members,
            joints=self.joints,
            layers=self.layers,
        )


def resolve_frame(spec: BoxSpec, catalog: Catalog) -> FrameGraph:
    profile = catalog.find(
        spec.material.shape,
        spec.material.outer_w_mm,
        spec.material.outer_h_mm,
        spec.material.wall,
        material_family=spec.material.family,
    )
    from .blocking import expand_blocking

    b = FrameBuilder(spec, profile)
    if spec.topology == "full_height_posts":
        b.build_posts()
        b.build_layer("base", b.s / 2, "corner_butt")
        b.build_layer("top", b.H - b.s / 2, "corner_butt")
    elif spec.topology == "top_bottom_frames":
        b.build_ladder_layer("base", b.s / 2)
        b.build_ladder_layer("top", b.H - b.s / 2)
        b.build_posts_between_frames()
    else:  # pragma: no cover
        raise NotImplementedError(f"topology {spec.topology!r} not implemented yet")
    expand_blocking(b, spec.blocking)
    return b.graph()
