"""Night lighting: lit copies of glazed modules, with the glass swapped for a lit (emissive) material.

No extra modules are needed in the kit. For every window, storefront and door module whose glass is found
(a material with "glass" / "glazing" in its name, or the kit's chosen Glass material), a hidden copy of the
module is kept in a collection "AA Lit | <module>" that is not part of any scene or kit. Its meshes are
copies with the glass replaced by "<glass>_Lit" (or the kit's chosen Lit material). The Geometry Nodes group
lists these copies after the kit's own modules, and the plan's lit windows point at them.

The copies are remade when the module they copy changes (its geometry, materials or objects, or the kit's glass
choice), so they always match it; an unchanged copy is kept as it is, because removing and adding objects makes
Blender re-evaluate the whole file.
In Unity the lit windows come in with their own material ("Glass_Lit"): give that one the emissive texture.
"""

import bpy
import hashlib

from .naming import tokens

LIT_ROLES = {"window": "windows", "storefront": "shops", "door": "shops"}
GLASS_WORDS = {"glass", "glazing", "glazed", "pane", "panes"}
LIT_PREFIX = "AA Lit | "
LIT_SUFFIX = "_Lit"
LIT_COLOR = (1.0, 0.78, 0.45)
LIT_STRENGTH = 4.0


def is_glass(mat, kp):
    """Is `mat` a glass material of this kit (the kit's chosen one, or any material named like glass)?"""
    if mat is None or mat.get("aa_lit_of"):
        return False
    if kp.glass_material is not None:
        return mat == kp.glass_material
    return bool(tokens(mat.name) & GLASS_WORDS)


def lit_material(glass, kp):
    """The lit version of a glass material: the kit's Lit material, or '<glass>_Lit' (made on first use)."""
    if kp.lit_material is not None:
        return kp.lit_material
    name = glass.name + LIT_SUFFIX
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = glass.copy()
    mat.name = name
    mat["aa_lit_of"] = glass.name
    mat.diffuse_color = (*LIT_COLOR, 1.0)
    try:    # glow in Blender's viewport and renders too; Unity gets the material name and sets up its own emission
        bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        sock = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
        sock.default_value = (*LIT_COLOR, 1.0)
        bsdf.inputs["Emission Strength"].default_value = LIT_STRENGTH
    except Exception:
        pass
    return mat


def _lit_slots(o, kp):
    """Material slot indices of `o` that hold glass."""
    return [i for i, sl in enumerate(o.material_slots) if is_glass(sl.material, kp)]


def module_has_glass(col, kp):
    return any(o.data is not None and hasattr(o.data, "materials") and _lit_slots(o, kp) for o in col.all_objects)


def _clear(vc):
    for o in list(vc.objects):
        data = o.data
        bpy.data.objects.remove(o)
        if data is not None and data.users == 0:     # only the copies' own meshes; shared data is still used
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Curve):
                bpy.data.curves.remove(data)


def _fingerprint(m, col, kp):
    """What a lit copy is made from: the module's geometry and materials (Mod.geo), its objects, its origin and the
    kit's glass / lit material choice. A copy with the same fingerprint is up to date and is kept as it is."""
    return hashlib.md5(repr((m.geo, tuple(o.name for o in col.all_objects), tuple(round(v, 5) for v in col.instance_offset),
                             kp.glass_material.name if kp.glass_material else None,
                             kp.lit_material.name if kp.lit_material else None)).encode("utf-8")).hexdigest()


def _reusable(vc, col, fp):
    """Is the existing lit copy `vc` up to date? Then its lit materials are returned, else None."""
    if vc is None or vc.get("aa_lit_fp") != fp or len(vc.objects) != len(col.all_objects):
        return None
    mats = vc.get("aa_lit_mats")
    if mats is None:
        return None
    names = [str(n) for n in mats]
    return names if all(bpy.data.materials.get(n) is not None for n in names) else None


