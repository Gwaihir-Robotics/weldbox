# weldbox — Functionality Deep Dive

weldbox turns a short YAML description of a welded square-tube box — a
machine base, enclosure, cart, bench, or cabinet frame — into everything a
laser tube cutting service needs to make the parts, and everything you need
to weld them together without a jig.

```
 spec.yaml ──▶ frame math ──▶ features ──▶ consolidation ──▶ outputs
 (source of    members +      tabs/slots/   fewer unique      STEP per part
  truth)       joints         rivet holes   part numbers      DXF per panel
                                                              assembly STEP
                                                              cut list + shipping
```

Everything up to geometry is pure math (no CAD kernel), so `--dry-run`
gives you a complete priced-out cut list in under a second.

---

## 1. The workflow

```sh
uv run weldbox catalog list --vendor rmfg          # 1. pick stock
uv run weldbox wizard                              # 2. author a spec (or write YAML by hand)
uv run weldbox generate my-box.yaml --dry-run      # 3. sanity-check the cut list + shipping
uv run weldbox generate my-box.yaml -o out         # 4. produce files
open out/my-box/assembly.step                      # 5. review in FreeCAD
# 6. upload out/my-box/parts/*.step and panels/*.dxf to the vendor
```

The YAML spec is the source of truth. The wizard is only a convenience that
writes one; you can always edit the file directly and regenerate.

---

## 2. The spec file, field by field

All lengths accept unit suffixes — `2000mm`, `1.5in`, `0.038"`, `1/4in`,
`3 1/2 in`, `2cm`, `1m` — and bare numbers are millimetres. Unknown fields
are **rejected with an error**, never silently ignored, so a typo cannot
quietly change your build.

```yaml
name: Epoxy Machine Cell        # used for output folder and file names
vendor: rmfg                    # rmfg | oshcut | fabtech (stub)
material:                       # catalog lookup key, not free-form:
  shape: square                 #   must match a profile the vendor stocks
  size: [1.5in]                 #   [w] or [w, h]
  wall: 0.120in
  family: A500                  #   disambiguates A500 vs 304 vs 6061 at the same size
exterior:                       # OUTER envelope of the frame
  height: 860mm                 #   Z
  width: 2000mm                 #   X
  depth: 660mm                  #   Y
topology: top_bottom_frames     # see section 3
joints:                         # all optional; defaults shown
  style: through_wall_tab       #   or plain_butt (no tabs anywhere)
  slot_clearance: 0.25mm        #   slip fit: slot = tab + this
  tab_width_fraction: 0.5       #   tab width as fraction of the receiving flat
  dogbone_radius: 1.0mm         #   corner relief circles in slots
  weld_gap: 0mm                 #   shortens every butting end
  corner_tabs: true             #   tab/slot at box corners too
blocking: [...]                 # see section 4
siding: {...}                   # see section 5
plates: [...]                   # see section 6
feet: {...}                     # see section 6 (caster/leveling-foot plates)
quantity: 5                     # assemblies; multiplies the cut list
consolidate: true               # see section 7
```

`material` must resolve to a real vendor profile — weldbox models the
vendor's actual stock (including the published outside corner radius) so
the STEP files you upload match what the service quotes against.

---

## 3. Topologies — how the box is framed

### `full_height_posts`

Four posts run the full height; every horizontal rail butts between them.
The classic cabinet/enclosure frame — vertical loads go straight down the
posts to the floor.

```
 ┌─post──────post─┐        posts:  height H        x4
 │  ═══rails═══   │        rails:  width  − 2×tube
 ║                ║                depth  − 2×tube
 │  ═══rails═══   │
 └─post──────post─┘
```

### `top_bottom_frames`

The top and bottom are complete rectangular frames whose **width rails run
solid across the full exterior width**; the depth rails butt between them,
and the posts butt *up into* the frames, tabbing into the full-width rails.
Right for benches and long tables where you want unbroken members across
the span (and two frames you can weld up flat on a table first).

```
 ╔════ solid width rail ════╗     top frame
 ║ post   post   post  post ║     posts: height − 2×tube, tab up/down
 ╚════ solid width rail ════╝     bottom frame
```

---

## 4. Blocking — interior structure

Three primitives, freely combined in the `blocking:` list.

### `level` — a horizontal frame at any height

```yaml
- type: level
  name: work-surface            # referenced by supports
  height: 1000mm
  height_ref: top_face          # top_face (default) | centerline | bottom_face
  cross_members: {count: 3, axis: depth}
```

