"""Tab/slot test coupon: a small 4-tube assembly for verifying joint
clearances with a vendor and material before ordering a full build.

The coupon is one corner of a box plus a support, inside a small cube
envelope (default 100mm):

    post     vertical, full envelope height
    rail-x   butts into the post   -> corner joint; its lower tab's slot
    rail-y   butts into the post      opens through the post's bottom end
                                      (the hook-in notch used at box corners)
    support  stands on rail-x at its midpoint -> closed tee joint

Between them the four members exercise every joint feature weldbox cuts:
end tabs, closed through-wall slots, open hook-in notches, and dog-bone
reliefs — so a single cheap order proves the slip fit on the real material
before a full frame is committed.
"""

from __future__ import annotations

from .frame import FrameGraph, Joint, Member
from .spec import BoxSpec, Exterior, JointConfig, MaterialRef
from .vendors import get_vendor

DEFAULT_ENVELOPE_MM = 100.0
# the support (one tube wide) must land on the rail with some shoulder
_MIN_FIT_MARGIN_MM = 20.0


def coupon_spec(
    vendor: str,
    size_mm: float,
    wall_mm: float,
    family: str | None,
    envelope_mm: float = DEFAULT_ENVELOPE_MM,
    joints: JointConfig | None = None,
    name: str | None = None,
) -> tuple[BoxSpec, float]:
    """Build the synthetic BoxSpec for a coupon. Returns (spec, envelope);
    the envelope is grown when the tube is too large for the requested cube
    (the rail must be long enough to carry the support plus a shoulder)."""
    min_envelope = 2 * size_mm + _MIN_FIT_MARGIN_MM
    envelope = max(envelope_mm, min_envelope)
    spec = BoxSpec(
        name=name or f"tab-slot-coupon-{size_mm:g}mm-x{wall_mm:g}mm",
        vendor=vendor,
        material=MaterialRef(shape="square", size=[size_mm], wall=wall_mm, family=family),
        exterior=Exterior(height=envelope, width=envelope, depth=envelope),
        joints=joints or JointConfig(),
        quantity=1,
    )
    return spec, envelope


def build_coupon(spec: BoxSpec, envelope: float) -> FrameGraph:
    profile = get_vendor(spec.vendor).catalog().find(
        spec.material.shape,
        spec.material.outer_w_mm,
        spec.material.outer_h_mm,
        spec.material.wall,
        material_family=spec.material.family,
    )
    if profile.shape != "square":
        raise NotImplementedError("coupons support square tube only")

    s = profile.outer_w_mm
    wg = spec.joints.weld_gap
    e = envelope
    half = s / 2
    arm = e - s - wg  # rail/support length

    members = [
        Member(id="post", role="post", profile=profile, axis="z",
               origin=(half, half, 0.0), length=e),
        Member(id="rail-x", role="rail", profile=profile, axis="x",
               origin=(s + wg, half, half), length=arm),
        Member(id="rail-y", role="rail", profile=profile, axis="y",
               origin=(half, s + wg, half), length=arm),
        # standing on rail-x at its midpoint, reaching the top of the envelope
        Member(id="support", role="support", profile=profile, axis="z",
               origin=((e + s) / 2, half, s + wg), length=arm),
    ]
    joints = [
        # corner joints into the post at the rail height: the lower tab's
        # slot lands flush with the post's bottom end -> open hook-in notch
        Joint(kind="corner_butt", tab_member="rail-x", tab_end=0,
              slot_member="post", slot_face="+x", position_mm=half),
        Joint(kind="corner_butt", tab_member="rail-y", tab_end=0,
              slot_member="post", slot_face="+y", position_mm=half),
        # closed tee joint mid-rail
        Joint(kind="tee", tab_member="support", tab_end=0,
              slot_member="rail-x", slot_face="+z", position_mm=arm / 2),
    ]
    return FrameGraph(spec=spec, profile=profile, members=members, joints=joints, layers={})
