Tube Cutting Design Rules
Laser tube cutting makes complex features vastly more manageable in metal tube, but there are still a few things to consider when making your design.

1. Start With an Extruded Model
Our system needs to convert your 3D model into toolpaths that our tube laser can follow, to cut your profiles. While there are many ways to create a 3D model, it's much more likely that your file will work correctly if you start by extruding the tube profile into a solid tube part, and then add holes and other cutouts subtractively.

2. Prepare Each File Separately
Do not upload assemblies containing multiple tube parts in one file. Instead, export each model separately. Multiple files can then be uploaded all at once by drag-dropping them into our system. If there are any features in your tube part that can't be produced on the tube laser (eg. machined features or chamfered holes), leave them out of your model for tube quoting.

3. Blind Features Not Supported
A tube laser must cut completely through the profile wall. It can't create any "blind" features, like a hole that extends only partially through a wall. That's easy to visualize, but it's easy to accidentally create blind features on the corners of square and rectangular tube. Make sure that even on the tube corners, the laser can go all the way through the material everywhere it has to cut.

Note that this rule is about a single wall in your tube profile: the laser does not have to cut completely through both sides of the tube. You can have different cutouts on each side of the tube.

4. Allow for Different Corner Radii in Your Design
The corner radii on rectangular and square tube can vary significantly depending on what mill makes them. The material standard allows for significant variation, with radii up to three times the wall thickness. When you design, be sure to allow for changes in radius. The actual profile likely won't exactly match the example profiles in our catalog.

Ref: https://www.oshcut.com/design-guide/design-rules