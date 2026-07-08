"""BoxSpec: the YAML spec schema. The YAML file is the source of truth;
the wizard only authors these files.

All lengths accept unit suffixes ("2000mm", "1.5in", '0.038"'); bare numbers
are millimetres. Values are normalized to float mm at validation time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Union

import yaml
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from .units import parse_length

LengthMM = Annotated[float, BeforeValidator(lambda v: parse_length(v))]


class SpecModel(BaseModel):
    """Base for all spec models: unknown fields are an error, not silently
    ignored — a typo'd or unsupported option must not change the build."""

    model_config = ConfigDict(extra="forbid")


class MaterialRef(SpecModel):
    """Catalog lookup key for the tube stock."""

    shape: Literal["square", "rect", "round"] = "square"
    size: list[LengthMM]  # [w] or [w, h]; OD for round
    wall: LengthMM
    family: str | None = None  # disambiguates e.g. A500 vs 304 at same size

    @property
    def outer_w_mm(self) -> float:
        return self.size[0]

    @property
    def outer_h_mm(self) -> float:
        return self.size[1] if len(self.size) > 1 else self.size[0]


class Exterior(SpecModel):
    height: LengthMM
    width: LengthMM
    depth: LengthMM


class JointConfig(SpecModel):
    style: Literal["through_wall_tab", "plain_butt"] = "through_wall_tab"
    # PRD: slot >= tab + 0.010in (0.25mm) for slip fit
    slot_clearance: LengthMM = 0.25
    # tab width as fraction of the receiving face's flat width
    tab_width_fraction: float = Field(default=0.5, gt=0.0, le=0.9)
    dogbone_radius: LengthMM = 1.0
    weld_gap: LengthMM = 0.0
    # corner butt joints get tab/slot too; slots whose tab wall is flush
    # with the post end become open hook-in notches
    corner_tabs: bool = True


class LevelSpec(SpecModel):
    """Horizontal frame at a given height with optional evenly spaced
    cross-members. `height_ref: top_face` puts the level's top surface at
    `height` (it is a work surface)."""

    type: Literal["level"]
    height: LengthMM
    height_ref: Literal["top_face", "centerline", "bottom_face"] = "top_face"
    name: str | None = None
    cross_members: CrossMembers | None = None


class CrossMembers(SpecModel):
    count: int = Field(gt=0)
    axis: Literal["width", "depth"] = "depth"


class SupportsSpec(SpecModel):
    """Vertical members between two horizontal layers, at the midpoints of
    the spanned members."""

    type: Literal["supports"]
    between: list[str]  # e.g. ["base", "level@1000"] or ["base", "work-surface"]
    at: Literal["midpoints"] = "midpoints"


class SpannerSpec(SpecModel):
    """Members across one or more horizontal faces. With count == 1 a single
    member is placed at `position` (fraction across the face); with
    count > 1 the members are evenly spaced (k / (count + 1)) and
    `position` is ignored."""

    type: Literal["spanner"]
    face: Annotated[
        list[Literal["top", "bottom"]],
        BeforeValidator(lambda v: [v] if isinstance(v, str) else v),
    ]
    axis: Literal["width", "depth"] = "width"
    count: int = Field(default=1, gt=0)
    position: float = Field(default=0.5, gt=0.0, lt=1.0)


BlockingItem = Annotated[
    Union[LevelSpec, SupportsSpec, SpannerSpec], Field(discriminator="type")
]


class SheetMaterialSpec(SpecModel):
    alloy: str = "304"
    thickness: LengthMM


class PanelSpec(SpecModel):
    faces: list[Literal["left", "right", "front", "back", "top", "bottom"]]
    material: SheetMaterialSpec


class AttachmentSpec(SpecModel):
    method: Literal["rivet"] = "rivet"
    rivet: LengthMM = 6.35  # 1/4 in nominal
    spacing: LengthMM = 100.0
    hole_clearance: LengthMM = 0.15


