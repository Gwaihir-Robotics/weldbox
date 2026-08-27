"""Interactive spec author. A thin front-end: asks questions, builds a
BoxSpec, writes YAML. No generator logic lives here — the YAML file is the
source of truth and `weldbox generate` runs headless from it."""

from __future__ import annotations

from pathlib import Path

import questionary
from rich.console import Console
from rich.panel import Panel

from .spec import (
    AttachmentSpec,
    BoxSpec,
    CrossMembers,
    Exterior,
    FeetSpec,
    FootPattern,
    LevelSpec,
    MaterialRef,
    MidFeet,
    PanelSpec,
    PlateSpec,
    SheetMaterialSpec,
    SidingSpec,
    SpannerSpec,
    SupportsSpec,
    dump_spec,
    load_spec,
)
from .units import inches, parse_length
from .vendors import VENDORS, get_vendor


def _ask_length(message: str, default: str = "") -> float:
    while True:
        raw = questionary.text(message + " (e.g. 2000mm, 1.5in)", default=default).unsafe_ask()
        try:
            return parse_length(raw)
        except ValueError as exc:
            print(f"  {exc}")


def _ask_plates(level_names: list[str], default_on: bool) -> list[PlateSpec]:
    """Deck plates: a laser-cut sheet resting on top of a layer, notched
    around the members that pass through it."""
    plates: list[PlateSpec] = []
    layer_choices = ["base", "top", *level_names]
    while questionary.confirm(
        "Add a deck plate (baseplate / work surface) resting on a layer?",
        default=default_on if not plates else False,
    ).unsafe_ask():
        layer = questionary.select("Rest the plate on which layer?", choices=layer_choices).unsafe_ask()
        thickness = _ask_length("Plate thickness", '0.075in')
        alloy = questionary.text("Plate alloy:", default="304").unsafe_ask()
        clearance = _ask_length("Clearance around posts/supports", "1mm")
        plates.append(
            PlateSpec(
                layer=layer,
                material=SheetMaterialSpec(alloy=alloy, thickness=thickness),
                post_clearance=clearance,
            )
        )
    return plates


def _ask_feet(default_on: bool) -> FeetSpec | None:
    """Caster / leveling-foot plates welded under the bottom frame."""
    if not questionary.confirm(
        "Add caster / leveling-foot plates under the bottom frame?", default=default_on
    ).unsafe_ask():
        return None

    thickness = _ask_length("Foot plate thickness", "0.25in")
    alloy = questionary.text("Foot plate alloy:", default="A36").unsafe_ask()
    size = _ask_length("Foot plate size (square side)", "4in")

    kind = questionary.select(
        "Mounting hole pattern:",
        choices=[
            questionary.Choice("square — 4-bolt pattern (+ optional centered stem hole)", "square"),
            questionary.Choice("single — one centered stem hole (leveling foot / stem caster)", "single"),
        ],
    ).unsafe_ask()
    if kind == "single":
        hole = _ask_length("Stem hole diameter", "0.5in")
        pattern = FootPattern(type="single", hole=hole)
    else:
        spacing = _ask_length("Bolt hole spacing (center-to-center)", "3in")
        hole = _ask_length("Bolt hole diameter", "0.41in")
        if questionary.confirm(
            "Also cut a centered stem/leveling hole (accepts either mount)?", default=True
        ).unsafe_ask():
            center_hole = _ask_length("Centered stem hole diameter", "0.5in")
        else:
            center_hole = 0.0
        pattern = FootPattern(type="square", spacing=spacing, hole=hole, center_hole=center_hole)

    corners = questionary.confirm("One plate per corner?", default=True).unsafe_ask()
    mid = None
    if questionary.confirm(
        "Add mid-span foot pairs (for long units)?", default=False
    ).unsafe_ask():
        count = int(questionary.text("How many positions?", default="1").unsafe_ask())
        axis = questionary.select("Spaced along:", choices=["width", "depth"]).unsafe_ask()
        mid = MidFeet(count=count, axis=axis)

    return FeetSpec(
        material=SheetMaterialSpec(alloy=alloy, thickness=thickness),
        size=size,
        pattern=pattern,
        corners=corners,
        mid=mid,
    )


