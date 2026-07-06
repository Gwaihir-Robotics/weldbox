"""Generation pipeline: spec -> frame -> features -> dedupe -> outputs."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from .dedupe import UniquePart, group_parts
from .features import plan_features
from .frame import FrameGraph, resolve_frame
from .manifest import write_manifest
from .spec import BoxSpec, load_spec
from .units import inches
from .vendors import get_vendor


def slugify(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def run_generate(
    spec_path: Path,
    out_root: Path,
    *,
    dry_run: bool = False,
    skip_assembly: bool = False,
    console: Console | None = None,
) -> Path:
    console = console or Console()
    spec = load_spec(spec_path)
    frame = resolve_frame(spec, get_vendor(spec.vendor).catalog())
    return produce_outputs(
        spec, frame, out_root, dry_run=dry_run, skip_assembly=skip_assembly, console=console
    )


def produce_outputs(
    spec,
    frame,
    out_root: Path,
    *,
    dry_run: bool = False,
    skip_assembly: bool = False,
    console: Console | None = None,
) -> Path:
    """Everything downstream of frame resolution: features, consolidation,
    cut list, files. Used by `generate` and by synthetic frames (`coupon`)."""
    console = console or Console()
    vendor = get_vendor(spec.vendor)

    hole_map = plan_features(frame, spec)
    if spec.consolidate:
        from .consolidate import consolidate_parts

        added = consolidate_parts(frame)
        if added:
            console.print(
                f"[dim]consolidation: added {sum(added.values())} sacrificial "
                f"slots/holes across {len(added)} members to reduce unique parts "
                f"(disable with consolidate: false)[/dim]"
            )
    parts = group_parts(frame)

    panels: list = []
    unique_panels: list = []
    if spec.siding and spec.siding.panels:
        from .panels.layout import consolidate_panels, panel_layouts

        panels = panel_layouts(frame, spec, hole_map)
        unique_panels = consolidate_panels(panels, enabled=spec.consolidate)

    from .shipping import estimate_shipping

    shipping = estimate_shipping(spec, parts, unique_panels, vendor.shipping_rules())

    _print_cutlist(console, spec, frame, parts)
    _check_design_rules(console, vendor, spec, parts)
    _print_shipping(console, vendor, shipping)

    if dry_run:
        return out_root

    out_dir = out_root / slugify(spec.name)
    parts_dir = out_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)

    from .geometry.assembly import export_assembly
    from .geometry.member import build_part_solid, export_part_step

    filenames: dict[str, str] = {}
    solids: dict[tuple, object] = {}
    for part in parts:
        solid = build_part_solid(part.exemplar)
        solids[part.signature] = solid
        fname = vendor.part_filename(f"{slugify(spec.name)}_{part.name}", part.exemplar.length, part.qty)
        export_part_step(solid, parts_dir / fname)
        filenames[part.name] = f"parts/{fname}"
    console.print(f"[green]Wrote {len(parts)} part STEP files to {parts_dir}")

    panel_files: list[tuple[str, str, int]] = []
    if unique_panels:
        from .panels.dxf import write_panel_dxf

        panels_dir = out_dir / "panels"
        panels_dir.mkdir(exist_ok=True)
        for panel in unique_panels:
            fname = f"{slugify(spec.name)}_{panel.name}.dxf"
            write_panel_dxf(panel, panels_dir / fname)
            panel_files.append((panel.name, f"panels/{fname}", panel.qty))
        console.print(
            f"[green]Wrote {len(unique_panels)} panel DXF files to {panels_dir} "
            f"({len(panels)} panels/assembly)"
        )

    if not skip_assembly:
        export_assembly(frame, parts, solids, panels, out_dir / "assembly.step")
        console.print(f"[green]Wrote assembly STEP to {out_dir / 'assembly.step'} (open in FreeCAD)")

    write_manifest(out_dir, spec, frame, parts, filenames, panel_files, shipping)
    console.print(f"[green]Wrote cutlist.md / cutlist.csv to {out_dir}")
    return out_dir


def _print_shipping(console: Console, vendor, shipping) -> None:
    if shipping is None:
        return
    if shipping.freight:
        console.print(
            f"[yellow]shipping:[/yellow] ~{shipping.total_lb:.0f} lb — this order "
            f"will ship LTL FREIGHT at {vendor.display_name} "
            f"(+${shipping.rules.freight_flat_usd:.0f} flat):"
        )
        for r in shipping.reasons:
            console.print(f"  [yellow]•[/yellow] {r}")
        if shipping.rules.freight_notes:
            console.print(f"  [dim]{shipping.rules.freight_notes}[/dim]")
    else:
        console.print(
            f"shipping: ~{shipping.total_lb:.0f} lb — within {vendor.display_name} "
            "standard parcel limits"
        )


def _print_cutlist(console: Console, spec: BoxSpec, frame: FrameGraph, parts: list[UniquePart]) -> None:
    table = Table(title=f"{spec.name} — cut list ({spec.quantity} assemblies)")
    table.add_column("Part")
    table.add_column("Length (mm)", justify="right")
    table.add_column("Length (in)", justify="right")
    table.add_column("Qty/assy", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Features", justify="right")
    for p in parts:
        table.add_row(
            p.name,
            f"{p.exemplar.length:.1f}",
            f"{inches(p.exemplar.length):.3f}",
            str(p.qty),
            str(p.qty * spec.quantity),
            str(len(p.exemplar.features)),
        )
    console.print(table)
    total = sum(p.qty for p in parts)
    stock = sum(frame.member(mid).length for p in parts for mid in p.member_ids)
    console.print(
        f"{total} members/assembly, {len(parts)} unique parts, "
        f"{stock / 1000:.1f} m stock/assembly ({stock * spec.quantity / 1000:.1f} m total)"
    )


def _check_design_rules(console: Console, vendor, spec: BoxSpec, parts: list[UniquePart]) -> None:
    from .features import RivetHole, SlotFeature

    rules = vendor.design_rules()
    warnings: list[str] = []
    for p in parts:
        m = p.exemplar
        if m.length > rules.max_part_length_mm:
            warnings.append(
                f"{p.name}: length {m.length:.0f}mm exceeds {vendor.display_name} "
                f"max {rules.max_part_length_mm:.0f}mm"
            )
        for f in m.features:
            if isinstance(f, RivetHole) and f.dia < rules.min_hole_dia_mm:
                warnings.append(
                    f"{p.name}: rivet hole {f.dia:.2f}mm below {vendor.display_name} "
                    f"min {rules.min_hole_dia_mm:.2f}mm"
                )
            if isinstance(f, SlotFeature) and f.dogbone_r < rules.min_slot_corner_r_mm:
                warnings.append(
                    f"{p.name}: dog-bone radius {f.dogbone_r:.2f}mm below "
                    f"{vendor.display_name} min {rules.min_slot_corner_r_mm:.2f}mm"
                )
    for w in dict.fromkeys(warnings):
        console.print(f"[yellow]warning:[/yellow] {w}")