A level is a full perimeter frame (4 rails teed into the posts) with
optional evenly spaced cross members butted between its rails.
`height_ref: top_face` means the *surface you'd put something on* is at the
given height — it's a work surface. Heights are validated against the box:
if a level can't fit, the error tells you the exact legal range for your
tube size and box height.

### `supports` — verticals between two layers

```yaml
- type: supports
  between: [base, work-surface]   # any two of: base, top, or a level name
  at: midpoints
```

Places a vertical member at the midpoint of each of the four rail pairs of
the two layers, butted between the lower rails' top faces and the upper
rails' bottom faces — load paths under a work surface without blocking the
interior.

### `spanner` — members across the top or bottom face

```yaml
- type: spanner
  face: [top, bottom]           # one face or a list
  axis: depth                   # width | depth
  count: 3                      # evenly spaced at k/(count+1)
  position: 0.5                 # used only when count == 1
```

Spanners butt between the two face rails perpendicular to their axis —
mounting rails for equipment, caster plates, or deck support.

---

## 5. Sheet metal siding

```yaml
siding:
  attachment: {method: rivet, rivet: 1/4in, spacing: 100mm, hole_clearance: 0.15mm}
  panels:
    - {faces: [left, right, back], material: {alloy: "304", thickness: 0.038"}}
  panel_margin: 0mm             # inset from the frame edge
  corner_radius: 5mm            # sheet corner radius (DXF + 3D)
```

What you get:

- **Rivet holes pre-cut in the tubes.** Every member whose outer face lies
  on a sided box face gets holes — rivet diameter + clearance (1/4" →
  6.5mm), evenly pitched at `spacing`, symmetric about the member's middle
  with a 20mm end margin. That includes mid-frame members (a level rail or
  support on a sided face gets a rivet row too).
- **A DXF flat pattern per unique panel** — closed polyline outline with
  true arc corners at `corner_radius`, CIRCLE holes, millimetre units
  (`$INSUNITS = 4`), DXF R2000 — the format flat-laser vendors ingest
  directly (SendCutSend, OshCut, Fabworks flat service).
- **Guaranteed alignment.** Panel holes are derived from the *same* planned
  holes as the tube cuts — they cannot drift apart.
- Panels appear in the assembly STEP as translucent solids with their holes
  and rounded corners, sitting proud on the frame face.

---

## 6. Deck plates and foot plates

A `plates:` entry adds a laser-cut sheet that rests **on top of** a
horizontal layer — the base frame, the top frame, or any named blocking
level:

```yaml
plates:
  - layer: base                 # base | top | a level's name | level@<height>
    material: {alloy: "304", thickness: 0.075in}
    margin: 0mm                 # inset from the frame exterior on all edges
    post_clearance: 1mm         # gap around every cutout
    corner_radius: 5mm          # outer sheet corners
    attachment: {rivet: 1/4in, spacing: 100mm}   # same options as siding
```

(The key is `layer`, not `on` — bare `on` is a boolean in YAML.)

What you get:

- **Cutouts around everything that passes through the sheet.** Any vertical
  member crossing the plate's thickness is notched out: corner posts become
  open corner notches, perimeter supports become edge notches, and a
  mid-plate vertical would become a rounded interior hole. Each cutout is
  the tube footprint plus `post_clearance`, with a concave relief radius
  matching the tube's outside corner radius, so the plate drops straight in
  around the welded frame.
- **Rivet holes shared with the tubes.** Every member whose top face is
  coplanar with the plate underside — the layer's rails, cross members, and
  spanners — gets a hole row on its top wall, and the plate gets the
  matching holes. A hole that would land inside (or within 2mm web of) a
  cutout is skipped on both sides, so tube and sheet can never disagree.
- The plate ships as a DXF like any panel, joins panel consolidation (two
  plates merge only when their cutout patterns coincide exactly under a
  flip — cutouts are structural and are never unioned), is counted in the
  shipping estimate, and appears in the assembly STEP as a brass-colored
  solid so it reads distinctly from the translucent siding.

The winding machine cell example carries a `layer: base` plate: its DXF has
four post corner notches, four support edge notches, and 37 rivet holes
into the base rails and the bottom spanner.

### Caster & leveling-foot plates (`feet:`)

`feet:` adds square plates welded to the **underside** of the bottom frame,
flush with the box exterior, carrying the mounting pattern for casters or
self-leveling feet (the caster itself is not modeled — just the plate):

