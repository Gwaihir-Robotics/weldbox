from pathlib import Path

import pytest

from weldbox.spec import BoxSpec, LevelSpec, SpannerSpec, SupportsSpec, dump_spec, load_spec

FIXTURE = Path(__file__).parent / "fixtures" / "winding_machine_cell.yaml"


def test_load_acceptance_fixture():
    spec = load_spec(FIXTURE)
    assert spec.name == "Winding Machine Cell"
    assert spec.vendor == "rfmg"
    assert spec.exterior.height == 2000.0
    assert spec.exterior.width == 1000.0
    assert spec.exterior.depth == 800.0
    assert spec.material.outer_w_mm == pytest.approx(38.1)
    assert spec.material.wall == pytest.approx(3.048)
    assert spec.quantity == 5

    kinds = [type(b) for b in spec.blocking]
    assert kinds == [LevelSpec, SupportsSpec, SpannerSpec, SpannerSpec]
    level = spec.blocking[0]
    assert level.height == 1000.0
    assert level.cross_members.count == 3
    assert level.cross_members.axis == "depth"

    assert spec.siding.attachment.rivet == pytest.approx(6.35)
    assert spec.siding.attachment.spacing == 100.0
    faces = [f for p in spec.siding.panels for f in p.faces]
    assert faces == ["left", "right", "back"]
    assert spec.siding.panels[0].material.thickness == pytest.approx(0.9652)


def test_joint_defaults():
    spec = load_spec(FIXTURE)
    assert spec.joints.style == "through_wall_tab"
    assert spec.joints.slot_clearance == pytest.approx(0.25)
    assert spec.joints.weld_gap == 0.0
    assert spec.joints.corner_tabs is True
    assert spec.siding.corner_radius == pytest.approx(5.0)


def test_too_small_exterior_rejected():
    with pytest.raises(ValueError, match="too small"):
        BoxSpec.model_validate(
            {
                "name": "tiny",
                "material": {"size": ["1.5in"], "wall": "0.120in"},
                "exterior": {"height": "50mm", "width": "1000mm", "depth": "800mm"},
            }
        )


def test_spec_roundtrip(tmp_path):
    spec = load_spec(FIXTURE)
    out = tmp_path / "roundtrip.yaml"
    dump_spec(spec, out)
    again = load_spec(out)
    assert again == spec
