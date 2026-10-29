"""Live updates: rebuild queue, timers and depsgraph / load / undo handlers."""

import bpy
import bmesh
import numpy as np
import traceback
from bpy.app.handlers import persistent

from .common import _state, is_building
from .kit import _in_tree, get_kit
from .planner import Plan
from .nodes import building_materials, ensure_data, ensure_group, ensure_modifier, write_data


def request(name):
    _state["dirty"].add(name)
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.0)


def request_all(kit_name=None):
    for o in bpy.data.objects:
        if is_building(o) and (kit_name is None or (o.aa_building.kit and o.aa_building.kit.name == kit_name)):
            request(o.name)


def invalidate_kits(kit_name=None):
    if kit_name is None:
        _state["kits"].clear()
    else:
        _state["kits"].pop(kit_name, None)
    _state["kit_version"] += 1
    request_all(kit_name)


def _tick():
    if _state["busy"]:
        return 0.05
    _state["busy"] = True
    try:
        names = list(_state["dirty"])
        _state["dirty"].clear()
        for n in names:
            o = bpy.data.objects.get(n)
            if not is_building(o):
                continue
            try:
                rebuild(o)
            except Exception as e:  # keep the UI alive; show the reason on the panel
                traceback.print_exc()
                try:
                    o.aa_building.status = "Error: " + str(e)[:200]
                except Exception:
                    pass
    finally:
        _state["busy"] = False
    return 0.01 if _state["dirty"] else None   # requests made during this run are not lost


@persistent
def _on_depsgraph(scene, depsgraph):
    if _state["busy"]:
        return
    kit_hits = set()
    for u in depsgraph.updates:
        idb = u.id
        if isinstance(idb, bpy.types.Object):
            o = idb.original
            if is_building(o):
                request(o.name)
            elif (u.is_updated_geometry or u.is_updated_transform) and o.name in _state["kit_objects"]:
                kit_hits.add(_state["kit_objects"][o.name])
        elif isinstance(idb, bpy.types.Collection):
            c = idb.original
            if c.name in _state["kit_cols"]:
                kit_hits.add(_state["kit_cols"][c.name])
    for k in kit_hits:
        invalidate_kits(k)


@persistent
def _on_load(_):
    _state["kits"].clear()
    _state["sigs"].clear()
    _state["failed"].clear()
    _state["kit_objects"].clear()
    _state["kit_cols"].clear()
    request_all()


@persistent
def _on_undo(_):
    _state["kits"].clear()
    _state["failed"].clear()
    request_all()


def settings_key(s):
    keys = ("floors", "seed", "ground_default", "vary_floors", "wall_mix", "round_all", "corner_radius",
            "corner_pieces", "cornice", "belt", "parapet", "roof_props", "ac", "awnings", "signs", "sign_chance", "lights",
            "balconies", "pipes", "quoins", "pilasters", "pilaster_ground", "shop_units", "shop_unit_max", "closed_shops",
            "recessed_doors", "recess_depth", "damage", "boarded_windows", "broken_roofline", "rubble", "interior_floors", "ground_height", "upper_height",
            "divider_type", "ground_mode", "ground_layout", "ground_entrance", "segment_repeat", "areaways", "areaway_shops",
            "rigid")
    vals = tuple(getattr(s, k) for k in keys)

    def nm(c):
        return c.name if c is not None else None
    refs = tuple(nm(getattr(s, k)) for k in ("cornice_module", "belt_module", "divider_module", "ground_module",
                                             "ground_corner_module", "ground_door"))
    segs = tuple((g.floors, g.layout, nm(g.module), nm(g.corner_module), round(g.height, 4), g.belt_below) for g in s.segments)
    return vals + refs + segs + (s.kit.name if s.kit else None, s.wall_material.name if s.wall_material else None,
                                 s.roof_material.name if s.roof_material else None)


def outline_key(obj):
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        ls = bm.edges.layers.int.get("aa_style")
        lf = bm.edges.layers.int.get("aa_fire")
        lr = bm.verts.layers.int.get("aa_round")
        return hash((tuple(round(c, 4) for v in bm.verts for c in v.co.xy),
                     tuple((e.verts[0].index, e.verts[1].index, e[ls] if ls else 0, e[lf] if lf else 0) for e in bm.edges),
                     tuple(v[lr] for v in bm.verts) if lr else (), len(bm.faces)))
    me = obj.data
    n = len(me.vertices)
    c = np.empty(n * 3)
    me.vertices.foreach_get("co", c)
    e = np.empty(len(me.edges) * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", e)
    parts = [np.round(c, 4).tobytes(), e.tobytes(), len(me.polygons)]
    for nm in ("aa_style", "aa_fire", "aa_round"):
        a = me.attributes.get(nm)
        if a is not None and a.data_type == "INT":
            arr = np.zeros(len(a.data), dtype=np.int32)
            a.data.foreach_get("value", arr)
            parts.append(arr.tobytes())
    return hash(tuple(parts))


def rebuild(obj, force=False):
    s = obj.aa_building
    kit = get_kit(s.kit) if s.kit else None
    data = s.data_obj
    owner_ok = data is not None and data.get("aa_owner") == obj.name
    scl = tuple(round(v, 5) for v in obj.scale)
    sig = (outline_key(obj), settings_key(s), kit.sig if kit else None, kit.version if kit else None,
           data.name if data else None, owner_ok, scl)
    if not force and _state["sigs"].get(obj.name) == sig and data is not None and owner_ok:
        return
    if not force and _state["failed"].get(obj.name) == sig:
        return   # these exact inputs failed last time: wait for a change instead of retrying on every update
    data = ensure_data(obj)
    _state["failed"][obj.name] = sig[:4] + (data.name, True, scl)   # cleared at the end once the rebuild succeeds
    plan = Plan(obj, s, kit).run()
    _state.setdefault("snap", {})[obj.name] = plan.snap_info if plan.rigid else None
    mats = building_materials(s, kit, (max(plan.proc.m) + 1) if plan.proc.m else 3)
    write_data(data, plan, mats)
    group = ensure_group(kit, s.kit)
    ensure_modifier(obj, group, data)
    msg = []
    if plan.sides:
        msg.append(f"{len(plan.points)} pieces · {s.floors} floor{'s' if s.floors > 1 else ''} · {plan.H + 0.02:.1f} m")
    extra = []
    if any(abs(v - 1.0) > 1e-4 for v in obj.scale):
        extra.append("Object is scaled: apply scale (Ctrl+A) so modules are not stretched")
    if s.kit is not None and _in_tree(obj, s.kit):
        extra.append("This building sits inside its kit collection: click Move Out of Kit")
    warnings = plan.warnings + extra + (kit.warnings if kit else ["No kit chosen: showing plain massing"])
    status = " | ".join(msg + warnings[:2])
    if s.status != status:
        s.status = status
    _state["sigs"][obj.name] = (outline_key(obj), settings_key(s), kit.sig if kit else None,
                                kit.version if kit else None, data.name, True, scl)
    _state["failed"].pop(obj.name, None)
