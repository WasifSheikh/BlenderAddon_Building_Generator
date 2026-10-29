"""2D helpers and the procedural mesh builder (roof, slabs, fillers, corner posts)."""

import numpy as np
from mathutils import Vector
from mathutils.geometry import tessellate_polygon


def _hull2d(pts):
    P = sorted({(round(p.x, 6), round(p.y, 6)) for p in pts})
    if len(P) < 3:
        return []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in P:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(P):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return [Vector((x, y, 0.0)) for x, y in lower[:-1] + upper[:-1]]


def _round_frame(xy, lo, hi):
    """Find the arc of a quarter-round corner module from its geometry, wherever its pivot is.
    Returns (centre, end_dir_A, inner_radius) in module space, or None."""
    if xy is None or len(xy) < 8:
        return None
    w, d = hi.x - lo.x, hi.y - lo.y
    if w < 0.2 or d < 0.2:
        return None
    best = None
    for cx, sx in ((lo.x, 1.0), (hi.x, -1.0)):
        for cy, sy in ((lo.y, 1.0), (hi.y, -1.0)):
            m = float(np.sqrt(((xy - np.array([cx, cy])) ** 2).sum(axis=1)).min())
            if best is None or m > best[0]:
                best = (m, cx, cy, sx, sy)
    r_in, cx, cy, sx, sy = best
    if r_in < 0.15 * min(w, d):
        return None
    u = Vector((sx, 0.0, 0.0))
    v = Vector((0.0, sy, 0.0))
    e_a = u if sx == sy else v      # side A's end: turning it +90 degrees gives side B's end
    return Vector((cx, cy, 0.0)), e_a, r_in


def v2(p):
    return Vector((p.x, p.y, 0.0))


def signed_area(pts):
    a = 0.0
    n = len(pts)
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        a += p.x * q.y - q.x * p.y
    return a / 2.0


def point_in_loop(pt, loop):
    inside = False
    n = len(loop)
    for i in range(n):
        a, b = loop[i], loop[(i + 1) % n]
        if (a.y > pt.y) != (b.y > pt.y):
            x = (b.x - a.x) * (pt.y - a.y) / (b.y - a.y + 1e-30) + a.x
            if pt.x < x:
                inside = not inside
    return inside


def point_in_shape(pt, loops):
    return sum(point_in_loop(pt, l) for l in loops) % 2 == 1


def dist_to_segment(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-12)))
    return (a + ab * t - p).length


def left_normal(t):
    return Vector((-t.y, t.x, 0.0))


def offset_loop(loop, dist):
    """Offset to the left (interior) by dist using mitres (capped)."""
    n = len(loop)
    out = []
    for i in range(n):
        a, p, b = loop[i - 1], loop[i], loop[(i + 1) % n]
        t1 = (p - a)
        t2 = (b - p)
        if t1.length < 1e-9 or t2.length < 1e-9:
            out.append(p.copy())
            continue
        n1 = left_normal(t1.normalized())
        n2 = left_normal(t2.normalized())
        den = 1.0 + n1.dot(n2)
        if den < 0.15:
            mvec = (n1 + n2).normalized() * 2.5 if (n1 + n2).length > 1e-6 else n1
        else:
            mvec = (n1 + n2) / den
        out.append(p + mvec * dist)
    return out


MAT_WALL, MAT_ROOF, MAT_FLOOR = range(3)
MAT_SHUTTER, MAT_BOARD = 3, 4


MAT_PARAPET = MAT_WALL  # parapets use the wall material (no duplicate material slot)


class Proc:
    def __init__(self):
        self.v = []
        self.f = []
        self.m = []

    def poly(self, pts, mat):
        if len(pts) < 3:
            return
        i = len(self.v)
        self.v.extend(Vector(p) for p in pts)
        self.f.append(tuple(range(i, i + len(pts))))
        self.m.append(mat)

    def prism(self, loops, z0, z1, mat, caps=True, top=True, bottom=True):
        loops = [l for l in loops if len(l) >= 3]
        if not loops or z1 - z0 < 1e-5:
            return
        if caps:
            flat = [p for l in loops for p in l]
            try:
                tris = tessellate_polygon([[Vector((p.x, p.y, 0.0)) for p in l] for l in loops])
            except Exception:
                tris = []
            for tri in tris:
                a, b, c = (flat[i] for i in tri)
                if (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x) < 0:
                    a, b = b, a
                if top:
                    self.poly([Vector((a.x, a.y, z1)), Vector((b.x, b.y, z1)), Vector((c.x, c.y, z1))], mat)
                if bottom:
                    self.poly([Vector((a.x, a.y, z0)), Vector((c.x, c.y, z0)), Vector((b.x, b.y, z0))], mat)
        for l in loops:
            n = len(l)
            for i in range(n):
                a, b = l[i], l[(i + 1) % n]
                if (b - a).length < 1e-6:
                    continue
                self.poly([Vector((a.x, a.y, z0)), Vector((b.x, b.y, z0)), Vector((b.x, b.y, z1)), Vector((a.x, a.y, z1))], mat)

    def ring(self, outer, inner, z0, z1, mat):
        """Closed band between two loops with the same vertex count (outer CCW, inner = inset)."""
        n = len(outer)
        for i in range(n):
            j = (i + 1) % n
            o0, o1, i0, i1 = outer[i], outer[j], inner[i], inner[j]
            self.poly([Vector((o0.x, o0.y, z1)), Vector((o1.x, o1.y, z1)), Vector((i1.x, i1.y, z1)), Vector((i0.x, i0.y, z1))], mat)
            self.poly([Vector((o0.x, o0.y, z0)), Vector((o1.x, o1.y, z0)), Vector((o1.x, o1.y, z1)), Vector((o0.x, o0.y, z1))], mat)
            self.poly([Vector((i1.x, i1.y, z0)), Vector((i0.x, i0.y, z0)), Vector((i0.x, i0.y, z1)), Vector((i1.x, i1.y, z1))], mat)

    def obox(self, c, ax, ay, az, hx, hy, hz, mat):
        """Oriented box: centre, three right-handed unit axes and half sizes."""
        X, Y, Z = ax * hx, ay * hy, az * hz
        p = [c - X - Y - Z, c + X - Y - Z, c + X + Y - Z, c - X + Y - Z,
             c - X - Y + Z, c + X - Y + Z, c + X + Y + Z, c - X + Y + Z]
        for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            self.poly([p[i] for i in f], mat)

    def uvs(self):
        out = []
        for face in self.f:
            pts = [self.v[i] for i in face]
            nrm = (pts[1] - pts[0]).cross(pts[2] - pts[0])
            if nrm.length > 1e-12:
                nrm.normalize()
            if abs(nrm.z) > 0.7:
                out.extend((p.x, p.y) for p in pts)
            else:
                tg = Vector((-nrm.y, nrm.x, 0.0))
                if tg.length < 1e-9:
                    tg = Vector((1, 0, 0))
                tg.normalize()
                out.extend((p.dot(tg), p.z) for p in pts)
        return out
