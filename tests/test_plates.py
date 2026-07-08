"""Deck plates: cutouts around vertical members, shared rivet holes, DXF."""

from pathlib import Path

import ezdxf
import pytest

from weldbox.features import RivetHole, plan_features
from weldbox.frame import resolve_frame
from weldbox.panels.layout import Cutout, Panel, consolidate_panels
from weldbox.panels.plates import plan_plates
from weldbox.spec import PlateSpec, SheetMaterialSpec, load_spec
from weldbox.vendors import get_vendor

FIXTURE = Path(__file__).parent / "fixtures" / "winding_machine_cell.yaml"
EXAMPLES = Path(__file__).parent.parent / "examples"

S = 38.1  # tube outer, mm
GAP = 1.0  # default post_clearance


def make_frame(layer="base", topology=None):
    spec = load_spec(FIXTURE)
    if topology:
        spec.topology = topology
    spec.plates = [
        PlateSpec(layer=layer, material=SheetMaterialSpec(alloy="304", thickness="0.075in"))
    ]
    frame = resolve_frame(spec, get_vendor("rmfg").catalog())
    plan_features(frame, spec)
    return spec, frame


@pytest.fixture(scope="module")
def base_plate():
    spec, frame = make_frame("base")
    return spec, frame, plan_plates(frame, spec)[0]


def test_plate_dimensions(base_plate):
    _, _, p = base_plate
    assert p.name == "base-plate"
    assert (p.width, p.height) == (1000.0, 800.0)
    assert p.thickness == pytest.approx(1.905)
    # underside on the base rails' top face
    assert p.origin3d == (0.0, 0.0, pytest.approx(S))
    assert p.normal == (0.0, 0.0, 1.0)


def test_corner_and_support_cutouts(base_plate):
    _, _, p = base_plate
    corner = [c for c in p.cutouts
              if (c.u0 == 0 or c.u1 == p.width) and (c.v0 == 0 or c.v1 == p.height)]
    edge = [c for c in p.cutouts if c not in corner]
    # 4 posts -> corner notches; 4 base->work-surface supports -> edge notches
    assert len(corner) == 4 and len(edge) == 4

    notch = S + GAP  # tube footprint + clearance, measured from the corner
    bl = min(corner, key=lambda c: (c.u0, c.v0))
    assert (bl.u0, bl.v0) == (0.0, 0.0)
    assert (bl.u1, bl.v1) == (pytest.approx(notch), pytest.approx(notch))

    front_support = next(c for c in edge if c.v0 == 0)
    assert front_support.u0 == pytest.approx(500 - S / 2 - GAP)
    assert front_support.u1 == pytest.approx(500 + S / 2 + GAP)
    assert front_support.v1 == pytest.approx(notch)


def test_holes_shared_with_tube_top_faces(base_plate):
    _, frame, p = base_plate
    # base-front-rail: not on a sided face, so all its rivet holes are plate
    # holes on its upward local face; the mid-span hole is skipped because
    # the support notch removes the sheet there
    rail = frame.member("base-front-rail")
    holes = [f for f in rail.features if isinstance(f, RivetHole)]
    assert len(holes) == 8
    assert len({h.face for h in holes}) == 1
    xs = sorted(round(rail.origin[0] + h.z, 1) for h in holes)
    assert xs == [100.0, 200.0, 300.0, 400.0, 600.0, 700.0, 800.0, 900.0]

    # bottom spanner supports the plate too and keeps all 9 holes
    spanner = frame.member("bottom-spanner-1")
    assert len([f for f in spanner.features if isinstance(f, RivetHole)]) == 9

    # left rail: 7 positions, midpoint skipped for the left support notch.
    # It also carries 7 siding holes for the left panel on its "-y" face;
    # the plate holes are the ones on its upward "+x" face.
    left = frame.member("base-left-rail")
    up = [f for f in left.features if isinstance(f, RivetHole) and f.face == "+x"]
    assert len(up) == 6

    # panel hole count equals the tube holes: 2x8 rails + 2x6 rails + 9
    assert len(p.holes) == 8 + 8 + 6 + 6 + 9


def test_no_hole_inside_a_cutout(base_plate):
    _, _, p = base_plate
    for u, v, dia in p.holes:
        for c in p.cutouts:
            inside = c.u0 - dia / 2 < u < c.u1 + dia / 2 and c.v0 - dia / 2 < v < c.v1 + dia / 2
            assert not inside, (u, v, c)


def test_top_plate_has_no_cutouts():
    spec, frame = make_frame("top")
    p = plan_plates(frame, spec)[0]
    # posts end at the plate underside; nothing passes through
    assert p.cutouts == []
    assert p.origin3d[2] == pytest.approx(2000.0)
    assert p.holes


