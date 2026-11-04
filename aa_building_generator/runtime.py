"""Live updates: rebuild queue, timers and depsgraph / load / undo handlers."""

import bpy
import bmesh
import hashlib
import numpy as np
import traceback
from bpy.app.handlers import persistent

from .common import _state, is_building
from .kit import _in_tree, get_kit, kit_signature, kit_structure
from .lighting import ensure_lit_variants, instance_indices
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


def _kit_changed(name):
    """A collection of this kit was flagged as updated: did the kit really change? Blender flags every collection in
    the file whenever any object is added or removed anywhere (the lit copies of lighting.py are such objects), so a
    flag alone used to re-read every kit and rebuild every building, which made the next flag: an endless loop."""
    root = bpy.data.collections.get(name)
    if root is None:
        return True                      # the kit was deleted or renamed: its buildings show that
    kit = _state["kits"].get(name)
    if kit is None:
        return False                     # already dropped (or never read): the next rebuild reads it anyway
    return kit.sig != kit_signature(root) or kit.struct != kit_structure(root)


@persistent
def _on_depsgraph(scene, depsgraph):
    if _state["busy"]:
        return
    kit_hits = set()
    col_hits = set()
    for u in depsgraph.updates:
        idb = u.id
        if isinstance(idb, bpy.types.Object):
            o = idb.original
            if is_building(o):
                request(o.name)
            elif (u.is_updated_geometry or u.is_updated_transform) and o.name in _state["kit_objects"]:
                kit_hits.add(_state["kit_objects"][o.name])
        elif isinstance(idb, bpy.types.Collection):
            k = _state["kit_cols"].get(idb.original.name)
            if k is not None:
                col_hits.add(k)
    for k in col_hits - kit_hits:
        if _kit_changed(k):
            kit_hits.add(k)
    for k in kit_hits:
        invalidate_kits(k)


@persistent
def _on_load(_):
    _state["kits"].clear()
    _state["sigs"].clear()
    _state["failed"].clear()
    _state["kit_objects"].clear()
    _state["kit_cols"].clear()
    _state.setdefault("digest", {}).clear()
    _state.setdefault("digest_v1", {}).clear()
    request_all()


@persistent
def _on_undo(_):
    _state["kits"].clear()
    _state["failed"].clear()
    request_all()


# settings added since 1.5.0: appended at the end, so the 1.5.0 key (and the digest of bakes made with it) is kept
NEW_KEYS = ("lit_windows", "lit_shops", "lit_variation")


def settings_key(s, legacy=False):
    keys = ("floors", "seed", "ground_default", "vary_floors", "wall_mix", "round_all", "corner_radius",
            "corner_pieces", "cornice", "belt", "parapet", "roof_props", "ac", "awnings", "signs", "sign_chance", "lights",
            "balconies", "pipes", "quoins", "pilasters", "pilaster_ground", "shop_units", "shop_unit_max", "closed_shops",
            "recessed_doors", "recess_depth", "damage", "boarded_windows", "broken_roofline", "rubble", "interior_floors", "ground_height", "upper_height",
            "divider_type", "ground_mode", "ground_layout", "ground_entrance", "segment_repeat", "areaways", "areaway_shops",
            "rigid", "ac_shift_x", "ac_shift_z")
    vals = tuple(getattr(s, k) for k in keys)

    def nm(c):
        return c.name if c is not None else None
    refs = tuple(nm(getattr(s, k)) for k in ("cornice_module", "belt_module", "divider_module", "ground_module",
                                             "ground_corner_module", "ground_door"))
    segs = tuple((g.floors, g.layout, nm(g.module), nm(g.corner_module), round(g.height, 4), g.belt_below) for g in s.segments)
    key = vals + refs + segs + (s.kit.name if s.kit else None, s.wall_material.name if s.wall_material else None,
                                s.roof_material.name if s.roof_material else None)
    return key if legacy else key + tuple(getattr(s, k) for k in NEW_KEYS)


