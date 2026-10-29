"""Self-test: builds reference buildings from the sample kit and compares their plans with a stored baseline.

Run it from F3 ("AA Buildings: Self-Test") after changing the code. Plans (which module goes where) are compared,
not meshes, so the result does not depend on the Blender version. New cases are added to the baseline
automatically; "Update baseline" replaces the stored results when a change is intended.
"""

import bpy
import hashlib
import json
import os
import re
import traceback
from mathutils import Vector

from .common import _state
from .kit import get_kit
from .planner import Plan
from .runtime import rebuild
from .sample_kit import _box

BASELINE = os.path.join(os.path.dirname(__file__), "tests", "selftest_baseline.json")

# (name, shape, width, depth, building settings). Keys starting with "_" are test switches, not settings.
CASES = [
    ("rect", "RECT", 16, 11, {}),
    ("courtyard", "COURTYARD", 20, 18, {}),
    ("l_rounded", "L", 18, 14, {"round_all": True, "floors": 3}),
    ("windows_side", "RECT", 14, 9, {"ground_default": "WINDOWS", "vary_floors": True}),
    ("u_extras", "U", 24, 20, {"balconies": 0.5, "ac": 0.5, "lights": 1.0}),
    ("back_t", "T", 22, 18, {"ground_default": "BACK", "floors": 2}),
    ("pilasters", "RECT", 26, 18, {"floors": 4, "_pilasters": True}),
    ("pilasters_upper_only", "RECT", 26, 18, {"floors": 4, "_pilasters": True, "pilaster_ground": False}),
    ("shop_units", "RECT", 24, 14, {"shop_units": True, "closed_shops": 0.5, "recessed_doors": 1.0}),
    ("shop_generated_shutters", "RECT", 24, 14, {"closed_shops": 1.0, "_no_kit_shutter": True}),
    ("windows_recessed", "RECT", 18, 12, {"ground_default": "WINDOWS", "recessed_doors": 1.0}),
    ("damage", "L", 20, 16, {"damage": 0.8}),
    ("damage_generated", "RECT", 18, 12, {"damage": 0.8, "_no_kit_damage": True}),
    ("pilasters_damaged_units", "RECT", 26, 18, {"floors": 4, "_pilasters": True, "damage": 0.6, "shop_units": True}),
    # 1.3.0: areaways, wall dividers, floor stack segments, ground floor modules, multi cornice
    ("areaways", "L", 20, 16, {"ground_default": "WINDOWS", "areaways": True}),
    ("areaways_shops_damaged", "RECT", 18, 12, {"areaways": True, "areaway_shops": True, "damage": 0.5}),
    ("wall_dividers", "RECT", 26, 18, {"floors": 4, "divider_type": "WALL", "_extras": ["Wall_Between_50x320"]}),
    ("segments", "RECT", 22, 14, {"floors": 6, "_segments": [
        {"layout": "SINGLE", "module": "Window_200x320"},
        {"layout": "CORNER", "corner_module": "Window_End_300x320", "module": "Window_Arched_200x320", "floors": 2, "belt_below": True},
        {"layout": "SINGLE", "module": "Window_Double_400x320", "height": 3.6}]}),
    ("segments_pilasters_repeat", "RECT", 26, 18, {"floors": 5, "_pilasters": True, "segment_repeat": True, "_segments": [
        {"layout": "SINGLE", "module": "Window_200x320"}, {"layout": "SINGLE", "module": "Window_Arched_200x320"}]}),
    ("ground_floor_modules", "RECT", 20, 14, {"ground_mode": "GROUND", "ground_layout": "CORNER", "areaways": True,
                                              "ground_corner_module": "Ground_Wall_200x400", "ground_module": "Ground_Window_200x400",
                                              "_segments": [{"layout": "SINGLE", "module": "Window_200x320"}]}),
    ("ground_floor_auto", "L", 20, 16, {"ground_mode": "GROUND"}),
    ("belt_without_crown", "RECT", 16, 11, {"cornice": False}),
    ("cornices_chosen", "RECT", 16, 11, {"cornice_module": "Cornice_B_200", "_extras": ["Belt_200"], "_segments": [
        {"layout": "AUTO"}, {"layout": "AUTO", "floors": 2, "belt_below": True}]}),
    ("crown_as_belt", "RECT", 16, 11, {"cornice_module": "Cornice_B_200", "floors": 3}),
]

