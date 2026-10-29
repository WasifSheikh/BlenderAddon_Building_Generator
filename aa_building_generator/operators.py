"""Operators for buildings, side styles, baking and kit maintenance."""

import bpy
import bmesh
import math
import random
from mathutils import Matrix

from .common import GEOM_TYPES, MOD_NAME, STYLE_INFO, _state, is_building
from .naming import tokens
from .kit import _inside_kit, _kit_meshes, _main_uv, _safe_collection, get_kit
from .planner import Plan
from .nodes import _set_input, building_materials, proc_mesh
from .runtime import invalidate_kits, rebuild, request, request_all
from .export import realized_mesh


SHAPES = {
    "RECT": [[(0, 0), (1, 0), (1, 1), (0, 1)]],
    "L": [[(0, 0), (1, 0), (1, 0.45), (0.45, 0.45), (0.45, 1), (0, 1)]],
    "U": [[(0, 0), (1, 0), (1, 1), (0.68, 1), (0.68, 0.42), (0.32, 0.42), (0.32, 1), (0, 1)]],
    "T": [[(0, 0.55), (0.32, 0.55), (0.32, 0), (0.68, 0), (0.68, 0.55), (1, 0.55), (1, 1), (0, 1)]],
    "COURTYARD": [[(0, 0), (1, 0), (1, 1), (0, 1)], [(0.3, 0.3), (0.3, 0.7), (0.7, 0.7), (0.7, 0.3)]],
}