def test_level_plate_notches_posts_only():
    spec, frame = make_frame("work-surface")
    p = plan_plates(frame, spec)[0]
    # posts pass through; the supports END at the level's underside
    assert len(p.cutouts) == 4
    assert all(c.u0 == 0 or c.u1 == p.width for c in p.cutouts)
    assert p.origin3d[2] == pytest.approx(1000.0)
    # holes into level rails and the 3 cross members
    cross = frame.member("work-surface-cross-1")
    assert any(isinstance(f, RivetHole) for f in cross.features)


def test_top_bottom_frames_posts_notched():
    spec, frame = make_frame("base", topology="top_bottom_frames")
    p = plan_plates(frame, spec)[0]
    # posts start exactly at the plate underside and pass through the sheet
    corner = [c for c in p.cutouts
              if (c.u0 == 0 or c.u1 == p.width) and (c.v0 == 0 or c.v1 == p.height)]
    assert len(corner) == 4


def test_unknown_layer_is_a_clean_error():
    spec = load_spec(FIXTURE)
    spec.plates = [
        PlateSpec(layer="mezzanine", material=SheetMaterialSpec(thickness="0.075in"))
    ]
    frame = resolve_frame(spec, get_vendor("rmfg").catalog())
    with pytest.raises(LookupError, match="available: base, top, work-surface"):
        plan_plates(frame, spec)


def test_plates_with_matching_cutouts_consolidate():
    cut = [Cutout(0, 0, 40, 40, 3), Cutout(60, 60, 100, 100, 3)]
    a = Panel(name="base-plate", face="plate:base", width=100, height=100,
              thickness=2, material="304", qty=1, holes=[(50, 20, 6.5)], cutouts=list(cut))
    b = Panel(name="mid-plate", face="plate:mid", width=100, height=100,
              thickness=2, material="304", qty=1, holes=[(50, 80, 6.5)],
              cutouts=[Cutout(0, 60, 40, 100, 3), Cutout(60, 0, 100, 40, 3)])
    # b's cutouts are a's under a v-flip -> one part, holes unioned... but the
    # v-flip also maps b's hole (50, 80) onto a's (50, 20): no extra holes
    unique = consolidate_panels([a, b], enabled=True)
    assert len(unique) == 1
    assert unique[0].qty == 2
    assert len(unique[0].holes) == 1


def test_plates_with_different_cutouts_stay_separate():
    a = Panel(name="a", face="plate:a", width=100, height=100, thickness=2,
              material="304", qty=1, cutouts=[Cutout(0, 0, 40, 40, 3)])
    b = Panel(name="b", face="plate:b", width=100, height=100, thickness=2,
              material="304", qty=1, cutouts=[Cutout(0, 0, 50, 50, 3)])
    assert len(consolidate_panels([a, b], enabled=True)) == 2


def test_plate_dxf_outline_has_notches(base_plate, tmp_path):
    from weldbox.panels.dxf import write_panel_dxf

    _, _, p = base_plate
    out = tmp_path / "base-plate.dxf"
    write_panel_dxf(p, out)

    doc = ezdxf.readfile(out)
    msp = doc.modelspace()
    polys = list(msp.query("LWPOLYLINE"))
    assert len(polys) == 1  # all 8 cutouts touch the outline -> single loop
    outline = polys[0]
    assert outline.closed
    pts = [(round(x, 2), round(y, 2), round(b, 5)) for x, y, _, _, b in outline.get_points()]
    xs, ys = [x for x, _, _ in pts], [y for _, y, _ in pts]
    assert min(xs) == 0 and max(xs) == 1000
    assert min(ys) == 0 and max(ys) == 800
    # concave reliefs: 1 per corner notch + 2 per edge notch = 4 + 8
    assert sum(1 for _, _, b in pts if b < 0) == 12
    # corner notch shoulder points sit on the outline edges
    notch = round(S + GAP, 2)
    assert (notch, 0.0, 0.0) in pts
    assert (0.0, notch, 0.0) in pts
    assert len(msp.query("CIRCLE")) == len(p.holes)


def test_interior_cutout_becomes_own_polyline(tmp_path):
    from weldbox.panels.dxf import write_panel_dxf

    p = Panel(name="t", face="plate:t", width=200, height=200, thickness=2,
              material="304", qty=1, corner_radius=5,
              cutouts=[Cutout(80, 80, 120, 120, 3)])
    out = tmp_path / "interior.dxf"
    write_panel_dxf(p, out)
    doc = ezdxf.readfile(out)
    polys = list(doc.modelspace().query("LWPOLYLINE"))
    assert len(polys) == 2
    inner = next(
        pl for pl in polys if max(x for x, *_ in pl.get_points()) <= 120.0
    )
    ipts = [(round(x, 2), round(y, 2)) for x, y, *_ in inner.get_points()]
    assert (83.0, 80.0) in ipts  # 80 + r


def test_example_specs_with_plates_dry_run(tmp_path):
    from rich.console import Console

    from weldbox.generate import run_generate

    for example in ("winding_machine_cell.yaml", "winding_machine_cell_1x1.yaml"):
        run_generate(EXAMPLES / example, tmp_path, dry_run=True,
                     console=Console(quiet=True))
