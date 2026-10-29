"""Kit analysis: finds the modules in a kit collection and measures them."""

import bpy
import hashlib
import math
import numpy as np
from mathutils import Matrix, Vector

from .common import GEOM_TYPES, _state, is_building
from .naming import (DAMAGE_WORDS, OLD_ROLES, ROUND_WORDS, SOCKET_RULES, is_areaway_tokens, name_numbers, name_radius,
                     role_from_tokens, tokens)
from .geometry import _round_frame


# pieces laid along a side: their left edge is what lines up, wherever the collection origin is
OFFSET_ROLES = {"window", "wall", "pilaster", "shutter", "storefront", "door", "cornice", "parapet", "awning", "sign", "balcony", "areaway"}


def _kit_roots():
    roots = set()
    for o in bpy.data.objects:
        b = getattr(o, "aa_building", None)
        if b is not None and b.enabled and b.kit:
            roots.add(b.kit)
    for sc in bpy.data.scenes:
        k = getattr(sc, "aa_build", None)
        if k is not None and k.kit:
            roots.add(k.kit)
    return roots


def _inside_kit(col):
    for r in _kit_roots():
        if col == r or col in r.children_recursive:
            return True
    return False


def _safe_collection(context):
    """Where new buildings go: never inside a kit collection."""
    c = context.collection
    if c is None or _inside_kit(c):
        return context.scene.collection
    return c


def _in_tree(obj, root):
    if root is None:
        return False
    tree = {root.name} | {c.name for c in root.children_recursive}
    return any(c.name in tree for c in obj.users_collection)


def _kit_meshes(root):
    out = {}
    for o in root.all_objects:
        if o.type == "MESH" and not is_building(o):
            out[o.data.name_full] = o.data
        elif o.type == "EMPTY" and o.instance_type == "COLLECTION" and o.instance_collection:
            for io in o.instance_collection.all_objects:
                if io.type == "MESH":
                    out[io.data.name_full] = io.data
    return list(out.values())


def _main_uv(me):
    for l in me.uv_layers:
        if l.active_render:
            return l
    return me.uv_layers[0] if me.uv_layers else None


class Mod:
    __slots__ = ("name", "role", "layer", "floor", "weight", "w", "h", "d", "x0", "lo", "hi", "sockets",
                 "kind", "turn", "trim_in", "trim_out", "radius", "index", "mounted", "cx", "cy", "rxy",
                 "tokens", "material", "sub", "guessed", "rc", "re", "rin", "damaged")

    def __init__(self):
        self.sockets = []
        self.kind = None
        self.turn = 0.0
        self.trim_in = self.trim_out = 0.0
        self.radius = 0.0
        self.index = -1
        self.material = None
        self.sub = ""
        self.guessed = True
        self.rc = Vector((0.0, 0.0, 0.0))     # rounded pieces: arc centre in module space
        self.re = Vector((0.0, -1.0, 0.0))    # rounded pieces: direction from the centre to side A's end
        self.rin = None
        self.damaged = False


class Kit:
    def __init__(self, name):
        self.name = name
        self.mods = []
        self.all = []
        self.by_role = {}
        self.gh = 4.0
        self.uh = 3.2
        self.depth = 0.3
        self.wall_lo = 0.0       # outside face of the straight walls (module Y, negative = outwards)
        self.wall_hi = 0.3       # inside face of the straight walls
        self.cornice_lo = -0.3
        self.cornice_hi = 0.0
        self.parapet_lo = 0.0
        self.parapet_hi = 0.25
        self.parapet_depth = 0.3
        self.cornice_h = 0.3
        self.wall_mat = None
        self.roof_mat = None
        self.roof_t = 0.2
        self.rot = 0.0
        self.scale = 1.0
        self.warnings = []
        self.loose = []
        self.version = 0
        self.sig = None
        self.default_radius = None
        self.uv_issue = False
        self.damaged = {}        # (role, width cm) -> damaged variants of that module
        self.by_name = {}        # module (collection) name -> Mod, frequency 0 included

    def role(self, r):
        return self.by_role.get(r, [])


def kit_signature(root):
    kp = root.aa_kit
    parts = [root.name, kp.front, kp.scale_mode, round(kp.scale, 6)]

    def visit(c):
        p = c.aa_module
        parts.append((c.name, len(c.objects), len(c.children), p.category, p.floor, round(p.weight, 3)))
        for ch in c.children:
            visit(ch)
    for ch in root.children:
        visit(ch)
    parts.append(len(root.objects))
    return hashlib.md5(repr(tuple(parts)).encode("utf-8")).hexdigest()


