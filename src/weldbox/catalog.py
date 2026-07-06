"""Vendor tube material catalogs.

Profiles are loaded from per-vendor YAML files (see vendors/data/*.yaml),
hand-encoded from each vendor's published material list. Dimensions in the
YAML are inches (as published); they are converted to mm on load.

Corner radius: some vendor tables (e.g. RMFG stainless and aluminum) omit
the outside corner radius. Where missing on a square/rect profile we fall
back to 2 x wall, which matches every steel row RMFG does publish.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .units import MM_PER_INCH

MATCH_TOL_MM = 0.02


@dataclass(frozen=True)
class TubeProfile:
    id: str
    shape: str  # "square" | "rect" | "round" | "pipe"
    outer_w_mm: float  # width (or OD for round)
    outer_h_mm: float  # height (== width for square/round)
    wall_mm: float
    corner_r_mm: float | None  # outside corner radius; None for round
    material_family: str  # e.g. "A500", "304", "6061 T6"
    display_name: str

    @property
    def corner_r_resolved_mm(self) -> float:
        """Outside corner radius, falling back to 2 x wall when unpublished."""
        if self.shape == "round":
            return 0.0
        if self.corner_r_mm is not None:
            return self.corner_r_mm
        return 2.0 * self.wall_mm

    @property
    def section_area_mm2(self) -> float:
        """Analytic hollow-section area (used for weight estimates)."""
        from math import pi

        w, h, t = self.outer_w_mm, self.outer_h_mm, self.wall_mm
        if self.shape == "round":
            return pi / 4 * (w**2 - (w - 2 * t) ** 2)
        r_out = self.corner_r_resolved_mm if self.corner_r_resolved_mm > 0.01 else 0.0
        r_in = max(r_out - t, 0.0)
        outer = w * h - (4 - pi) * r_out**2
        inner = (w - 2 * t) * (h - 2 * t) - (4 - pi) * r_in**2
        return outer - inner

    @property
    def density_g_cm3(self) -> float:
        return density_for(self.material_family)


def density_for(material_family: str) -> float:
    fam = material_family.lower()
    if "6061" in fam or "6063" in fam:
        return 2.70  # aluminum
    if "304" in fam or "stainless" in fam:
        return 8.00  # stainless
    return 7.85  # carbon/alloy steel (A500, 4130, DOM)


@dataclass(frozen=True)
class SheetMaterial:
    alloy: str
    thickness_mm: float


@dataclass
class Catalog:
    vendor: str
    profiles: list[TubeProfile] = field(default_factory=list)

    def find(
        self,
        shape: str,
        outer_w_mm: float,
        outer_h_mm: float,
        wall_mm: float,
        material_family: str | None = None,
    ) -> TubeProfile:
        shape = _normalize_shape(shape)
        matches = [
            p
            for p in self.profiles
            if _normalize_shape(p.shape) == shape
            and _close(p.wall_mm, wall_mm)
            and (
                (_close(p.outer_w_mm, outer_w_mm) and _close(p.outer_h_mm, outer_h_mm))
                or (_close(p.outer_w_mm, outer_h_mm) and _close(p.outer_h_mm, outer_w_mm))
            )
        ]
        if material_family:
            fam = material_family.lower()
            matches = [p for p in matches if fam in p.material_family.lower()]
        if not matches:
            raise LookupError(
                f"no {shape} profile {outer_w_mm:g}x{outer_h_mm:g}mm wall {wall_mm:g}mm"
                f"{' (' + material_family + ')' if material_family else ''}"
                f" in {self.vendor} catalog"
            )
        if len(matches) > 1:
            names = ", ".join(p.display_name for p in matches)
            raise LookupError(
                f"ambiguous profile match in {self.vendor} catalog ({names}); "
                "specify material family to disambiguate"
            )
        return matches[0]


def _close(a: float, b: float, tol: float = MATCH_TOL_MM) -> bool:
    return abs(a - b) <= tol


def _normalize_shape(shape: str) -> str:
    s = shape.lower()
    return {"rectangular": "rect", "rectangle": "rect"}.get(s, s)


def load_catalog(path: Path, vendor: str) -> Catalog:
    """Load a vendor catalog YAML (dimensions in inches) into mm profiles."""
    data = yaml.safe_load(path.read_text()) or {}
    profiles = []
    for row in data.get("profiles", []):
        shape = _normalize_shape(row["shape"])
        outer = row["outer_in"]
        if isinstance(outer, (int, float)):
            outer_w = outer_h = float(outer)
        else:
            outer_w, outer_h = (float(v) for v in outer)
        corner = row.get("corner_r_in")
        profiles.append(
            TubeProfile(
                id=row["id"],
                shape=shape,
                outer_w_mm=outer_w * MM_PER_INCH,
                outer_h_mm=outer_h * MM_PER_INCH,
                wall_mm=float(row["wall_in"]) * MM_PER_INCH,
                corner_r_mm=None if corner is None else float(corner) * MM_PER_INCH,
                material_family=str(row["family"]),
                display_name=row["name"],
            )
        )
    return Catalog(vendor=vendor, profiles=profiles)
