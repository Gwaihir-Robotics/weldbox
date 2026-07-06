import pytest

from weldbox.coupon import build_coupon, coupon_spec
from weldbox.dedupe import group_parts
from weldbox.features import SlotFeature, TabFeature, plan_features
from weldbox.spec import JointConfig

TUBE = 38.1
WALL = 3.048


def make(clearance=0.25, size=TUBE, wall=WALL, envelope=100.0, family=None):
    spec, env = coupon_spec(
        "rmfg", size, wall, family,
        envelope_mm=envelope,
        joints=JointConfig(slot_clearance=clearance),
    )
    frame = build_coupon(spec, env)
    plan_features(frame, spec)
    return spec, env, frame


def test_coupon_members_and_lengths():
    _, env, frame = make()
    assert env == 100.0
    lengths = {m.id: m.length for m in frame.members}
    assert lengths == {
        "post": pytest.approx(100.0),
        "rail-x": pytest.approx(61.9),
        "rail-y": pytest.approx(61.9),
        "support": pytest.approx(61.9),
    }


def test_coupon_fits_envelope():
    _, env, frame = make()
    for m in frame.members:
        s = m.profile.outer_w_mm / 2
        lo, hi = m.origin, m.end
        for i in range(3):
            axis_along = {"x": 0, "y": 1, "z": 2}[m.axis] == i
            pad = 0 if axis_along else s
            assert min(lo[i], hi[i]) - pad >= -1e-9, m.id
            assert max(lo[i], hi[i]) + pad <= env + 1e-9, m.id


def test_coupon_exercises_all_joint_features():
    _, _, frame = make()
    post = frame.member("post")
    slots = [f for f in post.features if isinstance(f, SlotFeature)]
    # 2 rails x 2 slots; the lower slot of each pair opens through the
    # post's bottom end (hook-in notch)
    assert len(slots) == 4
    half_w = (WALL + 0.25) / 2
    assert sum(1 for s in slots if s.z - half_w < 0) == 2
    assert sum(1 for s in slots if s.z - half_w > 0) == 2  # closed corner slots

    rail = frame.member("rail-x")
    rail_slots = [f for f in rail.features if isinstance(f, SlotFeature)]
    assert len(rail_slots) == 2  # closed tee slots from the support
    assert all(s.face == "+y" for s in rail_slots)  # top face of an x member

    for mid in ("rail-x", "rail-y", "support"):
        tabs = [f for f in frame.member(mid).features if isinstance(f, TabFeature)]
        assert len(tabs) == 2 and all(t.end == 0 for t in tabs), mid


def test_clearance_option_reaches_slots():
    _, _, frame = make(clearance=0.4)
    slot = next(f for f in frame.member("post").features if isinstance(f, SlotFeature))
    assert slot.width == pytest.approx(WALL + 0.4)


def test_envelope_grows_for_big_tube():
    # 2x2x0.25 tube can't fit the support on a 100mm coupon rail
    spec, env, frame = make(size=2 * 25.4, wall=0.25 * 25.4, family="A500")
    assert env == pytest.approx(2 * 2 * 25.4 + 20.0)
    rail = frame.member("rail-x")
    assert rail.length > 2 * 25.4  # support (one tube wide) fits with shoulder


def test_coupon_consolidates_rails_and_support():
    from weldbox.consolidate import consolidate_parts

    _, _, frame = make()
    consolidate_parts(frame)
    parts = group_parts(frame)
    assert len(parts) == 2  # post + one 61.9mm part x3
    by_qty = sorted(p.qty for p in parts)
    assert by_qty == [1, 3]