# 1.4.0: rigid modules (snapped footprint, no stretching) and window sides without wall pieces. These start from
# the 1.4 defaults. "_exact": no filler strips on the facade; "_no_upper_walls": no wall modules above the ground floor
CASES_14 = [
    ("windows_only", "RECT", 14, 9, {"ground_default": "WINDOWS", "wall_mix": 0.0, "_no_upper_walls": True}),
    ("rigid_rect", "RECT", 16, 11, {"rigid": True, "_exact": True, "_no_upper_walls": True}),
    ("rigid_odd_size", "RECT", 17.3, 10.6, {"rigid": True, "_exact": True}),
    ("rigid_courtyard", "COURTYARD", 20, 18, {"rigid": True}),
    ("rigid_l", "L", 20, 16, {"rigid": True, "round_all": True, "floors": 3}),
    ("rigid_windows_side", "RECT", 14, 9, {"rigid": True, "ground_default": "WINDOWS", "_no_upper_walls": True}),
    ("rigid_pilasters", "RECT", 26, 18, {"rigid": True, "floors": 4, "_pilasters": True, "_exact": True}),
    ("rigid_wall_dividers", "RECT", 25, 17, {"rigid": True, "floors": 4, "divider_type": "WALL", "_extras": ["Wall_Between_50x320"]}),
    ("rigid_segments", "RECT", 22, 14, {"rigid": True, "floors": 6, "_segments": [
        {"layout": "SINGLE", "module": "Window_200x320"},
        {"layout": "CORNER", "corner_module": "Window_End_300x320", "module": "Window_Arched_200x320", "floors": 2, "belt_below": True},
        {"layout": "SINGLE", "module": "Window_Double_400x320", "height": 3.6}]}),
    ("rigid_ground_floor", "RECT", 20, 14, {"rigid": True, "ground_mode": "GROUND", "ground_layout": "CORNER", "areaways": True,
                                            "ground_corner_module": "Ground_Wall_200x400", "ground_module": "Ground_Window_200x400",
                                            "_segments": [{"layout": "SINGLE", "module": "Window_200x320"}]}),
    ("rigid_shops_damaged", "RECT", 24, 14, {"rigid": True, "shop_units": True, "closed_shops": 0.5, "recessed_doors": 0.5,
                                             "damage": 0.5, "_pilasters": True}),
]

CASES += CASES_14

# what buildings defaulted to before 1.4.0: older cases start from these, so they keep their baseline
LEGACY = {"rigid": False, "wall_mix": 0.1}
NEW_DEFAULTS = {"rigid": False, "wall_mix": 0.0}
# modules that must never be stretched along the facade when Rigid modules is on
RIGID_ROLES = {"window", "wall", "storefront", "door", "pilaster", "shutter", "awning", "sign", "balcony", "areaway"}

# test-only modules, kept at frequency 0 unless a case lists them in "_extras" (chosen modules are used at 0 too)
EXTRA_MODULES = [
    ("Wall_Between_50x320", [("wall", (0.0, 0.0, 0.0), (0.5, 0.3, 3.2), "plaster")]),
    ("Window_Arched_200x320", [("wall", (0.0, 0.0, 0.0), (0.4, 0.3, 3.2), "plaster"), ("wall", (1.6, 0.0, 0.0), (2.0, 0.3, 3.2), "plaster"),
                               ("under", (0.4, 0.0, 0.0), (1.6, 0.3, 0.8), "plaster"), ("arch", (0.4, 0.0, 2.4), (1.6, 0.3, 3.2), "trim"),
                               ("glass", (0.4, 0.14, 0.8), (1.6, 0.18, 2.4), "glass")]),
    ("Window_End_300x320", [("wall", (0.0, 0.0, 0.0), (1.0, 0.3, 3.2), "brick"), ("wall", (2.2, 0.0, 0.0), (3.0, 0.3, 3.2), "brick"),
                            ("under", (1.0, 0.0, 0.0), (2.2, 0.3, 0.9), "brick"), ("over", (1.0, 0.0, 2.6), (2.2, 0.3, 3.2), "brick"),
                            ("glass", (1.0, 0.14, 0.9), (2.2, 0.18, 2.6), "glass")]),
    ("Belt_200", [("band", (0.0, -0.18, 0.0), (2.0, 0.15, 0.22), "trim")]),
    ("Cornice_B_200", [("band", (0.0, -0.4, 0.0), (2.0, 0.15, 0.45), "trim"), ("lip", (0.0, -0.5, 0.35), (2.0, 0.15, 0.45), "trim")]),
]
POINTERS = ("cornice_module", "belt_module", "divider_module", "ground_module", "ground_corner_module", "ground_door")
SEG_POINTERS = ("module", "corner_module")


