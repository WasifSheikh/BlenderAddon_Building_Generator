"""Reads a building's footprint mesh into closed loops of sides."""

import bmesh
import math
import numpy as np
from mathutils import Vector

from .geometry import left_normal, point_in_loop, signed_area


class Side:
    __slots__ = ("loop", "p", "q", "t", "n", "length", "yaw", "style", "fire", "id", "vstart", "turn", "rounded", "prev", "next")


def read_outline(obj):
    """Return (loops, sides, warnings). loops: list of lists of side indices; points are local XY."""
    warnings = []
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        co = [v.co.copy() for v in bm.verts]
        edges = [(e.verts[0].index, e.verts[1].index) for e in bm.edges]
        nface = [len(e.link_faces) for e in bm.edges]
        ls = bm.edges.layers.int.get("aa_style")
        lf = bm.edges.layers.int.get("aa_fire")
        lr = bm.verts.layers.int.get("aa_round")
        styles = [e[ls] if ls else 0 for e in bm.edges]
        fires = [e[lf] if lf else 0 for e in bm.edges]
        rounds = [v[lr] if lr else 0 for v in bm.verts]
        has_faces = len(bm.faces) > 0
    else:
        me = obj.data
        nv, ne = len(me.vertices), len(me.edges)
        c = np.empty(nv * 3)
        me.vertices.foreach_get("co", c)
        co = [Vector(c[i * 3:i * 3 + 3]) for i in range(nv)]
        ev = np.empty(ne * 2, dtype=np.int32)
        me.edges.foreach_get("vertices", ev)
        edges = [(int(ev[i * 2]), int(ev[i * 2 + 1])) for i in range(ne)]
        nl = len(me.loops)
        if nl:
            le = np.empty(nl, dtype=np.int32)
            me.loops.foreach_get("edge_index", le)
            nface = np.bincount(le, minlength=ne).tolist()
        else:
            nface = [0] * ne
        has_faces = len(me.polygons) > 0

        def attr(name, domain, n):
            a = me.attributes.get(name)
            if a is None or a.domain != domain or a.data_type != "INT":
                return [0] * n
            vals = np.zeros(n, dtype=np.int32)
            a.data.foreach_get("value", vals)
            return vals.tolist()
        styles = attr("aa_style", "EDGE", ne)
        fires = attr("aa_fire", "EDGE", ne)
        rounds = attr("aa_round", "POINT", nv)

    # points lying on top of each other (a cancelled extrude, a doubled vertex) count as one point
    rep = []
    first_at = {}
    for i, p in enumerate(co):
        rep.append(first_at.setdefault((round(p.x * 10000.0), round(p.y * 10000.0)), i))
    rounds = list(rounds)
    for i, r in enumerate(rep):
        if r != i and rounds[i]:
            rounds[r] = 1

    use = [i for i in range(len(edges)) if (nface[i] == 1 if has_faces else True) or (has_faces and nface[i] == 0)]
    adj = {}
    pairs = set()
    for i in use:
        a, b = rep[edges[i][0]], rep[edges[i][1]]
        if a == b:
            continue
        key = (min(a, b), max(a, b))
        if key in pairs:
            continue
        pairs.add(key)
        adj.setdefault(a, []).append((b, i))
        adj.setdefault(b, []).append((a, i))
    # prune dangling edges (stray lines sticking out of the outline)
    pruned = 0
    leaves = [v for v, nb in adj.items() if len(nb) == 1]
    while leaves:
        v = leaves.pop()
        if v not in adj or len(adj[v]) != 1:
            continue
        other, e = adj.pop(v)[0]
        pruned += 1
        adj[other] = [(x, ee) for x, ee in adj[other] if ee != e]
        if len(adj[other]) == 1:
            leaves.append(other)
        elif not adj[other]:
            adj.pop(other)
    if pruned:
        warnings.append(f"Ignored {pruned} loose edge(s) in the outline")
    bad = [v for v, nb in adj.items() if len(nb) != 2]
    if bad:
        warnings.append(f"Outline has {len(bad)} branching point(s); those loops are skipped")
    good = {v for v, nb in adj.items() if len(nb) == 2}
    seen = set()
    raw_loops = []
    for start in sorted(good):
        if start in seen:
            continue
        loop_v = []
        loop_e = []
        prev = None
        cur = start
        ok = True
        while True:
            if cur not in good:
                ok = False
                break
            loop_v.append(cur)
            seen.add(cur)
            nxt = [(v, e) for v, e in adj[cur] if e != prev]
            if not nxt:
                ok = False
                break
            v, e = nxt[0]
            loop_e.append(e)
            prev = e
            cur = v
            if cur == start:
                break
            if cur in seen:
                ok = False
                break
        if ok and len(loop_v) >= 3:
            raw_loops.append((loop_v, loop_e))
    # orientation: outer loops CCW, holes CW (building interior always on the left)
    pts_loops = [[co[i].xy.to_3d() for i in lv] for lv, _ in raw_loops]
    for p in pts_loops:
        for v in p:
            v.z = 0.0
    oriented = []
    for k, (lv, le) in enumerate(raw_loops):
        pts = pts_loops[k]
        if abs(signed_area(pts)) < 1e-4:
            continue
        depth = sum(point_in_loop(pts[0], other) for j, other in enumerate(pts_loops) if j != k)
        want_ccw = depth % 2 == 0
        if (signed_area(pts) > 0) != want_ccw:
            lv = [lv[0]] + lv[1:][::-1]
            le = le[::-1]
            pts = [co[i].xy.to_3d() for i in lv]
            for v in pts:
                v.z = 0.0
        oriented.append((lv, le, pts))

    sides = []
    loops = []
    for li, (lv, le, pts) in enumerate(oriented):
        n = len(pts)
        raw = []
        for i in range(n):
            s = Side()
            s.loop = li
            s.p = pts[i]
            s.q = pts[(i + 1) % n]
            d = s.q - s.p
            s.length = d.length
            if s.length < 1e-6:
                continue
            s.t = d / s.length
            s.n = left_normal(s.t)
            s.yaw = math.atan2(s.t.y, s.t.x)
            e = le[i]
            s.style = int(styles[e]) if 0 <= int(styles[e]) <= 5 else 0
            s.fire = 1 if fires[e] else 0
            s.id = e
            s.vstart = lv[i]
            s.rounded = 1 if rounds[lv[i]] else 0
            raw.append(s)
        # merge straight runs with identical style
        merged = []
        for s in raw:
            if merged:
                last = merged[-1]
                ang = abs(math.degrees(math.atan2(math.sin(s.yaw - last.yaw), math.cos(s.yaw - last.yaw))))
                if ang < 0.5 and s.style == last.style and s.fire == last.fire and not s.rounded:
                    last.q = s.q
                    last.length = (last.q - last.p).length
                    continue
            merged.append(s)
        if len(merged) > 1:
            first, last = merged[0], merged[-1]
            ang = abs(math.degrees(math.atan2(math.sin(first.yaw - last.yaw), math.cos(first.yaw - last.yaw))))
            if ang < 0.5 and first.style == last.style and first.fire == last.fire and not first.rounded:
                last.q = first.q
                last.length = (last.q - last.p).length
                merged.pop(0)
        if len(merged) < 3:
            continue
        idx = []
        for s in merged:
            idx.append(len(sides))
            sides.append(s)
        m = len(idx)
        for k in range(m):
            s = sides[idx[k]]
            s.prev = idx[k - 1]
            s.next = idx[(k + 1) % m]
        for k in range(m):
            s = sides[idx[k]]
            a = sides[s.prev]
            s.turn = math.degrees(math.atan2(math.sin(s.yaw - a.yaw), math.cos(s.yaw - a.yaw)))
        loops.append(idx)
    return loops, sides, warnings
