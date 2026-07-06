from pathlib import Path

import pytest

from weldbox.frame import resolve_frame
from weldbox.spec import load_spec
from weldbox.vendors import get_vendor

FIXTURE = Path(__file__).parent / "fixtures" / "winding_machine_cell.yaml"

TUBE = 38.1  # 1.5in


@pytest.fixture(scope="module")
def frame():
    spec = load_spec(FIXTURE)
    return resolve_frame(spec, get_vendor("rmfg").catalog())


def by_role(frame, role):
    return [m for m in frame.members if m.role == role]


def test_member_counts(frame):
    counts = {}
    for m in frame.members:
        counts[m.role] = counts.get(m.role, 0) + 1
    assert counts == {
        "post": 4,
        "rail": 8,        # base + top perimeters
        "level_rail": 4,  # work surface perimeter
        "cross": 3,
        "support": 4,
        "spanner": 2,
    }
    assert len(frame.members) == 25


def test_acceptance_lengths(frame):
    posts = by_role(frame, "post")
    assert all(m.length == pytest.approx(2000.0) for m in posts)

    # rails along width: 1000 - 2*38.1 = 923.8; along depth: 800 - 2*38.1 = 723.8
    for m in by_role(frame, "rail") + by_role(frame, "level_rail"):
        expected = 923.8 if m.axis == "x" else 723.8
        assert m.length == pytest.approx(expected), m.id

    # cross members run front-to-back
    for m in by_role(frame, "cross"):
        assert m.axis == "y"
        assert m.length == pytest.approx(723.8), m.id

    # supports: (980.95 - 19.05) - 38.1 = 923.8
    for m in by_role(frame, "support"):
        assert m.axis == "z"
        assert m.length == pytest.approx(923.8), m.id

    # spanners across the width
    for m in by_role(frame, "spanner"):
        assert m.axis == "x"
        assert m.length == pytest.approx(923.8), m.id


def test_work_surface_top_at_1000(frame):
    level = frame.layers["work-surface"]
    assert level.z_center == pytest.approx(1000.0 - TUBE / 2)


def test_cross_members_evenly_spaced(frame):
    xs = sorted(m.origin[0] for m in by_role(frame, "cross"))
    assert xs == [pytest.approx(250.0), pytest.approx(500.0), pytest.approx(750.0)]
    z = 1000.0 - TUBE / 2
    assert all(m.origin[2] == pytest.approx(z) for m in by_role(frame, "cross"))


def test_geometry_within_exterior(frame):
    for m in frame.members:
        s = m.profile.outer_w_mm / 2
        lo, hi = m.origin, m.end
        for i, limit in enumerate((1000.0, 800.0, 2000.0)):
            axis_along = {"x": 0, "y": 1, "z": 2}[m.axis] == i
            pad = 0 if axis_along else s
            assert min(lo[i], hi[i]) - pad >= -1e-9, m.id
            assert max(lo[i], hi[i]) + pad <= limit + 1e-9, m.id


def test_no_member_overlaps(frame):
    """No two members' solid bounding boxes overlap (butt joints touch only)."""
    def bbox(m):
        s = m.profile.outer_w_mm / 2
        lo, hi = m.origin, m.end
        box = []
        for i in range(3):
            axis_along = {"x": 0, "y": 1, "z": 2}[m.axis] == i
            pad = 0 if axis_along else s
            box.append((min(lo[i], hi[i]) - pad, max(lo[i], hi[i]) + pad))
        return box

    members = frame.members
    for i, a in enumerate(members):
        ba = bbox(a)
        for b in members[i + 1:]:
            bb = bbox(b)
            overlap = all(
                ba[k][0] < bb[k][1] - 1e-6 and bb[k][0] < ba[k][1] - 1e-6 for k in range(3)
            )
            assert not overlap, f"{a.id} overlaps {b.id}"


def test_joint_counts(frame):
    tees = [j for j in frame.joints if j.kind == "tee"]
    butts = [j for j in frame.joints if j.kind == "corner_butt"]
    # 8 perimeter rails x 2 ends butt into posts
    assert len(butts) == 16
    # level rails->posts (8) + crosses->level rails (6) + supports (8) + spanners (4)
    assert len(tees) == 26


def test_joint_positions_on_slot_members(frame):
    for j in frame.joints:
        slot = frame.member(j.slot_member)
        assert -1e-9 <= j.position_mm <= slot.length + 1e-9, j


# ---- top_bottom_frames topology --------------------------------------------

EPOXY = Path(__file__).parent.parent / "examples" / "epoxy_machine_cell.yaml"


@pytest.fixture(scope="module")
def ladder_frame():
    spec = load_spec(EPOXY)
    assert spec.topology == "top_bottom_frames"
    return resolve_frame(spec, get_vendor("rmfg").catalog())


