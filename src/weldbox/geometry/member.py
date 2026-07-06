"""Member solid construction and STEP export."""

from __future__ import annotations

from pathlib import Path

from build123d import Part, Pos, export_step, extrude

from ..features import RivetHole, SlotFeature, TabFeature
from ..frame import Member
from .cutters import end_trim, rivet_hole_cutter, slot_cutter
from .profile import hollow_section_sketch


def build_part_solid(member: Member) -> Part:
    """Build a member's solid in its local frame: cross-section centered on
    XY, nominal length 0..L along +Z (same convention as the vendor sample
    STEP files); tabs protrude past the nominal end planes."""
    profile = member.profile
    tabs0 = [f for f in member.features if isinstance(f, TabFeature) and f.end == 0]
    tabs1 = [f for f in member.features if isinstance(f, TabFeature) and f.end == 1]
    e0 = max((t.protrusion for t in tabs0), default=0.0)
    e1 = max((t.protrusion for t in tabs1), default=0.0)

    sketch = hollow_section_sketch(profile)
    solid = extrude(sketch, amount=member.length + e0 + e1)
    if e0:
        solid = Pos(0, 0, -e0) * solid

    if tabs0:
        solid -= end_trim(profile, tabs0, end=0, length=member.length)
    if tabs1:
        solid -= end_trim(profile, tabs1, end=1, length=member.length)

    for f in member.features:
        if isinstance(f, SlotFeature):
            solid -= slot_cutter(profile, f)
        elif isinstance(f, RivetHole):
            solid -= rivet_hole_cutter(profile, f)

    solid = Part(solid)
    if not solid.is_valid:
        raise RuntimeError(f"member {member.id}: boolean result is not a valid solid")
    solid.label = member.id
    return solid


def export_part_step(solid: Part, path: Path) -> None:
    export_step(solid, str(path))