def outline_key(obj):
    """A digest of the outline (points, edges, side styles). md5, so it is the same in every Blender session."""
    # Edit Mode and Object Mode give the same digest for the same outline
    h = hashlib.md5()
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.index_update()
        c = np.array([v.co[:] for v in bm.verts], dtype=np.float64).reshape(-1)
        e = np.array([(ed.verts[0].index, ed.verts[1].index) for ed in bm.edges], dtype=np.int32).reshape(-1)
        nf = len(bm.faces)
        layers = [(nm, bm.edges.layers.int.get(nm), bm.edges) for nm in ("aa_style", "aa_fire")] + \
                 [("aa_round", bm.verts.layers.int.get("aa_round"), bm.verts)]
        ints = [np.array([x[lay] for x in elems], dtype=np.int32) for _, lay, elems in layers if lay is not None]
    else:
        me = obj.data
        c = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", c)
        e = np.empty(len(me.edges) * 2, dtype=np.int32)
        me.edges.foreach_get("vertices", e)
        nf = len(me.polygons)
        ints = []
        for nm in ("aa_style", "aa_fire", "aa_round"):
            a = me.attributes.get(nm)
            if a is not None and a.data_type == "INT":
                arr = np.zeros(len(a.data), dtype=np.int32)
                a.data.foreach_get("value", arr)
                ints.append(arr)
    h.update((np.round(c, 4) + 0.0).tobytes())
    h.update(e.tobytes())
    h.update(str(nf).encode())
    for arr in ints:
        h.update(arr.tobytes())
    return h.hexdigest()


DIGEST_V = "v2:"   # v2 also covers the kit's module geometry; older bakes stored the plain v1 digest


def building_digest(obj, legacy=False):
    """What the building looks like now (outline, settings, kit and its geometry), or None before its first
    rebuild. Stored on the building when it is baked, so a bake that no longer matches can be found.
    legacy: the 1.5.0 digest (no kit geometry), to compare with bakes made before 1.6.0."""
    return _state.get("digest_v1" if legacy else "digest", {}).get(obj.name)


def bake_matches(obj, stored):
    """Does a stored bake digest match the building as it is now? Unknown (not rebuilt yet) counts as a match."""
    if stored.startswith(DIGEST_V):
        d = building_digest(obj)
        return d is None or d == stored
    if building_digest(obj) is None:
        return True
    return building_digest(obj, legacy=True) == stored   # a 1.5.0 bake: None (lit settings used since) = changed


def kit_uses_lights(root):
    """Does any building on this kit have lit windows? Then the kit's lit copies are kept up to date."""
    for o in bpy.data.objects:
        b = getattr(o, "aa_building", None)
        if b is not None and b.enabled and b.kit == root and (b.lit_windows > 0 or b.lit_shops > 0):
            return True
    return False


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
    if kit is not None and kit_uses_lights(s.kit):
        ensure_lit_variants(kit, s.kit)    # for every building of the kit: they share one node group
    write_data(data, plan, mats, instance_indices(plan, kit))
    group = ensure_group(kit, s.kit)
    ensure_modifier(obj, group, data)
    msg = []
    if plan.sides:
        msg.append(f"{len(plan.points)} pieces · {s.floors} floor{'s' if s.floors > 1 else ''} · {plan.H + 0.02:.1f} m")
        if plan.lit and kit is not None:
            lit = sum(1 for k in plan.lit if plan.points[k][1] in kit.lit)
            msg.append(f"{lit} lit")
    if (s.lit_windows > 0 or s.lit_shops > 0) and kit is not None and kit.mods and not kit.lit:
        plan.warnings.append("Lit windows: no glass found in the window modules (name the material *Glass*, "
                             "or pick it under Kit > Night lighting)")
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
    _state.setdefault("digest", {})[obj.name] = DIGEST_V + hashlib.md5(
        repr((sig[0], sig[1], sig[2], scl, kit.geo_sig if kit else None)).encode()).hexdigest()
    # the 1.5.0 digest, so bakes made with 1.5.0 still compare correctly (only when the new settings are unused)
    if not any(getattr(s, k) for k in NEW_KEYS):
        _state.setdefault("digest_v1", {})[obj.name] = hashlib.md5(
            repr((sig[0], settings_key(s, legacy=True), kit.sig_v1 if kit else None, scl)).encode()).hexdigest()
    else:
        _state.setdefault("digest_v1", {}).pop(obj.name, None)
    _state["failed"].pop(obj.name, None)
