"""Cut list manifest: cutlist.md + cutlist.csv."""

from __future__ import annotations

import csv
from pathlib import Path

from .dedupe import UniquePart
from .frame import FrameGraph
from .spec import BoxSpec
from .units import inches


def _rows(spec: BoxSpec, frame: FrameGraph, parts: list[UniquePart], filenames: dict[str, str]):
    for p in parts:
        yield {
            "part": p.name,
            "profile": p.exemplar.profile.display_name,
            "length_mm": f"{p.exemplar.length:.1f}",
            "length_in": f"{inches(p.exemplar.length):.3f}",
            "qty_per_assembly": p.qty,
            "qty_total": p.qty * spec.quantity,
            "members": ", ".join(p.member_ids),
            "file": filenames.get(p.name, ""),
        }


def write_manifest(
    out_dir: Path,
    spec: BoxSpec,
    frame: FrameGraph,
    parts: list[UniquePart],
    filenames: dict[str, str] | None = None,
    panel_files: list[tuple[str, str, int]] | None = None,  # (name, file, qty/assy)
    shipping=None,  # shipping.ShippingEstimate | None
) -> None:
    filenames = filenames or {}
    rows = list(_rows(spec, frame, parts, filenames))

    with (out_dir / "cutlist.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    total_members = sum(p.qty for p in parts)
    stock_mm = sum(frame.member(mid).length for p in parts for mid in p.member_ids)
    lines = [
        f"# Cut list — {spec.name}",
        "",
        f"- Vendor: **{spec.vendor}**",
        f"- Tube: **{frame.profile.display_name}**",
        f"- Exterior (H x W x D): **{spec.exterior.height:g} x {spec.exterior.width:g} x {spec.exterior.depth:g} mm**",
        f"- Assemblies: **{spec.quantity}**",
        f"- Tube members per assembly: **{total_members}** "
        f"({stock_mm / 1000:.1f} m of stock; {stock_mm * spec.quantity / 1000:.1f} m total)",
        "",
        "| Part | Profile | Length (mm) | Length (in) | Qty/assy | Qty total | File |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['part']} | {r['profile']} | {r['length_mm']} | {r['length_in']} "
            f"| {r['qty_per_assembly']} | {r['qty_total']} | {r['file']} |"
        )
    if panel_files:
        lines += [
            "",
            "## Sheet panels",
            "",
            "| Panel | Qty/assy | Qty total | File |",
            "|---|---:|---:|---|",
        ]
        for name, file, qty in panel_files:
            lines.append(f"| {name} | {qty} | {qty * spec.quantity} | {file} |")
    if shipping is not None:
        lines += ["", "## Shipping", ""]
        if shipping.freight:
            lines.append(
                f"**LTL freight required** (+${shipping.rules.freight_flat_usd:.0f} flat) — "
                f"estimated order weight ~{shipping.total_lb:.0f} lb."
            )
            lines.append("")
            for r in shipping.reasons:
                lines.append(f"- {r}")
            if shipping.rules.freight_notes:
                lines.append(f"\n_{shipping.rules.freight_notes}_")
        else:
            lines.append(
                f"Estimated order weight ~{shipping.total_lb:.0f} lb — within "
                "standard parcel limits."
            )
    lines.append("")
    (out_dir / "cutlist.md").write_text("\n".join(lines))
