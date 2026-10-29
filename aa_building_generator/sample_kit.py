"""A small placeholder kit so the tool can be tried right away."""

import bpy
from mathutils import Vector

from .common import is_building
from .nodes import _default_material
from .runtime import invalidate_kits


def _box(col, name, lo, hi, mat):
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.materials.append(mat)
    uv = me.uv_layers.new(name="UVMap")
    for p in me.polygons:
        ax = (0, 1) if abs(p.normal.z) > 0.5 else ((0, 2) if abs(p.normal.y) > 0.5 else (1, 2))
        for li in p.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (v[ax[0]], v[ax[1]])
    o = bpy.data.objects.new(name, me)
    col.objects.link(o)
    return o


class AAB_OT_sample_kit(bpy.types.Operator):
    bl_idname = "aab.sample_kit"
    bl_label = "Create Sample Kit"
    bl_description = "Make a small placeholder kit so you can try the tool right away"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        mat = {k: _default_material("AA Sample " + k, c) for k, c in {
            "brick": (0.42, 0.2, 0.14), "plaster": (0.72, 0.68, 0.6), "glass": (0.12, 0.2, 0.25),
            "trim": (0.78, 0.75, 0.68), "metal": (0.16, 0.17, 0.18), "canvas": (0.12, 0.38, 0.24),
            "roof": (0.15, 0.15, 0.16), "sign": (0.6, 0.12, 0.1)}.items()}
        root = bpy.data.collections.new("AA Sample Kit")
        context.scene.collection.children.link(root)
        grid = [0]

        def module(name):
            c = bpy.data.collections.new(name)
            root.children.link(c)
            off = Vector(((grid[0] % 8) * 8.0 - 80.0, (grid[0] // 8) * 8.0 + 40.0, 0.0))
            grid[0] += 1
            c.instance_offset = off
            return c, off

        def B(c, off, nm, lo, hi, m):
            _box(c, nm, Vector(lo) + off, Vector(hi) + off, mat[m])

        G, U, D = 4.0, 3.2, 0.3
        for w in (3.0,):
            c, o = module("Storefront_300x400")
            B(c, o, "pier L", (0, 0, 0), (0.3, D, G), "trim"); B(c, o, "pier R", (w - 0.3, 0, 0), (w, D, G), "trim")
            B(c, o, "header", (0.3, 0, 3.0), (w - 0.3, D, G), "brick"); B(c, o, "base", (0.3, 0, 0), (w - 0.3, D, 0.4), "trim")
            B(c, o, "glass", (0.3, 0.12, 0.4), (w - 0.3, 0.16, 3.0), "glass"); B(c, o, "back", (0.3, 1.0, 0), (w - 0.3, 1.05, 3.0), "plaster")
            c, o = module("Shop_Door_300x400")
            B(c, o, "pier L", (0, 0, 0), (0.3, D, G), "trim"); B(c, o, "pier R", (w - 0.3, 0, 0), (w, D, G), "trim")
            B(c, o, "header", (0.3, 0, 3.0), (w - 0.3, D, G), "brick"); B(c, o, "door", (1.0, 0.1, 0), (2.0, 0.18, 2.6), "metal")
            B(c, o, "glass", (0.3, 0.12, 0.4), (1.0, 0.16, 3.0), "glass"); B(c, o, "glass2", (2.0, 0.12, 0.4), (w - 0.3, 0.16, 3.0), "glass")
            B(c, o, "transom", (1.0, 0.12, 2.6), (2.0, 0.16, 3.0), "glass")

        def window_wall(c, o, w, h, holes, sill=True):
            xs = [0.0]
            for a, b in holes:
                xs += [a, b]
            xs.append(w)
            for k in range(0, len(xs), 2):
                if xs[k + 1] - xs[k] > 1e-6:
                    B(c, o, "wall", (xs[k], 0, 0), (xs[k + 1], D, h), "brick")
            for a, b in holes:
                B(c, o, "under", (a, 0, 0), (b, D, 0.9), "brick"); B(c, o, "over", (a, 0, h - 0.6), (b, D, h), "brick")
                B(c, o, "glass", (a, 0.14, 0.9), (b, 0.18, h - 0.6), "glass")
                if sill:
                    B(c, o, "sill", (a - 0.08, -0.08, 0.84), (b + 0.08, 0.05, 0.92), "trim")
        c, o = module("Window_200x320"); window_wall(c, o, 2.0, U, [(0.5, 1.5)])
        c, o = module("Window_Double_400x320"); window_wall(c, o, 4.0, U, [(0.5, 1.5), (2.5, 3.5)])
        c, o = module("Ground_Window_200x400"); window_wall(c, o, 2.0, G, [(0.45, 1.55)])
        c, o = module("Wall_200x320"); B(c, o, "wall", (0, 0, 0), (2.0, D, U), "brick")
        c, o = module("Ground_Wall_200x400"); B(c, o, "wall", (0, 0, 0), (2.0, D, G), "plaster")
        c, o = module("Service_Door_200x400")
        B(c, o, "wall L", (0, 0, 0), (0.5, D, G), "plaster"); B(c, o, "wall R", (1.5, 0, 0), (2.0, D, G), "plaster")
        B(c, o, "over", (0.5, 0, 2.4), (1.5, D, G), "plaster"); B(c, o, "door", (0.5, 0.12, 0), (1.5, 0.2, 2.4), "metal")
        c, o = module("Cornice_200"); B(c, o, "band", (0, -0.25, 0), (2.0, 0.15, 0.3), "trim"); B(c, o, "lip", (0, -0.32, 0.22), (2.0, 0.15, 0.3), "trim")
        c, o = module("Parapet_200"); B(c, o, "wall", (0, 0.0, 0), (2.0, 0.25, 0.7), "brick"); B(c, o, "cap", (0, -0.04, 0.7), (2.0, 0.29, 0.78), "trim")
        c, o = module("Awning_300"); B(c, o, "canvas", (0.15, -1.2, 0.0), (2.85, 0.0, 0.12), "canvas"); B(c, o, "valance", (0.15, -1.25, -0.25), (2.85, -1.2, 0.12), "canvas")
        c, o = module("Shop_Sign_600"); B(c, o, "board", (0.2, -0.14, 3.15), (5.8, 0.0, 3.75), "sign")
        c, o = module("AC_Unit"); B(c, o, "box", (0, -0.55, 0), (0.85, 0.0, 0.6), "metal")
        c, o = module("Wall_Light"); B(c, o, "lamp", (-0.1, -0.25, -0.15), (0.1, 0.0, 0.2), "metal")
        c, o = module("Drainpipe_320"); B(c, o, "pipe", (-0.05, -0.14, 0), (0.05, -0.04, U), "metal")
        c, o = module("Quoin_320")
        for k in range(5):
            z = k * 0.64
            ln = 0.45 if k % 2 == 0 else 0.3
            B(c, o, "stone", (0, -0.04, z + 0.02), (ln, 0, z + 0.3), "trim")
            B(c, o, "stone r", (-0.04, 0, z + 0.34), (0, ln, z + 0.62), "trim")
        c, o = module("Roof_AC"); B(c, o, "box", (-0.7, -0.55, 0), (0.7, 0.55, 0.9), "metal")
        c, o = module("Roof_Vent"); B(c, o, "vent", (-0.25, -0.25, 0), (0.25, 0.25, 0.9), "metal")
        c, o = module("Water_Tank"); B(c, o, "tank", (-0.8, -0.8, 0.4), (0.8, 0.8, 2.6), "metal"); B(c, o, "legs", (-0.7, -0.7, 0), (0.7, 0.7, 0.4), "metal")
        c, o = module("Fire_Escape_Landing_300")
        B(c, o, "deck", (0, -1.1, -0.06), (3.0, 0, 0), "metal"); B(c, o, "rail", (0, -1.12, 0.95), (3.0, -1.06, 1.0), "metal")
        B(c, o, "rail L", (0, -1.1, 0.95), (0.05, 0, 1.0), "metal"); B(c, o, "rail R", (2.95, -1.1, 0.95), (3.0, 0, 1.0), "metal")
        c, o = module("Fire_Escape_Stair_320")
        for k in range(16):
            B(c, o, "step", (0.4 + k * 0.14, -0.95, k * 0.2), (0.6 + k * 0.14, -0.15, k * 0.2 + 0.04), "metal")
        c, o = module("Fire_Escape_Ladder_400")
        B(c, o, "rail a", (2.5, -1.0, 0.3), (2.54, -0.96, 4.0), "metal"); B(c, o, "rail b", (2.9, -1.0, 0.3), (2.94, -0.96, 4.0), "metal")
        for k in range(10):
            B(c, o, "rung", (2.5, -1.0, 0.5 + k * 0.35), (2.94, -0.97, 0.53 + k * 0.35), "metal")
        c, o = module("Roof_Tile_200"); B(c, o, "slab", (0, 0, -0.2), (2.0, 2.0, 0), "roof")
        c, o = module("Window_Broken_200x320")
        B(c, o, "wall", (0, 0, 0), (0.5, D, U), "brick"); B(c, o, "wall", (1.5, 0, 0), (2.0, D, U), "brick")
        B(c, o, "under", (0.5, 0, 0), (1.5, D, 0.9), "brick"); B(c, o, "over", (0.5, 0, U - 0.6), (1.5, D, U), "brick")
        B(c, o, "dark", (0.5, 0.25, 0.9), (1.5, 0.3, U - 0.6), "metal")
        B(c, o, "shard", (0.5, 0.14, 2.2), (0.8, 0.18, U - 0.6), "glass"); B(c, o, "shard", (1.2, 0.14, 0.9), (1.5, 0.18, 1.3), "glass")
        B(c, o, "sill", (0.42, -0.08, 0.84), (1.58, 0.05, 0.92), "trim")
        c, o = module("Shutter_300x400")
        B(c, o, "panel", (0.3, -0.06, 0.0), (2.7, -0.02, 3.0), "metal"); B(c, o, "box", (0.25, -0.25, 3.0), (2.75, 0.0, 3.3), "metal")
        c, o = module("Areaway_200")
        B(c, o, "pit floor", (0, -1.2, -1.0), (2.0, 0.0, -0.9), "plaster")
        B(c, o, "retaining wall", (0, -1.3, -1.0), (2.0, -1.15, 0.12), "plaster")
        B(c, o, "coping", (0, -1.35, 0.12), (2.0, -1.1, 0.2), "trim")
        B(c, o, "rail", (0, -1.26, 0.95), (2.0, -1.2, 1.0), "metal")
        for x in (0.02, 0.98):
            B(c, o, "post", (x, -1.25, 0.2), (x + 0.04, -1.21, 0.95), "metal")
        c, o = module("Areaway_Corner")
        B(c, o, "pit floor", (-1.2, -1.2, -1.0), (0.0, 0.0, -0.9), "plaster")
        B(c, o, "wall a", (-1.3, -1.3, -1.0), (-1.15, 0.0, 0.12), "plaster")
        B(c, o, "wall b", (-1.15, -1.3, -1.0), (0.0, -1.15, 0.12), "plaster")
        B(c, o, "coping a", (-1.35, -1.35, 0.12), (-1.1, 0.0, 0.2), "trim")
        B(c, o, "coping b", (-1.1, -1.35, 0.12), (0.0, -1.1, 0.2), "trim")
        B(c, o, "rail a", (-1.26, -1.26, 0.95), (-1.2, 0.0, 1.0), "metal")
        B(c, o, "rail b", (-1.2, -1.26, 0.95), (0.0, -1.2, 1.0), "metal")
        c, o = module("Rubble_Pile")
        for x, y, r in ((0.0, 0.0, 0.45), (0.5, 0.2, 0.3), (-0.4, 0.3, 0.35), (0.2, -0.4, 0.25), (-0.2, -0.2, 0.2)):
            B(c, o, "chunk", (x - r, y - r, 0), (x + r, y + r, r * 1.2), "plaster")

        def find(lc):
            if lc.collection == root:
                return lc
            for ch in lc.children:
                r = find(ch)
                if r:
                    return r
        lc = find(context.view_layer.layer_collection)
        if lc:
            lc.hide_viewport = True
        context.scene.aa_build.kit = root
        obj = context.active_object
        if is_building(obj) and obj.aa_building.kit is None:
            obj.aa_building.kit = root
        invalidate_kits(None)
        return {"FINISHED"}