def _ids():
    out = set()
    for attr in ("scenes", "objects", "collections", "node_groups", "meshes", "curves", "materials", "images"):
        for idb in getattr(bpy.data, attr):
            out.add((attr, idb.name_full))
    return out


def _cleanup(before, keep_scene):
    win = bpy.context.window
    if win is not None and keep_scene is not None:
        win.scene = keep_scene
    for attr in ("scenes", "objects", "collections", "node_groups", "meshes", "curves", "materials", "images"):
        coll = getattr(bpy.data, attr)
        for idb in [i for i in coll if (attr, i.name_full) not in before]:
            try:
                coll.remove(idb)
            except Exception:
                pass
    _state["kits"].clear()
    _state["sigs"].clear()
    _state["failed"].clear()


def _add_pilasters(kit):
    """Upper and ground pilaster modules, kept at frequency 0 unless a case asks for them."""
    mat = bpy.data.materials.get("AA Sample trim")
    made = []
    for name, h in (("Pilaster_100x320", 3.2), ("Pilaster_Ground_100x400", 4.0)):
        c = bpy.data.collections.new(name)
        kit.children.link(c)
        off = Vector((-90.0, -20.0 - 6.0 * len(made), 0.0))
        c.instance_offset = off
        _box(c, name, Vector((0.0, -0.35, 0.0)) + off, Vector((1.0, 0.3, h)) + off, mat)
        c.aa_module.category = "pilaster"
        c.aa_module.weight = 0.0
        made.append(c)
    return made


def _add_extras(kit):
    made = []
    for k, (name, boxes) in enumerate(EXTRA_MODULES):
        c = bpy.data.collections.new(name)
        kit.children.link(c)
        off = Vector((-90.0 - 8.0 * k, 40.0, 0.0))
        c.instance_offset = off
        for nm, lo, hi, mat in boxes:
            _box(c, name + " " + nm, Vector(lo) + off, Vector(hi) + off, bpy.data.materials.get("AA Sample " + mat))
        c.aa_module.weight = 0.0
        made.append(c)
    return made


def _module(kit, name):
    for c in kit.children_recursive:
        if c.name == name or c.name.startswith(name + "."):
            return c
    raise KeyError(name)


def _r(v, n=3):
    return round(v, n) + 0.0


def _signature(plan, kit):
    # ".001" suffixes (a second sample kit in the same file) don't count as a change
    pts = sorted((tuple(_r(c) for c in p), re.sub(r"\.\d{3}$", "", kit.mods[i].name), _r(y, 4), tuple(_r(v) for v in s))
                 for p, i, y, s in plan.points)
    verts = sorted(tuple(_r(c) for c in v) for v in plan.proc.v)
    blob = repr((pts, verts, sorted(len(f) for f in plan.proc.f), sorted(plan.proc.m))).encode()
    return {"hash": hashlib.md5(blob).hexdigest(), "pieces": len(pts), "proc_faces": len(plan.proc.f)}


def _checks(plan, kit, opts):
    """Rules a case must keep, whatever the baseline says."""
    out = []
    if opts.get("rigid"):
        bad = sorted({kit.mods[i].name for _, i, _, sc in plan.points
                      if kit.mods[i].role in RIGID_ROLES and abs(sc[0] - 1.0) > 1e-6})
        if bad:
            out.append("stretched with Rigid modules on: " + ", ".join(bad[:4]))
        if opts.get("_exact") and plan.fill_strips:
            out.append(f"{plan.fill_strips} filler strip(s) on a snapped outline")
    if opts.get("_no_upper_walls"):
        n = sum(1 for p, i, _, _ in plan.points if kit.mods[i].role == "wall" and p.z > plan.levels[1] - 0.01)
        if n:
            out.append(f"{n} wall module(s) on the upper floors of window sides")
    return out


