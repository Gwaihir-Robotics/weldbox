"""End-to-end acceptance: the PRD's Winding Machine Cell example."""

from pathlib import Path

import ezdxf
import pytest

pytestmark = pytest.mark.slow

FIXTURE = Path(__file__).parent / "fixtures" / "winding_machine_cell.yaml"


@pytest.fixture(scope="module")
def out_dir(tmp_path_factory):
    from weldbox.generate import run_generate

    root = tmp_path_factory.mktemp("out")
    return run_generate(FIXTURE, root)


def test_output_bundle(out_dir):
    assert (out_dir / "cutlist.md").exists()
    assert (out_dir / "cutlist.csv").exists()
    assert (out_dir / "assembly.step").exists()
    assert len(list((out_dir / "parts").glob("*.step"))) == 3  # consolidated
    dxfs = sorted(p.name for p in (out_dir / "panels").glob("*.dxf"))
    # sides consolidate into one flat part; back stays its own
    assert len(dxfs) == 2
    assert any("left-right" in d for d in dxfs)


def test_manifest_contents(out_dir):
    md = (out_dir / "cutlist.md").read_text()
    assert "Winding Machine Cell" in md
    assert "1.5 x 1.5 x .120 in Square Tube" in md
    assert "2000 x 1000 x 800 mm" in md
    csv_text = (out_dir / "cutlist.csv").read_text()
    assert "2000.0" in csv_text and "923.8" in csv_text and "723.8" in csv_text


def test_panel_dxf_readable(out_dir):
    for dxf in (out_dir / "panels").glob("*.dxf"):
        doc = ezdxf.readfile(dxf)
        msp = doc.modelspace()
        assert len(msp.query("LWPOLYLINE")) == 1
        assert len(msp.query("CIRCLE")) > 0


def test_no_joint_interference():
    """Placed members must not overlap: tabs pass through slot voids."""
    from weldbox.features import plan_features
    from weldbox.frame import resolve_frame
    from weldbox.generate import load_spec
    from weldbox.geometry.assembly import member_location
    from weldbox.geometry.member import build_part_solid
    from weldbox.vendors import get_vendor

    from weldbox.consolidate import consolidate_parts

    spec = load_spec(FIXTURE)
    frame = resolve_frame(spec, get_vendor("rfmg").catalog())
    plan_features(frame, spec)
    consolidate_parts(frame)  # sacrificial cuts must not create interference

    pairs = [
        ("work-surface-cross-1", "work-surface-front-rail"),
        ("work-surface-front-rail", "post-fl"),
        ("support-base-work-surface-front", "base-front-rail"),
        ("top-spanner-1", "top-left-rail"),
        ("base-front-rail", "post-fl"),  # corner butt with hook-in tabs
        ("top-back-rail", "post-br"),
    ]
    for a_id, b_id in pairs:
        a, b = frame.member(a_id), frame.member(b_id)
        sa = build_part_solid(a).moved(member_location(a))
        sb = build_part_solid(b).moved(member_location(b))
        inter = sa.intersect(sb)
        vol = inter.volume if inter else 0.0
        assert vol == pytest.approx(0.0, abs=1e-6), f"{a_id} intersects {b_id}"


def test_ladder_topology_no_joint_interference():
    """top_bottom_frames: posts and depth rails tab into the full-width
    rails with zero overlap."""
    from weldbox.consolidate import consolidate_parts
    from weldbox.features import plan_features
    from weldbox.frame import resolve_frame
    from weldbox.generate import load_spec
    from weldbox.geometry.assembly import member_location
    from weldbox.geometry.member import build_part_solid
    from weldbox.vendors import get_vendor

    spec = load_spec(Path(__file__).parent.parent / "examples" / "epoxy_machine_cell.yaml")
    frame = resolve_frame(spec, get_vendor("rfmg").catalog())
    plan_features(frame, spec)
    consolidate_parts(frame)

    pairs = [
        ("post-fl", "base-front-rail"),
        ("post-br", "top-back-rail"),
        ("base-left-rail", "base-front-rail"),
        ("support-base-top-front", "top-front-rail"),
        ("top-spanner-1", "top-left-rail"),
    ]
    for a_id, b_id in pairs:
        a, b = frame.member(a_id), frame.member(b_id)
        sa = build_part_solid(a).moved(member_location(a))
        sb = build_part_solid(b).moved(member_location(b))
        inter = sa.intersect(sb)
        vol = inter.volume if inter else 0.0
        assert vol == pytest.approx(0.0, abs=1e-6), f"{a_id} intersects {b_id}"
