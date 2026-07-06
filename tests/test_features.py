from pathlib import Path

import pytest

from weldbox.features import RivetHole, SlotFeature, TabFeature, plan_features
from weldbox.frame import resolve_frame
from weldbox.spec import load_spec
from weldbox.vendors import get_vendor

FIXTURE = Path(__file__).parent / "fixtures" / "winding_machine_cell.yaml"

WALL = 3.048  # 0.120 in
TUBE = 38.1
CORNER_R = 6.096  # 0.24 in
FLAT = TUBE - 2 * CORNER_R  # 25.908


@pytest.fixture(scope="module")
def planned():
    spec = load_spec(FIXTURE)
    frame = resolve_frame(spec, get_vendor("rmfg").catalog())
    hole_map = plan_features(frame, spec)
    return spec, frame, hole_map


def feats(frame, member_id, kind):
    return [f for f in frame.member(member_id).features if isinstance(f, kind)]


def test_cross_member_tabs(planned):
    _, frame, _ = planned
    tabs = feats(frame, "work-surface-cross-1", TabFeature)
    # two tabs per end (both ends are tee joints)
    assert len(tabs) == 4
    assert {t.end for t in tabs} == {0, 1}
    for t in tabs:
        assert t.width == pytest.approx(0.5 * FLAT)
        assert t.protrusion == pytest.approx(WALL)  # welds flush through 0.120 wall
    # tabs come from the walls facing along the rail axis (global X = local
    # -y/+y for a y-axis member; LOCAL_BASIS y: local x->Z, local y->X)
    assert {t.wall for t in tabs if t.end == 0} == {"+y", "-y"}


def test_level_rail_slots_from_crosses(planned):
    _, frame, _ = planned
    rail = frame.member("work-surface-front-rail")
    all_slots = [f for f in rail.features if isinstance(f, SlotFeature)]
    # 3 crosses x 2 slots on the back face; the front support adds 2 more on
    # the bottom face (local -y for an x-axis member)
    assert len(all_slots) == 8
    assert len([s for s in all_slots if s.face == "-y"]) == 2
    slots = [s for s in all_slots if s.face == "+x"]
    assert len(slots) == 6
    for s in slots:
        assert s.length == pytest.approx(0.5 * FLAT + 0.25)
        assert s.width == pytest.approx(WALL + 0.25)
        assert s.dogbone_r == 1.0
        assert s.lateral == 0.0
        # slot face: cross members butt against the rail's back face
        # (global +Y); rail is an x-axis member (local x->Y) -> "+x"
        assert s.face == "+x"
    # slot pairs straddle each cross position (250/500/750 minus rail origin 38.1)
    zs = sorted(s.z for s in slots)
    offset = (TUBE - WALL) / 2
    expected = sorted([p - 38.1 + d for p in (250, 500, 750) for d in (-offset, offset)])
    assert zs == pytest.approx(expected)


def test_slots_stay_on_flat_region(planned):
    _, frame, _ = planned
    for m in frame.members:
        for s in (f for f in m.features if isinstance(f, SlotFeature)):
            # slot runs along the face lateral direction; it must fit within
            # the flat width between corner radii
            assert s.length / 2 + abs(s.lateral) <= FLAT / 2 + 1e-9, (m.id, s)


def test_corner_butts_get_tabs_too(planned):
    _, frame, _ = planned
    # corner_tabs default: every post receives 2 rail ends x 2 slots from
    # each of base, top, and the work-surface level = 12 slots
    for key in ("fl", "fr", "bl", "br"):
        post = frame.member(f"post-{key}")
        slots = [f for f in post.features if isinstance(f, SlotFeature)]
        assert len(slots) == 12
        assert all(isinstance(f, (SlotFeature, RivetHole)) for f in post.features)
    # base/top rails now carry end tabs into the posts
    rail = frame.member("base-front-rail")
    tabs = [f for f in rail.features if isinstance(f, TabFeature)]
    assert len(tabs) == 4
    assert {t.end for t in tabs} == {0, 1}


def test_corner_slots_open_at_post_ends(planned):
    """Bottom/top rail tab slots land flush with the post ends and become
    open hook-in notches (slot edge crosses the end plane)."""
    _, frame, _ = planned
    post = frame.member("post-fl")
    slots = [f for f in post.features if isinstance(f, SlotFeature)]
    zs = sorted(s.z for s in slots)
    half_w = (WALL + 0.25) / 2
    assert zs[0] - half_w < 0  # opens through the bottom end
    assert zs[-1] + half_w > 2000.0  # opens through the top end


def test_rivet_holes_on_back_face(planned):
    spec, frame, hole_map = planned
    assert set(hole_map) == {"left", "right", "back"}
    back = hole_map["back"]
    members_with_holes = {m.id for m, _ in back}
    # back face: 2 posts + base/top/level back rails + back support
    assert members_with_holes == {
        "post-bl", "post-br",
        "base-back-rail", "top-back-rail", "work-surface-back-rail",
        "support-base-work-surface-back",
    }
    for m, h in back:
        assert h.dia == pytest.approx(6.35 + 0.15)


def test_hole_spacing_pitch(planned):
    _, frame, hole_map = planned
    holes = sorted(h.z for m, h in hole_map["back"] if m.id == "post-bl")
    diffs = [b - a for a, b in zip(holes, holes[1:])]
    assert all(d == pytest.approx(100.0) for d in diffs)
    # symmetric about the post middle
    assert holes[0] + holes[-1] == pytest.approx(2000.0)
    # 2000mm post, 20mm end margins -> 20 holes at 100 pitch (50..1950)
    assert len(holes) == 20


def test_front_face_has_no_holes(planned):
    _, frame, hole_map = planned
    assert "front" not in hole_map
    front_post_holes = feats(frame, "post-fl", RivetHole)
    # fl post borders the left face (sided) but not front
    left_normals = {h.face for h in front_post_holes}
    assert len(front_post_holes) == 20
    assert len(left_normals) == 1
