"""Order shipping estimate: part weights/dimensions vs vendor parcel limits.

Weights are analytic (section area x length x density for tubes, area x
thickness for sheet) so the check runs in --dry-run without CAD. Feature
cuts remove <1% of material and are ignored — estimates round UP against
the thresholds anyway.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .catalog import density_for
from .dedupe import UniquePart
from .spec import BoxSpec
from .units import inches
from .vendors.base import ShippingRules

LB_PER_KG = 2.20462


@dataclass
class ShippingEstimate:
    total_lb: float
    freight: bool
    reasons: list[str] = field(default_factory=list)
    rules: ShippingRules | None = None


def _tube_part_weight_kg(part: UniquePart) -> float:
    m = part.exemplar
    volume_mm3 = m.profile.section_area_mm2 * m.length
    return volume_mm3 / 1000.0 * m.profile.density_g_cm3 / 1000.0


def estimate_shipping(
    spec: BoxSpec,
    parts: list[UniquePart],
    panels: list,  # unique panels.layout.Panel (qty = per assembly)
    rules: ShippingRules | None,
) -> ShippingEstimate | None:
    if rules is None:
        return None

    reasons: list[str] = []
    total_kg = 0.0

    def check_dims(name: str, dims_mm: tuple[float, float, float], weight_kg: float):
        nonlocal total_kg
        d = sorted((inches(v) for v in dims_mm), reverse=True)
        lb = weight_kg * LB_PER_KG
        if lb > rules.parcel_max_part_lb:
            reasons.append(f"part '{name}' weighs {lb:.0f} lb (> {rules.parcel_max_part_lb:.0f} lb)")
        if d[0] >= rules.parcel_max_length_in:
            reasons.append(
                f"part '{name}' is {d[0]:.1f}\" long (>= {rules.parcel_max_length_in:.0f}\")"
            )
        big, second = rules.parcel_max_two_dims_in
        if d[0] >= big and d[1] >= second:
            reasons.append(
                f"part '{name}' is {d[0]:.1f}\" x {d[1]:.1f}\" "
                f"(>= {big:.0f}\" x {second:.0f}\")"
            )

    for part in parts:
        m = part.exemplar
        w_kg = _tube_part_weight_kg(part)
        total_kg += w_kg * part.qty * spec.quantity
        check_dims(part.name, (m.length, m.profile.outer_w_mm, m.profile.outer_h_mm), w_kg)

    for panel in panels:
        w_kg = (
            panel.width * panel.height * panel.thickness / 1000.0
            * density_for(panel.material) / 1000.0
        )
        total_kg += w_kg * panel.qty * spec.quantity
        check_dims(f"panel {panel.name}", (panel.width, panel.height, panel.thickness), w_kg)

    total_lb = total_kg * LB_PER_KG
    if total_lb > rules.parcel_max_order_lb:
        reasons.append(
            f"order weighs ~{total_lb:.0f} lb total (> {rules.parcel_max_order_lb:.0f} lb)"
        )

    # duplicate part-level reasons collapse naturally via dict ordering
    reasons = list(dict.fromkeys(reasons))
    return ShippingEstimate(
        total_lb=total_lb, freight=bool(reasons), reasons=reasons, rules=rules
    )
