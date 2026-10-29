"""Extras on the facade and roof: sockets, signs, awnings, lights, AC units, balconies, fire escapes, pipes, roof props."""

import math
from mathutils import Matrix, Vector

from .common import STYLE_OPEN, STYLE_SHOP, _rng
from .geometry import dist_to_segment, point_in_shape, signed_area
from .tuning import (
    AC_ALONG,
    AC_Z,
    AWNING_Z,
    BALCONY_FIT,
    DECOR_FIT,
    FIRE_MIN_EXTRA,
    LIGHT_Z,
    PIPE_CHANCE,
    PIPE_INSET,
    PIPE_MIN_SIDE,
    RIGID_TOL,
    ROOF_PROP_AREA,
    ROOF_PROP_GAP,
    SIGN_Z,
)


class ExtrasMixin:
    """Facade and roof extras of a Plan."""

    def place_extras(self, i, sd, f, placed, z, h, seed, part=None, units=None):
        s = self.s
        kit = self.kit
        if kit is None:
            return
        rng = _rng(seed, sd.id, f, "x") if part is None else _rng(seed, sd.id, f, "x", part)
        socket_roles_used = set()
        enabled = {"awning": s.awnings > 0, "sign": s.signs and s.sign_chance > 0, "ac": s.ac > 0, "light": s.lights > 0,
                   "balcony": s.balconies > 0, "pipe": False}
        chance = {"awning": s.awnings, "sign": s.sign_chance, "ac": s.ac, "light": s.lights, "balcony": s.balconies}
        for m, start, w, sx, sz in placed:
            for role, loc, yaw in m.sockets:
                socket_roles_used.add(role)
                if not enabled.get(role) or rng.random() > chance.get(role, 1):
                    continue
                cands = kit.role(role)
                if not cands:
                    continue
                a = self.pick(rng, cands)
                along = start - m.x0 * sx + loc.x * sx
                pos = sd.p + sd.t * along + sd.n * loc.y + Vector((0, 0, z + loc.z * sz))
                self.add(a, pos, sd.yaw + yaw)
        if f == 0 and sd.style == STYLE_SHOP:
            gp = [p for p in placed if p[0].role in ("storefront", "door")]
            if units:
                self.place_unit_decor(sd, [[placed[k] for k in u if placed[k][0].role in ("storefront", "door")] for u in units],
                                      z, h, rng, socket_roles_used)
            else:
                self.place_span_decor(sd, gp, z, h, rng, socket_roles_used)
            lights = kit.role("light")
            if lights and s.lights > 0 and gp:
                joints = [gp[0][1]] + [p[1] + p[2] for p in gp]
                for jx in joints:
                    if rng.random() < s.lights:
                        lt = self.pick(rng, lights)
                        zz = z + (0 if lt.mounted else h * LIGHT_Z)
                        self.add(lt, sd.p + sd.t * (jx - lt.cx) + Vector((0, 0, zz)), sd.yaw)
        if f > 0:
            acs = kit.role("ac")
            bal = kit.role("balcony")
            for m, start, w, sx, sz in placed:
                if m.role != "window":
                    continue
                if acs and s.ac > 0 and "ac" not in socket_roles_used and rng.random() < s.ac:
                    a = self.pick(rng, acs)
                    along = start + w * AC_ALONG - a.cx
                    self.add(a, sd.p + sd.t * along + Vector((0, 0, z + h * AC_Z)), sd.yaw)
                elif bal and s.balconies > 0 and "balcony" not in socket_roles_used and rng.random() < s.balconies:
                    fits = [x for x in bal if BALCONY_FIT[0] <= w / x.w <= BALCONY_FIT[1]]
                    b = self.pick(rng, fits or bal)
                    bsx = w / b.w
                    if self.rigid and abs(b.w - w) <= RIGID_TOL:
                        self.add(b, sd.p + sd.t * (start - b.x0) + Vector((0, 0, z)), sd.yaw)
                    elif not self.rigid and BALCONY_FIT[0] <= bsx <= BALCONY_FIT[1]:   # close to the bay width: stretch it
                        self.add(b, sd.p + sd.t * (start - b.x0 * bsx) + Vector((0, 0, z)), sd.yaw, bsx)
                    elif b.w < w:               # narrower: keep its size, centred on the bay
                        self.add(b, sd.p + sd.t * (start + (w - b.w) / 2 - b.x0) + Vector((0, 0, z)), sd.yaw)

    def place_span_decor(self, sd, gp, z, h, rng, socket_roles_used):
        s = self.s
        kit = self.kit
        signs = kit.role("sign") if s.signs and _rng(s.seed, sd.id, "sign").random() < s.sign_chance else []
        awn = kit.role("awning") if (s.awnings > 0 and "awning" not in socket_roles_used) else []
        if not (signs or awn) or not gp:
            return
        i = 0
        sign_done = False
        while i < len(gp):
            done = False
            for kind, pool in (("sign", signs if not sign_done else []), ("awning", awn)):
                if not pool:
                    continue
                if kind == "awning" and rng.random() > s.awnings:
                    continue
                for k in (3, 2, 1, 4):
                    if i + k > len(gp):
                        continue
                    native = sum(p[0].w for p in gp[i:i + k])
                    scaled = sum(p[2] for p in gp[i:i + k])
                    fits = [a for a in pool if abs(a.w - native) / native < DECOR_FIT]
                    if not fits:
                        continue
                    a = self.pick(rng, fits)
                    asx = scaled / a.w
                    start = gp[i][1]
                    if self.rigid:      # its own width, centred on the shop fronts it belongs to
                        start, asx = start + (scaled - a.w) / 2, 1.0
                    if kind == "sign":
                        zz = z if a.mounted else z + h * SIGN_Z
                        sign_done = True
                    else:
                        zz = z if a.mounted else z + h * AWNING_Z
                    self.add(a, sd.p + sd.t * (start - a.x0 * asx) + Vector((0, 0, zz)), sd.yaw, asx)
                    i += k
                    done = True
                    break
                if done:
                    break
            if not done:
                i += 1

    def place_fire_escapes(self, seed):
        kit = self.kit
        if kit is None:
            return
        lands = kit.role("fire_landing")
        stairs = kit.role("fire_stair")
        ladders = kit.role("fire_ladder")
        n = len(self.heights)
        any_fire = any(sd.fire for sd in self.sides)
        if any_fire and not (lands or stairs):
            self.warnings.append("Fire escape is on, but the kit has no fire-escape modules")
            return
        for sd in self.sides:
            if not sd.fire or sd.style == STYLE_OPEN or n < 2:
                continue
            rng = _rng(seed, sd.id, "fire")
            land = self.pick(rng, lands) if lands else None
            w = land.w if land else (stairs[0].w if stairs else 3.0)
            if sd.length < w + FIRE_MIN_EXTRA:
                continue
            along = (sd.length - w) / 2
            for f in range(1, n):
                z = self.levels[f]
                if land:
                    self.add(land, sd.p + sd.t * (along - land.x0) + Vector((0, 0, z)), sd.yaw)
                if stairs and f < n - 1:
                    st = self.pick(rng, stairs)
                    self.add(st, sd.p + sd.t * along + Vector((0, 0, z)), sd.yaw, 1, 1, self.heights[f] / st.h)
            if ladders:
                ld = self.pick(rng, ladders)
                self.add(ld, sd.p + sd.t * along + Vector((0, 0, 0)), sd.yaw, 1, 1, self.levels[1] / ld.h)

    def place_pipes(self, seed):
        kit = self.kit
        s = self.s
        if kit is None or not s.pipes or not kit.role("pipe"):
            return
        for i, sd in enumerate(self.sides):
            if sd.style in (STYLE_OPEN,) or sd.length < PIPE_MIN_SIDE or sd.fire:
                continue
            rng = _rng(seed, sd.id, "pipe")
            if rng.random() > PIPE_CHANCE:
                continue
            p = self.pick(rng, kit.role("pipe"))
            end = self.corner_cache[sd.next]["U"]["end_A"]
            along = sd.length - end - PIPE_INSET - p.cx
            for f, h in enumerate(self.heights):
                if f == 0 and sd.style == STYLE_SHOP:
                    continue            # keep the shop front clear: the pipe starts above it
                self.add(p, sd.p + sd.t * along + Vector((0, 0, self.levels[f])), sd.yaw, 1, 1, h / p.h)

    def place_roof_props(self, seed, parapet_mods):
        kit = self.kit
        s = self.s
        if kit is None or s.roof_props <= 0 or not kit.role("roof_prop"):
            return
        loops = self.shape_loops(0.0)
        if not loops:
            return
        margin = max(kit.parapet_depth if parapet_mods else 0.25, 0.3) + 0.3
        area = sum(abs(signed_area(l)) for l in loops)
        target = max(1, int(round(area / ROOF_PROP_AREA * s.roof_props * 2)))
        xs = [p.x for l in loops for p in l]
        ys = [p.y for l in loops for p in l]
        rng = _rng(seed, "roof")
        props = kit.role("roof_prop")
        placed = []
        tries = 0
        while len(placed) < target and tries < target * 40:
            tries += 1
            m = self.pick(rng, props)
            yaw = rng.choice((0.0, math.pi / 2, math.pi, -math.pi / 2))
            c = Vector((rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys)), 0))
            r = m.rxy
            if not point_in_shape(c, loops):
                continue
            if any(dist_to_segment(c, l[k], l[(k + 1) % len(l)]) < r + margin for l in loops for k in range(len(l))):
                continue
            if any((c - pc).length < r + pr + ROOF_PROP_GAP for pc, pr in placed):
                continue
            placed.append((c, r))
            off = Matrix.Rotation(yaw, 3, "Z") @ Vector((m.cx, m.cy, 0))
            self.add(m, c - off + Vector((0, 0, self.roof_top)), yaw)
