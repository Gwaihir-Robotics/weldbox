from pathlib import Path

import ezdxf
import pytest

from weldbox.features import plan_features
from weldbox.frame import resolve_frame
from weldbox.panels.dxf import write_panel_dxf
from weldbox.panels.layout import panel_layouts
from weldbox.spec import load_spec
from weldbox.vendors import get_vendor

FIXTURE = Path(__file__).parent / "fixtures" / "winding_machine_cell.yaml"


@pytest.fixture(scope="module")
def panels():
    spec = load_spec(FIXTURE)
    frame = resolve_frame(spec, get_vendor("rfmg").catalog())
    hole_map = plan_features(frame, spec)
    return panel_layouts(frame, spec, hole_map)


def test_panel_dimensions(panels):
    by_name = {p.name: p for p in panels}
    assert set(by_name) == {"left", "right", "back"}
    # sides are depth x height, back is width x height
    assert (by_name["left"].width, by_name["left"].height) == (800.0, 2000.0)
    assert (by_name["right"].width, by_name["right"].height) == (800.0, 2000.0)
    assert (by_name["back"].width, by_name["back"].height) == (1000.0, 2000.0)
    for p in panels:
        assert p.thickness == pytest.approx(0.9652)
        assert p.material == "304"


def test_panel_holes_within_outline(panels):
    for p in panels:
        assert p.holes, p.name
        for u, v, dia in p.holes:
            assert 0 < u < p.width, (p.name, u)
            assert 0 < v < p.height, (p.name, v)
            assert dia == pytest.approx(6.5)


def test_panel_holes_land_on_tube_centerlines(panels):
    """Perimeter holes must sit half a tube in from the panel edges."""
    back = next(p for p in panels if p.name == "back")
    half = 38.1 / 2
    # post holes: u = 19.05 and 1000 - 19.05, spread over z
    us = sorted({round(u, 2) for u, v, d in back.holes})
    assert us[0] == pytest.approx(half)
    assert us[-1] == pytest.approx(1000 - half)
    vs = sorted({round(v, 2) for u, v, d in back.holes})
    assert vs[0] == pytest.approx(half)          # base rail
    assert vs[-1] == pytest.approx(2000 - half)  # top rail
    # work-surface rail row: centerline at 1000 - 19.05
    assert any(v == pytest.approx(1000 - half, abs=0.01) for v in vs)


def test_dxf_roundtrip(panels, tmp_path):
    p = next(p for p in panels if p.name == "back")
    assert p.corner_radius == pytest.approx(5.0)
    out = tmp_path / "back.dxf"
    write_panel_dxf(p, out)

    doc = ezdxf.readfile(out)
    assert doc.header["$INSUNITS"] == 4
    msp = doc.modelspace()
    polys = list(msp.query("LWPOLYLINE"))
    circles = list(msp.query("CIRCLE"))
    assert len(polys) == 1
    outline = polys[0]
    assert outline.closed
    # rounded rectangle: 8 vertices, 4 with 90-degree arc bulges
    pts = [(round(x, 2), round(y, 2), round(b, 5)) for x, y, _, _, b in outline.get_points()]
    assert len(pts) == 8
    r = 5.0
    assert (r, 0.0, 0.0) in pts
    assert any(x == 1000 - r and y == 0.0 and abs(b - 0.41421) < 1e-4 for x, y, b in pts)
    bulges = [b for _, _, b in pts if b != 0]
    assert len(bulges) == 4
    assert all(abs(b - 0.41421) < 1e-4 for b in bulges)
    # outline bounds unchanged by rounding
    xs = [x for x, _, _ in pts]
    ys = [y for _, y, _ in pts]
    assert min(xs) == 0 and max(xs) == 1000
    assert min(ys) == 0 and max(ys) == 2000
    assert len(circles) == len(p.holes)
    assert {round(c.dxf.radius, 3) for c in circles} == {3.25}


def test_left_right_panels_consolidate():
    """Sides must collapse to one flat part (flip the sheet for the other
    side) so vendors' multiples pricing applies."""
    from weldbox.panels.layout import consolidate_panels

    spec = load_spec(FIXTURE)
    frame = resolve_frame(spec, get_vendor("rfmg").catalog())
    hole_map = plan_features(frame, spec)
    all_panels = panel_layouts(frame, spec, hole_map)
    unique = consolidate_panels(all_panels, enabled=True)

    assert len(unique) == 2
    by_name = {p.name: p for p in unique}
    sides = by_name["left-right"]
    assert sides.qty == 2
    assert by_name["back"].qty == 1
    # every panel's holes match its unique part's pattern under a flat-part
    # transform; here left/right are congruent under identity
    left = next(p for p in all_panels if p.face == "left")
    right = next(p for p in all_panels if p.face == "right")
    assert sorted(left.holes) == sorted(right.holes)


def test_panel_consolidation_unions_asymmetric_holes():
    from weldbox.panels.layout import Panel, consolidate_panels

    a = Panel(name="left", face="left", width=100, height=200, thickness=1,
              material="304", qty=1, holes=[(10.0, 10.0, 6.5)])
    b = Panel(name="right", face="right", width=100, height=200, thickness=1,
              material="304", qty=1, holes=[(10.0, 190.0, 6.5)])
    unique = consolidate_panels([a, b], enabled=True)
    assert len(unique) == 1
    # aligned via a v-flip: no extra holes needed at all
    assert unique[0].qty == 2
    assert len(unique[0].holes) == 1


def test_panel_consolidation_conflict_keeps_separate():
    from weldbox.panels.layout import Panel, consolidate_panels

    # hole patterns that would land closer than the min web under every
    # transform -> panels must stay separate parts
    a = Panel(name="left", face="left", width=100, height=100, thickness=1,
              material="304", qty=1, holes=[(50.0, 50.0, 6.5)])
    b = Panel(name="right", face="right", width=100, height=100, thickness=1,
              material="304", qty=1, holes=[(53.0, 50.0, 6.5)])
    unique = consolidate_panels([a, b], enabled=True)
    assert len(unique) == 2


def test_dxf_sharp_corners_when_radius_zero(panels, tmp_path):
    import dataclasses

    p = dataclasses.replace(next(p for p in panels if p.name == "back"), corner_radius=0.0)
    out = tmp_path / "sharp.dxf"
    write_panel_dxf(p, out)
    doc = ezdxf.readfile(out)
    outline = list(doc.modelspace().query("LWPOLYLINE"))[0]
    pts = [(round(x, 3), round(y, 3)) for x, y, *_ in outline.get_points()]
    assert set(pts) == {(0, 0), (1000, 0), (1000, 2000), (0, 2000)}
