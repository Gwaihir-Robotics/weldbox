"""weldbox CLI: generate / wizard / catalog."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .units import inches
from .vendors import VENDORS, get_vendor

app = typer.Typer(help="Generate vendor-ready tube laser cut lists for welded boxes.")
catalog_app = typer.Typer(help="Browse vendor material catalogs.")
app.add_typer(catalog_app, name="catalog")

console = Console()


@catalog_app.command("list")
def catalog_list(
    vendor: str = typer.Option("rfmg", help=f"Vendor: {', '.join(sorted(VENDORS))}"),
    shape: str = typer.Option(None, help="Filter by shape: square, rect, round"),
) -> None:
    """List tube profiles available from a vendor."""
    v = get_vendor(vendor)
    cat = v.catalog()
    profiles = cat.profiles
    if shape:
        profiles = [p for p in profiles if p.shape == shape.lower().replace("rectangular", "rect")]
    if not profiles:
        console.print(
            f"[yellow]No profiles for vendor '{v.display_name}'"
            f"{f' with shape {shape}' if shape else ''}."
            + (" Catalog not yet encoded." if not cat.profiles else "")
        )
        raise typer.Exit(1)

    table = Table(title=f"{v.display_name} tube profiles ({len(profiles)})")
    table.add_column("Profile")
    table.add_column("Shape")
    table.add_column("Outer (in)", justify="right")
    table.add_column("Wall (in)", justify="right")
    table.add_column("Corner R (in)", justify="right")
    table.add_column("Family")
    for p in profiles:
        outer = (
            f"{inches(p.outer_w_mm):g}"
            if p.outer_w_mm == p.outer_h_mm
            else f"{inches(p.outer_w_mm):g} x {inches(p.outer_h_mm):g}"
        )
        corner = "—" if p.shape == "round" else (
            f"{inches(p.corner_r_mm):g}" if p.corner_r_mm is not None
            else f"{inches(p.corner_r_resolved_mm):g}*"
        )
        table.add_row(p.display_name, p.shape, outer, f"{inches(p.wall_mm):g}", corner, p.material_family)
    console.print(table)
    console.print("[dim]* corner radius not published; 2 x wall assumed[/dim]")


@app.command()
def generate(
    spec_path: Path = typer.Argument(..., help="Path to a box spec YAML file"),
    out: Path = typer.Option(Path("out"), "-o", "--out", help="Output directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print cut list only, no CAD"),
    skip_assembly: bool = typer.Option(False, help="Skip the combined assembly STEP"),
) -> None:
    """Generate the cut list (STEP files, panel DXFs, manifest) from a spec."""
    from pydantic import ValidationError

    from .generate import run_generate

    try:
        run_generate(spec_path, out, dry_run=dry_run, skip_assembly=skip_assembly, console=console)
    except ValidationError as exc:
        console.print(f"[red]error:[/red] invalid spec {spec_path}:")
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"])
            console.print(f"  [red]•[/red] {loc}: {err['msg']}")
        raise typer.Exit(1) from None
    except (ValueError, LookupError, NotImplementedError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(1) from None


@app.command()
def wizard(
    spec_path: Path = typer.Argument(None, help="Existing spec YAML to edit"),
) -> None:
    """Interactively author a box spec YAML."""
    from .wizard import run_wizard

    run_wizard(spec_path, console=console)


if __name__ == "__main__":
    app()
