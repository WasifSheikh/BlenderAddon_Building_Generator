"""Kit validator: finds problems in a kit that make buildings come out wrong, with a fix for each."""

import bpy

from .common import _state, is_building
from .kit import get_kit
from .operators import _active_kit

FACADE = ("window", "wall", "pilaster", "storefront", "door")
LEVELS = ("ERROR", "WARNING", "INFO")


def validate_kit(root):
    """List of (level, module, problem, fix), most serious first."""
    kit = get_kit(root)
    grid = max(root.aa_kit.grid, 0.01)
    out = []

    def add(level, module, msg, hint):
        out.append((level, module, msg, hint))

    used = [m for m in kit.all if m.weight > 0]
    roles = {m.role for m in used}
    if not kit.mods:
        add("ERROR", "", "No usable modules", "Put each module in its own child collection of the kit")
    if kit.loose:
        add("WARNING", "", f"{len(kit.loose)} loose object(s) in the kit root", "Click Make Modules from Loose Objects")
    if "window" not in roles:
        add("ERROR", "", "No window modules", "Upper floors become plain filler walls: add Window_... modules or set a Category")
    if not roles & {"storefront", "door"}:
        add("WARNING", "", "No storefront or door modules", "Ground floors will only use windows and walls")
    if "corner" not in roles:
        add("INFO", "", "No corner pieces", "Corners get generated posts; Corner_... modules give a finished look")
    if not roles & {"cornice", "parapet"}:
        add("INFO", "", "No cornice or parapet", "The roof edge gets a plain generated parapet")
    if "pilaster" in roles and not any(m.role == "pilaster" and m.floor in ("ground", "any") for m in used):
        add("INFO", "", "Pilasters have no ground-floor version", "Through the ground floor the upper pilaster is stretched to fit")
    if kit.scale != 1.0:
        add("INFO", "", f"Kit is scaled by {kit.scale:g}", "Modules look like centimetres and are converted automatically")
    if kit.uv_issue:
        add("WARNING", "", "UV maps have different names", "Click Fix UV Map Names, or baked and exported meshes get extra UV channels")
    storeys = {round(kit.gh, 2), round(kit.uh, 2)}
    # facing is judged against the kit's own convention: most modules here have their back face at the origin
    facade = [m for m in used if m.role in FACADE and not m.damaged]
    backs_at_origin = bool(facade) and sum(1 for m in facade if m.hi.y <= 0.05) >= 0.6 * len(facade)
    for m in kit.all:
        col = bpy.data.collections.get(m.name)
        if m.sub == "unknown":
            add("WARNING", m.name, "Category not recognised, so it is never used", "Set its Category in the module list, or rename it")
            continue
        if m.role == "ignore":
            continue
        if m.role in FACADE:
            if abs(m.w / grid - round(m.w / grid)) > 0.02:
                add("WARNING", m.name, f"Width {m.w:.2f} m is off the {grid:g} m grid", "Spans only fit cleanly when widths share a grid")
            if not any(abs(m.h - s) < 0.06 or abs(m.h - 2 * s) < 0.06 for s in storeys):
                add("WARNING", m.name, f"Height {m.h:.2f} m matches no floor ({kit.gh:.2f} / {kit.uh:.2f} m)",
                    "It gets stretched to the floor height; model it at a floor height")
            if backs_at_origin and m.lo.y > -0.05 and m.hi.y > 0.1:
                add("ERROR", m.name, "Seems to face the wrong way",
                    "Unlike the rest of the kit its geometry is behind the origin: rotate it 180 degrees")
            if abs(m.lo.z) > 0.05:
                add("WARNING", m.name, f"Bottom is {m.lo.z:+.2f} m off the origin", "Move the origin to the bottom edge")
            if m.x0 > 0.05:
                add("INFO", m.name, f"Geometry starts {m.x0:.2f} m right of the origin", "Handled automatically; a bottom-left origin keeps things tidy")
            elif m.x0 < -0.05:
                add("INFO", m.name, "Origin is not at the left edge", "Handled automatically; a bottom-left origin is the convention")
            if m.w < 0.1:
                add("WARNING", m.name, "Very narrow", "Check the module isn't empty or mis-scaled")
        if m.damaged and (m.role, int(round(m.w * 100))) not in {(x.role, int(round(x.w * 100))) for x in used if not x.damaged}:
            add("WARNING", m.name, "Damaged variant with no undamaged twin", "It is only used to replace a module of the same category and width")
        if col is None:
            continue
        meshes = [o for o in col.all_objects if o.type == "MESH" and not is_building(o)]
        scaled = next((o for o in meshes if any(abs(v - 1.0) > 1e-4 for v in o.scale)), None)
        if scaled is not None:
            add("WARNING", m.name, f"'{scaled.name}' has unapplied scale", "Select it and apply scale (Ctrl+A > Scale)")
        bare = [o for o in meshes if not o.material_slots or any(sl.material is None for sl in o.material_slots)]
        if bare:
            more = f" (+{len(bare) - 1} more)" if len(bare) > 1 else ""
            add("WARNING", m.name, f"'{bare[0].name}'{more} has no material", "Assign a material so exports have no empty slots")
        if any(not o.data.uv_layers for o in meshes):
            add("WARNING", m.name, "Has a mesh without UVs", "Unwrap it, or its textures will be stretched")
        nv = sum(len(o.data.vertices) for o in meshes)
        if nv > 60000:
            add("INFO", m.name, f"{nv:,} vertices", "Heavy for a module repeated many times; consider a lighter version")
    out.sort(key=lambda r: LEVELS.index(r[0]))
    return out


class AAB_OT_check_kit(bpy.types.Operator):
    bl_idname = "aab.check_kit"
    bl_label = "Check Kit"
    bl_description = "Look for problems in the kit (sizes, pivots, facing, categories, materials, UVs) and show how to fix them"

    def execute(self, context):
        root = _active_kit(context)
        if root is None:
            self.report({"WARNING"}, "Choose a kit first")
            return {"CANCELLED"}
        issues = validate_kit(root)
        _state.setdefault("checks", {})[root.name] = issues
        print(f"AA Buildings: Check Kit '{root.name}'")
        for lvl, mod, msg, hint in issues:
            print(f"  {lvl:7} {mod + ': ' if mod else ''}{msg}  ->  {hint}")
        n = {lv: sum(1 for i in issues if i[0] == lv) for lv in LEVELS}
        if not issues:
            self.report({"INFO"}, "Kit check: no problems found")
        else:
            self.report({"ERROR" if n["ERROR"] else ("WARNING" if n["WARNING"] else "INFO")},
                        f"Kit check: {n['ERROR']} error(s), {n['WARNING']} warning(s), {n['INFO']} note(s)")
        return {"FINISHED"}
