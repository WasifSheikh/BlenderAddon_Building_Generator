"""Ground-floor variety: matching shop units, closed shops behind shutters and recessed entrances."""

from mathutils import Vector

from .common import _rng
from .geometry import MAT_SHUTTER, MAT_WALL, signed_area
from .tuning import (
    AWNING_Z,
    RECESS_REVEAL_T,
    RECESS_SOFFIT_T,
    SHUTTER_HEIGHT_SHARE,
    SHUTTER_INSET,
    SHUTTER_MAX_H,
    RIGID_TOL,
    SIGN_Z,
    UNIT_SIGN_STRETCH,
)
from .fitting import weighted_choice

ENTRANCE_WORDS = {"door", "entrance", "entry"}


class GroundMixin:
    """Ground-floor variety of a Plan."""

    @staticmethod
    def is_entrance(m):
        return m.role == "door" or (m.role == "storefront" and bool(m.tokens & ENTRANCE_WORDS))

    def band_box(self, sd, u0, u1, y_out, y_in, z0, z1, mat):
        """A box along a side: u along the side, y across it (negative = outwards), z up."""
        pts = [sd.p + sd.t * u0 + sd.n * y_out, sd.p + sd.t * u1 + sd.n * y_out,
               sd.p + sd.t * u1 + sd.n * y_in, sd.p + sd.t * u0 + sd.n * y_in]
        if signed_area(pts) < 0:
            pts.reverse()
        self.proc.prism([pts], z0, z1, mat)

    # ---- shop units
    def group_shop_units(self, sd, start, seq, pool):
        """Shop fronts in runs of 1..N bays that share one design. Entrances keep their own module.
        Returns (new sequence, units as lists of indices into it)."""
        s = self.s
        rng = _rng(s.seed, sd.id, "units", round(start, 2))
        fronts = [m for m in pool if m.role == "storefront" and m.weight > 0 and not self.is_entrance(m)]
        out = list(seq)
        units = []
        i = 0
        while i < len(out):
            if out[i].role != "storefront":
                units.append([i])
                i += 1
                continue
            size = rng.randint(1, max(1, s.shop_unit_max))
            members = []
            while i < len(out) and len(members) < size and out[i].role == "storefront":
                members.append(i)
                i += 1
            design = {}
            for k in members:
                if self.is_entrance(out[k]):
                    continue
                wcm = int(round(out[k].w * 100))
                same = [m for m in fronts if int(round(m.w * 100)) == wcm]
                if not same:
                    continue
                if wcm not in design:
                    design[wcm] = weighted_choice(rng, same, [m.weight for m in same])
                out[k] = design[wcm]
            units.append(members)
        return out, units

    def place_unit_decor(self, sd, units, z, h, rng, socket_roles_used):
        """One sign across each shop unit, and one awning style per unit."""
        s = self.s
        kit = self.kit
        signs = kit.role("sign") if s.signs else []
        awn = kit.role("awning") if (s.awnings > 0 and "awning" not in socket_roles_used) else []
        lo, hi = UNIT_SIGN_STRETCH
        for gp in units:
            if not any(p[0].role == "storefront" for p in gp):
                continue
            start = gp[0][1]
            width = sum(p[2] for p in gp)
            native = sum(p[0].w for p in gp)
            if signs and _rng(s.seed, sd.id, "sign", round(start, 2)).random() < s.sign_chance:
                a = min(signs, key=lambda x: abs(x.w - native))
                asx = width / a.w
                if self.rigid:      # rigid modules: the sign keeps its width, centred on the unit
                    if a.w <= width + RIGID_TOL:
                        zz = z if a.mounted else z + h * SIGN_Z
                        self.add(a, sd.p + sd.t * (start + (width - a.w) / 2 - a.x0) + Vector((0, 0, zz)), sd.yaw)
                elif lo < asx < hi:
                    zz = z if a.mounted else z + h * SIGN_Z
                    self.add(a, sd.p + sd.t * (start - a.x0 * asx) + Vector((0, 0, zz)), sd.yaw, asx)
            if awn and rng.random() < s.awnings:
                design = self.pick(rng, awn)
                for m, st, w, sx, sz in gp:
                    asx = w / design.w
                    if lo < asx < hi:
                        zz = z if design.mounted else z + h * AWNING_Z
                        if self.rigid:
                            self.add(design, sd.p + sd.t * (st + (w - design.w) / 2 - design.x0) + Vector((0, 0, zz)), sd.yaw)
                        else:
                            self.add(design, sd.p + sd.t * (st - design.x0 * asx) + Vector((0, 0, zz)), sd.yaw, asx)

    # ---- closed shops
    def maybe_shutter(self, sd, m, start, w, z, h, sz):
        s = self.s
        if s.closed_shops <= 0 or _rng(s.seed, sd.id, "closed", round(start, 2)).random() >= s.closed_shops:
            return
        shut = self.kit.role("shutter") if self.kit else []
        if self.rigid:      # rigid modules: only a shutter of the same width; otherwise a generated one fits exactly
            shut = [x for x in shut if abs(x.w - w) <= RIGID_TOL]
        if shut:
            sh = min(shut, key=lambda x: abs(x.w - m.w))
            sx = 1.0 if self.rigid else w / sh.w
            ssz = sz if abs(sh.h - m.h) / max(m.h, 0.01) < 0.1 else 1.0
            self.add(sh, sd.p + sd.t * (start - sh.x0 * sx) + Vector((0, 0, z)), sd.yaw, sx, 1.0, ssz)
        else:
            self.roller_shutter(sd, m, start, w, z, h)

    def roller_shutter(self, sd, m, start, w, z, h):
        """A generated roller shutter in front of a shop front: slatted panel and a housing box on top."""
        inset = w * SHUTTER_INSET
        a, b = start + inset, start + w - inset
        top = z + min(h * SHUTTER_HEIGHT_SHARE, SHUTTER_MAX_H)
        y0 = min(self.wall_lo, m.lo.y) - 0.02            # just in front of the facade and the shop front
        self.band_box(sd, a, b, y0 - 0.04, y0, z, top, MAT_SHUTTER)
        n = max(4, min(14, int((top - z) / 0.2)))
        for k in range(1, n):                            # slat ridges
            zz = z + (top - z) * k / n
            self.band_box(sd, a, b, y0 - 0.055, y0 - 0.04, zz - 0.012, zz + 0.012, MAT_SHUTTER)
        self.band_box(sd, a - 0.05, b + 0.05, y0 - 0.24, y0, top, top + 0.28, MAT_SHUTTER)

    # ---- recessed entrances
    def recess_for(self, sd, m, start):
        s = self.s
        if s.recessed_doors <= 0 or not self.is_entrance(m):
            return 0.0
        if _rng(s.seed, sd.id, "recess", round(start, 2)).random() >= s.recessed_doors:
            return 0.0
        return s.recess_depth

    def recess_reveals(self, sd, start, w, z, h, depth):
        """Side walls and soffit lining an entrance set back into the facade."""
        y_out, y_in = self.wall_lo, self.wall_lo + depth
        t = RECESS_REVEAL_T
        self.band_box(sd, start, start + t, y_out, y_in, z, z + h, MAT_WALL)
        self.band_box(sd, start + w - t, start + w, y_out, y_in, z, z + h, MAT_WALL)
        self.band_box(sd, start, start + w, y_out, y_in, z + h - RECESS_SOFFIT_T, z + h, MAT_WALL)