class SidingSpec(SpecModel):
    attachment: AttachmentSpec = AttachmentSpec()
    panels: list[PanelSpec] = []
    panel_margin: LengthMM = 0.0  # inset from frame exterior edge
    corner_radius: LengthMM = 5.0  # sheet corner radius


class PlateSpec(SpecModel):
    """Laser-cut sheet plate resting on top of a horizontal layer (base, top,
    or a named level). The plate gets cutouts around any vertical member that
    passes through it (corner posts, supports) and rivet holes into the top
    faces of the members it rests on (rails, cross members, spanners)."""

    # layer name: base, top, a level's name, or level@<height>. Named
    # `layer` (not `on`) because bare `on` is a YAML 1.1 boolean.
    layer: str = "base"
    material: SheetMaterialSpec
    margin: LengthMM = 0.0  # inset from the frame exterior on all edges
    post_clearance: LengthMM = 1.0  # gap around each cutout member
    corner_radius: LengthMM = 5.0  # outer sheet corner radius
    attachment: AttachmentSpec = AttachmentSpec()


class FootPattern(SpecModel):
    """Mounting hole pattern cut into each foot plate, centered on the
    plate: `square` is 4 holes at `spacing` center-to-center (bolt-on caster
    or machine mount), `single` is one center hole (threaded-stem caster or
    self-leveling foot). The square pattern also gets a `center_hole` by
    default so the same plate accepts either mount; set it to 0 to omit."""

    type: Literal["square", "single"] = "square"
    spacing: LengthMM = 76.2  # 3in c-to-c; ignored for single
    hole: LengthMM = 10.4  # 0.41in — 3/8in bolt clearance
    center_hole: LengthMM = 12.7  # 0.5in stem/leveling-foot hole; 0 disables


class MidFeet(SpecModel):
    """Extra foot plates for long spans: `count` positions evenly spaced
    along `axis` (k / (count + 1)), one plate on each of the two edges
    parallel to that axis."""

    count: int = Field(gt=0)
    axis: Literal["width", "depth"] = "width"


class FeetSpec(SpecModel):
    """Caster / leveling-foot plates welded to the underside of the bottom
    frame, flush with the box exterior. Default: one per corner."""

    material: SheetMaterialSpec
    size: LengthMM = 101.6  # square plate side, 4in
    corner_radius: LengthMM = 5.0
    pattern: FootPattern = FootPattern()
    corners: bool = True
    mid: MidFeet | None = None


class BoxSpec(SpecModel):
    name: str
    vendor: str = "rmfg"
    material: MaterialRef
    exterior: Exterior
    topology: Literal["full_height_posts", "top_bottom_frames"] = "full_height_posts"
    joints: JointConfig = JointConfig()
    blocking: list[BlockingItem] = []
    siding: SidingSpec | None = None
    plates: list[PlateSpec] = []
    feet: FeetSpec | None = None
    quantity: int = Field(default=1, ge=1)
    # add sacrificial slots/holes so same-length members collapse into one
    # part number (fewer unique parts to order); disable for cosmetic faces
    consolidate: bool = True

    @model_validator(mode="after")
    def _check_dims(self) -> "BoxSpec":
        tube = max(self.material.outer_w_mm, self.material.outer_h_mm)
        for axis, value in (
            ("height", self.exterior.height),
            ("width", self.exterior.width),
            ("depth", self.exterior.depth),
        ):
            if value <= 2 * tube:
                raise ValueError(
                    f"exterior {axis} {value:g}mm is too small for {tube:g}mm tube"
                )
        return self


LevelSpec.model_rebuild()


def load_spec(path: Path | str) -> BoxSpec:
    data = yaml.safe_load(Path(path).read_text())
    return BoxSpec.model_validate(data)


def dump_spec(spec: BoxSpec, path: Path | str) -> None:
    data = spec.model_dump(mode="json", exclude_none=True)
    Path(path).write_text(yaml.safe_dump(data, sort_keys=False))