```yaml
feet:
  material: {alloy: "A36", thickness: 0.25in}
  size: 4in                     # square plate side
  corner_radius: 5mm
  pattern:
    type: square                # square | single
    spacing: 3in                # hole center-to-center (square pattern)
    hole: 0.41in                # 3/8in bolt clearance
    center_hole: 0.5in          # extra stem/leveling-foot hole; 0 to omit
  corners: true                 # default: one plate per corner
  mid: {count: 1, axis: width}  # extra pairs for long spans (see below)
```

- **Placement.** `corners: true` (default) puts one plate in each corner.
  For long units, `mid` adds `count` evenly spaced positions along `axis`,
  with a plate on *each* of the two edges parallel to that axis — the epoxy
  cell's `mid: {count: 1, axis: width}` yields 6 casters on its 2000mm span.
- **Hole pattern**, centered on each plate: `square` cuts 4 holes at
  `spacing` center-to-center (bolt-on caster / machine mount) *plus* a
  centered `center_hole` (0.5in default) so the same plate also accepts a
  threaded-stem caster or leveling foot — set `center_hole: 0` to omit it.
  `single` cuts just the one center hole
  (`pattern: {type: single, hole: 0.5in}`).
- The plates are **welded gussets** — no holes are cut into the tubes. All
  plates are identical, so they consolidate into a single flat part
  (`foot.dxf`, qty N), join the shipping estimate, and show up in the
  assembly STEP as dark steel plates hanging `thickness` below z=0.
- Errors are validated up front: a `spacing`/`hole` combination that does
  not fit the plate, corner plates that would overlap on a small footprint,
  and `corners: false` with no `mid` all fail with a clear message.

---

## 7. Part-count consolidation

Vendors price multiples of the same part dramatically cheaper, so weldbox
works hard to minimize unique part numbers (`consolidate: true`, the
default).

**Tubes.** Members with the same profile and cut length often differ only
in *which faces* carry slots or holes. weldbox aligns every member of such
a group through the square tube's 8 symmetries (4 rotations × end-for-end
flip), unions the feature sets, and cuts the union into all of them. The
extra cuts are sacrificial — unused slots or holes over solid tube — and
the pass is guarded: it only ever *adds cuts* (never tabs), it never lets
two features come closer than a 0.5mm web, and a member that can't merge
safely keeps its own part number.

**Panels.** A flat sheet with through-holes can be flipped over or rotated
180° in plane, so left/right, front/back, and top/bottom panels of the same
size merge into one blank (`left-right.dxf`, qty 2). Differing hole
patterns are unioned under the best alignment; patterns that would collide
stay separate.

Real numbers: the PRD's winding machine cell is 25 members that would
naively be 13 unique parts — consolidation ships it as **3**. The epoxy
cell's 22 members also ship as **3** (its posts and supports turn out to be
literally the same part).

Set `consolidate: false` if you don't want sacrificial cuts on visible
faces — only exactly-identical parts merge then.

---

## 8. The tab/slot system (jigless welding)

Every joint self-locates for tack welding — no jigs, clamps, or layout:

- At each butting end, the two walls parallel to the receiving member's
  axis each grow a **tab**: the wall's own thickness, half the receiving
  flat width wide, protruding exactly one receiving-wall thickness so it
  finishes **flush with the far side of the wall** after welding.
