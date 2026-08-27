"""Plate geometry — imports OCP, so marked slow. Run with: pytest -m slow"""

from pathlib import Path

import pytest

from weldbox.features import plan_features
from weldbox.frame import resolve_frame
from weldbox.panels.plates import plan_plates
from weldbox.spec import PlateSpec, SheetMaterialSpec, load_spec
from weldbox.vendors import get_vendor

pytestmark = pytest.mark.slow

FIXTURE = Path(__file__).parent / "fixtures" / "winding_machine_cell.yaml"
EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture(scope="module")
def planned():
    spec = load_spec(FIXTURE)
    spec.plates = [
        PlateSpec(layer="base", material=SheetMaterialSpec(alloy="304", thickness="0.075in"))
    ]
    frame = resolve_frame(spec, get_vendor("rmfg").catalog())
    plan_features(frame, spec)
    plate = plan_plates(frame, spec)[0]
    return spec, frame, plate


def test_plate_solid_valid_and_volume(planned):
    import math

    from weldbox.geometry.assembly import panel_solid

    _, _, plate = planned
    solid = panel_solid(plate)
    assert solid.is_valid

    # gross area minus cutouts and holes; the corner/relief radii shift the
    # true volume by well under 0.1%
    gross = plate.width * plate.height
    removed = sum((c.u1 - c.u0) * (c.v1 - c.v0) for c in plate.cutouts)
    removed += sum(math.pi * (d / 2) ** 2 for _, _, d in plate.holes)
    approx = (gross - removed) * plate.thickness
    assert solid.volume == pytest.approx(approx, rel=1e-3)

    bb = solid.bounding_box()
    assert bb.min.Z == pytest.approx(38.1, abs=0.01)
    assert bb.max.Z == pytest.approx(38.1 + plate.thickness, abs=0.01)


def test_assembly_colors_track_the_bom():
    """Every member sharing a unique part (one STEP file) gets one color;
    distinct parts get distinct colors. In the epoxy cell the posts and the
    supports consolidate into the same part, so they must share a color."""
    from weldbox.consolidate import consolidate_parts
    from weldbox.dedupe import group_parts
    from weldbox.features import plan_features as _pf
    from weldbox.frame import resolve_frame as _rf
    from weldbox.geometry.assembly import _assign_part_colors
    from weldbox.panels.feet import plan_feet
    from weldbox.panels.layout import consolidate_panels
    from weldbox.spec import load_spec as _ls
    from weldbox.vendors import get_vendor as _gv

    spec = _ls(EXAMPLES / "epoxy_machine_cell.yaml")
    frame = _rf(spec, _gv(spec.vendor).catalog())
    _pf(frame, spec)
    consolidate_parts(frame)
    parts = group_parts(frame)
    feet = plan_feet(spec)
    consolidate_panels(feet, enabled=True)  # sets part_name in place

    member_color, panel_color = _assign_part_colors(parts, feet)

    # posts and supports are literally the same part -> same color
    assert member_color["post-fl"] == member_color["support-base-top-front"]
    # a full-width rail is a different part -> a different color
    assert member_color["base-front-rail"] != member_color["post-fl"]
    # every member is colored, and distinct parts have distinct colors
    assert all(m.id in member_color for m in frame.members)
    part_colors = [member_color[p.member_ids[0]] for p in parts]
    assert len(set(part_colors)) == len(parts)
    # all 6 feet are one part -> one color, distinct from the tube parts
    assert len(panel_color) == 1
    assert next(iter(panel_color.values())) not in part_colors


def test_plate_clears_every_member(planned):
    """The notched plate must not intersect any tube — posts and supports
    pass through the cutouts with clearance."""
    from weldbox.geometry.assembly import member_location, panel_solid
    from weldbox.geometry.member import build_part_solid

    _, frame, plate = planned
    sheet = panel_solid(plate)
    zmin, zmax = 38.1 - 5.0, 38.1 + plate.thickness + 5.0
    for m in frame.members:
        z0, z1 = m.origin[2], m.origin[2] + m.length
        if m.axis != "z":
            z0, z1 = m.origin[2] - 20, m.origin[2] + 20
        if z1 < zmin or z0 > zmax:
            continue  # nowhere near the plate
        solid = build_part_solid(m).moved(member_location(m))
        inter = sheet.intersect(solid)
        vol = inter.volume if inter else 0.0
        assert vol == pytest.approx(0.0, abs=1e-6), f"plate intersects {m.id}"
