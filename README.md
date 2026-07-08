# weldbox

Vendor-ready tube-laser cut lists for jigless welded frames — STEP + DXF
from a YAML spec.

| Enclosure with riveted siding (`full_height_posts`) | Bench frame (`top_bottom_frames`) |
|---|---|
| ![Winding machine cell: tube frame with work surface and riveted stainless siding](https://raw.githubusercontent.com/Gwaihir-Robotics/weldbox/main/docs/images/weldbox_sample_1.jpg) | ![Epoxy machine cell: bench frame with solid full-width rails and posts butting up into them](https://raw.githubusercontent.com/Gwaihir-Robotics/weldbox/main/docs/images/weldbox_sample_2.jpg) |

Generate laser tube cut lists for welded square-tube boxes and machine
bases. From a single YAML spec, weldbox produces:

- **`parts/*.step`** — one STEP file per unique tube part (deduplicated with
  quantities), ready to upload to a tube laser service (RMFG, OshCut, Fabworks)
- **`panels/*.dxf`** — flat patterns for riveted sheet-metal siding and deck
  plates (baseplates/work surfaces, auto-notched around posts and supports),
  with rivet holes that match the holes pre-cut in the tubes
- **`assembly.step`** — the full assembly for visual review (open in FreeCAD)
- **`cutlist.md` / `cutlist.csv`** — the manifest with lengths and quantities

Frames are self-fixturing: tee joints get through-wall tab-and-slot features
(slip fit +0.25mm, dog-bone corner reliefs per vendor best practice) so parts
interlock at 90° for tack welding without jigs.

**[Read the functionality deep dive →](https://github.com/Gwaihir-Robotics/weldbox/blob/main/docs/FUNCTIONALITY.md)** — topologies,
blocking primitives, the tab/slot system, part-count consolidation, siding,
deck plates, shipping checks, and the full spec reference.

## Quick start

```sh
uv sync

# browse a vendor's tube catalog
uv run weldbox catalog list --vendor rmfg --shape square

# check the cut list without generating CAD (fast)
uv run weldbox generate examples/winding_machine_cell.yaml --dry-run

# full generation
uv run weldbox generate examples/winding_machine_cell.yaml -o out
open out/winding-machine-cell/assembly.step   # opens in FreeCAD

# author a new spec interactively
uv run weldbox wizard

# order a cheap 4-tube test coupon before committing to a full build:
# verifies the tab/slot slip fit on your actual material and vendor
uv run weldbox coupon --size 1.5in --wall 0.120in -o out
```

## Test coupons

`weldbox coupon` generates a small (100mm cube) 4-tube assembly — a post,
two rails into it at a corner, and a support teed into a rail — that
exercises every joint feature weldbox cuts: end tabs, closed through-wall
slots, the open hook-in corner notches, and dog-bone reliefs. Order one
from your vendor in your material first, and check the fit-up before
spending on a full frame. Bracket the slip fit by rerunning with different
clearances:

```sh
uv run weldbox coupon --slot-clearance 0.15mm --name coupon-tight  -o out
uv run weldbox coupon --slot-clearance 0.25mm --name coupon-nominal -o out
uv run weldbox coupon --slot-clearance 0.40mm --name coupon-loose  -o out
```

## The spec file

The YAML spec is the source of truth (the wizard just writes one). Lengths
accept unit suffixes (`2000mm`, `1.5in`, `0.038"`, `1/4in`); bare numbers are
millimetres. See `examples/winding_machine_cell.yaml` for a complete example:

```yaml
name: Winding Machine Cell
vendor: rmfg
material: {shape: square, size: [1.5in], wall: 0.120in, family: A500}
exterior: {height: 2000mm, width: 1000mm, depth: 800mm}
topology: full_height_posts
blocking:
  - type: level          # horizontal frame; top surface at `height`
    name: work-surface
    height: 1000mm
    cross_members: {count: 3, axis: depth}
  - type: supports        # verticals between two layers, at rail midpoints
    between: [base, work-surface]
  - type: spanner         # single member across a face
    face: top
    axis: width
siding:
  attachment: {method: rivet, rivet: 0.25in, spacing: 100mm}
  panels:
    - {faces: [left, right, back], material: {alloy: "304", thickness: 0.038"}}
plates:                   # laser-cut deck plate resting on a layer
  - layer: base           # base | top | a level's name
    material: {alloy: "304", thickness: 0.075in}
quantity: 5
```

### Conventions

- Box coordinates: X = width, Y = depth, Z = height; the exterior dimensions
  are outer envelope dimensions.
- `full_height_posts`: 4 posts run full height; all rails butt between posts.
- `level` heights place the level's **top surface** at the given height (it
  is a work surface); use `height_ref: centerline|bottom_face` to override.
- Rivet holes: rivet diameter + 0.15mm clearance, evenly pitched at
  `spacing`, on every member whose outer face lies on a sided box face.
  Panel DXF holes are derived from the same list, so they always line up.
- All joints get tab/slot by default, including box corners — corner slots
  that land flush with a post end become open hook-in notches. Disable with
  `joints: {corner_tabs: false}`. `joints.weld_gap` shortens butting ends.
- Sheet panels get a `siding.corner_radius` (default 5mm) applied to the
  DXF outline and the assembly solids; panels carry their rivet holes in 3D.
- `plates:` adds a deck plate on top of the base, top, or a level: it is
  auto-notched around every vertical member passing through it (corner
  notches at posts, edge notches at supports, +`post_clearance`) and shares
  rivet holes with the top faces of the rails/crosses/spanners beneath it.
- `feet:` adds caster / leveling-foot plates welded under the bottom frame:
  4 corners by default, extra mid-span pairs via `mid: {count, axis}` for
  long units, with a configurable mounting pattern (`square` bolt pattern
  or a `single` stem hole). See `examples/epoxy_machine_cell.yaml`.
- Same-size panels consolidate into one flat part (vendors price multiples
  cheaper): a sheet with through-holes can be flipped or rotated 180 in
  plane, so left/right, front/back, and top/bottom pairs share one DXF
  (e.g. `left-right.dxf`, qty 2). When hole patterns differ, the union is
  cut into both so the blank stays reversible; conflicting patterns stay
  separate parts.
- In the assembly STEP, members are colored by role (posts slate, rails
  gray, level rails teal, crosses orange, supports green, spanners purple)
  and panels are translucent. The assembly is written as flat named
  products (one per member/panel) with colors on every face, which FreeCAD
  imports as individually selectable/hideable colored objects regardless
  of its STEP import preferences.
- `consolidate: true` (default) adds sacrificial slots/holes so same-length
  members collapse into one part number — the example box goes from 13
  unique parts to 3. Set `consolidate: false` if you don't want unused
  cuts on visible faces.

## Vendors

`rmfg` is fully encoded (from `docs/samples/rmfg/material_list.md`) and
`oshcut` carries all 93 published square-tube profiles with true corner
radii (from `docs/samples/oshcut/material_list.md`); `fabtech` is a stub
awaiting a material list. Vendor shipping rules
(RMFG's LTL freight thresholds, see `docs/samples/rmfg/shipping.md`) drive
an order-level estimate: the generator weighs the cut list analytically and
warns — in the console and on `cutlist.md` — when a part dimension or the
order weight will trigger freight, with the specific reasons and the flat
surcharge. Vendor catalogs live in
`src/weldbox/vendors/data/*.yaml` — dimensions in inches as published, with
corner radius falling back to 2 x wall where unpublished.

## Development

```sh
uv run pytest -m "not slow"   # fast tests: frame math, features, dedupe (<1s)
uv run pytest -m slow         # geometry tests (build123d/OpenCascade)
uv run pytest                 # everything
```

Pipeline: `spec.py` (YAML schema) → `frame.py`/`blocking.py` (member/joint
math, no CAD) → `features.py` (tab/slot/hole placement, no CAD) →
`dedupe.py` (symmetry-aware part grouping) → `geometry/` (build123d solids,
STEP) + `panels/` (DXF) → `manifest.py`.

All dimension and placement math is CAD-free and covered by fast tests;
geometry tests verify solids against analytic volumes and RMFG's published
stock STEP files, and assert zero interference at assembled joints.

## License and attribution

weldbox is released under the [MIT License](https://github.com/Gwaihir-Robotics/weldbox/blob/main/LICENSE).

The RMFG reference data in `docs/samples/rmfg/` (tube profile
specifications, stock STEP/DXF geometry, and shipping thresholds) is
published by RMFG as design-against reference material for their laser tube
cutting service: <https://www.rmfg.com/docs/services/laser-tube-cutting>.
It is included here for interoperability and remains theirs; weldbox is not
affiliated with or endorsed by RMFG.
