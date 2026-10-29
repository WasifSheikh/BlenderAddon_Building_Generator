"""Plans a building: which module goes where on every side, corner and roof line.

Plan combines the core (floors, corners, roof) with the mixins in facades, lines and extras."""

import math
from mathutils import Matrix, Vector

from .common import GROUND_DEFAULT_STYLE, STYLE_AUTO, STYLE_OPEN, STYLE_SHOP, STYLE_WINDOWS, _rng
from .geometry import MAT_FLOOR, MAT_PARAPET, MAT_ROOF, MAT_WALL, Proc, _hull2d, offset_loop
from .outline import read_outline
from .tuning import BELT_DROP, FLOOR_SLAB_T, PARAPET_FALLBACK_H, PARAPET_FALLBACK_T
from .fitting import _copy_mod, weighted_choice
from .facades import FacadeMixin
from .storefronts import GroundMixin
from .damage import DamageMixin
from .lines import LineMixin
from .extras import ExtrasMixin
from .areaways import AreawayMixin
from .rigid import RigidMixin


class FloorSpec:
    """What one floor is built from: chosen modules (or None = the kit mix), height and belt."""
    __slots__ = ("seg", "layout", "corner", "middle", "h", "belt", "door", "entrance")

    def __init__(self, h, seg=-1):
        self.seg = seg
        self.layout = "AUTO"
        self.corner = None
        self.middle = None
        self.h = h
        self.belt = False
        self.door = None
        self.entrance = True

    @property
    def explicit(self):
        return self.corner is not None or self.middle is not None

    def bay_mod(self, kind):
        """Module for a bay ("corner" or "middle"); None = pick from the kit."""
        if kind == "corner":
            return self.corner or self.middle
        return self.middle


