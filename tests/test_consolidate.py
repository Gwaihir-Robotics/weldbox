from pathlib import Path

import pytest

from weldbox.consolidate import consolidate_parts
from weldbox.dedupe import group_parts
from weldbox.features import RivetHole, SlotFeature, TabFeature, plan_features
from weldbox.frame import resolve_frame
from weldbox.spec import load_spec
from weldbox.vendors import get_vendor

FIXTURE = Path(__file__).parent / "fixtures" / "winding_machine_cell.yaml"


def build_frame(consolidate: bool):
    spec = load_spec(FIXTURE)
    frame = resolve_frame(spec, get_vendor("rfmg").catalog())
    plan_features(frame, spec)
    added = consolidate_parts(frame) if consolidate else {}
    return frame, added


def test_reduces_to_three_unique_parts():
    frame, added = build_frame(consolidate=True)
    parts = group_parts(frame)
    assert len(parts) == 3
    by_len = {round(p.exemplar.length, 1): p.qty for p in parts}
    assert by_len == {2000.0: 4, 923.8: 12, 723.8: 9}
    assert sum(p.qty for p in parts) == len(frame.members)
    assert sum(added.values()) > 0


def test_without_consolidation_stays_thirteen():
    frame, _ = build_frame(consolidate=False)
    assert len(group_parts(frame)) == 13


def test_consolidation_only_adds_cuts_never_tabs():
    before, _ = build_frame(consolidate=False)
    tabs_before = {
        m.id: sorted(
            (f.end, f.wall) for f in m.features if isinstance(f, TabFeature)
        )
        for m in before.members
    }
    after, added = build_frame(consolidate=True)
    for m in after.members:
        tabs = sorted((f.end, f.wall) for f in m.features if isinstance(f, TabFeature))
        assert tabs == tabs_before[m.id], m.id
    # every added feature is a slot or hole (a cut), never a tab
    total_tabs_before = sum(len(v) for v in tabs_before.values())
    total_tabs_after = sum(
        1 for m in after.members for f in m.features if isinstance(f, TabFeature)
    )
    assert total_tabs_after == total_tabs_before


def test_planned_features_survive():
    """Consolidation must never drop a feature that was actually needed."""
    from weldbox.features import feature_key

    before, _ = build_frame(consolidate=False)
    needed = {m.id: {feature_key(f) for f in m.features} for m in before.members}
    after, _ = build_frame(consolidate=True)
    for m in after.members:
        have = {feature_key(f) for f in m.features}
        assert needed[m.id] <= have, f"{m.id} lost planned features"


def test_no_feature_overlaps():
    from weldbox.consolidate import _has_conflict

    frame, _ = build_frame(consolidate=True)
    for m in frame.members:
        assert not _has_conflict(m.features), m.id