- The receiving face gets matching **through-wall slots** at
  tab + 0.25mm (the 0.010" slip fit tube-laser vendors recommend), with
  **dog-bone relief circles** in the corners so the slot can't start a
  crack.
- Slots always land on the flat region between the tube's corner radii.
- At box corners, the outer tab's slot lands flush with the post end and
  becomes an **open hook-in notch** — drop the rail in, it self-squares.
- Everything is tunable per spec (`joints:`): clearance, tab width
  fraction, dog-bone radius, weld gap, corner tabs on/off, or
  `style: plain_butt` for plain saw-style cuts.

Correctness is enforced by the test suite: assembled members are checked
for **zero boolean interference** — every tab passes exactly through its
slot void.

---

## 9. Outputs

```
out/<name>/
├── cutlist.md            # human cut list + shipping estimate
├── cutlist.csv           # same data for spreadsheets
├── parts/
│   └── <name>_<part>_<length>mm_x<qty>.step
├── panels/
│   └── <name>_<faces>.dxf
└── assembly.step         # open in FreeCAD
```

- **Part STEPs** are built in the vendor-stock convention (cross-section
  centered on origin, extruded along +Z) and modeled against the vendor's
  published geometry — the generated 1.5×1.5×0.120 profile matches RMFG's
  own reference STEP within 0.5%.
- **The assembly STEP** contains one *named product per member and panel*
  (`post-fl`, `work-surface-cross-2`, `panel-back`, …), colored by role —
  posts slate, rails gray, level rails teal, crosses orange, supports
  green, spanners purple, panels translucent — with colors on every face,
  so FreeCAD shows an inspectable, hideable, colored model regardless of
  its STEP import preferences.
- **The cut list** shows per-part length (mm and inches), quantity per
  assembly, and total quantity across the order, plus total stock meters.

### Design-rule and shipping checks

Every run (including `--dry-run`) checks the vendor's design rules
(minimum hole diameter, dog-bone radius, maximum part length) and estimates
the **order shipping**: analytic part weights (section area × length ×
material density; sheet area × thickness) against the vendor's parcel
limits. For RMFG that means LTL freight is flagged — with the specific
trigger and the $200 flat surcharge — when any part exceeds 100 lb or 60"
(or 48"×30" on two dimensions), or the order exceeds 200 lb.

---

## 10. Test coupons — verify the fit before you commit

```sh
weldbox coupon --vendor rmfg --size 1.5in --wall 0.120in \
               --slot-clearance 0.25mm --dogbone 1.0mm -o out
```

Generates a 4-tube assembly inside a 100mm cube (grown automatically if the
tube needs more room): a post, two rails butting into it at a corner, and a
support teed into one rail's midpoint. Between them the four members carry
every joint feature weldbox cuts — end tabs, closed through-wall slots, the
open hook-in notches that occur at box corners, and dog-bone reliefs — so
one small order proves the slip fit on the *real* material with the *real*
vendor's laser before a full frame is committed.

The output is the standard bundle (part STEPs, assembly STEP, cut list —
typically 2 unique parts, ~2 lb, well under parcel limits). Rerun with
different `--slot-clearance` values and distinct `--name`s to bracket the
fit; whatever clearance welds best goes into your real spec's
`joints.slot_clearance`.

---

## 11. Vendors

Vendor data lives in `src/weldbox/vendors/data/*.yaml` behind a small
`Vendor` interface (catalog, design rules, shipping rules, file naming):

- **rmfg** — fully encoded: 56 profiles (A500/4130/DOM steel, 304
  stainless, 6061/6063 aluminum) with published corner radii, design notes,
  and LTL freight thresholds. Source:
  <https://www.rmfg.com/docs/services/laser-tube-cutting>
- **oshcut** — 93 square-tube profiles (A513, A500, 304 ornamental,
  6061 T6, 6063 T52) encoded from the public catalog API with published
  corner radii (extruded aluminum is a true sharp corner, r=0) and the
  235in max part length. Source: <https://app.oshcut.com/catalog/tube>
  (reference DXFs under `docs/samples/oshcut/`). Shipping rules not yet
  encoded.
- **fabtech** — registered stub awaiting a material list.

To add a vendor: drop a `data/<slug>.yaml` (dimensions in inches as
published; omit corner radius where unpublished and weldbox assumes
2×wall), subclass `Vendor` with its rules, and register it. Catalog lookups
are tolerant (±0.02mm) and demand a `family` when a size/wall exists in
several alloys.

---

## 12. Validation and errors

- Unknown/typo'd spec fields → error naming the exact path
  (`blocking.1.spanner.cross_members: Extra inputs are not permitted`).
- Level heights → validated against the box with the legal range in the
  message, in *your* `height_ref` terms.
- Exterior too small for the tube, unknown vendors/layers, ambiguous
  catalog matches → specific errors.
- The CLI prints one clean error line and exits 1 — no tracebacks.

---

## 13. Current limitations

- Frame math supports **square tube** only (rect/round profiles exist in
  the catalog for future use; round stock is not applicable to this joint
  system).
- One tube profile per box.
- Gussets are not yet generated.
- Blocking members can be placed at positions that collide with each other
  (e.g. a spanner through a support); member-vs-member placement collision
  checking is on the roadmap — the bounding-box overlap tests catch this in
  the standard layouts.
- The `fabtech` catalog is empty until its material list is transcribed;
  `oshcut` covers square tube only (weldbox frames are square-only).
