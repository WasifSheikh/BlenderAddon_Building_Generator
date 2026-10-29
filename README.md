# AA Building Generator

A Blender extension (Blender 4.2+, tested in 5.2) that turns an editable outline into a finished modular
building, live, from a kit of modules. Made for **Alien Armageddon**.

Draw or edit the outline and the building follows: each side gets the best mix of the kit's windows,
storefronts, doors, dividers, corner pieces, cornices and parapets, plus extras (signs, awnings, AC units,
fire escapes, damage). Buildings bake to module instances or one mesh, and export to Unity as FBX.

## Repository layout

```
aa_building_generator/      the extension itself (this folder is what gets packaged)
  blender_manifest.toml     id, version, Blender version
  __init__.py               registration, and the module list in load order
  tests/selftest_baseline.json
CHANGELOG.md
```

Each module in `aa_building_generator/` has one job and only imports the modules before it in the list in
`__init__.py` (common, naming, geometry, kit, outline, tuning, fitting, storefronts, damage, facades, lines,
extras, areaways, rigid, planner, nodes, runtime, props, export, operators, validate, sample_kit, ui,
selftest). Tuning values (stretch limits, heights, margins, snapping) live in `tuning.py`.

## Install for artists

1. Build the zip (below), or take the released `aa_building_generator-<version>.zip`.
2. In Blender: Edit > Preferences > Get Extensions, drop-down at the top right > Install from Disk, pick the zip.
3. 3D Viewport > sidebar (N) > **AA Buildings** tab.

Installing a newer zip replaces the old version. Saved .blend files keep working.

## Develop

Work on the files in `aa_building_generator/` and let Blender load them from here, so there is only one
copy. On Windows, replace the installed extension folder with a link to this folder (run in `cmd`, with
Blender closed):

```
rmdir /s /q "%APPDATA%\Blender Foundation\Blender\5.2\extensions\user_default\aa_building_generator"
mklink /J "%APPDATA%\Blender Foundation\Blender\5.2\extensions\user_default\aa_building_generator" "F:\My tools\BlenderAddon_Building_Generator\aa_building_generator"
```

After editing, untick and re-tick the extension in Preferences (or F3 > Reload Scripts): every module
reloads in order.

### Self-test

F3 > **AA Buildings: Self-Test** builds 35 reference buildings from the sample kit and compares their plans
(which module goes where) with `tests/selftest_baseline.json`, so it does not depend on the Blender version.
It also checks rules that must always hold: with Rigid modules on no facade module is stretched, snapped
outlines need no filler strips, and window sides get no wall pieces on the upper floors.

- New cases are added to the baseline automatically.
- When a change to the output is intended, tick **Update baseline** in the redo panel and commit the
  updated JSON together with the change.
- Cases added before 1.4.0 start from the old defaults (no rigid modules, Blank wall mix 0.1) so their
  baseline stays valid.

### Build the zip

```
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --factory-startup --command extension build --source-dir aa_building_generator --output-dir dist
```

This validates the manifest and writes `dist/aa_building_generator-<version>.zip`. Bump `version` in
`blender_manifest.toml` and add a `CHANGELOG.md` entry for each release.
