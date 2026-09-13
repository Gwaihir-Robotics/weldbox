# Removable covers with receiving holes in the tube

Use `siding.fit: opening_overlay` for separate flat covers over each vertical
frame opening. The sheet overlaps the two vertical tube faces; fasteners engage
the **outside tube wall only**, expanding in its hollow interior. There are no
welded receiving tabs or separate backing plates. Full-face riveted `overlay`
and tab-supported `inset` siding remain separate options.

```yaml
siding:
  fit: opening_overlay
  corner_radius: 2mm
  panels:
    - faces: [front, back]
      material: {alloy: '5052', thickness: 1.5mm}
  opening_overlay:
    clearance: 2mm
    edge_overlap: 24mm
    hole_offset: 12mm
    split_heights: [602mm]
    fastener_spacing: 300mm
    end_offset: 20mm
    fastener:
      panel_hole: 6.10mm
      receiver_hole: 6.40mm
      grip_min: 3.0mm
      grip_max: 5.3mm
      panel_max: 2.5mm
      grommet: NY-4G-43-20
      plunger: NY-4P-43-1-50
```

The example is for a 750 mm-high frame with 2 × 2 × .120 in tube. Split heights
are Z coordinates from the tube-frame bottom. `clearance` applies at the top
and bottom of openings and either side of splits; lateral edges instead overlap
by `edge_overlap`. `hole_offset` locates the hole into the vertical member from
the clear opening edge. The example gives 12 mm from hole center to sheet edge
and 2.8 mm between neighboring sheets on a shared 50.8 mm-wide post.

Tube features and panel holes derive from the same centers. The generator checks
that each receiver is on one flat vertical tube face beyond the rounded corner,
that covers do not overlap on shared posts, and that sheet + resolved tube wall
fits the configured grip. Unsupported opening shapes or dimensions raise errors.
Fasteners are not modeled. Mechanical retention, weld/slot clearance, coatings,
panel stiffness, temperature and withdrawal/tool access need application checks.

The [Southco catalog](https://media.southco.com/media/static/Literature/ny-wg.en.pdf)
identifies length code 43 for 3.0–5.3 mm combined grip, up to 2.5 mm removable
sheet. This candidate accommodates 4.548 mm total here. The older code 42 used
with 2 mm receiving tabs has a 4.4 mm maximum and does not accommodate this tube
wall plus sheet. Panel/receiver holes remain 6.10/6.40 mm nominal; their finished
ranges are 6.04–6.15 and 6.35–6.45 mm. Confirm on an actual finished coupon.

The existing sheet pipeline produces cover DXFs and positioned cover STEPs.
`assembly.step` includes covers; `structure.step` omits them. `panel-layouts.json`
records every sheet, and `panel-fasteners.json` identifies the tube attachment
and candidate quantities. Tube receiving holes are already in the tube STEP
parts and assembled frame. No tab DXFs are generated for this mode. Sheets and
heads project beyond the bare tube width; remove them when that transport
width must be maintained. These covers do not seal the frame or qualify it as
an electrical enclosure or machine guard.


## Cover the top horizontal tube and expose equipment holes

`top_extension` extends only the covers in the uppermost row, in their existing
flat plane. A 50.8 mm extension on this example reaches Z=748, retaining the
2 mm clearance beneath the frame top. It does not bend onto the top surface.
Lower covers, split seams, and vertical-tube fastener locations remain unchanged.
The extension cannot exceed the frame height minus the edge clearance.

`access_holes` adds panel-only holes using absolute face U/V coordinates:

```yaml
    top_extension: 50.8mm
    access_holes:
      - {face: front, u: 310mm, v: 724.6mm, diameter: 6.6mm}
```

Every hole must land on exactly one sheet with at least 2 mm ligament to its
edges and other holes. These holes are exported in the sheet DXF and STEP, but
do not drill steel or count as panel fasteners. The application must supply and
check matching tube holes, fastener load paths and panel removal. A sheet hole
is not a selection or rating of a rivet, rivnut or bracket attachment.