def _new_outline_mesh(name, shape, width, depth):
    loops = SHAPES[shape]
    bm = bmesh.new()
    outer = [bm.verts.new(((x - 0.5) * width, (y - 0.5) * depth, 0)) for x, y in loops[0]]
    if len(loops) == 1:
        bm.faces.new(outer)
    else:
        inner = [bm.verts.new(((x - 0.5) * width, (y - 0.5) * depth, 0)) for x, y in loops[1]]
        n = len(outer)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((outer[i], outer[j], inner[(n - j) % n], inner[(n - i) % n]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.attributes.new("aa_style", "INT", "EDGE")
    me.attributes.new("aa_fire", "INT", "EDGE")
    me.attributes.new("aa_round", "INT", "POINT")
    return me


def _guess_kit(context):
    sc = context.scene.aa_build
    if sc.kit:
        return sc.kit
    for c in bpy.data.collections:
        if c.name.startswith("AA Sample Kit") or ("kit" in tokens(c.name) and c.children):
            return c
    return None


def _make_building(context, obj, rigid=True):
    s = obj.aa_building
    if not s.enabled:
        s.rigid = rigid     # new buildings use whole modules; older ones keep the setting they were made with
    s.enabled = True
    if s.kit is None:
        s.kit = _guess_kit(context)
    me = obj.data
    for nm, dom in (("aa_style", "EDGE"), ("aa_fire", "EDGE"), ("aa_round", "POINT")):
        if obj.mode != "EDIT" and me.attributes.get(nm) is None:
            me.attributes.new(nm, "INT", dom)
    request(obj.name)


class AAB_OT_add(bpy.types.Operator):
    bl_idname = "aab.add_building"
    bl_label = "Add Building"
    bl_description = "Add a new building at the 3D cursor"
    bl_options = {"REGISTER", "UNDO"}
    shape: bpy.props.EnumProperty(name="Shape", items=[
        ("RECT", "Rectangle", ""), ("L", "L-shape", ""), ("U", "U-shape", ""), ("T", "T-shape", ""),
        ("COURTYARD", "Courtyard", "")], default="RECT")
    width: bpy.props.FloatProperty(name="Width", default=16.0, min=2, unit="LENGTH")
    depth: bpy.props.FloatProperty(name="Depth", default=11.0, min=2, unit="LENGTH")
    floors: bpy.props.IntProperty(name="Floors", default=4, min=1, max=60)
    rigid: bpy.props.BoolProperty(name="Rigid modules", default=True,
                                  description="Modules keep their exact width; the outline starts on the module grid")

    def execute(self, context):
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        me = _new_outline_mesh("AA Building", self.shape, self.width, self.depth)
        obj = bpy.data.objects.new("AA Building", me)
        _safe_collection(context).objects.link(obj)
        obj.location = context.scene.cursor.location
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        obj.aa_building.floors = self.floors
        obj.aa_building.seed = random.randint(1, 9999)
        _make_building(context, obj, self.rigid)
        if obj.aa_building.rigid:
            snap_outline_mesh(obj)      # a new outline starts on the module grid, so it matches the building
        return {"FINISHED"}


class AAB_OT_make(bpy.types.Operator):
    bl_idname = "aab.make_building"
    bl_label = "Make Selected a Building"
    bl_description = "Use the active mesh (an outline or a flat shape) as a building footprint"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        o = context.active_object
        return o is not None and o.type == "MESH" and not is_building(o)

    def execute(self, context):
        _make_building(context, context.active_object)
        return {"FINISHED"}


class AAB_OT_remove(bpy.types.Operator):
    bl_idname = "aab.remove_building"
    bl_label = "Turn Back into Plain Mesh"
    bl_description = "Stop generating; keeps the outline mesh"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        if not is_building(obj):
            return {"CANCELLED"}
        obj.aa_building.enabled = False
        mod = obj.modifiers.get(MOD_NAME)
        if mod:
            obj.modifiers.remove(mod)
        data = obj.aa_building.data_obj
        obj.aa_building.data_obj = None
        if data and data.get("aa_owner") == obj.name:
            me = data.data
            bpy.data.objects.remove(data)
            if me and me.users == 0:
                bpy.data.meshes.remove(me)
        _state["sigs"].pop(obj.name, None)
        return {"FINISHED"}


def _selected_edges_set(obj, layer_name, value, all_edges=False, toggle=False):
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        lay = bm.edges.layers.int.get(layer_name) or bm.edges.layers.int.new(layer_name)
        edges = [e for e in bm.edges if (e.select or all_edges)]
        if toggle:
            value = 0 if edges and all(e[lay] for e in edges) else 1
        for e in edges:
            e[lay] = value
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        return len(edges)
    me = obj.data
    a = me.attributes.get(layer_name) or me.attributes.new(layer_name, "INT", "EDGE")
    if toggle:
        vals = [d.value for d in a.data]
        value = 0 if vals and all(vals) else 1
    for d in a.data:
        d.value = value
    me.update()
    return len(a.data)


class AAB_OT_style(bpy.types.Operator):
    bl_idname = "aab.set_style"
    bl_label = "Set Side Style"
    bl_description = "Set the style of the selected sides (all sides when not in Edit Mode)"
    bl_options = {"REGISTER", "UNDO"}
    style: bpy.props.IntProperty(default=0, min=0, max=5)

    @classmethod
    def description(cls, context, props):
        return STYLE_INFO[props.style][1] + (". Applies to the selected edges" if context.mode == "EDIT_MESH" else ". Applies to every side")

    def execute(self, context):
        obj = context.active_object
        if not is_building(obj):
            return {"CANCELLED"}
        n = _selected_edges_set(obj, "aa_style", self.style, all_edges=obj.mode != "EDIT")
        if obj.mode == "EDIT" and n == 0:
            self.report({"WARNING"}, "Select one or more outline edges first")
        request(obj.name)
        return {"FINISHED"}


class AAB_OT_fire(bpy.types.Operator):
    bl_idname = "aab.toggle_fire"
    bl_label = "Fire Escape"
    bl_description = "Toggle a fire escape on the selected sides"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        if not is_building(obj):
            return {"CANCELLED"}
        if obj.mode != "EDIT":
            self.report({"WARNING"}, "Tab into Edit Mode and select the sides first")
            return {"CANCELLED"}
        _selected_edges_set(obj, "aa_fire", 1, toggle=True)
        request(obj.name)
        return {"FINISHED"}


class AAB_OT_round(bpy.types.Operator):
    bl_idname = "aab.toggle_round"
    bl_label = "Round Corner"
    bl_description = "Toggle rounded corners on the selected outline points"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        if not is_building(obj) or obj.mode != "EDIT":
            self.report({"WARNING"}, "Tab into Edit Mode and select corner points first")
            return {"CANCELLED"}
        bm = bmesh.from_edit_mesh(obj.data)
        lay = bm.verts.layers.int.get("aa_round") or bm.verts.layers.int.new("aa_round")
        vs = [v for v in bm.verts if v.select]
        if not vs:
            self.report({"WARNING"}, "Select corner points first")
            return {"CANCELLED"}
        val = 0 if all(v[lay] for v in vs) else 1
        for v in vs:
            v[lay] = val
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        request(obj.name)
        return {"FINISHED"}


def snap_outline_mesh(obj):
    """Move the outline onto the footprint the building shows (Rigid modules). Returns how far it moved, or 0."""
    s = obj.aa_building
    kit = get_kit(s.kit) if s.kit else None
    plan = Plan(obj, s, kit).run()
    info = plan.snap_info
    if not info or info["moved"] < 1e-4:
        return 0.0
    ca, sa = math.cos(info["angle"]), math.sin(info["angle"])
    mu, mv = info["maps"]

    def snap(co):
        u, v = ca * co.x + sa * co.y, -sa * co.x + ca * co.y
        u, v = mu.get(round(u, 4), u), mv.get(round(v, 4), v)
        return ca * u - sa * v, sa * u + ca * v
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        for v in bm.verts:
            v.co.x, v.co.y = snap(v.co)
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    else:
        for v in obj.data.vertices:
            v.co.x, v.co.y = snap(v.co)
        obj.data.update()
    request(obj.name)
    return info["moved"]


class AAB_OT_snap_outline(bpy.types.Operator):
    bl_idname = "aab.snap_outline"
    bl_label = "Snap Outline"
    bl_description = "Move the outline onto the building it shows: every side becomes a whole number of modules"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        o = context.active_object
        return is_building(o) and o.aa_building.rigid

    def execute(self, context):
        moved = snap_outline_mesh(context.active_object)
        if moved:
            self.report({"INFO"}, f"Outline snapped (moved up to {moved:.2f} m)")
        else:
            self.report({"INFO"}, "The outline is already on the module grid")
        return {"FINISHED"}


class AAB_OT_reseed(bpy.types.Operator):
    bl_idname = "aab.reseed"
    bl_label = "New Variation"
    bl_description = "Shuffle the module choice"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        if is_building(obj):
            obj.aa_building.seed = random.randint(1, 99999)
        return {"FINISHED"}


class AAB_OT_refresh(bpy.types.Operator):
    bl_idname = "aab.refresh"
    bl_label = "Rescan Kit"
    bl_description = "Re-read the kit modules and rebuild every building"

    def execute(self, context):
        _state["kits"].clear()
        _state["sigs"].clear()
        _state["failed"].clear()
        _state["kit_version"] += 1
        request_all()
        return {"FINISHED"}


class AAB_OT_bake(bpy.types.Operator):
    bl_idname = "aab.bake"
    bl_label = "Bake"
    bl_description = "Make a static copy of the building: module instances to edit by hand, or one mesh for export"
    bl_options = {"REGISTER", "UNDO"}
    mode: bpy.props.EnumProperty(name="Bake as", default="INSTANCES", items=[
        ("INSTANCES", "Module instances", "One collection instance per module under a parent empty: move, delete or swap pieces by hand"),
        ("MESH", "Single mesh", "Everything joined into one mesh (real geometry, ready for FBX export to Unity)")])
    target: bpy.props.EnumProperty(name="Put it in", default="THIS", items=[
        ("THIS", "This scene", "Add the baked copy next to the live building"),
        ("NEW_SCENE", "New scene", "Put the baked copy in a separate scene")])
    hide_live: bpy.props.BoolProperty(name="Hide the live building", default=True)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj = context.active_object
        if not is_building(obj):
            return {"CANCELLED"}
        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        rebuild(obj, force=True)
        if self.target == "THIS":
            scene = context.scene
        else:
            scene = bpy.data.scenes.get("AA Baked Buildings") or bpy.data.scenes.new("AA Baked Buildings")
        baked = self.bake_instances(obj, scene) if self.mode == "INSTANCES" else self.bake_mesh(context, obj, scene)
        if self.target == "THIS":
            if self.hide_live:
                obj.hide_set(True)
            for o in context.selected_objects:
                o.select_set(False)
            try:
                baked.hide_set(False)
                baked.select_set(True)
                context.view_layer.objects.active = baked
            except Exception:
                pass
        else:
            self.report({"INFO"}, f"Baked into scene '{scene.name}'")
        return {"FINISHED"}

    def home_collection(self, obj, scene):
        if self.target == "THIS":
            cols = [c for c in obj.users_collection if not _inside_kit(c)]
            return cols[0] if cols else scene.collection
        return scene.collection

    def bake_mesh(self, context, obj, scene):
        me = realized_mesh(context, obj)
        # baking again replaces the previous baked copy instead of adding another one
        baked = next((o for o in scene.objects if o.type == "MESH" and o.get("aa_baked_from") == obj.name
                      and not o.get("aa_baked_part")), None)
        if baked is not None:
            old = baked.data
            baked.data = me
            if old is not None and old.users == 0:
                bpy.data.meshes.remove(old)
        else:
            baked = bpy.data.objects.new(obj.name + " (baked)", me)
            self.home_collection(obj, scene).objects.link(baked)
        me.name = obj.name + " (baked)"
        baked["aa_baked_from"] = obj.name
        baked.matrix_world = obj.matrix_world.copy()
        return baked

    def bake_instances(self, obj, scene):
        s = obj.aa_building
        kit = get_kit(s.kit) if s.kit else None
        plan = Plan(obj, s, kit).run()
        # one collection per baked building; baking again replaces its contents
        bc = next((c for c in scene.collection.children_recursive if c.get("aa_baked_from") == obj.name), None)
        if bc is None:
            bc = bpy.data.collections.new(obj.name + " (instances)")
            bc["aa_baked_from"] = obj.name
            self.home_collection(obj, scene).children.link(bc)
        for o in [o for o in bc.all_objects if o.get("aa_baked_part")]:
            me = o.data if o.type == "MESH" else None
            bpy.data.objects.remove(o)
            if me is not None and me.users == 0:
                bpy.data.meshes.remove(me)
        root = bpy.data.objects.new(obj.name + " (instances)", None)
        root.empty_display_type = "PLAIN_AXES"
        root["aa_baked_from"] = obj.name
        root["aa_baked_part"] = "root"
        bc.objects.link(root)
        root.matrix_world = obj.matrix_world.copy()
        if kit is not None:
            K = Matrix.Rotation(kit.rot, 4, "Z") @ Matrix.Diagonal((kit.scale, kit.scale, kit.scale, 1.0))
            for pos, index, yaw, scl in plan.points:
                m = kit.mods[index]
                col = bpy.data.collections.get(m.name)
                if col is None:
                    continue
                e = bpy.data.objects.new(m.name, None)
                e.instance_type = "COLLECTION"
                e.instance_collection = col
                e.empty_display_size = 0.2
                e["aa_baked_from"] = obj.name
                e["aa_baked_part"] = "module"
                bc.objects.link(e)
                e.parent = root
                e.matrix_basis = Matrix.Translation(pos) @ Matrix.Rotation(yaw, 4, "Z") @ \
                    Matrix.Diagonal((scl[0], scl[1], scl[2], 1.0)) @ K
        if plan.proc.f:
            me = proc_mesh(obj.name + " (structure)", plan.proc, building_materials(s, kit, (max(plan.proc.m) + 1) if plan.proc.m else 3))
            so = bpy.data.objects.new(obj.name + " (structure)", me)
            so["aa_baked_from"] = obj.name
            so["aa_baked_part"] = "structure"
            bc.objects.link(so)
            so.parent = root
        return root


class AAB_OT_make_modules(bpy.types.Operator):
    bl_idname = "aab.make_modules"
    bl_label = "Make Modules from Loose Objects"
    bl_description = "Put each loose object of the kit into its own module collection (pivot = object origin)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        root = _active_kit(context)
        if root is None:
            return {"CANCELLED"}
        made = 0
        for o in [o for o in root.objects if o.type in GEOM_TYPES and o.parent is None and not is_building(o)]:
            c = bpy.data.collections.new(o.name)
            root.children.link(c)
            c.instance_offset = o.matrix_world.translation
            for x in [o] + list(o.children_recursive):
                c.objects.link(x)
                if root in x.users_collection:
                    root.objects.unlink(x)
            made += 1
        invalidate_kits(root.name)
        self.report({"INFO"}, f"Made {made} module(s)")
        return {"FINISHED"}


class AAB_OT_hide_kit(bpy.types.Operator):
    bl_idname = "aab.hide_kit"
    bl_label = "Show / Hide Kit"
    bl_description = "Show or hide the kit modules in the viewport"

    def execute(self, context):
        root = _active_kit(context)
        if root is None:
            return {"CANCELLED"}

        def find(lc):
            if lc.collection == root:
                return lc
            for ch in lc.children:
                r = find(ch)
                if r:
                    return r
            return None
        lc = find(context.view_layer.layer_collection)
        if lc is None:
            self.report({"INFO"}, "The kit is not in this scene (that is fine)")
            return {"CANCELLED"}
        lc.hide_viewport = not lc.hide_viewport
        return {"FINISHED"}


def _active_kit(context):
    obj = context.active_object
    if is_building(obj) and obj.aa_building.kit:
        return obj.aa_building.kit
    return context.scene.aa_build.kit


class AAB_OT_move_out(bpy.types.Operator):
    bl_idname = "aab.move_out_of_kit"
    bl_label = "Move Out of Kit"
    bl_description = "Move this building out of its kit collection (a building inside its own kit can break the kit)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        if not is_building(obj) or obj.aa_building.kit is None:
            return {"CANCELLED"}
        root = obj.aa_building.kit
        tree = {root.name} | {c.name for c in root.children_recursive}
        target = _safe_collection(context)
        if target.name in tree:
            target = context.scene.collection
        if target not in obj.users_collection:
            target.objects.link(obj)
        for c in list(obj.users_collection):
            if c.name in tree:
                c.objects.unlink(obj)
        invalidate_kits(root.name)
        self.report({"INFO"}, f"Moved to '{target.name}'")
        return {"FINISHED"}


class AAB_OT_fix_uvs(bpy.types.Operator):
    bl_idname = "aab.fix_uv_names"
    bl_label = "Fix UV Map Names"
    bl_description = "Rename the main UV map of every kit mesh to 'UVMap' so baked buildings export with one UV channel"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        root = _active_kit(context)
        if root is None:
            return {"CANCELLED"}
        changed = 0
        for me in _kit_meshes(root):
            if me.library is not None:
                continue
            uv = _main_uv(me)
            if uv is None or uv.name == "UVMap":
                continue
            other = me.uv_layers.get("UVMap")
            if other is not None:
                other.name = "UVMap_extra"
            uv.name = "UVMap"
            changed += 1
        invalidate_kits(root.name)
        self.report({"INFO"}, f"Renamed {changed} UV map(s) to 'UVMap'")
        return {"FINISHED"}


# ---- floor stack segments
SEGMENT_COPY = ("floors", "layout", "module", "corner_module", "height", "belt_below")


class AAB_OT_segment_add(bpy.types.Operator):
    bl_idname = "aab.segment_add"
    bl_label = "Add Segment"
    bl_description = "Add a segment of upper floors (a copy of the selected one)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        if not is_building(obj):
            return {"CANCELLED"}
        s = obj.aa_building
        src = s.segments[s.segment_index] if 0 <= s.segment_index < len(s.segments) else None
        seg = s.segments.add()
        if src is not None:
            for k in SEGMENT_COPY:
                setattr(seg, k, getattr(src, k))
            seg.belt_below = False
        s.segment_index = len(s.segments) - 1
        request(obj.name)
        return {"FINISHED"}


class AAB_OT_segment_remove(bpy.types.Operator):
    bl_idname = "aab.segment_remove"
    bl_label = "Remove Segment"
    bl_description = "Remove the selected segment"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        if not is_building(obj):
            return {"CANCELLED"}
        s = obj.aa_building
        if 0 <= s.segment_index < len(s.segments):
            s.segments.remove(s.segment_index)
            s.segment_index = max(0, min(s.segment_index, len(s.segments) - 1))
        request(obj.name)
        return {"FINISHED"}


class AAB_OT_segment_move(bpy.types.Operator):
    bl_idname = "aab.segment_move"
    bl_label = "Move Segment"
    bl_description = "Move the selected segment in the list (the list runs from the lowest floors to the highest)"
    bl_options = {"REGISTER", "UNDO"}
    direction: bpy.props.EnumProperty(items=[("UP", "Up", "Earlier in the list: lower floors"), ("DOWN", "Down", "Later in the list: higher floors")])

    def execute(self, context):
        obj = context.active_object
        if not is_building(obj):
            return {"CANCELLED"}
        s = obj.aa_building
        i = s.segment_index
        j = i - 1 if self.direction == "UP" else i + 1   # the list runs from the lowest segment to the highest
        if 0 <= i < len(s.segments) and 0 <= j < len(s.segments):
            s.segments.move(i, j)
            s.segment_index = j
        request(obj.name)
        return {"FINISHED"}
