# Changelog

## 1.4.0 (2026-10-29)

From the artists' 1.3.0 feedback.

- **Rigid modules.** A new switch (on for new buildings) that keeps every facade module at its exact width:
  windows, walls, storefronts, doors and dividers are never stretched, so a bake to module instances stays
  on the kit's grid. Instead, the building snaps to whole modules as the outline is edited.
  - Each side works out the lengths it fills exactly (window and divider widths, corner pieces, entrances)
    and every line of the outline snaps to a grid in object space. Each line snaps on its own: dragging one
    edge never moves the others, and the building grows or shrinks one module at a time.
  - **Snap Outline** moves the outline onto the building it shows. Add Building starts on the grid.
  - In Edit Mode the side labels show where a side snaps to (17.90 m → 17.60 m).
  - Rotated outlines snap in their own frame. Sides at other angles don't snap; they fill with whole
    modules and filler strips.
  - The ground floor fills with whole modules too, and uses a wall piece next to the entrance (or at the
    ends) when that makes it fit exactly. Where whole modules can't fit (angled sides, inside corners
    without corner pieces), plain filler strips close the gap, and the status line counts them.
  - Cornices, belts and parapets fit with whole pieces when the kit's corner pieces allow it; otherwise
    they still stretch slightly, and the status line says so.
  - Signs, awnings, shutters and balconies keep their own width, centred on what they belong to.
  - Buildings made before 1.4 keep stretching until Rigid modules is ticked.
- **Window sides get windows only.** Blank wall mix now defaults to 0, so wall pieces no longer appear
  among the windows unless the slider is raised. Buildings that never changed the slider lose those
  walls when their file is opened.
- Self-test: 11 new cases (35 in all) and rule checks for rigid modules and window-only sides.

## 1.3.0

- Ground floor type: Storefront, or a Ground floor of chosen modules with an entrance.
- Upper floors built from segments (runs of floors with their own modules, height and belt cornice).
- Corner + middle modules; wall or pilaster dividers; separate crown and belt cornices; areaways.

## 1.2.0

- Pilasters between window bays, bake as module instances, shop-front variety (units, shutters,
  recessed entrances), damage, Export FBX for Unity, Check Kit. Now a Blender extension with a self-test.

## 1.0.1

- Corner pieces for belt, cornice and roof edge; rounded corners found from their shape; stable variation;
  Move Out of Kit and Fix UV Map Names.
