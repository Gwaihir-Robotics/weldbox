"""Vendor abstraction: each vendor supplies a material catalog, design rules,
and part-file naming. New vendors register in VENDORS."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path

from ..catalog import Catalog, load_catalog


@dataclass(frozen=True)
class DesignRules:
    min_hole_dia_mm: float = 2.0
    min_slot_corner_r_mm: float = 0.5
    max_part_length_mm: float = 6000.0


@dataclass(frozen=True)
class ShippingRules:
    """Parcel limits; exceeding any threshold forces LTL freight."""

    parcel_max_order_lb: float
    parcel_max_part_lb: float
    parcel_max_length_in: float
    # freight if a part's two largest dims are >= both of these
    parcel_max_two_dims_in: tuple[float, float]
    freight_flat_usd: float
    freight_notes: str = ""


class Vendor:
    slug: str = ""
    display_name: str = ""
    rules: DesignRules = DesignRules()
    shipping: ShippingRules | None = None

    def catalog(self) -> Catalog:
        return _load_vendor_catalog(self.slug)

    def design_rules(self) -> DesignRules:
        return self.rules

    def shipping_rules(self) -> ShippingRules | None:
        return self.shipping

    def part_filename(self, part_name: str, length_mm: float, qty: int) -> str:
        safe = part_name.lower().replace(" ", "-")
        return f"{safe}_{length_mm:.1f}mm_x{qty}.step"


@lru_cache(maxsize=None)
def _load_vendor_catalog(slug: str) -> Catalog:
    data_dir = resources.files("weldbox.vendors") / "data"
    return load_catalog(Path(str(data_dir / f"{slug}.yaml")), vendor=slug)


class Rmfg(Vendor):
    slug = "rmfg"
    display_name = "RMFG"
    # From RMFG design notes: "Use larger holes and slots for cleaner features".
    # Published limits are not public; conservative defaults.
    rules = DesignRules(min_hole_dia_mm=3.0, min_slot_corner_r_mm=0.5, max_part_length_mm=6000.0)
    # docs/samples/rmfg/shipping.md
    shipping = ShippingRules(
        parcel_max_order_lb=200.0,
        parcel_max_part_lb=100.0,
        parcel_max_length_in=60.0,
        parcel_max_two_dims_in=(48.0, 30.0),
        freight_flat_usd=200.0,
        freight_notes=(
            "$200 flat per order; ~3 business days transit after production; "
            "ships and delivers Mon-Fri only"
        ),
    )


class Oshcut(Vendor):
    slug = "oshcut"
    display_name = "OshCut"


class Fabtech(Vendor):
    slug = "fabtech"
    display_name = "Fabtech"


VENDORS: dict[str, Vendor] = {v.slug: v for v in (Rmfg(), Oshcut(), Fabtech())}

# historical misspelling of rmfg, kept so specs written against <= 0.2.0 load
_ALIASES = {"rfmg": "rmfg"}


def get_vendor(slug: str) -> Vendor:
    key = slug.lower()
    key = _ALIASES.get(key, key)
    try:
        return VENDORS[key]
    except KeyError:
        raise LookupError(
            f"unknown vendor {slug!r}; available: {', '.join(sorted(VENDORS))}"
        ) from None
