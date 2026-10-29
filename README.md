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
tools/ci_selftest.py        runs the self-test in background Blender (CI, or locally)
tools/release_notes.py      checks a release tag against the manifest, prints its changelog entry
.github/workflows/build.yml self-test and build on every push; GitHub release on version tags
CHANGELOG.md
```

Each module in `aa_building_generator/` has one job and only imports the modules before it in the list in
`__init__.py` (common, naming, geometry, kit, outline, tuning, fitting, storefronts, damage, facades, lines,
extras, areaways, rigid, planner, nodes, runtime, props, export, operators, validate, sample_kit, ui,
selftest). Tuning values (stretch limits, heights, margins, snapping) live in `tuning.py`.

## Install for artists

Add this repository to Blender once; after that Blender offers every new release as an update.

1. If an older version was installed from a zip, remove it first: Edit > Preferences > Get Extensions,
   find AA Building Generator under the "User Default" repository, drop-down > Uninstall.
2. In Get Extensions, open the **Repositories** drop-down at the top right > **+** > **Add Remote Repository**,
   and paste:
   ```
   https://github.com/WasifSheikh/BlenderAddon_Building_Generator/releases/latest/download/index.json
   ```
   Tick **Check for Updates on Startup**.
3. Search for **AA Building Generator** in Get Extensions and click Install.
4. 3D Viewport > sidebar (N) > **AA Buildings** tab.

Saved .blend files keep working across versions. Without the repository, the zip from the
[latest release](https://github.com/WasifSheikh/BlenderAddon_Building_Generator/releases/latest) installs with
Get Extensions > drop-down > Install from Disk.

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

Run the same check CI runs, from the repository folder:

```
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background --factory-startup --python-exit-code 1 --python tools/ci_selftest.py
```

### Build the zip locally

```
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --factory-startup --command extension build --source-dir aa_building_generator --output-dir dist
```

This validates the manifest and writes `dist/aa_building_generator-<version>.zip` (`dist/` is not committed).

## Release

GitHub Actions (`.github/workflows/build.yml`) runs the self-test in headless Blender and builds the zip on
every push and pull request. To publish a version:

1. Bump `version` in `aa_building_generator/blender_manifest.toml`.
2. Add a `## <version>` section at the top of `CHANGELOG.md`: it becomes the release notes.
3. Commit, push, then tag and push the tag:
   ```
   git tag v1.4.0
   git push origin v1.4.0
   ```

The workflow checks that the tag matches the manifest, then publishes a GitHub release with the zip and
`index.json`. Artists who added the repository URL above get the update offered in Blender.
If the self-test fails, nothing is released: fix it, delete the tag (`git push --delete origin v1.4.0`,
`git tag -d v1.4.0`) and tag again.
