"""Tube cross-section sketches (build123d), matching vendor stock geometry."""

from __future__ import annotations

from build123d import Rectangle, RectangleRounded, Sketch

from ..catalog import TubeProfile

# below this, an inner radius is treated as a sharp corner
_MIN_RADIUS = 0.01


def hollow_section_sketch(profile: TubeProfile) -> Sketch:
    """Cross-section of a square/rect tube: rounded outer rectangle minus
    rounded inner rectangle, centered on the origin (the member centerline).
    Inner corner radius = outer radius - wall, clamped to sharp when the
    published outer radius does not exceed the wall (e.g. 1x1x1/16 A500)."""
    if profile.shape not in ("square", "rect"):
        raise NotImplementedError(f"geometry for {profile.shape} tube not implemented")
    w, h, t = profile.outer_w_mm, profile.outer_h_mm, profile.wall_mm
    r_out = profile.corner_r_resolved_mm

    outer = RectangleRounded(w, h, r_out) if r_out > _MIN_RADIUS else Rectangle(w, h)
    r_in = r_out - t
    if r_in > _MIN_RADIUS:
        inner = RectangleRounded(w - 2 * t, h - 2 * t, r_in)
    else:
        inner = Rectangle(w - 2 * t, h - 2 * t)
    return outer - inner


def section_area(profile: TubeProfile) -> float:
    """Analytic cross-section area of the hollow section (mm^2)."""
    return profile.section_area_mm2