class Plan(FacadeMixin, GroundMixin, LineMixin, ExtrasMixin, DamageMixin, AreawayMixin, RigidMixin):
    def __init__(self, obj, s, kit):
        self.obj = obj
        self.s = s
        self.kit = kit
        self.points = []   # (pos, index, yaw, scale)
        self.proc = Proc()
        self.warnings = []
        self.count = 0
        self.dmg = s.damage if s is not None else 0.0
        self.bays = {}     # side index -> (divider or None, [(start, width, native width cm, kind)]) or None
        self.ground_marks = {}    # side id -> [(start, width, is entrance)] of the ground floor
        self.areaway_depth = {}   # side index -> how far its areaway reaches out
        self.line_like = {}       # line layer -> chosen module its corner pieces should match
        self._bad_refs = set()
        self.rigid = bool(getattr(s, "rigid", False)) if s is not None else False
        self.snap_info = None     # rigid modules: how the footprint was snapped (see rigid.py)
        self.fill_strips = 0      # rigid modules: filler strips where whole modules don't fit
        self.line_stretch = 0     # rigid modules: line runs that had to stretch

    # ---- helpers
    def add(self, m, pos, yaw, sx=1.0, sy=1.0, sz=1.0, rel=None):
        if m is None or m.index < 0:
            return
        if self.dmg > 0 and self.kit is not None and self.kit.damaged:
            m = self.damaged_variant(m, pos)
        self.points.append((Vector(pos), m.index, yaw, (sx, sy, sz)))

    def pool(self, role, floor):
        k = self.kit
        if k is None:
            return []
        mods = [m for m in k.role(role) if m.index >= 0]
        want = [m for m in mods if m.floor in (floor, "any")]
        return want or mods

    def pick(self, rng, mods):
        if not mods:
            return None
        return weighted_choice(rng, mods, [m.weight for m in mods])

    def mod_for(self, col, roles=None):
        """The kit module behind a chosen collection, or None (with a warning when it can't be used)."""
        if col is None or self.kit is None:
            return None
        m = self.kit.by_name.get(col.name)
        if m is not None and m.index >= 0 and (roles is None or m.role in roles):
            return m
        if col.name not in self._bad_refs:
            self._bad_refs.add(col.name)
            self.warnings.append(f"'{col.name}' can't be used there: pick a module of this kit with a matching category")
        return None

    @staticmethod
    def chosen(m):
        """A chosen module as a fitting candidate: used even when its frequency is 0."""
        if m is None or m.weight > 0:
            return m
        c = _copy_mod(m)
        c.weight = 1.0
        return c

    def corner_mod(self, layer, kind, floor_h=None, turn=None, floor=None, sub=None, line_h=None, like=None):
        if self.kit is None:
            return None
        c = [m for m in self.kit.role("corner") if m.layer == layer and m.kind == kind]
        if turn is not None:
            c = [m for m in c if abs(m.turn - turn) < 3.0]
        if floor is not None:
            pref = [m for m in c if m.floor in (floor, "any")]
            if pref:
                c = pref
            elif floor == "upper":    # never put a ground-floor piece (door, shop) on upper floors
                c = [m for m in c if not (m.tokens & {"ground", "door", "entrance", "shop", "storefront"})]
        if sub is not None:
            pref = [m for m in c if m.sub == sub]
            if pref:
                c = pref              # Belt_Corner for the belt, Cornice_Corner for the roof cornice
        if not c:
            return None
        ref_h = line_h if line_h is not None else floor_h
        c.sort(key=lambda m: (m.floor != floor, -len(m.tokens & like.tokens) if like is not None else 0,
                              abs(m.h - ref_h) if ref_h is not None else 0.0, m.name))
        return c[0]

    def band(self, layer):
        """(outside, inside) faces of a layer in module Y (negative = outwards)."""
        b = getattr(self, "bands", {}).get(layer)
        if b:
            return b
        k = self.kit
        if layer in ("cornice", "belt"):
            return (k.cornice_lo, k.cornice_hi) if k else (-0.3, 0.0)
        if layer == "parapet":
            return (k.parapet_lo, k.parapet_hi) if k else (0.0, 0.25)
        return self.wall_lo, self.wall_hi

    def add_rounded(self, m, R, A, B, z, sz=1.0):
        """Place a quarter-round module so its arc lines up with a corner of radius R (pivot independent)."""
        V = B.p
        C = V - A.t * R + B.t * R
        e_w = -A.n                       # world direction from the arc centre to side A's end
        yaw = math.atan2(e_w.y, e_w.x) - math.atan2(m.re.y, m.re.x)
        k = R / m.radius if m.radius > 0.05 else 1.0
        if not 0.8 < k < 1.25:
            k = 1.0
        rot = Matrix.Rotation(yaw, 3, "Z")
        pos = C - rot @ (Vector((m.rc.x, m.rc.y, 0.0)) * k) + Vector((0, 0, z))
        self.add(m, pos, yaw, k, k, sz)

    # ---- main
    def run(self):
        s = self.s
        kit = self.kit
        loops, sides, warns = read_outline(self.obj)
        self.warnings += warns
        self.sides = sides
        self.loops = loops
        if not sides:
            self.warnings.append("Draw a closed outline (edges or a flat face) to make a building")
            return self
        n = s.floors
        gh = s.ground_height if s.ground_height > 0 else (kit.gh if kit else 4.0)
        uh = s.upper_height if s.upper_height > 0 else (kit.uh if kit else 3.2)
        self.floor_specs = self.resolve_specs(n, gh, uh)
        heights = [sp.h for sp in self.floor_specs]
        levels = [0.0]
        for h in heights:
            levels.append(levels[-1] + h)
        H = levels[-1]
        self.heights, self.levels, self.H = heights, levels, H
        self.wall_lo, self.wall_hi = (kit.wall_lo, kit.wall_hi) if kit else (0.0, 0.3)
        self.depth = self.wall_hi - self.wall_lo
        seed = s.seed
        default_style = GROUND_DEFAULT_STYLE[s.ground_default]
        no_shops = s.ground_mode == "GROUND"
        for sd in sides:
            sd_style = sd.style if sd.style != STYLE_AUTO else default_style
            if no_shops and sd_style == STYLE_SHOP:
                sd_style = STYLE_WINDOWS      # a ground floor without shops: Shop sides get the ground floor modules
            sd.style = sd_style

        # -------- the horizontal lines: belt cornices, crown cornice, roof edge (parapet)
        cors = kit.role("cornice") if kit else []
        parapet_mods = kit.role("parapet") if kit else []
        crown_x = self.chosen(self.mod_for(s.cornice_module, ("cornice",)))
        belt_x = self.chosen(self.mod_for(s.belt_module, ("cornice",)))
        roofc = [crown_x] if crown_x else ([m for m in cors if m.sub == "cornice"] or cors)
        # no belt cornice in the kit: the crown cornice stands in for it
        belts = [belt_x] if belt_x else ([m for m in cors if m.sub == "belt"] or roofc)
        cornice_on = s.cornice and bool(roofc)
        self.line_like = {"cornice": crown_x, "belt": belt_x or (crown_x if belts is roofc else None)}
        # rigid modules: the lines the snap tries to fit with whole pieces too
        self.line_sets = [(nm, mods) for nm, mods, on in (
            ("cornice", roofc, cornice_on),
            ("parapet", parapet_mods, s.parapet),
            ("belt", belts, n > 1 and (s.belt or any(g.belt_below for g in s.segments))),
        ) if on and mods]

        def med(vals):
            vals = sorted(vals)
            return vals[len(vals) // 2]
        self.line_h = {}
        self.bands = {}
        for nm, mods in (("belt", belts), ("cornice", roofc), ("parapet", parapet_mods)):
            if mods:
                self.line_h[nm] = max(m.h for m in mods)
                self.bands[nm] = (med([m.lo.y for m in mods]), med([m.hi.y for m in mods]))

        # -------- corners (rigid modules: snap the footprint to whole modules, then corners again)
        self.corner_cache = {}
        for i, sd in enumerate(sides):
            self.corner_cache[i] = self.resolve_corner(sides[sd.prev], sd, s.round_all, s.corner_radius)
        if self.rigid and self.snap_outline(seed):
            for i, sd in enumerate(sides):
                self.corner_cache[i] = self.resolve_corner(sides[sd.prev], sd, s.round_all, s.corner_radius)

        # -------- façades
        for i, sd in enumerate(sides):
            if sd.style == STYLE_OPEN:
                continue
            for f in range(n):
                layer = "G" if f == 0 else "U"
                start = self.corner_cache[i][layer]["start_B"]
                end = self.corner_cache[sd.next][layer]["end_A"]
                L = sd.length - start - end
                if L <= 0.02:
                    continue
                self.place_facade_span(i, sd, f, start, L, heights[f], levels[f], seed)

        # -------- corner pieces / posts
        for i, sd in enumerate(sides):
            a = sides[sd.prev]
            if sd.style == STYLE_OPEN or a.style == STYLE_OPEN:
                continue
            info = self.corner_cache[i]
            for f in range(n):
                layer = "G" if f == 0 else "U"
                self.emit_corner(info[layer], sd, a, levels[f], heights[f])
            if s.quoins and kit and kit.role("corner_trim") and info["sharp_convex90"]:
                rng = _rng(seed, i, "quoin")
                q = self.pick(rng, self.pool("corner_trim", "upper"))
                if q is not None:
                    for f in range(n):
                        if f == 0 and (sd.style == STYLE_SHOP or a.style == STYLE_SHOP):
                            continue
                        self.add(q, sd.p + Vector((0, 0, levels[f])), sd.yaw, 1, 1, heights[f] / q.h)

        # -------- belt cornices (above the ground floor and under segments that ask for one) and crown cornice
        belt_floors = {f for f in range(1, n) if self.floor_specs[f].belt}
        if s.belt and n > 1:
            belt_floors.add(1)
        if belts:
            for f in sorted(belt_floors):
                self.place_line(belts, "belt", levels[f] - BELT_DROP, seed, "belt" if f == 1 else f"belt{f}")
        cornice_top = H
        if cornice_on:
            self.place_line(roofc, "cornice", H - 0.02, seed, "cornice")
            cornice_top = H - 0.02 + max(m.hi.z for m in roofc) - 0.02
        roof_top = H + 0.02
        self.roof_top = roof_top

        # -------- parapet
        if s.parapet:
            if parapet_mods:
                self.place_line(parapet_mods, "parapet", cornice_top if cornice_on else H, seed, "parapet")
            else:
                base = cornice_top if cornice_on else H
                for loop in self.shape_loops(self.wall_lo):
                    inner = offset_loop(loop, PARAPET_FALLBACK_T)
                    self.proc.ring(loop, inner, base - 0.02, base + PARAPET_FALLBACK_H, MAT_PARAPET)

        # -------- roof slab and floors (the roof covers the full wall thickness)
        roof_loops = self.shape_loops(self.wall_lo + 0.03)
        t = kit.roof_t if kit else 0.2
        self.proc.prism(roof_loops, roof_top - t, roof_top, MAT_ROOF)
        if s.interior_floors:
            fl = self.shape_loops(self.wall_hi + 0.02)
            for z in levels[:-1]:
                self.proc.prism(fl, z - FLOOR_SLAB_T, z, MAT_FLOOR)

        # -------- areaways, fire escapes, pipes, roof props
        self.place_areaways(seed)
        self.place_fire_escapes(seed)
        self.place_pipes(seed)
        self.place_roof_props(seed, parapet_mods)
        self.place_rubble(seed)
        if self.fill_strips:
            self.warnings.append(f"Rigid modules: {self.fill_strips} plain filler strip(s) where whole modules don't fit")
        if self.line_stretch:
            self.warnings.append(f"Rigid modules: cornice / parapet stretched to fit on {self.line_stretch} run(s)")
        return self

    # ---- floor stack
    def resolve_specs(self, n, gh, uh):
        """One FloorSpec per floor: the ground floor, then the upper floors from the segment list."""
        s = self.s
        g = FloorSpec(gh)
        if s.ground_mode == "GROUND":
            g.layout = s.ground_layout
            if g.layout != "AUTO":
                g.middle = self.mod_for(s.ground_module, ("window", "wall", "storefront", "door"))
            if g.layout == "CORNER":
                g.corner = self.mod_for(s.ground_corner_module, ("window", "wall", "storefront", "door"))
            g.entrance = s.ground_entrance
            g.door = self.mod_for(s.ground_door, ("door", "storefront")) if s.ground_entrance else None
        specs = [g]
        segs = list(s.segments)
        order = []                    # (segment index, first floor of this run of the segment)
        for k, sg in enumerate(segs):
            order += [(k, j == 0) for j in range(max(1, sg.floors))]
        for f in range(1, n):
            k = f - 1
            if not order:
                specs.append(FloorSpec(uh))
                continue
            if k < len(order):
                idx, first = order[k]
            elif s.segment_repeat:
                idx, first = order[k % len(order)]
            else:
                idx, first = order[-1][0], False
            sg = segs[idx]
            sp = FloorSpec(sg.height if sg.height > 0 else uh, idx)
            sp.layout = sg.layout
            if sg.layout != "AUTO":
                sp.middle = self.mod_for(sg.module, ("window", "wall"))
            if sg.layout == "CORNER":
                sp.corner = self.mod_for(sg.corner_module, ("window", "wall"))
            sp.belt = first and sg.belt_below
            specs.append(sp)
        return specs[:max(n, 1)]

    # ---- corners
    def resolve_corner(self, A, B, round_all, R_user):
        turn = B.turn
        convex = turn > 1.0
        reflex = turn < -1.0
        layers = ("G", "U", "belt", "cornice", "parapet")
        # which kit corner pieces each layer uses: (kit layer, line sub-type)
        LINE = {"belt": ("cornice", "belt"), "cornice": ("cornice", "cornice"), "parapet": ("parapet", None)}
        info = {"sharp_convex90": False, "rounded": None}

        def blank():
            return {"end_A": 0.0, "start_B": 0.0, "piece": None, "post": None, "arc": None}

        if A.style == STYLE_OPEN or B.style == STYLE_OPEN:
            # party wall: the neighbouring building closes this end, so no trims or corner pieces
            for layer in layers:
                info[layer] = blank()
            return info
        gh = self.heights[0]
        uh = self.heights[1] if len(self.heights) > 1 else gh
        lh = getattr(self, "line_h", {})

        def line_piece(layer, kind, turn_=None):
            klayer, sub = LINE[layer]
            return self.corner_mod(klayer, kind, turn=turn_, sub=sub, line_h=lh.get(layer),
                                   like=getattr(self, "line_like", {}).get(layer))

        # ---- rounded corner: one radius for every layer, kit pieces where the kit has them
        if convex and abs(turn - 90) < 5 and (B.rounded or round_all):
            pieces = {"G": self.corner_mod("facade", "rounded", gh, floor="ground"),
                      "U": self.corner_mod("facade", "rounded", uh, floor="upper"),
                      "belt": line_piece("belt", "rounded"),
                      "cornice": line_piece("cornice", "rounded"),
                      "parapet": line_piece("parapet", "rounded")}
            src = pieces["G"] or pieces["U"] or pieces["cornice"] or pieces["belt"] or pieces["parapet"]
            R = src.radius if src else R_user
            R = max(min(R, 0.49 * min(A.length, B.length)), 0.05)   # never wider than the shorter side allows
            info["rounded"] = R
            for layer in layers:
                d = blank()
                d["end_A"] = d["start_B"] = R
                pc = pieces[layer]
                if pc is not None and pc.radius > 0.05 and not 0.8 < R / pc.radius < 1.25:
                    pc = None   # the kit piece can't be resized to this radius: draw the arc instead
                if pc is not None:
                    d["piece"] = ("rounded", pc)
                else:
                    d["arc"] = R
                info[layer] = d
            return info

        right_angle = abs(abs(turn) - 90) < 3
        for layer in layers:
            d = blank()
            fh, fl = {"G": (gh, "ground"), "U": (uh, "upper")}.get(layer, (None, None))
            pc = None
            if self.s.corner_pieces and (convex or reflex):
                if layer in ("G", "U"):
                    pc = self.corner_mod("facade", "join", fh, turn, floor=fl) or \
                        (self.corner_mod("facade", "pier", fh, 90.0 if convex else -90.0, floor=fl) if right_angle else None)
                else:
                    pc = line_piece(layer, "join", turn) or \
                        (line_piece(layer, "pier", 90.0 if convex else -90.0) if right_angle else None)
                    if pc is None and convex and right_angle and layer != "parapet":
                        pc = line_piece(layer, "cap")
            under = info.get("U") if layer == "parapet" else None
            if pc is not None and pc.kind in ("join", "pier"):
                d["end_A"], d["start_B"] = pc.trim_in, pc.trim_out
                d["piece"] = (pc.kind, pc)
            elif pc is not None:
                d["piece"] = (pc.kind, pc)
            elif under is not None and under["piece"]:
                # no roof-edge corner piece: the roof edge stops where the wall corner piece below starts
                d["end_A"], d["start_B"] = under["end_A"], under["start_B"]
                if convex:
                    d["block"] = True
            elif convex:
                lo_y, hi_y = self.band(layer)
                k = math.tan(math.radians(min(turn, 170.0)) / 2)
                if lo_y < -1e-3:
                    d["start_B"] = max(lo_y * k, lo_y * 4)    # start before the corner: closes the outside notch
                else:
                    d["start_B"] = min(hi_y * k, hi_y * 4)
                if abs(turn - 90) > 3:
                    d["post"] = True
                if layer == "U" and abs(turn - 90) < 5:
                    info["sharp_convex90"] = True
            info[layer] = d
        return info

    def emit_corner(self, d, B, A, z, h, layer_h=None, band=None, mat=MAT_WALL):
        V = B.p
        piece = d["piece"]
        hh = layer_h if layer_h else h
        if piece:
            kind, m = piece
            sz = hh / m.h if m.h > 0.05 and layer_h is None else 1.0
            if kind == "rounded":
                self.add_rounded(m, d["end_A"], A, B, z, sz)
            else:
                self.add(m, V + Vector((0, 0, z)), B.yaw, 1, 1, sz)
            return
        lo_y, hi_y = band if band else (self.wall_lo, self.wall_hi)
        if d["arc"]:
            R = d["arc"]
            C = V - A.t * R + B.t * R
            outer, inner = self.arc_points(C, A, B, R - lo_y, R - hi_y)
            self.proc.prism([outer + inner[::-1]], z, z + hh, mat)
        elif d["post"]:
            s_len = d["start_B"]
            mit = (A.n + B.n) / max(1.0 + A.n.dot(B.n), 0.2)
            pts = [V + A.n * lo_y, V + A.n * hi_y,
                   V + B.t * s_len + B.n * lo_y, V + B.t * s_len + B.n * hi_y,
                   V + mit * lo_y, V + mit * hi_y]
            hull = _hull2d(pts)
            if len(hull) >= 3:
                self.proc.prism([hull], z, z + hh, mat)

    def arc_points(self, C, A, B, r_out, r_in, segs=8):
        a0 = math.atan2(-B.t.y, -B.t.x)
        a1 = math.atan2(A.t.y, A.t.x)
        da = math.atan2(math.sin(a1 - a0), math.cos(a1 - a0))
        outer, inner = [], []
        for k in range(segs + 1):
            ang = a0 + da * k / segs
            dvec = Vector((math.cos(ang), math.sin(ang), 0))
            outer.append(C + dvec * max(r_out, 0.02))
            inner.append(C + dvec * max(r_in, 0.02))
        return outer, inner

    def shape_loops(self, inset):
        """Outline loops with rounded corners expanded, inset to the interior (negative = outwards)."""
        out = []
        for idx in self.loops:
            pts = []
            for i in idx:
                sd = self.sides[i]
                a = self.sides[sd.prev]
                R = self.corner_cache[i]["rounded"]
                if R:
                    C = sd.p - a.t * R + sd.t * R
                    outer, _ = self.arc_points(C, a, sd, R, R)
                    pts.extend(outer)
                else:
                    pts.append(sd.p.copy())
            clean = []
            for p in pts:
                if not clean or (p - clean[-1]).length > 1e-4:
                    clean.append(p)
            if len(clean) > 2 and (clean[0] - clean[-1]).length < 1e-4:
                clean.pop()
            if len(clean) >= 3:
                out.append(offset_loop(clean, inset) if inset else clean)
        return out