def run_wizard(spec_path: Path | None, console: Console | None = None) -> None:
    console = console or Console()
    existing = load_spec(spec_path) if spec_path and Path(spec_path).exists() else None
    if existing:
        console.print(f"[dim]Editing {spec_path} (answers pre-filled where possible)[/dim]")

    name = questionary.text(
        "Project name:", default=existing.name if existing else "My Box"
    ).unsafe_ask()

    vendor_slug = questionary.select(
        "Vendor:",
        choices=sorted(VENDORS),
        default=existing.vendor if existing else "rmfg",
    ).unsafe_ask()
    vendor = get_vendor(vendor_slug)
    catalog = vendor.catalog()
    squares = [p for p in catalog.profiles if p.shape == "square"]
    if not squares:
        console.print(f"[red]{vendor.display_name} catalog is not encoded yet; aborting.")
        return

    profile = questionary.select(
        "Tube profile:",
        choices=[questionary.Choice(p.display_name, value=p) for p in squares],
    ).unsafe_ask()

    height = _ask_length("Exterior height", "2000mm")
    width = _ask_length("Exterior width", "1000mm")
    depth = _ask_length("Exterior depth", "800mm")

    topology = questionary.select(
        "Frame topology:",
        choices=[
            questionary.Choice(
                "full_height_posts — 4 posts run full height, rails butt between them",
                "full_height_posts",
            ),
            questionary.Choice(
                "top_bottom_frames — width rails run solid across top/bottom, posts butt up into them",
                "top_bottom_frames",
            ),
        ],
        default=None,
    ).unsafe_ask()

    blocking = []
    level_names: list[str] = []
    while questionary.confirm("Add blocking (level / supports / spanner)?", default=bool(
        existing.blocking if existing else False
    )).unsafe_ask():
        kind = questionary.select(
            "Blocking type:",
            choices=[
                questionary.Choice("level — horizontal frame at a height (work surface, shelf)", "level"),
                questionary.Choice("supports — verticals between two layers at rail midpoints", "supports"),
                questionary.Choice("spanner — single member across the top or bottom face", "spanner"),
                questionary.Choice("done", "done"),
            ],
        ).unsafe_ask()
        if kind == "done":
            break
        if kind == "level":
            lname = questionary.text("Level name (e.g. work-surface):").unsafe_ask() or None
            h = _ask_length("Level height (top surface)")
            cm = None
            if questionary.confirm("Add evenly spaced cross members on this level?", default=True).unsafe_ask():
                count = int(questionary.text("How many?", default="3").unsafe_ask())
                axis = questionary.select("Cross member direction:", choices=["depth", "width"]).unsafe_ask()
                cm = CrossMembers(count=count, axis=axis)
            blocking.append(LevelSpec(type="level", name=lname, height=h, cross_members=cm))
            level_names.append(lname or f"level@{h:g}")
        elif kind == "supports":
            layer_choices = ["base", "top", *level_names]
            lo = questionary.select("Between (lower layer):", choices=layer_choices).unsafe_ask()
            hi = questionary.select("and (upper layer):", choices=layer_choices).unsafe_ask()
            blocking.append(SupportsSpec(type="supports", between=[lo, hi]))
        elif kind == "spanner":
            faces = questionary.checkbox(
                "Face(s):", choices=["top", "bottom"]
            ).unsafe_ask() or ["top"]
            axis = questionary.select("Direction:", choices=["width", "depth"]).unsafe_ask()
            count = int(questionary.text("How many (evenly spaced)?", default="1").unsafe_ask())
            blocking.append(SpannerSpec(type="spanner", face=faces, axis=axis, count=count))

    siding = None
    if questionary.confirm("Add sheet metal siding (riveted panels)?", default=False).unsafe_ask():
        faces = questionary.checkbox(
            "Which faces get panels?",
            choices=["left", "right", "front", "back", "top", "bottom"],
        ).unsafe_ask()
        if faces:
            thickness = _ask_length("Sheet thickness", '0.038"')
            alloy = questionary.text("Sheet alloy:", default="304").unsafe_ask()
            rivet = _ask_length("Rivet diameter", "1/4in")
            spacing = _ask_length("Rivet spacing", "100mm")
            siding = SidingSpec(
                attachment=AttachmentSpec(rivet=rivet, spacing=spacing),
                panels=[
                    PanelSpec(
                        faces=faces,
                        material=SheetMaterialSpec(alloy=alloy, thickness=thickness),
                    )
                ],
            )

    plates = _ask_plates(level_names, default_on=bool(existing.plates if existing else False))
    feet = _ask_feet(default_on=bool(existing.feet if existing else False))

    quantity = int(questionary.text("How many assemblies?", default="1").unsafe_ask())

    spec = BoxSpec(
        name=name,
        vendor=vendor_slug,
        material=MaterialRef(
            shape="square",
            size=[profile.outer_w_mm],
            wall=profile.wall_mm,
            family=profile.material_family,
        ),
        exterior=Exterior(height=height, width=width, depth=depth),
        topology=topology,
        blocking=blocking,
        siding=siding,
        plates=plates,
        feet=feet,
        quantity=quantity,
    )

    out = Path(spec_path) if spec_path else Path(
        questionary.text("Save spec as:", default=f"{name.lower().replace(' ', '-')}.yaml").unsafe_ask()
    )
    dump_spec(spec, out)
    extras = ""
    if plates:
        extras += f"Deck plates: {', '.join(p.layer for p in plates)}\n"
    if feet:
        n = (4 if feet.corners else 0) + (2 * feet.mid.count if feet.mid else 0)
        extras += f"Foot plates: {n} ({feet.pattern.type} pattern)\n"
    console.print(
        Panel(
            f"Spec written to [bold]{out}[/bold]\n"
            f"Tube: {profile.display_name}\n"
            f"Exterior: {height:g} x {width:g} x {depth:g} mm "
            f"({inches(height):.1f} x {inches(width):.1f} x {inches(depth):.1f} in)\n"
            f"{extras}\n"
            f"Generate the cut list with:\n  [bold]weldbox generate {out}[/bold]",
            title="Done",
        )
    )
