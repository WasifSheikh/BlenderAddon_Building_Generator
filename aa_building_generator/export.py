"""Unity export: one FBX per building with Unity axes, plus an optional collision shell."""

import bpy
import bmesh
import numpy as np
import os
import re
from mathutils import Matrix

from .common import MOD_NAME, _state, is_building
from .geometry import Proc
from .kit import get_kit
from .nodes import _set_input
from .planner import Plan
from .runtime import rebuild

# FBX settings that import into Unity with no rotation fix and 1 unit = 1 metre
UNITY_FBX = dict(
    use_selection=True, object_types={"MESH"}, apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS",
    axis_forward="-Z", axis_up="Y", bake_space_transform=True, use_mesh_modifiers=True,
    mesh_smooth_type="FACE", add_leaf_bones=False, use_custom_props=False, path_mode="AUTO",
)


def realized_mesh(context, obj):
    """The live building as one real mesh (modules made real), without the generator's own attributes."""
    mod = obj.modifiers.get(MOD_NAME)
    _set_input(mod, "Realize", True)
    context.view_layer.update()
    dg = context.evaluated_depsgraph_get()
    try:
        me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    finally:
        _set_input(mod, "Realize", False)
    for nm in [a.name for a in me.attributes if a.name.startswith("aa_")]:
        try:
            me.attributes.remove(me.attributes[nm])
        except Exception:
            pass
    return me


def collider_mesh(obj, name, top):
    """A closed low-poly shell around the footprint (outer wall face) from the ground to `top`."""
    s = obj.aa_building
    kit = get_kit(s.kit) if s.kit else None
    plan = Plan(obj, s, kit).run()
    proc = Proc()
    proc.prism(plan.shape_loops(plan.wall_lo), 0.0, top, 0)
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in proc.v], [], proc.f)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bm.to_mesh(me)
    bm.free()
    me.update()
    return me


def clean_name(name):
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", name).strip("_") or "Building"


class AAB_OT_export_unity(bpy.types.Operator):
    bl_idname = "aab.export_unity"
    bl_label = "Export FBX for Unity"
    bl_description = "Export the selected buildings (or the active one) as FBX files set up for Unity, each with an optional collider"

    @classmethod
    def poll(cls, context):
        return is_building(context.active_object) or any(is_building(o) for o in context.selected_objects)

    def execute(self, context):
        sp = context.scene.aa_build
        if sp.export_dir.startswith("//") and not bpy.data.filepath:
            self.report({"ERROR"}, "Save the .blend file first, or choose an absolute export folder")
            return {"CANCELLED"}
        if not hasattr(bpy.ops.export_scene, "fbx"):
            self.report({"ERROR"}, "The FBX exporter is not available: enable the 'FBX format' add-on")
            return {"CANCELLED"}
        folder = bpy.path.abspath(sp.export_dir)
        os.makedirs(folder, exist_ok=True)
        buildings = [o for o in context.selected_objects if is_building(o)]
        if not buildings and is_building(context.active_object):
            buildings = [context.active_object]
        if context.object is not None and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        prev_sel, prev_act = list(context.selected_objects), context.view_layer.objects.active
        done = []
        try:
            for obj in buildings:
                rebuild(obj, force=True)
                temp = []
                try:
                    name = clean_name(obj.name)
                    me = realized_mesh(context, obj)
                    temp.append(bpy.data.objects.new(name, me))
                    if sp.export_collider == "SHELL" and len(me.vertices):
                        co = np.empty(len(me.vertices) * 3)
                        me.vertices.foreach_get("co", co)
                        temp.append(bpy.data.objects.new(name + "_Collider", collider_mesh(obj, name + "_Collider", float(co[2::3].max()))))
                    M = Matrix.Identity(4) if sp.export_at_origin else obj.matrix_world.copy()
                    for o in temp:
                        context.scene.collection.objects.link(o)
                        o.matrix_world = M
                    for o in context.selected_objects:
                        o.select_set(False)
                    for o in temp:
                        o.select_set(True)
                    context.view_layer.objects.active = temp[0]
                    path = os.path.join(folder, name + ".fbx")
                    bpy.ops.export_scene.fbx(filepath=path, **UNITY_FBX)
                    done.append(path)
                finally:
                    for o in temp:
                        data = o.data
                        bpy.data.objects.remove(o)
                        if data is not None and data.users == 0:
                            bpy.data.meshes.remove(data)
        finally:
            for o in context.selected_objects:
                o.select_set(False)
            for o in prev_sel:
                try:
                    o.select_set(True)
                except ReferenceError:
                    pass
            try:
                context.view_layer.objects.active = prev_act
            except ReferenceError:
                pass
        _state["last_export"] = done
        self.report({"INFO"}, f"Exported {len(done)} building(s) to {folder}")
        return {"FINISHED"}
