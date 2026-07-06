from pathlib import Path

import pytest

from weldbox.dedupe import group_parts, part_signature
from weldbox.features import plan_features
from weldbox.frame import resolve_frame
from weldbox.spec import load_spec
from weldbox.vendors import get_vendor

FIXTURE = Path(__file__).parent / "fixtures" / "winding_machine_cell.yaml"


@pytest.fixture(scope="module")
def parts_and_frame():
    spec = load_spec(FIXTURE)
    frame = resolve_frame(spec, get_vendor("rmfg").catalog())
    plan_features(frame, spec)
    return group_parts(frame), frame


def group_of(parts, member_id):
    return next(p for p in parts if member_id in p.member_ids)


def test_plain_parts_merge(parts_and_frame):
    parts, _ = parts_and_frame
    # 3 identical cross members collapse into one part
    assert group_of(parts, "work-surface-cross-1").qty == 3
    # the spanners, the front support, and the (corner-tabbed) plain top
    # front rail are physically identical: 923.8mm, four end tabs, no holes
    spanners = group_of(parts, "top-spanner-1")
    assert set(spanners.member_ids) == {
        "top-spanner-1",
        "bottom-spanner-1",
        "support-base-work-surface-front",
        "top-front-rail",
    }


def test_posts_split_by_chirality(parts_and_frame):
    parts, _ = parts_and_frame
    # bl/br posts are rotations of each other; fl and fr are mirror images
    # (left-hand vs right-hand corner posts) and stay separate parts
    assert group_of(parts, "post-bl") is group_of(parts, "post-br")
    fl = group_of(parts, "post-fl")
    fr = group_of(parts, "post-fr")
    assert fl is not fr
    assert fl.qty == fr.qty == 1
    assert group_of(parts, "post-bl").qty == 2


def test_supports_merge_by_rotation(parts_and_frame):
    parts, _ = parts_and_frame
    # back/left/right supports all have tabs + one riveted face -> one part,
    # and the top back rail (tabs + 9 holes) is the same part too
    back = group_of(parts, "support-base-work-surface-back")
    assert set(back.member_ids) == {
        "support-base-work-surface-back",
        "support-base-work-surface-left",
        "support-base-work-surface-right",
        "top-back-rail",
    }


def test_flip_symmetry_signature():
    """A part's signature must equal its end-swapped twin's."""
    spec = load_spec(FIXTURE)
    frame = resolve_frame(spec, get_vendor("rmfg").catalog())
    plan_features(frame, spec)
    m = frame.member("work-surface-cross-1")
    sig_a = part_signature(m)

    # flip the member end-for-end by hand: ends swap, z -> L - z, y -> -y
    from weldbox.features import SlotFeature, TabFeature

    flipped = []
    flip_face = {"+x": "+x", "-x": "-x", "+y": "-y", "-y": "+y"}
    for f in m.features:
        if isinstance(f, TabFeature):
            flipped.append(
                TabFeature(end=1 - f.end, wall=flip_face[f.wall], width=f.width, protrusion=f.protrusion)
            )
        elif isinstance(f, SlotFeature):
            flipped.append(
                SlotFeature(
                    face=flip_face[f.face],
                    z=m.length - f.z,
                    lateral=-f.lateral if f.face in ("+x", "-x") else f.lateral,
                    length=f.length,
                    width=f.width,
                    dogbone_r=f.dogbone_r,
                )
            )
        else:
            flipped.append(f)
    m2 = type(m)(
        id="twin", role=m.role, profile=m.profile, axis=m.axis,
        origin=m.origin, length=m.length, features=flipped,
    )
    assert part_signature(m2) == sig_a


def test_total_member_count_preserved(parts_and_frame):
    parts, frame = parts_and_frame
    assert sum(p.qty for p in parts) == len(frame.members)
    all_ids = [mid for p in parts for mid in p.member_ids]
    assert len(all_ids) == len(set(all_ids))
