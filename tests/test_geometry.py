"""Geometry tests — import OCP, so marked slow. Run with: pytest -m slow"""

from pathlib import Path

import pytest

from weldbox.features import plan_features
from weldbox.frame import Member, resolve_frame
from weldbox.spec import load_spec
from weldbox.vendors import get_vendor

pytestmark = pytest.mark.slow

FIXTURE = Path(__file__).parent / "fixtures" / "winding_machine_cell.yaml"
SAMPLE_STEP = (
    Path(__file__).parent.parent
    / "docs" / "samples" / "rmfg" / "square_1.5x1.5x0.120.step"
)


@pytest.fixture(scope="module")
def profile():
    return get_vendor("rmfg").catalog().find("square", 38.1, 38.1, 3.048)


@pytest.fixture(scope="module")
def planned_frame():
    spec = load_spec(FIXTURE)
    frame = resolve_frame(spec, get_vendor("rmfg").catalog())
    hole_map = plan_features(frame, spec)
    return spec, frame, hole_map


def test_profile_volume_matches_analytic(profile):
    from weldbox.geometry.member import build_part_solid
    from weldbox.geometry.profile import section_area

    m = Member(id="stub", role="test", profile=profile, axis="z",
               origin=(0, 0, 0), length=152.4)
    solid = build_part_solid(m)
    assert solid.is_valid
    expected = section_area(profile) * 152.4
    assert solid.volume == pytest.approx(expected, rel=1e-3)


def test_profile_matches_vendor_sample(profile):
    """Our generated stub must match RMFG's published stock geometry."""
    from build123d import import_step

    from weldbox.geometry.member import build_part_solid

    sample = import_step(str(SAMPLE_STEP))
    m = Member(id="stub", role="test", profile=profile, axis="z",
               origin=(0, 0, 0), length=152.4)
    ours = build_part_solid(m)

    assert ours.volume == pytest.approx(sample.volume, rel=5e-3)
    sb = sample.bounding_box()
    ob = ours.bounding_box()
    assert (sb.max - sb.min).X == pytest.approx((ob.max - ob.min).X, abs=0.05)
    assert (sb.max - sb.min).Y == pytest.approx((ob.max - ob.min).Y, abs=0.05)
    assert (sb.max - sb.min).Z == pytest.approx((ob.max - ob.min).Z, abs=0.05)


def test_tabs_protrude_and_slots_cut(planned_frame):
    from weldbox.geometry.member import build_part_solid
    from weldbox.geometry.profile import section_area

    spec, frame, _ = planned_frame
    cross = frame.member("work-surface-cross-1")
    solid = build_part_solid(cross)
    assert solid.is_valid

    # tabs extend exactly wall_B (3.048) past each nominal end plane
    bb = solid.bounding_box()
    assert bb.min.Z == pytest.approx(-3.048, abs=0.01)
    assert bb.max.Z == pytest.approx(cross.length + 3.048, abs=0.01)

    # volume: nominal stock + 4 tab prisms - nothing else (no slots on a cross)
    nominal = section_area(cross.profile) * cross.length
    tab_volume = sum(
        t.width * cross.profile.wall_mm * t.protrusion
        for t in cross.features
        if hasattr(t, "protrusion")
    )
    assert solid.volume == pytest.approx(nominal + tab_volume, rel=5e-3)


def test_slot_reduces_volume(planned_frame):
    from weldbox.geometry.member import build_part_solid
    from weldbox.geometry.profile import section_area
    from weldbox.features import SlotFeature, RivetHole
    import math

    spec, frame, _ = planned_frame
    post = frame.member("post-fl")  # 4 slots + 20 rivet holes, no tabs
    solid = build_part_solid(post)
    assert solid.is_valid

    nominal = section_area(post.profile) * post.length
    wall = post.profile.wall_mm
    removed = 0.0
    for f in post.features:
        if isinstance(f, SlotFeature):
            removed += f.length * f.width * wall  # dog-bones add a little more
        elif isinstance(f, RivetHole):
            removed += math.pi * (f.dia / 2) ** 2 * wall
    assert solid.volume < nominal - removed * 0.95
    assert solid.volume > nominal - removed * 2.0


def test_exported_step_reimports_valid(planned_frame, tmp_path):
    from build123d import import_step

    from weldbox.geometry.member import build_part_solid, export_part_step

    _, frame, _ = planned_frame
    m = frame.member("work-surface-cross-1")
    solid = build_part_solid(m)
    out = tmp_path / "cross.step"
    export_part_step(solid, out)
    again = import_step(str(out))
    assert again.is_valid
    assert again.volume == pytest.approx(solid.volume, rel=1e-6)


def test_assembly_bbox(planned_frame):
    from weldbox.geometry.assembly import build_frame_compound

    _, frame, _ = planned_frame
    compound = build_frame_compound(frame)
    bb = compound.bounding_box()
    assert bb.min.X == pytest.approx(0, abs=0.01)
    assert bb.min.Y == pytest.approx(0, abs=0.01)
    assert bb.min.Z == pytest.approx(0, abs=0.01)
    assert bb.max.X == pytest.approx(1000, abs=0.01)
    assert bb.max.Y == pytest.approx(800, abs=0.01)
    assert bb.max.Z == pytest.approx(2000, abs=0.01)
