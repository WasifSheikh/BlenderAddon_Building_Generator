"""Areaways (basement light wells): the kit's areaway modules laid along the base of the facade, clear of entrances."""

from mathutils import Vector

from .common import STYLE_OPEN, STYLE_SHOP, _rng
from .tuning import AREAWAY_ENTRANCE_CLEAR, AREAWAY_MIN_SHARE, LINE_MAX_STRETCH
from .fitting import fill_span, rigid_fill, rigid_w


class AreawayMixin:
    """Areaways of a Plan. Runs on every side that has one, stopping at entrances; corner pieces where two runs meet."""

    def areaway_side(self, sd):
        if sd.style == STYLE_OPEN:
            return False
        return sd.style != STYLE_SHOP or self.s.areaway_shops

    def areaway_corner(self, i):
        """Corner piece for the corner at the start of side i, or None."""
        sd = self.sides[i]
        a = self.sides[sd.prev]
        if sd.turn <= 1.0 or not (self.areaway_side(sd) and self.areaway_side(a)):
            return None
        right = abs(sd.turn - 90.0) < 3.0
        return self.corner_mod("areaway", "join", turn=sd.turn) or \
            (self.corner_mod("areaway", "pier", turn=90.0) if right else None) or \
            (self.corner_mod("areaway", "cap") if right else None)

    def place_areaways(self, seed):
        s = self.s
        kit = self.kit
        if not s.areaways or kit is None:
            return
        mods = [m for m in kit.role("areaway") if m.w > 0.05]
        if not mods:
            self.warnings.append("Areaways are on, but the kit has no areaway modules (name them Areaway_...)")
            return
        depth = max(max(-m.lo.y for m in mods), 0.0)
        min_run = min(m.w for m in mods) * AREAWAY_MIN_SHARE
        corners = {i: self.areaway_corner(i) for i in range(len(self.sides))}
        touches = {}
        for i, sd in enumerate(self.sides):
            if not self.areaway_side(sd):
                continue
            a = max(self.corner_cache[i]["G"]["start_B"], 0.0)
            b = min(sd.length - self.corner_cache[sd.next]["G"]["end_A"], sd.length)
            pc = corners[i]
            if pc is not None and pc.kind in ("join", "pier"):
                a = max(a, pc.trim_out)
            pn = corners.get(sd.next)
            if pn is not None and pn.kind in ("join", "pier"):
                b = min(b, sd.length - pn.trim_in)
            if sd.turn < -1.0 and self.areaway_side(self.sides[sd.prev]):
                a = max(a, depth)          # inside corner: the neighbouring areaway already runs across here
            # gaps between the entrances of the ground floor
            blocked = sorted((st - AREAWAY_ENTRANCE_CLEAR, st + w + AREAWAY_ENTRANCE_CLEAR)
                             for st, w, ent in self.ground_marks.get(sd.id, []) if ent)
            free, x = [], a
            for u0, u1 in blocked:
                if u0 > x:
                    free.append((x, min(u0, b)))
                x = max(x, u1)
                if x >= b:
                    break
            if x < b:
                free.append((x, b))
            free = [(u0, u1) for u0, u1 in free if u1 - u0 >= min_run]
            rng = _rng(seed, sd.id, "areaway")
            placed_any = False
            for u0, u1 in free:
                if self.rigid:      # whole areaways, centred on the free run
                    seq, lead, _ = rigid_fill(u1 - u0, mods, rng)
                    scale, cursor = 1.0, u0 + lead
                else:
                    seq, scale = fill_span(u1 - u0, mods, rng, None, LINE_MAX_STRETCH)
                    cursor = u0
                if not seq:
                    continue
                for m in seq:
                    self.add(m, sd.p + sd.t * (cursor - m.x0 * scale), sd.yaw, scale)
                    cursor += rigid_w(m) if self.rigid else m.w * scale
                placed_any = True
            if placed_any:
                self.areaway_depth[i] = depth
                touches[i] = (bool(free) and abs(free[0][0] - a) < 1e-6, bool(free) and abs(free[-1][1] - b) < 1e-6)
        for i, pc in corners.items():
            sd = self.sides[i]
            if pc is None or i not in touches or sd.prev not in touches:
                continue
            if touches[i][0] and touches[sd.prev][1]:
                self.add(pc, sd.p + Vector((0.0, 0.0, 0.0)), sd.yaw)
