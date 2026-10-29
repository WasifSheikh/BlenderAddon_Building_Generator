"""Sidebar panels and the Edit Mode side-style overlay."""

import bpy
import traceback
from mathutils import Vector

from .common import (
    GROUND_DEFAULT_STYLE,
    STYLE_AUTO,
    STYLE_BACK,
    STYLE_BLANK,
    STYLE_INFO,
    STYLE_OPEN,
    STYLE_SHOP,
    STYLE_WINDOWS,
    _state,
    is_building,
)
from .naming import ROLE_DEFS, ROLE_LABEL
from .kit import _in_tree
from .outline import read_outline
from .operators import _active_kit


def _floor_ranges(s):
    """(first floor, last floor) of each segment, counting the ground floor as floor 1."""
    out, f = [], 2
    for g in s.segments:
        out.append((f, f + max(1, g.floors) - 1))
        f += max(1, g.floors)
    return out


def _mod_label(seg_or_s, layout, mod, corner):
    if layout == "AUTO":
        return "Kit mix"
    a = mod.name if mod else "Kit mix"
    if layout == "CORNER":
        return f"{corner.name if corner else a} | {a}"
    return a


class AAB_UL_segments(bpy.types.UIList):
    bl_idname = "AAB_UL_segments"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        ranges = _floor_ranges(data)
        a, b = ranges[index]
        top = data.floors
        row = layout.row(align=True)
        if a > top:
            row.active = False
            rng = "above roof"
        else:
            b = min(b, top) if index < len(ranges) - 1 or data.segment_repeat else top
            rng = f"F{a}" if a == b else f"F{a}–F{b}"
        row.label(text=rng, icon="ALIGN_JUSTIFY" if item.belt_below else "DOT")
        row.label(text=_mod_label(item, item.layout, item.module, item.corner_module))


def _draw_modules(col, owner, layout_prop, mod_prop, corner_prop):
    col.prop(owner, layout_prop, text="")
    lay = getattr(owner, layout_prop)
    if lay == "SINGLE":
        col.prop(owner, mod_prop, text="Module")
    elif lay == "CORNER":
        col.prop(owner, corner_prop, text="Corners")
        col.prop(owner, mod_prop, text="Middle")


