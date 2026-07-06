Tube Box Generator

Many laser cutting services are exposing tube cutting as a service. Tubes, particularly square tube can be cut to length so that they can be welded together to form machinery boxes/cabinet bases. 

Services that expose this service include:

https://www.fabworks.com/services/tube-laser-cutting
https://tube.oshcut.com/
https://www.rmfg.com/laser-tube-cutting


I would like to be able to spec the outer dimentions of a box (larger than 12" x 12" x 12") and have the pieces automatically generated as a cut list (multiple step files) for easy upload to the services. I have attached step and/or dfx  patterns for RMFG and OshCut in /docs/samples/<vendor_name>/**

I have also put tables (partial) of the materials offered as a markdown file in /docs/samples/<vendor_name>/material_list.md

I think the experience would be improved by a user interface, but a terminal interface with questions like inclusion of gussets, or additional supports (blocking?)  would be helpful. We might also want to spec sheet metal siding that can easily be tack welded or rivited (we pre-cut the rivet holes in the tube for sheet metal adhesion). 

We have freecad installed, I'm ok with leveraging that as a partial visual for the final assembly. If possible, I would like to avoid creating a 3d viewer in javascript - that seems like a waste of time.

We want to have some some tab/slot setup to improve assembly and welding:

In tube laser cutting, tab-and-slot connections (or hook-in-slot designs) allow two pieces of metal to interlock and self-locate. This eliminates the need for expensive jigs, clamps, and manual layout during assembly. Tabs are typically designed to be slightly smaller than the slot width to create an easy slip-fit for welding.Design Best PracticesClearance: To achieve a proper slip fit, make your slot's width and length at least 0.010 inches (or roughly 0.25 mm) larger than the thickness of the mating tab.Radius and Corner Relief: Right angles and square corners create localized stress concentration points in the metal tubing. Always incorporate small radii or "dog-bone" reliefs in the corners of your slots to prevent cracking during use.Self-Fixturing: Design the tabs so the parts interlock perfectly at the correct angle (e.g., 90° for frames). This allows the connected tubes to hold themselves in position while being tack-welded.


Example Use Case:

Name: Winding Machine Cell
Vendor: RMFG
Material: 1.5 x 1.5 x .120 in Square Tube	Square	1.5" × 1.5"	wall-thickness:0.12	corner-radus:0.24
Exterior Size:
  height: 2000mm
  width: 1000mm
  depth: 800mm
Blocking: 
  a. perpedicular to height axis at 1000mm ("work surface"). 3x evenly spaced blocking of work surface extending from front to back(depth)
  b. vertical supports between base and this at midpoints
  c. midpoint of top extending across the width
  d. midpoint of bottom extending across the width
  
Sheet metal siding:
  attachment: rivet 100mm spacing 1/4" rivet
  pieces:
    a. sides (stainless - 0.038")
    b. back (stainless - 0.038")
quantity: 5




