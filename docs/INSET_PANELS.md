# Removable inset siding

For flat covers with holes directly in the tube and **no receiving tabs**, use
[opening_overlay](OPENING_COVERS.md). The inset mode below explicitly uses tabs.

`siding.fit: inset` fills the clear rectangular openings of the selected vertical
frame faces. The default `overlay` mode and its rivet holes remain unchanged.
Inset siding uses a separate `inset.fastener` configuration; it does not drill an
overlay rivet pattern into the tubes.

```yaml
siding:
  fit: inset
  corner_radius: 2mm
  panels:
    - faces: [front, back]
      material: {alloy: '5052', thickness: 1.5mm}
  inset:
    clearance: 2mm
    recess: 10mm
    split_heights: [602mm]
    fastener_spacing: 300mm
    end_offset: 20mm
    tab_projection: 25mm
    tab_width: 40mm
    tab_material: {alloy: A36, thickness: 2mm}
    fastener:
      panel_hole: 6.10mm
      receiver_hole: 6.40mm
      grip_min: 2.1mm
      grip_max: 4.4mm
      panel_max: 1.6mm
      grommet: NY-4G-42-20
      plunger: NY-4P-42-1-50
```

All dimensions are mm or unit-bearing lengths. Recess measures inward from the
outer tube face to the exposed panel surface. Clearance applies around each
opening and on both sides of a split; the example creates a 4 mm split seam.
Split heights are Z coordinates measured from the tube frame bottom, independent
of feet/floor placement. These example split heights suit a 750 mm-high frame;
choose them for each application.

The generator projects members touching the chosen face, finds the free
rectangles, and derives separate flat receiver tabs along both vertical edges.
Tabs butt against the inside edges of the posts and require edge welding. Tabs
sit immediately behind the panel. Their depth must place the weld edge on the
flat tube wall beyond its rounded corner. They are not tube-laser tabs/slots.
Fastener centers are shared between the panel and its receiver, but the diameters
are independently configured. Quantity is per assembly; grommets and plungers
are separate items. Plastic fasteners are not electrical bonding connections.

Outputs include panel/tab DXFs through the existing sheet pipeline, the complete
`assembly.step`, `structure.step` with the removable panels omitted, positioned
panel STEP files in `panel-instances/`, and `panel-layouts.json` and
`panel-fasteners.json`. Existing cutlists include the sheet part quantities.
Inset panels use exact sheet deduplication: extra sacrificial holes are not added.
`structure.step` retains feet, other fixed sheets, and welded receiver tabs.

The first implementation supports square/rectangular tube, vertical faces,
flat sheets, and rectangular openings bounded by continuous vertical receiving
members. Unsupported irregular openings, duplicate faces/splits, insufficient
edge ligaments, and incompatible panel/grip thicknesses raise errors. It does not
model the purchased plastic fasteners, certify retention or panel stiffness,
choose weld sizes, or generate folded sheet edges. Verify panel withdrawal paths
in the consuming machine assembly. A decorative cover is not automatically a
qualified machine guard or electrical enclosure.

The example fastener pair is based on the [Southco NYLATCH catalog](https://media.southco.com/media/static/Literature/ny-wg.en.pdf):
6.04–6.15 mm panel hole, 6.35–6.45 mm receiving hole, 1.6 mm maximum panel
thickness, 2.1–4.4 mm combined grip, and 85 °C maximum operating temperature.
Allow for finishing/coatings; qualify hole fit and retention with a coupon before
ordering production panels. The configurable values are a candidate, not vendor
approval of this assembly.
