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

ROLE_COLORS: dict[str, tuple[float, float, float]] = {
    "post": (0.35, 0.38, 0.45),      # slate
    "rail": (0.55, 0.58, 0.62),      # steel gray
    "level_rail": (0.13, 0.55, 0.55),  # teal
    "cross": (0.85, 0.55, 0.15),     # orange
    "support": (0.35, 0.65, 0.30),   # green
    "spanner": (0.55, 0.35, 0.65),   # purple
}
PANEL_COLOR = (0.75, 0.78, 0.82, 0.45)  # translucent sheet
PLATE_COLOR = (0.80, 0.68, 0.35, 0.85)  # deck plates: brass, mostly opaque
FOOT_COLOR = (0.30, 0.32, 0.38, 1.0)    # welded foot plates: dark steel


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


def build_frame_compound(frame: FrameGraph) -> Compound:
    """One solid per member, built from the member's own features (not the
    deduped exemplar's) so mirrored/rotated twins render correctly."""
    solids = []
    for m in frame.members:
        solid = build_part_solid(m)
        placed = solid.moved(member_location(m))
        placed.label = m.id
        placed.color = Color(*ROLE_COLORS.get(m.role, (0.6, 0.6, 0.6)))
        solids.append(placed)
    return Compound(children=solids, label="frame")


def export_assembly(
    frame: FrameGraph,
    parts: list[UniquePart],
    solids: dict,
    panels: Iterable[PanelLayout],
    path: Path,
) -> None:
    children = list(build_frame_compound(frame).children)
    for panel in panels:
        children.append(panel_solid(panel))
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


def panel_solid(panel: PanelLayout) -> Part:
    """Sheet panel solid with rounded corners and rivet holes, sitting proud
    on its box face.

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
    if panel.face == "foot":
        solid.label = panel.name
        solid.color = Color(*FOOT_COLOR)
    elif panel.face.startswith("plate:"):
        solid.label = panel.name
        solid.color = Color(*PLATE_COLOR)
    else:
        solid.label = f"panel-{panel.name}"
        solid.color = Color(*PANEL_COLOR)
    return solid
