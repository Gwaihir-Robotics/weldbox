"""Caster / leveling-foot plates."""

from pathlib import Path

import pytest

from weldbox.panels.feet import plan_feet
from weldbox.panels.layout import consolidate_panels
from weldbox.spec import (
    BoxSpec,
    Exterior,
    FeetSpec,
    FootPattern,
    MaterialRef,
    MidFeet,
    SheetMaterialSpec,
    load_spec,
)

EXAMPLES = Path(__file__).parent.parent / "examples"


def make_spec(**feet_kwargs) -> BoxSpec:
    feet_kwargs.setdefault("material", SheetMaterialSpec(alloy="A36", thickness="0.25in"))
    return BoxSpec(
        name="t",
        material=MaterialRef(size=["1.5in"], wall="0.120in"),
        exterior=Exterior(height=860, width=2000, depth=660),
        feet=FeetSpec(**feet_kwargs),
    )


def test_default_four_corner_feet():
    spec = make_spec()
    feet = plan_feet(spec)
    assert len(feet) == 4
    a = 101.6
    corners = {(round(p.origin3d[0], 1), round(p.origin3d[1], 1)) for p in feet}
    assert corners == {(0.0, 0.0), (2000 - a, 0.0), (0.0, 660 - a), (2000 - a, 660 - a)}
    for p in feet:
        assert (p.width, p.height) == (a, a)
        assert p.origin3d[2] == 0.0
        assert p.normal == (0.0, 0.0, -1.0)  # hangs below the frame
        assert p.thickness == pytest.approx(6.35)


def test_square_pattern_holes_centered():
    spec = make_spec(size="4in", pattern=FootPattern(type="square", spacing="3in", hole="0.41in"))
    p = plan_feet(spec)[0]
    # 4 bolt holes + the default 1/2in center hole (stem/leveling option)
    assert len(p.holes) == 5
    c, s = 101.6 / 2, 76.2 / 2
    assert {(round(u, 2), round(v, 2)) for u, v, _ in p.holes} == {
        (round(c - s, 2), round(c - s, 2)), (round(c + s, 2), round(c - s, 2)),
        (round(c - s, 2), round(c + s, 2)), (round(c + s, 2), round(c + s, 2)),
        (round(c, 2), round(c, 2)),
    }
    corner = [d for u, v, d in p.holes if round(u, 2) != round(c, 2)]
    assert all(d == pytest.approx(0.41 * 25.4) for d in corner)
    center = next(d for u, v, d in p.holes if round(u, 2) == round(c, 2))
    assert center == pytest.approx(12.7)


def test_square_pattern_center_hole_disabled():
    spec = make_spec(pattern=FootPattern(type="square", center_hole=0))
    assert len(plan_feet(spec)[0].holes) == 4


def test_center_hole_clash_with_pattern():
    # a big center hole against a tight pattern must not silently overlap
    with pytest.raises(ValueError, match="center hole"):
        plan_feet(make_spec(size="3in", pattern=FootPattern(spacing="1in", center_hole="1in")))


def test_single_post_pattern():
    spec = make_spec(pattern=FootPattern(type="single", hole="0.5in"))
    p = plan_feet(spec)[0]
    assert p.holes == [(101.6 / 2, 101.6 / 2, pytest.approx(12.7))]


def test_mid_feet_along_width():
    spec = make_spec(mid=MidFeet(count=1, axis="width"))
    feet = plan_feet(spec)
    assert len(feet) == 6  # 4 corners + a front/back pair at mid-span
    a = 101.6
    mids = [p for p in feet if abs(p.origin3d[0] - (1000 - a / 2)) < 0.01]
    assert {round(p.origin3d[1], 1) for p in mids} == {0.0, 660 - a}


def test_mid_feet_along_depth():
    spec = make_spec(corners=False, mid=MidFeet(count=2, axis="depth"))
    feet = plan_feet(spec)
    assert len(feet) == 4
    ys = sorted(round(p.origin3d[1] + 101.6 / 2, 1) for p in feet)
    assert ys == [220.0, 220.0, 440.0, 440.0]


def test_feet_consolidate_to_one_part():
    spec = make_spec(mid=MidFeet(count=1, axis="width"))
    unique = consolidate_panels(plan_feet(spec), enabled=True)
    assert len(unique) == 1
    assert unique[0].qty == 6
    assert unique[0].name == "foot"


def test_pattern_too_big_for_plate():
    with pytest.raises(ValueError, match="does not fit"):
        plan_feet(make_spec(size="3in", pattern=FootPattern(spacing="3in")))


def test_oversize_corner_plates():
    with pytest.raises(ValueError, match="overlap"):
        plan_feet(make_spec(size="14in"))


def test_no_placement_is_an_error():
    with pytest.raises(ValueError, match="nothing to place"):
        plan_feet(make_spec(corners=False))


def test_epoxy_example_dry_run(tmp_path):
    from rich.console import Console

    from weldbox.generate import run_generate

    spec = load_spec(EXAMPLES / "epoxy_machine_cell.yaml")
    assert spec.feet is not None and spec.feet.mid.count == 1
    run_generate(EXAMPLES / "epoxy_machine_cell.yaml", tmp_path, dry_run=True,
                 console=Console(quiet=True))