class AAB_PT_main(bpy.types.Panel):
    bl_label = "AA Buildings"
    bl_idname = "AAB_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AA Buildings"

    def draw(self, context):
        l = self.layout
        obj = context.active_object
        if not is_building(obj):
            col = l.column(align=True)
            col.scale_y = 1.4
            col.operator_menu_enum("aab.add_building", "shape", text="Add Building", icon="HOME")
            if obj is not None and obj.type == "MESH":
                l.operator("aab.make_building", icon="MOD_BUILD")
            l.separator()
            l.prop(context.scene.aa_build, "kit")
            if context.scene.aa_build.kit is None:
                l.operator("aab.sample_kit", icon="ASSET_MANAGER")
            box = l.box()
            box.label(text="1. Add a building (or use any flat mesh)", icon="DOT")
            box.label(text="2. Tab into Edit Mode and shape it", icon="DOT")
            box.label(text="3. Select edges and pick a side style", icon="DOT")
            return
        s = obj.aa_building
        col = l.column(align=True)
        col.prop(s, "kit")
        if s.kit is None:
            l.operator("aab.sample_kit", icon="ASSET_MANAGER")
        row = l.row(align=True)
        row.prop(s, "floors")
        row = l.row(align=True)
        row.prop(s, "seed")
        row.operator("aab.reseed", text="", icon="FILE_REFRESH")
        # ---- rigid modules
        box = l.box()
        row = box.row(align=True)
        row.prop(s, "rigid", icon="SNAP_INCREMENT")
        info = _state.get("snap", {}).get(obj.name) if s.rigid else None
        if info and info.get("moved", 0.0) > 0.005:
            row.operator("aab.snap_outline", text="Snap Outline", icon="SNAP_ON")
            box.label(text=f"Outline {info['moved']:.2f} m off the grid", icon="INFO")
        elif not s.rigid:
            box.label(text="Modules stretch to fill each side", icon="INFO")
        # ---- ground floor
        box = l.box()
        box.label(text="Ground floor", icon="HOME")
        box.row().prop(s, "ground_mode", expand=True)
        if s.ground_mode == "STOREFRONT":
            box.prop(s, "ground_default", text="Auto sides")
        else:
            c = box.column(align=True)
            _draw_modules(c, s, "ground_layout", "ground_module", "ground_corner_module")
            r = box.row(align=True)
            r.prop(s, "ground_entrance")
            sub = r.row(align=True)
            sub.active = s.ground_entrance
            sub.prop(s, "ground_door", text="")
        # ---- floor stack
        box = l.box()
        box.label(text="Upper floors (floor 2 up)", icon="LINENUMBERS_ON")
        row = box.row()
        row.template_list("AAB_UL_segments", "", s, "segments", s, "segment_index", rows=3)
        col = row.column(align=True)
        col.operator("aab.segment_add", text="", icon="ADD")
        col.operator("aab.segment_remove", text="", icon="REMOVE")
        col.separator()
        col.operator("aab.segment_move", text="", icon="TRIA_UP").direction = "UP"
        col.operator("aab.segment_move", text="", icon="TRIA_DOWN").direction = "DOWN"
        if not s.segments:
            box.label(text="No segments: every upper floor uses the kit mix", icon="INFO")
        elif 0 <= s.segment_index < len(s.segments):
            g = s.segments[s.segment_index]
            c = box.column(align=True)
            r = c.row(align=True)
            r.prop(g, "floors")
            r.prop(g, "height", text="Height")
            _draw_modules(c, g, "layout", "module", "corner_module")
            c.prop(g, "belt_below")
            covered = sum(max(1, x.floors) for x in s.segments)
            r = box.row()
            r.prop(s, "segment_repeat")
            if covered < s.floors - 1 and not s.segment_repeat:
                box.label(text=f"Segments cover {covered} of {s.floors - 1} upper floors: the last one continues", icon="INFO")
            elif covered > s.floors - 1:
                box.label(text=f"Segments cover {covered} floors, the building has {s.floors - 1} upper floors", icon="INFO")
        box = l.box()
        editing = obj.mode == "EDIT"
        box.label(text="Selected sides" if editing else "All sides", icon="EDGESEL" if editing else "MESH_DATA")
        grid = box.grid_flow(columns=3, even_columns=True, align=True)
        for k in (STYLE_SHOP, STYLE_WINDOWS, STYLE_BACK, STYLE_BLANK, STYLE_OPEN, STYLE_AUTO):
            name, desc, icon, _ = STYLE_INFO[k]
            op = grid.operator("aab.set_style", text=name, icon=icon)
            op.style = k
        if editing:
            row = box.row(align=True)
            row.operator("aab.toggle_fire", icon="OUTLINER_OB_FORCE_FIELD")
            row.operator("aab.toggle_round", icon="SPHERECURVE")
        else:
            box.label(text="Tab into Edit Mode to style single sides", icon="INFO")
        l.prop(s, "round_all")
        # ---- facade: dividers, cornices, areaways
        box = l.box()
        col = box.column(align=True)
        col.prop(s, "pilasters")
        sub = col.column(align=True)
        sub.active = s.pilasters
        sub.row(align=True).prop(s, "divider_type", expand=True)
        sub.prop(s, "divider_module", text="")
        sub.prop(s, "pilaster_ground")
        col = box.column(align=True)
        r = col.row(align=True)
        r.prop(s, "cornice")
        sub = r.row(align=True)
        sub.active = s.cornice
        sub.prop(s, "cornice_module", text="")
        r = col.row(align=True)
        r.prop(s, "belt", text="Belt cornice")
        sub = r.row(align=True)
        sub.active = s.belt or any(g.belt_below for g in s.segments)
        sub.prop(s, "belt_module", text="")
        col = box.column(align=True)
        col.prop(s, "areaways")
        r = col.row()
        r.active = s.areaways
        r.prop(s, "areaway_shops")
        l.prop(s, "damage", slider=True)
        status = s.status or "Building…"
        col = l.column(align=True)
        for part in status.split(" | ")[:3]:
            col.label(text=part, icon="CHECKMARK" if " pieces" in part else "ERROR")
        if s.kit is not None and _in_tree(obj, s.kit):
            l.operator("aab.move_out_of_kit", icon="EXPORT")
        l.prop(s, "show_extras", icon="TRIA_DOWN" if s.show_extras else "TRIA_RIGHT", emboss=False)
        if s.show_extras:
            b = l.box()
            b.label(text="Extras")
            c = b.column(align=True)
            for k in ("awnings", "sign_chance", "lights", "ac", "balconies", "roof_props"):
                c.prop(s, k, slider=True)
            c = b.column(align=True)
            for k in ("signs", "parapet", "pipes", "quoins", "interior_floors"):
                c.prop(s, k)
            b.label(text="Ground floor")
            c = b.column(align=True)
            c.prop(s, "shop_units")
            r = c.row()
            r.active = s.shop_units
            r.prop(s, "shop_unit_max")
            c.prop(s, "closed_shops", slider=True)
            c.prop(s, "recessed_doors", slider=True)
            r = c.row()
            r.active = s.recessed_doors > 0
            r.prop(s, "recess_depth")
            b.label(text="Damage")
            c = b.column(align=True)
            c.active = s.damage > 0
            c.prop(s, "boarded_windows")
            c.prop(s, "broken_roofline")
            c.prop(s, "rubble")
            b.label(text="Floors & fitting")
            c = b.column(align=True)
            c.prop(s, "ground_height")
            c.prop(s, "upper_height")
            c = b.column(align=True)
            c.prop(s, "vary_floors")
            c.prop(s, "wall_mix", slider=True)
            c.prop(s, "corner_pieces")
            c.prop(s, "corner_radius")
            b.label(text="Materials (empty = from kit)")
            b.prop(s, "wall_material", text="Walls")
            b.prop(s, "roof_material", text="Roof")
        l.separator()
        row = l.row(align=True)
        row.scale_y = 1.3
        row.operator("aab.bake", text="Bake…", icon="EXPORT")
        sp = context.scene.aa_build
        box = l.box()
        box.label(text="Unity export", icon="FILE_3D")
        box.prop(sp, "export_dir", text="")
        r = box.row(align=True)
        r.prop(sp, "export_at_origin")
        r.prop(sp, "export_collider", text="")
        box.operator("aab.export_unity", icon="EXPORT")
        l.operator("aab.remove_building", icon="X")


