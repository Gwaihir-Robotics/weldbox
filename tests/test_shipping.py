from pathlib import Path

import pytest

from weldbox.consolidate import consolidate_parts
from weldbox.dedupe import group_parts
from weldbox.features import plan_features
from weldbox.frame import resolve_frame
from weldbox.panels.layout import panel_layouts
from weldbox.shipping import estimate_shipping
from weldbox.spec import BoxSpec, load_spec
from weldbox.vendors import get_vendor

FIXTURE = Path(__file__).parent / "fixtures" / "winding_machine_cell.yaml"


def build(spec):
    vendor = get_vendor(spec.vendor)
    frame = resolve_frame(spec, vendor.catalog())
    hole_map = plan_features(frame, spec)
    consolidate_parts(frame)
    parts = group_parts(frame)
    panels = panel_layouts(frame, spec, hole_map) if spec.siding else []
    return estimate_shipping(spec, parts, panels, vendor.shipping_rules())


def test_winding_cell_triggers_freight():
    est = build(load_spec(FIXTURE))
    assert est is not None
    assert est.freight
    # posts are 78.7in long (>= 60in) and the panels are 78.7 x 39.4in
    assert any("post" in r and "78.7" in r for r in est.reasons)
    assert any("panel" in r for r in est.reasons)
    assert any("order weighs" in r for r in est.reasons)
    # 25.6 m of 1.5x1.5x0.120 steel/assembly x5 + stainless panels: heavy
    assert 800 < est.total_lb < 1500


def test_small_box_is_parcel():
    spec = BoxSpec.model_validate(
        {
            "name": "toolbox",
            "vendor": "rfmg",
            "material": {"size": ["1in"], "wall": "0.065in", "family": "A500"},
            "exterior": {"height": "400mm", "width": "500mm", "depth": "400mm"},
        }
    )
    est = build(spec)
    assert est is not None
    assert not est.freight
    assert est.reasons == []
    assert est.total_lb < 30


def test_two_dims_threshold():
    # short but wide/deep box: longest part < 60in but a panel is 49 x 31in
    spec = BoxSpec.model_validate(
        {
            "name": "flat crate",
            "vendor": "rfmg",
            "material": {"size": ["1in"], "wall": "0.065in", "family": "A500"},
            "exterior": {"height": "790mm", "width": "1250mm", "depth": "400mm"},
            "siding": {
                "panels": [
                    {"faces": ["front"], "material": {"alloy": "304", "thickness": '0.038"'}}
                ]
            },
        }
    )
    est = build(spec)
    assert est.freight
    assert any(">= 48\" x 30\"" in r for r in est.reasons)


def test_no_rules_vendor_returns_none():
    spec = load_spec(FIXTURE)
    vendor = get_vendor("oshcut")
    assert vendor.shipping_rules() is None
    assert estimate_shipping(spec, [], [], None) is None
