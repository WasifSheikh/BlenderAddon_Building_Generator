"""Damage and ruin: damaged module variants, boarded windows, a broken roofline and rubble."""

import math
from mathutils import Euler, Vector

from .common import STYLE_OPEN, _rng
from .geometry import MAT_BOARD, MAT_WALL
from .tuning import BOARDED_SHARE, ROOFLINE_GAP_SHARE, RUBBLE_SPACING


class DamageMixin:
    """Damage of a Plan. Everything is keyed on position, so the same building always breaks the same way."""

    def damaged_variant(self, m, pos):
        cands = self.kit.damaged.get((m.role, int(round(m.w * 100))))
        if not cands:
            return m
        rng = _rng(self.s.seed, "dmg", round(pos.x, 2), round(pos.y, 2), round(pos.z, 2))
        if rng.random() >= self.dmg:
            return m
        same_floor = [c for c in cands if m.floor == "any" or c.floor in (m.floor, "any")]
        return self.pick(rng, same_floor or cands)

    def roofline_gap(self, layer, pos):
        if self.dmg <= 0 or not self.s.broken_roofline or layer not in ("cornice", "parapet"):
            return False
        return _rng(self.s.seed, "roofline", round(pos.x, 2), round(pos.y, 2)).random() < self.dmg * ROOFLINE_GAP_SHARE

    def board_up(self, sd, start, w, z, h):
        """Planks nailed across the opening(s) of one window module."""
        if self.dmg <= 0 or not self.s.boarded_windows:
            return
        rng = _rng(self.s.seed, "boards", sd.id, round(start, 2), round(z, 2))
        if rng.random() >= self.dmg * BOARDED_SHARE:
            return
        up = Vector((0.0, 0.0, 1.0))
        openings = 2 if w >= 3.2 else 1
        y0 = self.wall_lo - 0.03
        for k in range(openings):
            cx = start + (k + 0.5) * w / openings
            bw = min(w / openings * 0.62, 1.6)
            z0, z1 = z + h * 0.28, z + h * 0.78
            planks = rng.randint(3, 5)
            for j in range(planks):
                zc = z0 + (z1 - z0) * (j + 0.5) / planks + rng.uniform(-0.05, 0.05)
                tilt = math.radians(rng.uniform(-14.0, 14.0))
                ax = sd.t * math.cos(tilt) + up * math.sin(tilt)
                az = -sd.t * math.sin(tilt) + up * math.cos(tilt)
                ay = az.cross(ax)
                c = sd.p + sd.t * (cx + rng.uniform(-0.08, 0.08)) + sd.n * (y0 - 0.015 * j) + Vector((0.0, 0.0, zc))
                self.proc.obox(c, ax, ay, az, bw * rng.uniform(0.52, 0.62), 0.012, rng.uniform(0.07, 0.1), MAT_BOARD)

    def place_rubble(self, seed):
        if self.dmg <= 0 or not self.s.rubble:
            return
        mods = self.kit.role("rubble") if self.kit else []
        for i, sd in enumerate(self.sides):
            if sd.style == STYLE_OPEN:
                continue
            rng = _rng(seed, sd.id, "rubble")
            out = self.wall_lo - self.areaway_depth.get(i, 0.0)    # beyond the areaway, if there is one
            piles = int(sd.length / RUBBLE_SPACING * self.dmg + rng.random())
            for _ in range(piles):
                along = rng.uniform(0.6, max(sd.length - 0.6, 0.7))
                base = sd.p + sd.t * along + sd.n * (out - rng.uniform(0.4, 1.4))
                if mods:
                    self.add(self.pick(rng, mods), base, rng.uniform(-math.pi, math.pi))
                    continue
                for _k in range(rng.randint(4, 9)):
                    r = rng.uniform(0.1, 0.32)
                    off = Vector((rng.uniform(-0.7, 0.7), rng.uniform(-0.5, 0.5), r * 0.55))
                    R = Euler((rng.uniform(0, math.pi), rng.uniform(0, math.pi), rng.uniform(0, math.pi))).to_matrix()
                    self.proc.obox(base + off, Vector(R.col[0]), Vector(R.col[1]), Vector(R.col[2]),
                                   r * rng.uniform(0.8, 1.6), r, r * rng.uniform(0.6, 1.1), MAT_WALL)