class AAB_PT_kit(bpy.types.Panel):
    bl_label = "Kit"
    bl_idname = "AAB_PT_kit"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AA Buildings"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        l = self.layout
        root = _active_kit(context)
        if root is None:
            l.label(text="Choose a kit collection above")
            l.operator("aab.sample_kit", icon="ASSET_MANAGER")
            return
        kit = _state["kits"].get(root.name)
        l.label(text=root.name, icon="OUTLINER_COLLECTION")
        row = l.row(align=True)
        row.operator("aab.refresh", icon="FILE_REFRESH")
        row.operator("aab.hide_kit", icon="HIDE_OFF")
        kp = root.aa_kit
        c = l.column(align=True)
        c.prop(kp, "front")
        c.prop(kp, "scale_mode")
        if kp.scale_mode == "CUSTOM":
            c.prop(kp, "scale")
        c.prop(kp, "grid")
        l.operator("aab.check_kit", icon="VIEWZOOM")
        issues = _state.get("checks", {}).get(root.name)
        if issues is not None:
            box = l.box()
            if not issues:
                box.label(text="No problems found", icon="CHECKMARK")
            for lvl, mod, msg, hint in issues[:30]:
                col = box.column(align=True)
                col.label(text=(mod + ": " if mod else "") + msg, icon={"ERROR": "CANCEL", "WARNING": "ERROR", "INFO": "INFO"}[lvl])
                sub = col.row()
                sub.scale_y = 0.7
                sub.label(text="     " + hint)
            if len(issues) > 30:
                box.label(text=f"+ {len(issues) - 30} more in the system console")
        if kit is None:
            l.label(text="Kit will be read when a building uses it")
            return
        l.label(text=f"Ground {kit.gh:.2f} m · upper {kit.uh:.2f} m · wall {kit.wall_hi - kit.wall_lo:.2f} m")
        for w in kit.warnings:
            l.label(text=w, icon="ERROR")
        if getattr(kit, "uv_issue", False):
            l.operator("aab.fix_uv_names", icon="UV")
        if kit.loose:
            l.operator("aab.make_modules", icon="OUTLINER_COLLECTION")
        counts = {}
        for m in kit.all:
            counts[m.role] = counts.get(m.role, 0) + 1
        grid = l.grid_flow(columns=2, even_columns=True)
        for r, _, _ in ROLE_DEFS[1:]:
            if counts.get(r):
                grid.label(text=f"{ROLE_LABEL[r]}: {counts[r]}")
        sc = context.scene.aa_build
        l.prop(sc, "show_kit", text=f"Modules ({len(kit.all)}) – fix categories", icon="TRIA_DOWN" if sc.show_kit else "TRIA_RIGHT", emboss=False)
        if sc.show_kit:
            b = l.box()
            names = [m.name for m in kit.all]
            cut = 0
            if len(names) > 1:
                pre = names[0]
                for nm in names[1:]:
                    while not nm.startswith(pre):
                        pre = pre[:-1]
                cut = max(pre.rfind("_"), pre.rfind(" "), pre.rfind("|")) + 1
            for m in kit.all:
                col = bpy.data.collections.get(m.name)
                if col is None:
                    continue
                row = b.row(align=True)
                icon = "QUESTION" if m.sub == "unknown" else ("CHECKMARK" if m.role != "ignore" else "X")
                row.label(text=m.name[cut:][:30], icon=icon)
                row.prop(col.aa_module, "category", text="")
                row.prop(col.aa_module, "floor", text="")
                row.prop(col.aa_module, "weight", text="")


