"""Rigid modules: every facade module keeps its own width, and the footprint snaps to whole modules.

Each side works out its step: the lengths its floors fill exactly with whole modules, as
"span = c + k * g" (in centimetres). The lines of the outline (the sides running across it) then snap
to a grid in object space, so that every side between them gets a span of that form. Each line snaps
on its own, from its own position only: dragging one edge never moves the others, and the same outline
always gives the same building.
"""

import math
from mathutils import Vector

from .common import STYLE_BACK, STYLE_BLANK, STYLE_OPEN, STYLE_SHOP, STYLE_WINDOWS
from .geometry import left_normal
from .fitting import width_cm
from .tuning import SNAP_MAX_STEP, SNAP_MIN_SIDE

AXIS_TOL = math.sin(math.radians(0.5))   # a side within this of the snap frame's axes snaps


def _gcd(vals):
    g = 0
    for v in vals:
        g = math.gcd(g, int(v))
    return g


def _combine(a, b):
    """Two steps (g, c) as one that satisfies both, or None (Chinese remainder theorem)."""
    (g1, c1), (g2, c2) = a, b
    g = g1 * g2 // math.gcd(g1, g2)
    if g > SNAP_MAX_STEP:
        return None
    for k in range(g // g1):
        c = c1 + k * g1
        if (c - c2) % g2 == 0:
            return g, c % g
    return None


class RigidMixin:
    """Footprint snapping for rigid modules, part of a Plan."""

    # ---- steps
    def floor_step(self, sd, f, seed):
        """(g, c) in cm: this floor's span fills exactly with whole modules when span = c + k * g. None: no modules."""
        s = self.s
        spec = self.floor_specs[f]
        if len(self.heights) > 1 and sd.style not in (STYLE_BLANK, STYLE_OPEN):
            divs = self.divider_mods("upper") if s.pilasters else []
            ref = self.reference_spec()
            wins = [m for m in self.pool("window", "upper") if m.weight > 0 and m.w > 0.05]
            bays = ref is not None or bool(divs and wins)
            if f == 0 and bays and (self.ground_modules(sd) or (divs and s.pilaster_ground)):
                return None      # the ground floor follows the bays above: no step of its own
        if f > 0 and len(self.heights) > 1 and sd.style not in (STYLE_BLANK, STYLE_OPEN):
            if spec.explicit or ref is not None:
                sp = spec if spec.explicit else ref
                div, _ = self.bay_divider(sd, seed, divs)
                p = width_cm(div) if div is not None else 0
                wm = width_cm(sp.middle) if sp.middle is not None else int(round(self.typical_window_w() * 100))
                wc = width_cm(sp.bay_mod("corner")) if sp.bay_mod("corner") is not None else wm
                g = wm + p
                return (g, (2 * wc + p) % g) if g > 0 else None
            if divs:
                if wins:
                    div, _ = self.bay_divider(sd, seed, divs)
                    p = width_cm(div)
                    g = _gcd(width_cm(m) + p for m in wins)
                    return (g, (-p) % g) if g > 0 else None
        pool, door, _ = self.span_pool(sd, f, seed)
        widths = [width_cm(m) for m in pool if m.weight > 0 and m.w > 0.05]
        g = _gcd(widths)
        if g <= 0:
            return None
        return g, (width_cm(door) % g) if door is not None else 0

    def side_step(self, i, sd, seed):
        """(layer, g, c): the step of a side's span on its main layer (the upper floors, or the only floor).
        The ground floor and the cornice / parapet / belt lines join in when they don't make the step any coarser;
        otherwise the ground floor fits with wall pieces or filler strips, and the lines stretch."""
        n = len(self.heights)
        cs, ce = self.corner_cache[i], self.corner_cache[sd.next]

        def shifted(st, layer, main):
            # a layer's run differs from the main span by the difference of their corner trims
            delta = int(round((cs[main]["start_B"] + ce[main]["end_A"] - cs[layer]["start_B"] - ce[layer]["end_A"]) * 100))
            return st[0], (st[1] - delta) % st[0]

        def lines(main, step):
            for layer, mods in getattr(self, "line_sets", ()):
                g = _gcd(width_cm(m) for m in mods if m.weight > 0 and m.w > 0.05)
                if g <= 0:
                    continue
                both = _combine(step, shifted((g, 0), layer, main))
                if both is not None and both[0] <= step[0]:
                    step = both
            return step
        if n == 1:
            st = self.floor_step(sd, 0, seed)
            return ("G",) + lines("G", st) if st else None
        step = None
        for f in range(1, n):
            st = self.floor_step(sd, f, seed)
            if st is None:
                continue
            if step is None:
                step = st
            else:
                both = _combine(step, st)
                if both is not None:     # floors that can't share a step get filler strips instead
                    step = both
        if step is None:
            return None
        gst = self.floor_step(sd, 0, seed)
        if gst is not None:
            both = _combine(step, shifted(gst, "G", "U"))
            if both is not None and both[0] <= step[0]:   # the ground floor never makes the step coarser
                step = both
        return ("U",) + lines("U", step)

    # ---- snapping
    def snap_outline(self, seed):
        """Move the outline lines onto the module grid. Returns True when the footprint changed."""
        sides = self.sides
        self.snap_info = None
        if not sides:
            return False
        longest = max(sides, key=lambda x: x.length)
        ang = math.atan2(longest.t.y, longest.t.x) % (math.pi / 2)
        if ang > math.pi / 4:
            ang -= math.pi / 2
        if abs(ang) < 1e-5:
            ang = 0.0
        ca, sa = math.cos(ang), math.sin(ang)

        def to_f(p):
            return [ca * p.x + sa * p.y, -sa * p.x + ca * p.y]

        pts = [to_f(sd.p) for sd in sides]          # point k = start of side k
        axis = {}
        for k, sd in enumerate(sides):
            tu, tv = to_f(sd.t)
            if abs(tv) < AXIS_TOL:
                axis[k] = 0      # runs along u: its ends share v, its length is set by u lines
            elif abs(tu) < AXIS_TOL:
                axis[k] = 1

        # lines: points joined by sides running across them share one coordinate
        groups = []
        for ax in (0, 1):
            parent = list(range(len(sides)))

            def find(a):
                while parent[a] != a:
                    parent[a] = parent[parent[a]]
                    a = parent[a]
                return a
            for k, sd in enumerate(sides):
                if axis.get(k) == 1 - ax:
                    parent[find(k)] = find(sd.next)
            members = {}
            for k in range(len(sides)):
                members.setdefault(find(k), []).append(k)
            groups.append(members)

        # each side needs the distance between its two lines to come out as d + k * g. The lines get grid
        # offsets that satisfy these (most important sides first), worked out from the sides alone, never
        # from where the lines are, so every line can then snap on its own.
        order = {STYLE_SHOP: 0, STYLE_WINDOWS: 1, STYLE_BACK: 2, STYLE_BLANK: 3}
        edges = [[], []]
        for k, sd in enumerate(sides):
            ax = axis.get(k)
            if ax is None or sd.style == STYLE_OPEN:
                continue
            st = self.side_step(k, sd, seed)
            if st is None:
                continue
            layer, g, c = st
            t_start = self.corner_cache[k][layer]["start_B"]
            t_end = self.corner_cache[sd.next][layer]["end_A"]
            forward = to_f(sd.t)[ax] > 0
            lo, hi = (k, sd.next) if forward else (sd.next, k)
            edges[ax].append((order.get(sd.style, 4), k, lo, hi, g, c / 100.0 + t_start + t_end))

        new = [list(p) for p in pts]
        lattice = {}
        for ax in (0, 1):
            root_of = {k: r for r, mem in groups[ax].items() for k in mem}
            step = {}
            for _, _, lo, hi, g, _ in edges[ax]:
                for ln in (root_of[lo], root_of[hi]):
                    a = step.get(ln, g)
                    both = a * g // math.gcd(a, g)
                    step[ln] = both if both <= SNAP_MAX_STEP else max(a, g)
            # weighted union-find: off[x] = offset of line x from its parent
            parent = {ln: ln for ln in step}
            off = {ln: 0.0 for ln in step}

            def find(x):
                o = 0.0
                while parent[x] != x:
                    o += off[x]
                    x = parent[x]
                return x, o
            for _, _, lo, hi, g, d in sorted(edges[ax]):
                (ra, oa), (rb, ob) = find(root_of[lo]), find(root_of[hi])
                if ra != rb:            # place hi's lines so that hi - lo = d
                    parent[rb] = ra
                    off[rb] = oa + d - ob
            for ln in step:
                _, o = find(ln)
                lattice[(ax, ln)] = (o, step[ln] / 100.0)
            for ln, mem in groups[ax].items():
                if (ax, ln) not in lattice:
                    continue
                phase, G = lattice[(ax, ln)]
                x0 = sum(pts[k][ax] for k in mem) / len(mem)
                x = phase + round((x0 - phase) / G) * G
                for k in mem:
                    new[k][ax] = x

        # never collapse or flip a side: push the far line out to its next grid position
        for _ in range(12):
            bad = False
            for k, sd in enumerate(sides):
                ax = axis.get(k)
                if ax is None:
                    continue
                d0 = pts[sd.next][ax] - pts[k][ax]
                d1 = new[sd.next][ax] - new[k][ax]
                if abs(d0) >= SNAP_MIN_SIDE and (d1 * d0 <= 0 or abs(d1) < SNAP_MIN_SIDE):
                    bad = True
                    root = next(r for r, mem in groups[ax].items() if sd.next in mem)
                    if (ax, root) not in lattice:
                        self.warnings.append("Rigid modules: the outline is too small to snap to whole modules")
                        return False
                    _, G = lattice[(ax, root)]
                    x = new[sd.next][ax]
                    while (x - new[k][ax]) * d0 < SNAP_MIN_SIDE:
                        x += G if d0 > 0 else -G
                    for m in groups[ax][root]:
                        new[m][ax] = x
            if not bad:
                break
        else:
            self.warnings.append("Rigid modules: the outline is too small to snap to whole modules")
            return False

        def from_f(u, v):
            return Vector((ca * u - sa * v, sa * u + ca * v, 0.0))

        moved = max(math.hypot(new[k][0] - pts[k][0], new[k][1] - pts[k][1]) for k in range(len(sides)))
        maps = ({}, {})
        for k in range(len(sides)):
            for ax in (0, 1):
                maps[ax][round(pts[k][ax], 4)] = new[k][ax]
        self.snap_info = {"angle": ang, "maps": maps, "moved": moved,
                          "lengths": {}}
        if moved < 1e-6:
            for sd in sides:
                self.snap_info["lengths"][sd.id] = sd.length
            return False
        drawn = {sd.id: sd.length for sd in sides}
        for k, sd in enumerate(sides):
            sd.p = from_f(*new[k])
        for sd in sides:
            sd.q = sides[sd.next].p.copy()
            d = sd.q - sd.p
            sd.length = d.length
            if sd.length > 1e-6:
                sd.t = d / sd.length
                sd.n = left_normal(sd.t)
                sd.yaw = math.atan2(sd.t.y, sd.t.x)
        for sd in sides:
            a = sides[sd.prev]
            sd.turn = math.degrees(math.atan2(math.sin(sd.yaw - a.yaw), math.cos(sd.yaw - a.yaw)))
            self.snap_info["lengths"][sd.id] = sd.length
        self.snap_info["drawn"] = drawn
        return True
