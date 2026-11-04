# Changelog

## 1.6.1 (2026-11-04)

Performance fixes: a file with several live buildings and night lighting no longer lags.

- **Endless rebuild loop.** Remaking the lit window copies adds and removes objects, and Blender then flags every
  collection in the file as changed. The add-on read that as "every kit was edited", re-read all kits, rebuilt every
  building and remade the lit copies again, forever, even with nothing touched. A flagged kit collection now only
  counts when the kit really changed (its modules, objects or settings).
- Adding or deleting any object in the file no longer re-reads every kit and rebuilds every building.
- Lit copies are kept when the module they copy hasn't changed; only an edited glazed module gets a new copy.
  Before, every kit read (any kit edit, every undo) deleted and re-made all of them.
- Changing a module's category, floor, frequency or AC spot, or a kit setting, re-reads only that kit instead of
  every kit in the file.
- The Edit Mode side overlay reads the outline once per change instead of twice per redraw.

## 1.6.0 (2026-11-04)

- **Night lighting.** New Night lighting box: **Lit windows** and **Lit shop fronts** light a share of the windows,
  storefronts and glazed doors, and **Light pattern** picks other ones. No extra modules are needed: each glazed
  module gets a hidden lit copy whose glass is `<glass>_Lit` (made from the glass material, glowing in Blender
  too). In Unity, give `Glass_Lit` the emissive texture. Raising the share only adds lights, damaged windows stay
  dark, and both kinds of bake and the FBX export carry the lit material.
  - Kit > Night lighting: choose the kit's **Glass** material when it isn't named like glass, or one **Lit glass**
    material for everything.
- Fixes
  - A building copied with Shift+D (or copy / paste) no longer shares the original's bake: before, baking the copy
    overwrote the original's baked copy while the original still showed it as up to date.
  - The mesh bake and the instance bake are tracked separately: re-baking one no longer marks the other as up to
    date. Update Changed Bakes re-bakes only the stale one, so hand edits in an up-to-date bake are kept.
  - Editing a kit module's geometry or materials now marks the bakes made from it as changed. (Bakes made with
    1.5.0 keep the 1.5.0 check until they are baked again.)
  - Baking or exporting a building in a hidden or excluded collection works (before, it could export an empty
    mesh). One building that fails no longer stops an export of several; the report names it.
  - The Buildings panel's "Update N Changed Bakes" counts only the buildings it can update (in this view layer).
- Self-test: 3 lighting cases and checks for the fixes above (41 cases).

## 1.5.0 (2026-11-02)

- **Every building stays live.** Keep as many adjustable buildings in a file as you like and bake each one
  as often as you like.
  - Each building remembers its own baked copy. Baking again updates that copy in place, even after it was
    renamed or moved, and never touches another building's bake. (Before, a bake was found by the live
    building's name, so baking a building again replaced an older bake of it, even a renamed one.)
  - **As a new copy** in the Bake dialog keeps the previous bake and starts a new one.
  - Re-baking keeps the baked copy's place in the level (mesh and instance bakes).
  - New **Buildings** panel: every live building in the scene, click to edit (shows it if hidden), eye to
    show / hide, and whether its bake is up to date or was edited since. **Update Changed Bakes** re-bakes
    only the buildings that changed. Add and **Duplicate** (an independent live copy with the same
    settings) are always at hand. With a baked copy selected, one click jumps back to its live building.
  - **Copy Settings to Selected** gives other buildings the active one's settings, outlines untouched.
  - Bake dialog defaults to Single mesh.
- **Wall AC units: two-axis placement.** Each window module gets an AC spot (Default, Custom with Across /
  Height, or No AC) under Details & extras > AC spot per window module, since windows sit in different
  places on different modules. Each building also has a Sideways / Up-down nudge for all its AC units.
- Baked and exported meshes always have exactly one UV map, `UVMap`: UVs from modules whose UV maps have
  other names (map1, DiffuseUV ...) are merged into it instead of becoming extra, half-empty UV layers.
- Baking or exporting a hidden live building works (it is shown for a moment while it is evaluated).
- Renaming a building renames its hidden data object to match. Moving outline points up or down in Edit
  Mode now rebuilds the building.
- Self-test: 3 AC cases and bake checks (38 cases).

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
- Self-test: 11 new cases (35 in all) and rule checks for rigid modules and window-only sides. It also runs
  in background Blender, so CI runs it on every push.
- Published as GitHub releases with a Blender extension repository index: add the repository URL in
  Blender once and new versions arrive as updates.

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