def collect_modules(root):
    found = []

    def geom(o):
        return (o.type in GEOM_TYPES and not is_building(o)) or \
            (o.type == "EMPTY" and o.instance_type == "COLLECTION" and o.instance_collection)

    def visit(c, path):
        direct = [o for o in c.objects if geom(o)]
        if direct:
            found.append((c, path))
            return
        for ch in c.children:
            visit(ch, path + [c.name])
    for ch in root.children:
        visit(ch, [root.name])
    loose = [o.name for o in root.objects if o.type in GEOM_TYPES and o.parent is None and not is_building(o)]
    found.sort(key=lambda x: x[0].name)
    return found, loose


def _iter_geometry(col, base):
    """Yield (object, matrix) for geometry in a module, including one level of nested collection instances."""
    for o in col.all_objects:
        if is_building(o):
            continue
        if o.type in GEOM_TYPES:
            yield o, base @ o.matrix_world
        elif o.type == "EMPTY" and o.instance_type == "COLLECTION" and o.instance_collection:
            ic = o.instance_collection
            inner = base @ o.matrix_world @ Matrix.Translation(-Vector(ic.instance_offset))
            for io in ic.all_objects:
                if io.type in GEOM_TYPES:
                    yield io, inner @ io.matrix_world


def _measure(col, A, dg):
    base = A @ Matrix.Translation(-Vector(col.instance_offset))
    lo = np.array([1e9, 1e9, 1e9])
    hi = -lo
    mat_area = {}
    count = 0
    xys = []
    for o, M in _iter_geometry(col, base):
        me = None
        eo = None
        try:
            if dg is not None:
                eo = o.evaluated_get(dg)
                me = eo.to_mesh()
            elif o.type == "MESH":
                me = o.data
            if me is None or len(me.vertices) == 0:
                continue
            n = len(me.vertices)
            co = np.empty(n * 3, dtype=np.float64)
            me.vertices.foreach_get("co", co)
            co = co.reshape(n, 3)
            m = np.array(M)
            pts = co @ m[:3, :3].T + m[:3, 3]
            lo = np.minimum(lo, pts.min(axis=0))
            hi = np.maximum(hi, pts.max(axis=0))
            xys.append(pts[:, :2].copy())
            count += n
            np_ = len(me.polygons)
            if np_:
                areas = np.empty(np_)
                me.polygons.foreach_get("area", areas)
                mi = np.empty(np_, dtype=np.int32)
                me.polygons.foreach_get("material_index", mi)
                slots = o.material_slots
                for idx in np.unique(mi):
                    if 0 <= idx < len(slots) and slots[idx].material:
                        mat = slots[idx].material.name
                        mat_area[mat] = mat_area.get(mat, 0.0) + float(areas[mi == idx].sum())
        except Exception:
            continue
        finally:
            if eo is not None:
                try:
                    eo.to_mesh_clear()
                except Exception:
                    pass
    if count == 0:
        return None
    sockets = []
    for o in col.all_objects:
        if o.type == "EMPTY" and o.instance_type != "COLLECTION":
            M = base @ o.matrix_world
            loc = M.to_translation()
            yaw = M.to_euler().z
            sockets.append((o.name, o.get("aa_socket_role"), Vector(loc), yaw))
    material = max(mat_area, key=mat_area.get) if mat_area else None
    xy = np.concatenate(xys) if xys else np.zeros((0, 2))
    if len(xy) > 6000:
        xy = xy[:: len(xy) // 6000 + 1]
    return Vector(lo), Vector(hi), sockets, material, xy


def _mode(values):
    if not values:
        return None
    counts = {}
    for v in values:
        k = round(v, 2)
        counts[k] = counts.get(k, 0) + 1
    best = max(counts.values())
    return max(k for k, c in counts.items() if c == best)


def build_kit(root):
    kit = Kit(root.name)
    kp = root.aa_kit
    rot = {"NEG_Y": 0.0, "POS_Y": math.pi, "NEG_X": math.pi / 2, "POS_X": -math.pi / 2}[kp.front]
    found, loose = collect_modules(root)
    kit.loose = loose
    try:
        dg = bpy.context.evaluated_depsgraph_get()
    except Exception:
        dg = None
    # unit scale
    scale = kp.scale if kp.scale_mode == "CUSTOM" else 1.0
    A = Matrix.Rotation(rot, 4, "Z") @ Matrix.Diagonal((scale, scale, scale, 1.0))
    measured = []
    for col, path in found:
        r = _measure(col, A, dg)
        if r is None:
            continue
        measured.append((col, path, r))
        for o in col.all_objects:
            _state["kit_objects"][o.name] = root.name
        _state["kit_cols"][col.name] = root.name
    _state["kit_cols"][root.name] = root.name
    if kp.scale_mode == "AUTO" and measured:
        heights = sorted(r[1].z - r[0].z for _, _, r in measured)
        med = heights[len(heights) // 2]
        if med > 30:  # centimetre kit
            scale = 0.01
            A = Matrix.Rotation(rot, 4, "Z") @ Matrix.Diagonal((scale, scale, scale, 1.0))
            measured = [(c, p, _measure(c, A, dg)) for c, p, _ in measured]
            measured = [m for m in measured if m[2] is not None]
    kit.rot = rot
    kit.scale = scale

    offset_mods = []
    for col, path, (lo, hi, sockets, material, xy) in measured:
        m = Mod()
        m.name = col.name
        m.lo, m.hi = lo, hi
        m.material = material
        props = col.aa_module
        t_name = tokens(col.name)
        t_all = set(t_name)
        for p in path[1:]:
            t_all |= tokens(p)
        m.tokens = t_all
        m.damaged = bool(t_all & DAMAGE_WORDS)
        role = None
        has_join = any("join" in tokens(sn) for sn, _, _, _ in sockets)
        if props.category != "AUTO":
            role = props.category
            m.guessed = False
        elif has_join:
            role = "corner"
        else:
            # module name first, then a category saved by the old assembler, then folder names
            role = role_from_tokens(t_name)
            if role is None and col.get("aa_role") in OLD_ROLES:
                role = OLD_ROLES[col.get("aa_role")]
            if role is None:
                for p in reversed(path[1:]):
                    role = role_from_tokens(tokens(p))
                    if role:
                        break
        if role is None:
            role = "ignore"
            m.guessed = False
            m.sub = "unknown"
        m.role = role
        m.weight = props.weight
        # fitting size
        mw = hi.x - lo.x
        mh = hi.z - max(lo.z, 0.0)
        x0 = lo.x if lo.x < -0.15 * max(mw, 0.01) else 0.0
        if role in OFFSET_ROLES and lo.x > 0.25 * max(hi.x - lo.x, 0.01):
            x0 = lo.x   # the geometry sits well right of the collection origin: measure from its left edge
            offset_mods.append(col.name)
        mw_fit = hi.x - x0
        nums = name_numbers(col.name)
        w = None
        h = None
        if isinstance(col.get("aa_width_cm"), (int, float)) and col.get("aa_width_cm") > 0:
            w = col["aa_width_cm"] / 100.0
        if isinstance(col.get("aa_height_cm"), (int, float)) and col.get("aa_height_cm") > 0:
            h = col["aa_height_cm"] / 100.0
        if role in ("fire_stair", "fire_ladder", "pipe") and len(nums) == 1:
            if abs(nums[0] - mh) / max(mh, 0.01) < 0.35:
                h = h or nums[0]
        else:
            if nums and w is None and abs(nums[0] - mw_fit) / max(mw_fit, 0.01) < 0.2:
                w = nums[0]
            if len(nums) >= 2 and h is None and abs(nums[-1] - mh) / max(mh, 0.01) < 0.2:
                h = nums[-1]
            elif len(nums) == 1 and w is None and h is None and abs(nums[0] - mh) / max(mh, 0.01) < 0.2:
                h = nums[0]
        m.w = max(w or mw_fit, 0.05)
        m.h = max(h or mh, 0.05)
        m.x0 = x0
        m.d = max(hi.y, 0.02)
        m.mounted = lo.z > 1.0
        m.cx = (lo.x + hi.x) / 2
        m.cy = (lo.y + hi.y) / 2
        m.rxy = math.hypot(hi.x - lo.x, hi.y - lo.y) / 2
        # floor preference
        fl = props.floor
        if fl == "AUTO":
            sec = col.get("aa_section")
            if sec in ("ground", "upper"):
                fl = sec
            elif "ground" in t_all or "first" in t_all or "groundfloor" in t_all:
                fl = "ground"
            elif "upper" in t_all:
                fl = "upper"
        m.floor = fl
        # sockets
        join_in = join_out = None
        for sname, srole, loc, yaw in sockets:
            st = tokens(sname)
            if "join" in st and "in" in st or sname.upper().startswith("AA_JOIN_IN"):
                join_in = loc
                continue
            if "join" in st and "out" in st or sname.upper().startswith("AA_JOIN_OUT"):
                join_out = loc
                continue
            r2 = OLD_ROLES.get(srole, srole) if srole else None
            if not r2:
                for rr, toks in SOCKET_RULES:
                    if st & toks:
                        r2 = rr
                        break
            if r2:
                m.sockets.append((r2, Vector(loc), yaw))
        # corners
        if role == "corner":
            is_round = bool(t_all & ROUND_WORDS)
            if is_areaway_tokens(t_all):
                m.layer = "areaway"
            elif "parapet" in t_all:
                m.layer = "parapet"
            elif t_all & {"cornice", "molding", "moulding", "belt", "course", "trim"}:
                m.layer = "cornice"
                m.sub = "belt" if t_all & {"belt", "course"} else "cornice"
            elif "roof" in t_all and t_all & {"tile", "slab"}:
                m.layer = "roof"
            elif "edge" in t_all or "roof" in t_all:
                m.layer = "parapet"  # Roof_Corner, Roof_Edge_Corner ...: the roof-edge (parapet) line
            else:
                m.layer = "facade"   # a piece much lower than a storey is matched to a line below
            if join_in is not None and join_out is not None:
                m.kind = "join"
                turn = col.get("aa_turn_degrees")
                m.turn = float(turn) if isinstance(turn, (int, float)) else math.degrees(math.atan2(join_in.y, -join_in.x))
                m.trim_in = join_in.length
                m.trim_out = max(join_out.x, 0.0)
            elif is_round or (lo.x >= -0.1 and hi.y <= 0.1 and lo.y < -0.3):
                m.kind = "rounded"
                frame = _round_frame(xy, lo, hi) if is_round else None
                if frame:
                    m.rc, m.re, m.rin = frame
                else:
                    m.radius = name_radius(col.name) or (nums[0] if nums else hi.x)
            elif hi.x <= 0.05 and hi.y <= 0.05:
                m.kind = "cap"
            elif lo.y < -0.5 and hi.y < 0.6 and lo.x > -0.6:
                m.kind = "pier"          # inside return (concave corner)
                m.turn = -90.0
                m.trim_in = -lo.y
                m.trim_out = hi.x
            else:
                m.kind = "pier"          # outside corner sitting on the corner point
                m.turn = 90.0
                m.trim_in = max(hi.y, 0.0)
                m.trim_out = max(hi.x, 0.0)
        else:
            m.layer = "facade"
        if role == "cornice":
            m.sub = "belt" if t_name & {"belt", "course"} else "cornice"
        kit.all.append(m)

    kit.mods = [m for m in kit.all if m.role not in ("ignore", "roof_tile")]
    for i, m in enumerate(kit.mods):
        m.index = i
    kit.by_name = {m.name: m for m in kit.all}
    for m in kit.all:
        if m.weight <= 0:           # frequency 0 = never used
            continue
        if m.damaged:               # damaged variants only ever replace their undamaged twin
            kit.damaged.setdefault((m.role, int(round(m.w * 100))), []).append(m)
        else:
            kit.by_role.setdefault(m.role, []).append(m)

    # floor heights
    ground_src = [m.h for m in kit.role("storefront")] or [m.h for m in kit.role("door")] or \
                 [m.h for m in kit.role("window") if m.floor == "ground"]
    upper_src = [m.h for m in kit.role("window") if m.floor != "ground"] or \
                [m.h for m in kit.role("wall") if m.floor != "ground"]
    uh = _mode(upper_src)
    gh = _mode(ground_src)
    kit.uh = uh or gh or 3.2
    kit.gh = gh or kit.uh
    for m in kit.all:
        if m.floor == "AUTO":
            if m.role in ("storefront", "door"):
                m.floor = "ground"
            elif m.role in ("window", "wall", "pilaster", "corner", "corner_trim"):
                ng = abs(m.h - kit.gh) < 0.06
                nu = abs(m.h - kit.uh) < 0.06
                m.floor = "any" if ng == nu else ("ground" if ng else "upper")
            else:
                m.floor = "any"

    def med(vals, default):
        vals = sorted(vals)
        return vals[len(vals) // 2] if vals else default
    facade = [m for m in kit.mods if m.role in ("window", "wall", "storefront") and not m.damaged]
    if facade:
        ds = sorted(m.d for m in facade)
        kit.depth = min(max(ds[len(ds) // 2], 0.05), 1.5)
    kit.wall_lo = med([m.lo.y for m in facade], 0.0)
    kit.wall_hi = med([m.hi.y for m in facade], 0.3)
    if kit.wall_hi - kit.wall_lo < 0.05:
        kit.wall_hi = kit.wall_lo + 0.05
    cors = kit.role("cornice")
    kit.cornice_lo = med([m.lo.y for m in cors], -0.3)
    kit.cornice_hi = med([m.hi.y for m in cors], 0.0)
    par = kit.role("parapet")
    kit.parapet_lo = med([m.lo.y for m in par], 0.0)
    kit.parapet_hi = med([m.hi.y for m in par], 0.25)
    if par:
        pd = sorted(m.d for m in par)
        kit.parapet_depth = min(max(pd[len(pd) // 2], 0.05), 1.5)
    cor = [m.hi.z for m in cors if m.sub == "cornice"] or [m.hi.z for m in cors]
    if cor:
        kit.cornice_h = max(cor)
    # corner pieces much lower than a storey belong to the belt / roof edge
    storey = min(kit.gh, kit.uh)
    lines = [("cornice", "belt", m.h) for m in cors if m.sub == "belt"] + \
            [("cornice", "cornice", m.h) for m in cors if m.sub != "belt"] + \
            [("parapet", "", m.h) for m in par]
    for m in kit.all:
        if m.role != "corner":
            continue
        if m.layer == "facade" and m.h < 0.5 * storey:
            if lines:   # unnamed short corner piece: give it to the line whose height it matches
                lay, sub, _ = min(lines, key=lambda x: abs(x[2] - m.h))
                m.layer, m.sub = lay, sub
            else:
                m.layer, m.sub = "cornice", "cornice"
        if m.kind == "rounded" and m.rin is not None:
            ref = {"facade": kit.wall_hi, "cornice": kit.cornice_hi, "parapet": kit.parapet_hi}.get(m.layer, 0.0)
            m.radius = name_radius(m.name) or max(m.rin + ref, 0.2)
    walls = [m for m in kit.role("wall") + kit.role("window") if m.floor != "ground"] or kit.role("wall") or kit.role("window")
    mats = {}
    for m in walls:
        if m.material:
            mats[m.material] = mats.get(m.material, 0) + (2 if m.role == "wall" else 1)
    kit.wall_mat = max(mats, key=mats.get) if mats else None
    roofs = kit.role("roof_tile")
    if roofs:
        kit.roof_mat = roofs[0].material
        kit.roof_t = max(min(roofs[0].hi.z - roofs[0].lo.z, 1.0), 0.05)
    rounded = [m for m in kit.role("corner") if m.kind == "rounded" and m.layer == "facade"]
    kit.default_radius = rounded[0].radius if rounded else None
    if not kit.mods:
        kit.warnings.append("No usable modules found in this kit")
    if offset_mods:
        kit.warnings.append(f"{len(offset_mods)} module(s) sit away from their collection origin (measured from their geometry)")
    if loose:
        kit.warnings.append(f"{len(loose)} loose object(s) in the kit root are not modules yet")
    names = set()
    for me in _kit_meshes(root):
        uv = _main_uv(me)
        if uv is not None:
            names.add(uv.name)
    kit.uv_issue = bool(names - {"UVMap"})
    if kit.uv_issue:
        kit.warnings.append("UV maps have different names (" + ", ".join(sorted(names)) + "): Fix UV Map Names before baking")
    kit.sig = kit_signature(root)
    kit.version = _state["kit_version"]
    return kit


def get_kit(root):
    if root is None:
        return None
    k = _state["kits"].get(root.name)
    sig = kit_signature(root)
    if k is None or k.sig != sig:
        k = build_kit(root)
        _state["kits"][root.name] = k
    return k