def _variant(col, root, kp, lit_mats, m=None):
    """Fill 'AA Lit | <module>' with copies of the module's objects, glass swapped for its lit material.
    Removing and adding objects makes Blender re-evaluate the whole file, so an up-to-date copy is kept."""
    vc = bpy.data.collections.get(LIT_PREFIX + col.name)
    fp = _fingerprint(m, col, kp) if m is not None and m.geo else None
    if fp is not None:
        kept = _reusable(vc, col, fp)
        if kept is not None:
            lit_mats.update(kept)
            if vc.get("aa_lit_kit") != root.name:
                vc["aa_lit_kit"] = root.name
            return vc
    if vc is None:
        vc = bpy.data.collections.new(LIT_PREFIX + col.name)
    vc.use_fake_user = True        # not in any scene: kept by the node group and this flag
    vc["aa_lit_kit"] = root.name
    vc["aa_lit_module"] = col.name
    _clear(vc)
    own = set()
    vc.instance_offset = col.instance_offset
    copies = {}
    for o in col.all_objects:
        c = o.copy()
        c.name = o.name + " (lit)"
        c["aa_lit_variant"] = True
        slots = _lit_slots(o, kp) if o.data is not None and hasattr(o.data, "materials") else []
        if slots:
            # Geometry Nodes takes materials from the mesh, not the object: the copy gets its own mesh
            c.data = o.data.copy()
            c.data.name = o.data.name + " (lit)"
            for i in slots:
                lit = lit_material(o.material_slots[i].material, kp)
                lit_mats.add(lit.name)
                own.add(lit.name)
                if i < len(c.data.materials):
                    c.data.materials[i] = lit
                if c.material_slots[i].link == "OBJECT":
                    c.material_slots[i].material = lit
        vc.objects.link(c)
        copies[o] = c
    for o, c in copies.items():
        if o.parent in copies:
            c.parent = copies[o.parent]
            c.matrix_parent_inverse = o.matrix_parent_inverse.copy()
    vc["aa_lit_mats"] = sorted(own)
    vc["aa_lit_fp"] = fp or ""
    return vc


def ensure_lit_variants(kit, root):
    """Make sure every glazed window / storefront / door module of `kit` has an up-to-date lit copy.
    Fills kit.lit (module index -> instance list index) and kit.lit_names. Runs once per kit read."""
    if kit is None or root is None or kit.lit_synced:
        return
    kit.lit_synced = True
    kp = root.aa_kit
    kit.lit, kit.lit_names, kit.lit_mats = {}, [], set()
    keep = set()
    for m in kit.mods:
        if m.role not in LIT_ROLES or m.damaged:
            continue
        col = bpy.data.collections.get(m.name)
        if col is None or not module_has_glass(col, kp):
            continue
        vc = _variant(col, root, kp, kit.lit_mats, m)
        keep.add(vc.name)
        kit.lit[m.index] = len(kit.mods) + len(kit.lit_names)
        kit.lit_names.append(vc.name)
    for vc in [c for c in bpy.data.collections if c.get("aa_lit_kit") == root.name and c.name not in keep]:
        _clear(vc)
        bpy.data.collections.remove(vc)


def lit_kind(m):
    """'windows' or 'shops' for a module that can be lit, else None."""
    return None if m.damaged else LIT_ROLES.get(m.role)


def instance_indices(plan, kit):
    """Instance list index of every plan point: lit points use their module's lit copy when it has one."""
    if kit is None or not kit.lit or not plan.lit:
        return [p[1] for p in plan.points]
    return [kit.lit.get(p[1], p[1]) if k in plan.lit else p[1] for k, p in enumerate(plan.points)]


def entry_name(kit, index):
    """Collection name of an instance list entry (a kit module, or a lit copy after them)."""
    n = len(kit.mods)
    return kit.mods[index].name if index < n else kit.lit_names[index - n]
