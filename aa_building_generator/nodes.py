"""Writes the plan into the hidden data mesh and builds the Geometry Nodes setup."""

import bpy
import random

from .common import MOD_NAME, is_building


def _default_material(name, color):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = (*color, 1.0)
        try:
            mat.use_nodes = True
        except Exception:
            pass
        try:
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            bsdf.inputs["Base Color"].default_value = (*color, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.85
        except Exception:
            pass
    return mat


def building_materials(s, kit, used=3):
    wall = s.wall_material or (bpy.data.materials.get(kit.wall_mat) if kit and kit.wall_mat else None) or _default_material("AA Wall", (0.55, 0.5, 0.45))
    roof = s.roof_material or (bpy.data.materials.get(kit.roof_mat) if kit and kit.roof_mat else None) or _default_material("AA Roof", (0.16, 0.16, 0.17))
    floor = _default_material("AA Floor", (0.35, 0.33, 0.3))
    out = [wall, roof, floor]
    if used > 3:
        out.append(_default_material("AA Shutter", (0.4, 0.42, 0.44)))
    if used > 4:
        out.append(_default_material("AA Boards", (0.38, 0.27, 0.16)))
    return out


def ensure_data(obj):
    s = obj.aa_building
    data = s.data_obj
    owner = data.get("aa_owner") if data else None
    if data is not None and owner and owner != obj.name:
        other = bpy.data.objects.get(owner)
        if other is not None and is_building(other) and other.aa_building.data_obj == data:
            data = None  # this object is a duplicate: give it its own data
    if data is None:
        if s.data_obj is not None:
            s.seed = random.randint(1, 99999)  # a duplicate gets its own variation
        me = bpy.data.meshes.new("AA Data | " + obj.name)
        data = bpy.data.objects.new("AA Data | " + obj.name, me)
        s.data_obj = data
    data["aa_owner"] = obj.name
    return data


def write_data(data, plan, mats):
    me = data.data
    proc = plan.proc
    verts = [tuple(v) for v in proc.v]
    nproc = len(verts)
    verts += [tuple(p[0]) for p in plan.points]
    me.clear_geometry()
    for nm in ("aa_inst", "aa_module", "aa_rot", "aa_scale"):
        a = me.attributes.get(nm)
        if a is not None:
            me.attributes.remove(a)
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    me.from_pydata(verts, [], proc.f)
    me.materials.clear()
    for m in mats:
        me.materials.append(m)
    if proc.f:
        me.polygons.foreach_set("material_index", proc.m)
        uv = me.uv_layers.new(name="UVMap")
        flat = [c for pair in proc.uvs() for c in pair]
        uv.data.foreach_set("uv", flat)
    nv = len(verts)
    flag = me.attributes.new("aa_inst", "BOOLEAN", "POINT")
    flag.data.foreach_set("value", [False] * nproc + [True] * len(plan.points))
    idx = me.attributes.new("aa_module", "INT", "POINT")
    idx.data.foreach_set("value", [0] * nproc + [p[1] for p in plan.points])
    rot = me.attributes.new("aa_rot", "FLOAT_VECTOR", "POINT")
    rot.data.foreach_set("vector", [0.0] * (nproc * 3) + [c for p in plan.points for c in (0.0, 0.0, p[2])])
    sc = me.attributes.new("aa_scale", "FLOAT_VECTOR", "POINT")
    sc.data.foreach_set("vector", [1.0] * (nproc * 3) + [c for p in plan.points for c in p[3]])
    me.update()


def proc_mesh(name, proc, mats):
    """The generated roof, slabs, fillers and corner posts as an ordinary mesh."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in proc.v], [], proc.f)
    for m in mats:
        me.materials.append(m)
    if proc.f:
        me.polygons.foreach_set("material_index", proc.m)
        uv = me.uv_layers.new(name="UVMap")
        uv.data.foreach_set("uv", [c for pair in proc.uvs() for c in pair])
    me.update()
    return me


def _set_input(mod, name, value):
    g = mod.node_group
    ident = None
    for item in g.interface.items_tree:
        if getattr(item, "item_type", "") == "SOCKET" and item.in_out == "INPUT" and item.name == name:
            ident = item.identifier
    if ident is None:
        return
    try:
        getattr(mod.properties.inputs, ident).value = value
    except Exception:
        try:
            mod[ident] = value
        except Exception:
            pass
    mod.id_data.update_tag()


def _get_input(mod, name):
    g = mod.node_group
    for item in g.interface.items_tree:
        if getattr(item, "item_type", "") == "SOCKET" and item.in_out == "INPUT" and item.name == name:
            try:
                return getattr(mod.properties.inputs, item.identifier).value
            except Exception:
                try:
                    return mod[item.identifier]
                except Exception:
                    return None
    return None


def ensure_group(kit, root):
    name = "AA Building | " + (root.name if root else "no kit")
    sig = "v2|" + (str((kit.sig, round(kit.rot, 4), round(kit.scale, 6), tuple(m.name for m in kit.mods))) if kit else "none")
    g = bpy.data.node_groups.get(name)
    if g is not None and g.get("aa_sig") == sig:
        return g
    if g is None:
        g = bpy.data.node_groups.new(name, "GeometryNodeTree")
        try:
            g.is_modifier = True
        except Exception:
            pass
        g.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        g.interface.new_socket(name="Data", in_out="INPUT", socket_type="NodeSocketObject")
        g.interface.new_socket(name="Realize", in_out="INPUT", socket_type="NodeSocketBool")
        g.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nodes, links = g.nodes, g.links
    nodes.clear()
    gi = nodes.new("NodeGroupInput")
    go = nodes.new("NodeGroupOutput")
    gi.location = (-1200, 0)
    go.location = (900, 0)
    oi = nodes.new("GeometryNodeObjectInfo")
    oi.transform_space = "ORIGINAL"
    oi.location = (-1000, 0)
    links.new(gi.outputs["Data"], oi.inputs["Object"])
    flag = nodes.new("GeometryNodeInputNamedAttribute")
    flag.data_type = "BOOLEAN"
    flag.inputs["Name"].default_value = "aa_inst"
    flag.location = (-1000, -250)
    sep = nodes.new("GeometryNodeSeparateGeometry")
    sep.domain = "POINT"
    sep.location = (-800, 0)
    links.new(oi.outputs["Geometry"], sep.inputs["Geometry"])
    links.new(flag.outputs["Attribute"], sep.inputs["Selection"])
    join = nodes.new("GeometryNodeJoinGeometry")
    join.location = (400, 0)
    links.new(sep.outputs["Inverted"], join.inputs[0])
    if kit and kit.mods:
        idx = nodes.new("GeometryNodeInputNamedAttribute")
        idx.data_type = "INT"
        idx.inputs["Name"].default_value = "aa_module"
        rot = nodes.new("GeometryNodeInputNamedAttribute")
        rot.data_type = "FLOAT_VECTOR"
        rot.inputs["Name"].default_value = "aa_rot"
        scl = nodes.new("GeometryNodeInputNamedAttribute")
        scl.data_type = "FLOAT_VECTOR"
        scl.inputs["Name"].default_value = "aa_scale"
        idx.location, rot.location, scl.location = (-800, -300), (-800, -450), (-800, -600)
        # every module becomes one entry of an instance list, in kit.mods order (index = aa_module)
        g2i = nodes.new("GeometryNodeGeometryToInstance")
        g2i.location = (-250, 0)
        infos = []
        for i, m in enumerate(kit.mods):
            ci = nodes.new("GeometryNodeCollectionInfo")
            ci.transform_space = "ORIGINAL"
            col = bpy.data.collections.get(m.name)
            if col is not None:
                ci.inputs["Collection"].default_value = col
            ci.inputs["Separate Children"].default_value = False
            ci.inputs["Reset Children"].default_value = False
            ci.label = m.name[:60]
            ci.location = (-500, -160 * i)
            infos.append(ci)
        for ci in reversed(infos):   # a multi-input socket lists its newest link first
            links.new(ci.outputs[0], g2i.inputs[0])
        src = g2i.outputs[0]
        if abs(kit.rot) > 1e-6 or abs(kit.scale - 1.0) > 1e-9:
            tr = nodes.new("GeometryNodeTransform")
            tr.inputs["Rotation"].default_value = (0.0, 0.0, kit.rot)
            tr.inputs["Scale"].default_value = (kit.scale, kit.scale, kit.scale)
            tr.location = (-50, 0)
            links.new(src, tr.inputs["Geometry"])
            src = tr.outputs[0]
        iop = nodes.new("GeometryNodeInstanceOnPoints")
        iop.location = (150, 0)
        links.new(sep.outputs["Selection"], iop.inputs["Points"])
        links.new(src, iop.inputs["Instance"])
        iop.inputs["Pick Instance"].default_value = True
        links.new(idx.outputs["Attribute"], iop.inputs["Instance Index"])
        links.new(rot.outputs["Attribute"], iop.inputs["Rotation"])
        links.new(scl.outputs["Attribute"], iop.inputs["Scale"])
        links.new(iop.outputs[0], join.inputs[0])
    real = nodes.new("GeometryNodeRealizeInstances")
    real.location = (600, -150)
    links.new(join.outputs[0], real.inputs[0])
    sw = nodes.new("GeometryNodeSwitch")
    sw.input_type = "GEOMETRY"
    sw.location = (750, 0)
    links.new(gi.outputs["Realize"], sw.inputs["Switch"])
    links.new(join.outputs[0], sw.inputs["False"])
    links.new(real.outputs[0], sw.inputs["True"])
    links.new(sw.outputs[0], go.inputs[0])
    g["aa_sig"] = sig
    return g


def ensure_modifier(obj, group, data):
    mod = obj.modifiers.get(MOD_NAME)
    if mod is None or mod.type != "NODES":
        mod = obj.modifiers.new(MOD_NAME, "NODES")
        mod.show_in_editmode = True
        mod.show_on_cage = False
    if mod.node_group != group:
        mod.node_group = group
    if _get_input(mod, "Data") != data:
        _set_input(mod, "Data", data)
    return mod