_draw_handles = []


def _overlay_data(obj):
    try:
        loops, sides, _ = read_outline(obj)
    except Exception:
        return [], []
    M = obj.matrix_world
    lines = []
    labels = []
    snap = _state.get("snap", {}).get(obj.name) if obj.aa_building.rigid else None
    auto_as = GROUND_DEFAULT_STYLE[obj.aa_building.ground_default]
    for sd in sides:
        a = M @ sd.p
        b = M @ sd.q
        lines.append((a, b, auto_as if sd.style == STYLE_AUTO else sd.style))
        mid = (a + b) / 2
        name = STYLE_INFO[sd.style][0]
        if sd.style == STYLE_AUTO:
            name = "Auto (" + STYLE_INFO[GROUND_DEFAULT_STYLE[obj.aa_building.ground_default]][0] + ")"
        txt = name + (" + fire escape" if sd.fire else "") + f"  {sd.length:.2f} m"
        snapped = snap["lengths"].get(sd.id) if snap else None
        if snapped is not None and abs(snapped - sd.length) > 0.005:
            txt += f"  → {snapped:.2f} m"
        labels.append((mid, txt, STYLE_INFO[sd.style][3]))
        if sd.rounded:
            labels.append((M @ sd.p, "round", (1, 1, 1, 1)))
    return lines, labels


def _draw_view():
    try:
        import gpu
        from gpu_extras.batch import batch_for_shader
        ctx = bpy.context
        obj = ctx.active_object
        if not is_building(obj) or obj.mode != "EDIT" or not ctx.scene.aa_build.show_overlay:
            return
        lines, _ = _overlay_data(obj)
        if not lines:
            return
        shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
        region = ctx.region
        gpu.state.depth_test_set("NONE")
        gpu.state.blend_set("ALPHA")
        by_style = {}
        for a, b, st in lines:
            by_style.setdefault(st, []).extend([a + Vector((0, 0, 0.02)), b + Vector((0, 0, 0.02))])
        for st, pts in by_style.items():
            batch = batch_for_shader(shader, "LINES", {"pos": pts})
            shader.uniform_float("viewportSize", (region.width, region.height))
            shader.uniform_float("lineWidth", 5.0)
            shader.uniform_float("color", STYLE_INFO[st][3])
            batch.draw(shader)
        gpu.state.blend_set("NONE")
    except Exception:
        _state["draw_error"] = traceback.format_exc()


def _draw_px():
    try:
        import blf
        from bpy_extras import view3d_utils
        ctx = bpy.context
        obj = ctx.active_object
        if not is_building(obj) or obj.mode != "EDIT" or not ctx.scene.aa_build.show_overlay:
            return
        region = ctx.region
        rv3d = ctx.region_data
        _, labels = _overlay_data(obj)
        blf.size(0, 13)
        for pos, txt, col in labels:
            p2 = view3d_utils.location_3d_to_region_2d(region, rv3d, pos)
            if p2 is None:
                continue
            w, h = blf.dimensions(0, txt)
            blf.color(0, 0, 0, 0, 0.8)
            blf.position(0, p2.x - w / 2 + 1, p2.y + 7, 0)
            blf.draw(0, txt)
            blf.color(0, *col)
            blf.position(0, p2.x - w / 2, p2.y + 8, 0)
            blf.draw(0, txt)
    except Exception:
        pass
