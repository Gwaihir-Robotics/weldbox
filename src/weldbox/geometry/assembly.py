"""Assembly STEP export: every member placed in box coordinates, plus sheet
panels. This is the file to open in FreeCAD for a visual check.

Members are colored by role and panels are translucent so the structure is
easy to inspect; each member/panel is a separately named product in the
STEP tree, so individual parts can be hidden to look at joints.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from build123d import (
    Circle,
    Color,
    Compound,
    Location,
    Part,
    Plane,
    Pos,
    RectangleRounded,
    Rectangle,
    export_step,
    extrude,
)

from ..dedupe import UniquePart
from ..frame import AXIS_DIR, LOCAL_BASIS, FrameGraph, Member
from ..panels.layout import Panel as PanelLayout
from .member import build_part_solid

# Assembly colors track the BILL OF MATERIALS, not member roles: every
# member that consolidates into the same unique part (the same STEP file)
# gets the same color, and distinct parts get distinct colors, so the
# assembly reads as a visual key to the cut list. Interchangeable members
# (e.g. posts and supports that turn out to be the same part) share a color.
#
# Categorical palette (saturated hues first, then lighter tints) — assigned
# in cut-list order, tubes then sheet parts, wrapping if a BOM ever exceeds
# the palette length.
_PALETTE_HEX = [
    "1f77b4", "ff7f0e", "2ca02c", "d62728", "9467bd",
    "8c564b", "e377c2", "17becf", "bcbd22", "7f7f7f",
    "aec7e8", "ffbb78", "98df8a", "ff9896", "c5b0d5",
    "c49c94", "f7b6d2", "9edae5", "dbdb8d", "c7c7c7",
]


def _hex_rgb(h: str) -> tuple[float, float, float]:
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


PALETTE: list[tuple[float, float, float]] = [_hex_rgb(h) for h in _PALETTE_HEX]

# sheet parts keep an alpha so siding stays see-through while plates read solid
_PANEL_ALPHA = 0.45   # riveted siding
_PLATE_ALPHA = 0.85   # deck plates
_FOOT_ALPHA = 1.0     # welded foot plates

# fallback when the assembly is built without a BOM color map (role coloring)
ROLE_COLORS: dict[str, tuple[float, float, float]] = {
    "post": (0.35, 0.38, 0.45),
    "rail": (0.55, 0.58, 0.62),
    "level_rail": (0.13, 0.55, 0.55),
    "cross": (0.85, 0.55, 0.15),
    "support": (0.35, 0.65, 0.30),
    "spanner": (0.55, 0.35, 0.65),
}


def member_location(member: Member) -> Location:
    """Transform from member-local frame (features/geometry convention) to
    box coordinates: local z -> member axis, local x/y -> LOCAL_BASIS."""
    lx_axis, ly_axis = LOCAL_BASIS[member.axis]
    plane = Plane(
        origin=member.origin,
        x_dir=AXIS_DIR[lx_axis],
        z_dir=AXIS_DIR[member.axis],
    )
    return plane.location


def build_frame_compound(
    frame: FrameGraph, member_color: dict | None = None
) -> Compound:
    """One solid per member, built from the member's own features (not the
    deduped exemplar's) so mirrored/rotated twins render correctly.

    `member_color` maps member id -> rgb (BOM coloring: same unique part =
    same color). Without it, members fall back to role colors."""
    solids = []
    for m in frame.members:
        solid = build_part_solid(m)
        placed = solid.moved(member_location(m))
        placed.label = m.id
        if member_color is not None:
            rgb = member_color.get(m.id, (0.6, 0.6, 0.6))
        else:
            rgb = ROLE_COLORS.get(m.role, (0.6, 0.6, 0.6))
        placed.color = Color(*rgb)
        solids.append(placed)
    return Compound(children=solids, label="frame")


def _panel_alpha(face: str) -> float:
    if face == "foot":
        return _FOOT_ALPHA
    if face.startswith("plate:"):
        return _PLATE_ALPHA
    return _PANEL_ALPHA


def _assign_part_colors(
    parts: list[UniquePart], panels: Iterable[PanelLayout]
) -> tuple[dict, dict]:
    """Assign a palette color to every unique part, in cut-list order (tubes
    first, then sheet parts by first appearance). Returns
    (member id -> rgb, panel part name -> rgb)."""
    member_color: dict[str, tuple] = {}
    panel_color: dict[str, tuple] = {}
    i = 0
    for part in parts:
        rgb = PALETTE[i % len(PALETTE)]
        i += 1
        for mid in part.member_ids:
            member_color[mid] = rgb
    for panel in panels:
        key = panel.part_name or panel.name
        if key not in panel_color:
            panel_color[key] = PALETTE[i % len(PALETTE)]
            i += 1
    return member_color, panel_color


def export_assembly(
    frame: FrameGraph,
    parts: list[UniquePart],
    solids: dict,
    panels: Iterable[PanelLayout],
    path: Path,
) -> None:
    panels = list(panels)
    member_color, panel_color = _assign_part_colors(parts, panels)
    children = list(build_frame_compound(frame, member_color).children)
    for panel in panels:
        rgb = panel_color[panel.part_name or panel.name]
        children.append(panel_solid(panel, (*rgb, _panel_alpha(panel.face))))
    _export_step_flat_colored(children, path)


def _export_step_flat_colored(children: list[Part], path: Path) -> None:
    """Write the assembly as FLAT named products (no nested STEP assembly
    tree) with colors on both the solids and every face.

    FreeCAD 1.1 imports this structure most reliably: each member arrives
    as its own selectable/hideable object, and face-level colors survive
    even when its 'compound merge' import preference flattens shapes —
    per-solid colors alone are dropped in that mode.
    """
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.Quantity import Quantity_Color, Quantity_ColorRGBA, Quantity_TOC_RGB
    from OCP.TopLoc import TopLoc_Location
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_StepModelType
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool

    doc = TDocStd_Document(TCollection_ExtendedString("weldbox"))
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())

    for child in children:
        c = child.color
        rgba = Quantity_ColorRGBA(
            Quantity_Color(c.wrapped.GetRGB().Red(), c.wrapped.GetRGB().Green(),
                           c.wrapped.GetRGB().Blue(), Quantity_TOC_RGB),
            c.wrapped.Alpha(),
        )
        # bake the placement into the geometry: XCAF treats a located shape
        # as instance-of-prototype and AddSubShape then cannot attach face
        # colors to the instance's faces
        shape = child.wrapped
        loc = shape.Location()
        if not loc.IsIdentity():
            local = shape.Located(TopLoc_Location())
            shape = BRepBuilderAPI_Transform(local, loc.Transformation(), True).Shape()

        label = shape_tool.AddShape(shape, False)
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(child.label))
        color_tool.SetColor(label, rgba, XCAFDoc_ColorType.XCAFDoc_ColorGen)
        exp = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
        while exp.More():
            face_label = shape_tool.AddSubShape(label, exp.Current())
            if not face_label.IsNull():
                color_tool.SetColor(face_label, rgba, XCAFDoc_ColorType.XCAFDoc_ColorSurf)
            exp.Next()

    writer = STEPCAFControl_Writer()
    writer.SetColorMode(True)
    writer.SetNameMode(True)
    writer.Transfer(doc, STEPControl_StepModelType.STEPControl_AsIs)
    status = writer.Write(str(path))
    if status != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise RuntimeError(f"STEP write failed for {path}")


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def panel_solid(panel: PanelLayout, color: tuple | None = None) -> Part:
    """Sheet panel solid with rounded corners and rivet holes, sitting proud
    on its box face. `color` is an rgba tuple (BOM coloring); without it the
    panel falls back to a neutral tint by kind.

    Sketched on Plane(origin, x_dir=u, z_dir=u x v): with that choice the
    plane's local (x, y) axes are exactly the panel's (u, v) regardless of
    whether (u, v, outward-normal) is right-handed, so hole coordinates are
    never mirrored. The extrude direction is flipped when the plane normal
    points into the box.
    """
    w, h, r = panel.width, panel.height, panel.corner_radius
    sheet = (
        RectangleRounded(w, h, r) if r > 0 else Rectangle(w, h)
    )
    sketch = Pos(w / 2, h / 2) * sheet
    for c in panel.cutouts:
        # extend sides that lie on the outline past it, so notch cutters
        # clear the edge; the cutter's rounded corners land outside the sheet
        # there, leaving a straight edge cut that matches the DXF outline
        ext = c.radius + 2.0
        u0 = c.u0 - ext if c.u0 <= 1e-6 else c.u0
        v0 = c.v0 - ext if c.v0 <= 1e-6 else c.v0
        u1 = c.u1 + ext if c.u1 >= w - 1e-6 else c.u1
        v1 = c.v1 + ext if c.v1 >= h - 1e-6 else c.v1
        cw, ch = u1 - u0, v1 - v0
        rn = min(c.radius, cw / 2 - 0.01, ch / 2 - 0.01)
        cutter = RectangleRounded(cw, ch, rn) if rn > 0.01 else Rectangle(cw, ch)
        sketch -= Pos((u0 + u1) / 2, (v0 + v1) / 2) * cutter
    for u, v, dia in panel.holes:
        sketch -= Pos(u, v) * Circle(dia / 2)

    n_rh = _cross(panel.u_dir, panel.v_dir)
    plane = Plane(origin=panel.origin3d, x_dir=panel.u_dir, z_dir=n_rh)
    outward = sum(n_rh[i] * panel.normal[i] for i in range(3))  # +1 or -1
    solid = extrude(plane * sketch, amount=outward * panel.thickness)

    solid = Part(solid)
    is_sheet_part = panel.face == "foot" or panel.face.startswith("plate:")
    solid.label = panel.name if is_sheet_part else f"panel-{panel.name}"
    if color is None:  # neutral fallback by kind
        if panel.face == "foot":
            color = (0.30, 0.32, 0.38, _FOOT_ALPHA)
        elif panel.face.startswith("plate:"):
            color = (0.80, 0.68, 0.35, _PLATE_ALPHA)
        else:
            color = (0.75, 0.78, 0.82, _PANEL_ALPHA)
    solid.color = Color(*color)
    return solid