def test_ladder_full_width_rails(ladder_frame):
    """Front/back rails of both frames run solid across the full width."""
    for layer in ("base", "top"):
        for key in ("front", "back"):
            m = ladder_frame.member(f"{layer}-{key}-rail")
            assert m.axis == "x"
            assert m.length == pytest.approx(2000.0)
            assert m.origin[0] == 0.0
        for key in ("left", "right"):
            m = ladder_frame.member(f"{layer}-{key}-rail")
            assert m.axis == "y"
            assert m.length == pytest.approx(660 - 2 * TUBE)


def test_ladder_posts_butt_into_frames(ladder_frame):
    for key in ("fl", "fr", "bl", "br"):
        post = ladder_frame.member(f"post-{key}")
        assert post.origin[2] == pytest.approx(TUBE)
        assert post.length == pytest.approx(860 - 2 * TUBE)
    # each post tabs into the full-width rails above and below it
    post_joints = [j for j in ladder_frame.joints if j.tab_member == "post-fl"]
    assert {(j.slot_member, j.slot_face) for j in post_joints} == {
        ("base-front-rail", "+z"),
        ("top-front-rail", "-z"),
    }


def test_ladder_member_counts(ladder_frame):
    counts = {}
    for m in ladder_frame.members:
        counts[m.role] = counts.get(m.role, 0) + 1
    # 3 depth spanners on each of the top and bottom faces (face list x count)
    assert counts == {"rail": 8, "post": 4, "support": 4, "spanner": 6}
    top_xs = sorted(
        m.origin[0]
        for m in ladder_frame.members
        if m.role == "spanner" and m.origin[2] > 800
    )
    assert top_xs == [pytest.approx(500.0), pytest.approx(1000.0), pytest.approx(1500.0)]


def test_ladder_geometry_within_exterior(ladder_frame):
    for m in ladder_frame.members:
        s = m.profile.outer_w_mm / 2
        lo, hi = m.origin, m.end
        for i, limit in enumerate((2000.0, 660.0, 860.0)):
            axis_along = {"x": 0, "y": 1, "z": 2}[m.axis] == i
            pad = 0 if axis_along else s
            assert min(lo[i], hi[i]) - pad >= -1e-9, m.id
            assert max(lo[i], hi[i]) + pad <= limit + 1e-9, m.id


def test_ladder_no_member_overlaps(ladder_frame):
    def bbox(m):
        s = m.profile.outer_w_mm / 2
        lo, hi = m.origin, m.end
        box = []
        for i in range(3):
            axis_along = {"x": 0, "y": 1, "z": 2}[m.axis] == i
            pad = 0 if axis_along else s
            box.append((min(lo[i], hi[i]) - pad, max(lo[i], hi[i]) + pad))
        return box

    members = ladder_frame.members
    for i, a in enumerate(members):
        ba = bbox(a)
        for b in members[i + 1:]:
            bb = bbox(b)
            overlap = all(
                ba[k][0] < bb[k][1] - 1e-6 and bb[k][0] < ba[k][1] - 1e-6 for k in range(3)
            )
            assert not overlap, f"{a.id} overlaps {b.id}"


# ---- level height validation ------------------------------------------------


def _spec_with_level(height, height_ref="top_face", exterior_height="860mm"):
    from weldbox.spec import BoxSpec

    return BoxSpec.model_validate(
        {
            "name": "t",
            "material": {"size": ["1.5in"], "wall": "0.120in", "family": "A500"},
            "exterior": {"height": exterior_height, "width": "2000mm", "depth": "660mm"},
            "blocking": [{"type": "level", "name": "lv", "height": height, "height_ref": height_ref}],
        }
    )


def test_level_above_box_message():
    with pytest.raises(ValueError, match=r"above the box .exterior height 860mm."):
        resolve_frame(_spec_with_level("1000mm"), get_vendor("rmfg").catalog())
    with pytest.raises(ValueError, match=r"must be between 76.2mm and 821.9mm"):
        resolve_frame(_spec_with_level("1000mm"), get_vendor("rmfg").catalog())


def test_level_colliding_with_top_frame_message():
    with pytest.raises(ValueError, match="collides with the base or top frame"):
        resolve_frame(_spec_with_level("850mm"), get_vendor("rmfg").catalog())


def test_level_too_low_message():
    with pytest.raises(ValueError, match="collides with the base or top frame"):
        resolve_frame(_spec_with_level("50mm"), get_vendor("rmfg").catalog())


def test_level_range_respects_height_ref():
    # centerline range shifts by half a tube vs top_face
    with pytest.raises(ValueError, match=r"must be between 57.15mm and 802.85mm"):
        resolve_frame(
            _spec_with_level("30mm", height_ref="centerline"), get_vendor("rmfg").catalog()
        )


def test_level_at_range_edges_ok():
    # exactly at the published limits must build
    frame = resolve_frame(_spec_with_level("821.9mm"), get_vendor("rmfg").catalog())
    assert "lv" in frame.layers
    frame = resolve_frame(_spec_with_level("76.2mm"), get_vendor("rmfg").catalog())
    assert "lv" in frame.layers