def run_self_test(update=False, cases=None):
    win = bpy.context.window
    keep = win.scene if win else None
    before = _ids()
    results, errors = {}, []
    try:
        sc = bpy.data.scenes.new("AAB Self-Test")
        win.scene = sc
        with bpy.context.temp_override(window=win, scene=sc):
            bpy.ops.aab.sample_kit()
        kit_col = sc.aa_build.kit
        pil = _add_pilasters(kit_col)
        extras = _add_extras(kit_col)
        for name, shape, w, d, opts in (cases or CASES):
            try:
                for c in pil:
                    c.aa_module.weight = 1.0 if opts.get("_pilasters") else 0.0
                for c in extras:
                    c.aa_module.weight = 1.0 if c.name.split(".")[0] in opts.get("_extras", ()) else 0.0
                for c in kit_col.children:
                    if c.name.startswith("Shutter_"):
                        c.aa_module.weight = 0.0 if opts.get("_no_kit_shutter") else 1.0
                    elif c.name.startswith(("Window_Broken", "Rubble_")):
                        c.aa_module.weight = 0.0 if opts.get("_no_kit_damage") else 1.0
                with bpy.context.temp_override(window=win, scene=sc):
                    bpy.ops.aab.add_building(shape=shape, width=w, depth=d, rigid=bool(opts.get("rigid")))
                o = bpy.context.view_layer.objects.active
                o.location.x = 40.0 * len(results)
                s = o.aa_building
                s.seed = 1234
                for k, v in (NEW_DEFAULTS if any(name == c[0] for c in CASES_14) else LEGACY).items():
                    setattr(s, k, v)
                for k, v in opts.items():
                    if k in POINTERS:
                        setattr(s, k, _module(kit_col, v))
                    elif not k.startswith("_"):
                        setattr(s, k, v)
                for seg in opts.get("_segments", ()):
                    g = s.segments.add()
                    for k, v in seg.items():
                        setattr(g, k, _module(kit_col, v) if k in SEG_POINTERS else v)
                kit = get_kit(kit_col)
                plan = Plan(o, s, kit).run()
                rebuild(o, force=True)
                results[name] = _signature(plan, kit)
                results[name]["status"] = s.status
                errors += [f"{name}: {e}" for e in _checks(plan, kit, opts)]
            except Exception:
                errors.append(f"{name}: {traceback.format_exc().strip().splitlines()[-1]}")
    finally:
        _cleanup(before, keep)
    base = {}
    if os.path.exists(BASELINE):
        with open(BASELINE, encoding="utf-8") as fh:
            base = json.load(fh)
    changed = [n for n in results if n in base and base[n]["hash"] != results[n]["hash"]]
    new = [n for n in results if n not in base]
    merged = dict(base)
    for n in new:
        merged[n] = results[n]
    if update:
        merged.update(results)
    if new or update:
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        with open(BASELINE, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=1, sort_keys=True)
    report = {"results": results, "changed": changed, "new": new, "errors": errors, "updated": bool(update)}
    _state["selftest"] = report
    return report


class AAB_OT_self_test(bpy.types.Operator):
    bl_idname = "aab.self_test"
    bl_label = "AA Buildings: Self-Test"
    bl_description = "Build reference buildings from the sample kit and compare them with the stored baseline"
    update_baseline: bpy.props.BoolProperty(name="Update baseline", default=False,
                                            description="Store the current results as the new reference")

    def execute(self, context):
        r = run_self_test(self.update_baseline)
        if r["errors"]:
            self.report({"ERROR"}, "Self-test errors: " + "; ".join(r["errors"]))
        elif r["changed"] and not r["updated"]:
            self.report({"WARNING"}, "Changed: " + ", ".join(r["changed"]))
        else:
            self.report({"INFO"}, f"Self-test: {len(r['results'])} cases OK" + (f", {len(r['new'])} new" if r["new"] else ""))
        return {"FINISHED"}
