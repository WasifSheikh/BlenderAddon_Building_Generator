"""Facade spans: module choice per floor, pilaster bays and the ground floor between them."""

from mathutils import Vector

import math

from .common import STYLE_BACK, STYLE_BLANK, STYLE_OPEN, STYLE_SHOP, STYLE_WINDOWS, _rng
from .geometry import MAT_WALL
from .kit import Mod
from .naming import BETWEEN_WORDS
from .tuning import (
    BAY_STRETCH,
    DOOR_BAY_STRETCH,
    ENTRANCE_MIN_EXTRA,
    PILASTER_END_MARGIN,
    PILASTER_STRETCH,
    RIGID_TOL,
    SHOP_ENTRANCE_MIN_SIDE,
    WALL_MIX_WEIGHT,
)
from .fitting import _copy_mod, fill_span, rigid_fill, rigid_w, weighted_choice


class FacadeMixin:
    """Facade spans of a Plan."""

    # ---- façades
    def place_facade_span(self, i, sd, f, start, L, h, z, seed):
        bp = self.bay_plan(i, sd, seed)
        spec = self.floor_specs[f]
        if bp is not None and f > 0:
            self.place_upper_bays(i, sd, f, bp, h, z, seed, start, L)
            return
        if f == 0 and self.ground_modules(sd):
            # a ground floor of chosen modules: share the bays above, or lay out its own
            gbays = self.ground_bays_from(bp, start, L) if bp is not None else None
            if spec.explicit and (gbays is None or not self.bays_fit(spec, gbays[1])):
                gbays = self.explicit_bays(start, L, None, spec)
            if gbays is not None:
                door = self.ground_door(sd, seed)
                self.place_bays(i, sd, 0, gbays[0], gbays[1], h, z, seed, spec, door=door)
                self.bay_ends(sd, start, L, gbays[1], z, h)
                return
        pool, door, rng = self.span_pool(sd, f, seed)
        if bp is not None and bp[0] is not None and f == 0 and self.s.pilaster_ground:
            self.place_ground_bays(i, sd, start, L, h, z, seed, bp, pool, door, rng)
            return
        if f > 0 and spec.explicit and sd.style != STYLE_BLANK:
            own = self.explicit_bays(start, L, None, spec)
            if own is not None:
                self.place_bays(i, sd, f, None, own[1], h, z, seed, spec)
                self.bay_ends(sd, start, L, own[1], z, h)
                return
        units = []
        placed = self.fill_and_place(sd, start, L, h, z, pool, rng, door, ground=(f == 0), units_out=units)
        if placed is not None:
            self.place_extras(i, sd, f, placed, z, h, seed, units=units or None)

    def ground_modules(self, sd):
        """True when this side's ground floor is built from the Ground floor settings (no shops)."""
        return self.s.ground_mode == "GROUND" and sd.style == STYLE_WINDOWS

    def ground_door(self, sd, seed):
        spec = self.floor_specs[0]
        if not spec.entrance:
            return None
        d = spec.door or self.pick(_rng(seed, sd.id, "G"), self.pool("door", "ground"))
        if d is not None and sd.length >= d.w + ENTRANCE_MIN_EXTRA:
            return d
        return None

    def span_pool(self, sd, f, seed):
        """Module pool, optional entrance and random stream for one floor of one side."""
        s = self.s
        kit = self.kit
        floor = "ground" if f == 0 else "upper"
        style = sd.style
        door = None
        mix = 0.0
        if f == 0:
            rng = _rng(seed, sd.id, "G")
            if style == STYLE_SHOP:
                roles = ["storefront", "window", "wall"]
            elif style == STYLE_WINDOWS:
                roles = ["window", "wall"]
                d = self.pick(rng, self.pool("door", "ground"))
                if self.ground_modules(sd):
                    spec = self.floor_specs[0]
                    d = (spec.door or d) if spec.entrance else None
                if d is not None and sd.length >= d.w + ENTRANCE_MIN_EXTRA:   # an entrance whenever it fits
                    door = d
            elif style == STYLE_BACK:
                roles = ["wall", "window"]
                door = self.pick(rng, self.pool("door", "ground"))
            else:
                roles = ["wall", "window"]
        else:
            key = (seed, sd.id, "U", f) if s.vary_floors else (seed, sd.id, "U")
            rng = _rng(*key)
            if style == STYLE_BLANK:
                roles = ["wall", "window"]
            else:
                roles = ["window", "wall"]
                mix = s.wall_mix
        pool = []
        for r in roles:
            pool = self.pool(r, floor)
            if pool:
                break
        spec = self.floor_specs[f]
        if spec.explicit and (f > 0 and style != STYLE_BLANK or f == 0 and self.ground_modules(sd)):
            pool = []
            for m in (spec.middle, spec.corner):     # chosen modules only, used even at frequency 0
                if m is not None and all(c.name != m.name for c in pool):
                    c = _copy_mod(m)
                    c.weight = 1.0
                    pool.append(c)
            mix = 0.0
        if f == 0 and style == STYLE_SHOP and pool and pool[0].role != "storefront" and sd.length > SHOP_ENTRANCE_MIN_SIDE:
            door = self.pick(rng, self.pool("door", "ground"))  # kit has no storefronts: add an entrance
        if mix > 0 and roles[0] == "window" and pool and pool[0].role == "window":
            walls = self.pool("wall", floor)
            extra = []
            for w in walls:
                c = Mod()
                for a in Mod.__slots__:
                    if hasattr(w, a):
                        setattr(c, a, getattr(w, a))
                c.weight = w.weight * mix * WALL_MIX_WEIGHT
                extra.append(c)
            pool = pool + extra
        return pool, door, rng

    def fill_and_place(self, sd, start, L, h, z, pool, rng, door, ground=False, units_out=None):
        """Fill [start, start + L] along a side; returns what was placed, or None when a plain filler wall was used.
        On the ground floor this also applies shop units, shutters and recessed entrances."""
        if self.rigid:
            # whole modules only; on the ground floor a wall piece may join when the main modules can't fit
            # exactly (next to the entrance, or at the ends). Upper floors never get one: windows only.
            helpers = [m for m in self.pool("wall", "ground") if m.weight > 0] if ground else ()
            seq, lead, tail = rigid_fill(L, pool, rng, door, helpers) if (pool or door) else (None, 0.0, 0.0)
            scale = 1.0
            if seq is not None:
                start = self.strips(sd, start, L, lead, tail, z, h)
        else:
            seq, scale = fill_span(L, pool, rng, door) if pool else (None, 1.0)
        if seq is None:
            self.filler(sd, start, L, z, h)
            return None
        shop = ground and sd.style == STYLE_SHOP
        units = None
        if shop and self.s.shop_units:
            seq, units = self.group_shop_units(sd, start, seq, pool)
        cursor = start
        placed = []
        for m in seq:
            w = rigid_w(m) if self.rigid else m.w * scale
            sz = h / m.h if abs(h - m.h) > 0.005 else 1.0
            recess = self.recess_for(sd, m, cursor) if ground else 0.0
            pos = sd.p + sd.t * (cursor - m.x0 * scale) + Vector((0, 0, z))
            if recess:
                pos = pos + sd.n * recess
            self.add(m, pos, sd.yaw, scale, 1.0, sz)
            if recess:
                self.recess_reveals(sd, cursor, w, z, h, recess)
            elif shop and m.role == "storefront":
                self.maybe_shutter(sd, m, cursor, w, z, h, sz)
            if m.role == "window":
                self.board_up(sd, cursor, w, z, h)
            if ground:
                self.mark_ground(sd, cursor, w, self.is_entrance(m))
            placed.append((m, cursor, w, scale, sz))
            cursor += w
        if units_out is not None and units:
            units_out.extend(units)
        return placed

    # ---- bays: window bays with a divider (pilaster or wall piece) between each pair
    def divider_mods(self, floor):
        """Divider candidates for one floor: the chosen divider module, or the kit's pilasters / between-window walls."""
        s = self.s
        role = "wall" if s.divider_type == "WALL" else "pilaster"
        ex = self.mod_for(s.divider_module, (role,))
        if ex is not None and (floor == "upper" or ex.floor in ("ground", "any")):
            return [ex]
        cands = [m for m in self.pool(role, floor) if m.weight > 0 and m.w > 0.05]
        if role == "wall" and cands:
            pref = [m for m in cands if m.tokens & BETWEEN_WORDS]
            if pref or floor == "ground":
                return pref     # ground floor without its own between-window wall: the upper one runs down
            narrow = min(m.w for m in cands)
            cands = [m for m in cands if m.w < narrow + 0.01]
        return cands

    def reference_spec(self):
        """The lowest upper floor with chosen modules: its module widths set the bay rhythm of every floor."""
        for sp in self.floor_specs[1:]:
            if sp.explicit:
                return sp
        return None

    def typical_window_w(self):
        wins = [m for m in self.pool("window", "upper") if m.weight > 0 and m.w > 0.05]
        if not wins:
            return 2.0
        ws = sorted(m.w for m in wins)
        return ws[len(ws) // 2]

    def bay_plan(self, i, sd, seed):
        """The upper-floor bay rhythm of a side, shared by every floor so dividers and chosen modules stack.
        Returns (divider or None, [(start, width, native width in cm, "corner" | "middle"), ...]) or None."""
        if i in self.bays:
            return self.bays[i]
        res = None
        s = self.s
        if len(self.heights) > 1 and sd.style not in (STYLE_BLANK, STYLE_OPEN):
            divs = self.divider_mods("upper") if s.pilasters else []
            ref = self.reference_spec()
            start = self.corner_cache[i]["U"]["start_B"]
            L = sd.length - start - self.corner_cache[sd.next]["U"]["end_A"]
            if ref is not None:
                div, _ = self.bay_divider(sd, seed, divs)
                res = self.explicit_bays(start, L, div, ref) if L > 0.05 else None
            elif divs:
                wins = [m for m in self.pool("window", "upper") if m.weight > 0 and m.w > 0.05]
                if wins:
                    div, rng = self.bay_divider(sd, seed, divs)
                    p = div.w
                    units = []
                    for m in wins:          # a window bay plus the divider that follows it
                        u = _copy_mod(m)
                        u.w = m.w + p
                        units.append(u)
                    if self.rigid:
                        seq, lead, _ = rigid_fill(L + p, units, rng) if L > 0.05 else (None, 0.0, 0.0)
                        if seq and len(seq) >= 2:
                            bays, x = [], start + lead
                            last = len(seq) - 1
                            for j, u in enumerate(seq):
                                w = rigid_w(u) - rigid_w(div)
                                bays.append((x, w, int(round(w * 100)), "corner" if j in (0, last) else "middle"))
                                x += w + rigid_w(div)
                            res = (div, bays)
                        seq = None
                    else:
                        seq, _ = fill_span(L + p, units, rng) if L > 0.05 else (None, 1.0)
                    if seq and len(seq) >= 2:
                        widths = [u.w - p for u in seq]
                        k = (L - p * (len(seq) - 1)) / sum(widths)   # windows stretch, dividers keep their size
                        if PILASTER_STRETCH[0] < k < PILASTER_STRETCH[1]:
                            bays, x = [], start
                            last = len(widths) - 1
                            for j, w in enumerate(widths):
                                bays.append((x, w * k, int(round(w * 100)), "corner" if j in (0, last) else "middle"))
                                x += w * k + p
                            res = (div, bays)
        self.bays[i] = res
        return res

    def bay_divider(self, sd, seed, divs):
        """The divider a side's bays use (None without dividers), and the random stream that picked it."""
        rng = _rng(seed, sd.id, "bays")
        return (self.pick(rng, divs) if divs else None), rng

    def explicit_bays(self, start, L, div, spec):
        """Bays for chosen modules: corner bays at both ends, middle bays in between, all stretched alike.
        Returns (divider, bays) or None when the span is too short or too long for them."""
        p = div.w if div is not None else 0.0
        wm = spec.middle.w if spec.middle is not None else self.typical_window_w()
        wc = spec.bay_mod("corner").w if spec.bay_mod("corner") is not None else wm
        if self.rigid:
            return self.rigid_bays(start, L, div, round(wm, 2), round(wc, 2))
        best = None
        n_max = int(L / max(min(wm, wc), 0.3)) + 3
        for nb in range(1, n_max + 1):
            natural = wm if nb == 1 else 2 * wc + (nb - 2) * wm
            avail = L - p * (nb - 1)
            if avail <= 0.05:
                break
            k = avail / natural
            score = abs(math.log(k))
            if best is None or score < best[0] - 1e-9:
                best = (score, nb, k)
        if best is None or not BAY_STRETCH[0] < best[2] < BAY_STRETCH[1]:
            return None
        _, nb, k = best
        bays, x = [], start
        for j in range(nb):
            kind = "corner" if nb > 1 and j in (0, nb - 1) else "middle"
            wn = wc if kind == "corner" else wm
            bays.append((x, wn * k, int(round(wn * 100)), kind))
            x += wn * k + p
        return div, bays

    def rigid_bays(self, start, L, div, wm, wc):
        """Bays at their own width: as many as fit, centred on the span (the ends get filler strips)."""
        p = rigid_w(div) if div is not None else 0.0
        best = None
        for nb in range(1, int(L / max(min(wm, wc), 0.3)) + 3):
            total = (wm if nb == 1 else 2 * wc + (nb - 2) * wm) + p * (nb - 1)
            if total > L + RIGID_TOL:
                break
            best = (nb, L - total)
        if best is None:
            return None
        nb, left = best
        bays, x = [], start + round(left / 2, 4)
        for j in range(nb):
            kind = "corner" if nb > 1 and j in (0, nb - 1) else "middle"
            wn = wc if kind == "corner" else wm
            bays.append((x, wn, int(round(wn * 100)), kind))
            x += wn + p
        return div, bays

    def bay_ends(self, sd, start, L, bays, z, h):
        """Rigid modules: plain filler strips where the bays leave the ends of a span open."""
        if not self.rigid or not bays:
            return
        a = bays[0][0] - start
        b = start + L - (bays[-1][0] + bays[-1][1])
        if a > RIGID_TOL:
            self.filler(sd, start, a, z, h)
        if b > RIGID_TOL:
            self.filler(sd, start + L - b, b, z, h)

    def strips(self, sd, start, L, lead, tail, z, h):
        """Filler strips for what whole modules leave open at both ends of a span; returns where the modules start."""
        if lead > RIGID_TOL:
            self.filler(sd, start, lead, z, h)
        if tail > RIGID_TOL:
            self.filler(sd, start + L - tail, tail, z, h)
        return start + lead

    def ground_bays_from(self, bp, start, L):
        """The ground floor under the upper bays: dividers (if they run through) stand under the ones above."""
        div, bays = bp
        end = start + L
        g = None
        if div is not None and self.s.pilaster_ground:
            gdivs = self.divider_mods("ground")
            g = gdivs[0] if gdivs else div
        gw = g.w if g is not None else 0.0
        p = div.w if div is not None else 0.0
        centres = [x + w + p / 2 for x, w, _, _ in bays[:-1]]
        if self.rigid:      # the strips at the ends stay strips: the ground bays line up with the bays above
            start, end = bays[0][0], bays[-1][0] + bays[-1][1]
        edges = [start]
        for c in centres:
            edges += [c - gw / 2, c + gw / 2]
        edges.append(end)
        out = []
        for j, (_, _, wcm, kind) in enumerate(bays):
            a, b = edges[2 * j], edges[2 * j + 1]
            if b - a <= 0.05:
                return None
            out.append((a, b - a, wcm, kind))
        return g, out

    def bays_fit(self, spec, bays):
        """Can this floor's chosen modules fill these bays without squashing or stretching them out of shape?"""
        lo, hi = DOOR_BAY_STRETCH
        for _, w, _, kind in bays:
            m = spec.bay_mod(kind)
            if m is None:
                continue
            if self.rigid and abs(w - rigid_w(m)) > RIGID_TOL:
                return False
            if not lo < w / m.w < hi:
                return False
        return True

    def own_bays(self, spec, div, bays, span=None):
        """Bays of the same span laid out for this floor's own modules (they don't fit the shared rhythm)."""
        start = bays[0][0]
        end = bays[-1][0] + bays[-1][1]
        if span is not None:
            start, end = span[0], span[0] + span[1]
        return self.explicit_bays(start, end - start, div, spec)

    def place_upper_bays(self, i, sd, f, bp, h, z, seed, start=None, L=None):
        div, bays = bp
        spec = self.floor_specs[f]
        if spec.explicit and not self.bays_fit(spec, bays):
            own = self.own_bays(spec, div, bays, (start, L) if self.rigid else None)
            if own is not None:
                div, bays = own
        self.place_bays(i, sd, f, div, bays, h, z, seed, spec)
        self.bay_ends(sd, start, L, bays, z, h)

    def place_bays(self, i, sd, f, div, bays, h, z, seed, spec, door=None):
        """One floor laid into bays: chosen modules where the floor has them, the kit mix otherwise."""
        s = self.s
        ground = f == 0
        if ground:
            rng = _rng(seed, sd.id, "G", "bays")
            wins = self.pool("window", "ground")
            walls = []
        else:
            rng = _rng(*((seed, sd.id, "U", f) if s.vary_floors else (seed, sd.id, "U")))
            wins = self.pool("window", "upper")
            walls = self.pool("wall", "upper") if s.wall_mix > 0 else []
        door_k = len(bays) // 2 if door is not None else -1
        placed = []
        for k, (x, w, wcm, kind) in enumerate(bays):
            if k == door_k:
                placed += self.place_door_bay(sd, x, w, h, z, door, rng)
            else:
                m = spec.bay_mod(kind) if spec is not None else None
                run = None      # rigid modules: the bay is filled with whole modules from this pool instead
                if m is None:
                    same = [m for m in wins if m.weight > 0 and int(round(m.w * 100)) == wcm]
                    blank = [m for m in walls if m.weight > 0 and int(round(m.w * 100)) == wcm]
                    if same or blank:
                        m = weighted_choice(rng, same + blank, [m.weight for m in same] + [m.weight * s.wall_mix * WALL_MIX_WEIGHT for m in blank])
                    elif self.rigid:
                        run = [c for c in wins if c.weight > 0 and c.w > 0.05]
                    else:   # no kit window of this width: the closest one, stretched
                        cands = [c for c in wins if c.weight > 0 and c.w > 0.05]
                        if cands:
                            best = min(abs(c.w - w) for c in cands)
                            near = [c for c in cands if abs(c.w - w) < best + 0.01]
                            m = weighted_choice(rng, near, [c.weight for c in near])
                if m is not None and self.rigid and abs(w - rigid_w(m)) > RIGID_TOL:
                    run, m = [self.chosen(m)], None
                if run is not None:
                    placed += self.place_run(sd, x, w, run, z, h, rng, ground)
                elif m is None:
                    self.filler(sd, x, w, z, h)
                else:
                    sx = 1.0 if self.rigid else w / m.w
                    sz = h / m.h if abs(h - m.h) > 0.005 else 1.0
                    self.add(m, sd.p + sd.t * (x - m.x0 * sx) + Vector((0, 0, z)), sd.yaw, sx, 1.0, sz)
                    if m.role == "window":
                        self.board_up(sd, x, w, z, h)
                    if ground:
                        self.mark_ground(sd, x, w, self.is_entrance(m))
                    placed.append((m, x, w, sx, sz))
            if div is not None and k < len(bays) - 1:
                dsz = h / div.h if abs(h - div.h) > 0.005 else 1.0
                self.add(div, sd.p + sd.t * (x + w - div.x0) + Vector((0, 0, z)), sd.yaw, 1.0, 1.0, dsz)
        self.place_extras(i, sd, f, placed, z, h, seed)

    def place_run(self, sd, x, w, pool, z, h, rng, ground=False):
        """Rigid modules: whole modules from `pool` across [x, x + w], filler strips for what is left."""
        seq, lead, tail = rigid_fill(w, pool, rng)
        if seq is None:
            self.filler(sd, x, w, z, h)
            return []
        cursor = self.strips(sd, x, w, lead, tail, z, h)
        placed = []
        for m in seq:
            mw = rigid_w(m)
            sz = h / m.h if abs(h - m.h) > 0.005 else 1.0
            self.add(m, sd.p + sd.t * (cursor - m.x0) + Vector((0, 0, z)), sd.yaw, 1.0, 1.0, sz)
            if m.role == "window":
                self.board_up(sd, cursor, mw, z, h)
            if ground:
                self.mark_ground(sd, cursor, mw, self.is_entrance(m))
            placed.append((m, cursor, mw, 1.0, sz))
            cursor += mw
        return placed

    def place_door_bay(self, sd, x, w, h, z, door, rng):
        """An entrance in one bay: stretched to the bay when close, otherwise flanked by walls.
        Rigid modules: the entrance keeps its width, flanked by whole walls and filler strips."""
        lo, hi = DOOR_BAY_STRETCH
        if self.rigid:
            walls = [m for m in self.pool("wall", "ground") if m.weight > 0]
            seq, lead, tail = rigid_fill(w, walls, rng, door) if door.w <= w + RIGID_TOL else (None, 0.0, 0.0)
            if seq is not None:
                x = self.strips(sd, x, w, lead, tail, z, h)
            scale = 1.0
        elif lo < w / door.w < hi:
            seq, scale = [door], w / door.w
        else:
            walls = [m for m in self.pool("wall", "ground") if m.weight > 0]
            seq, scale = fill_span(w, walls, rng, door) if walls else (None, 1.0)
        placed = []
        if seq is None:     # walls can't fill around it: the door at its own width, plain wall either side
            dx = x + (w - door.w) / 2
            if dx - x > 0.02:
                self.filler(sd, x, dx - x, z, h)
                self.filler(sd, dx + door.w, x + w - dx - door.w, z, h)
            seq, scale, x = [door], 1.0, dx
        cursor = x
        for m in seq:
            mw = rigid_w(m) if self.rigid else m.w * scale
            sz = h / m.h if abs(h - m.h) > 0.005 else 1.0
            recess = self.recess_for(sd, m, cursor)
            pos = sd.p + sd.t * (cursor - m.x0 * scale) + Vector((0, 0, z))
            if recess:
                pos = pos + sd.n * recess
            self.add(m, pos, sd.yaw, scale, 1.0, sz)
            if recess:
                self.recess_reveals(sd, cursor, mw, z, h, recess)
            self.mark_ground(sd, cursor, mw, m is door or self.is_entrance(m))
            placed.append((m, cursor, mw, scale, sz))
            cursor += mw
        return placed

    def mark_ground(self, sd, start, w, entrance):
        self.ground_marks.setdefault(sd.id, []).append((start, w, entrance))

    def place_ground_bays(self, i, sd, start, L, h, z, seed, bp, pool, door, rng):
        """Ground floor split by pilasters standing under the upper ones; each piece between them is filled as usual."""
        div, bays = bp
        gdivs = self.divider_mods("ground")
        gdiv = self.pick(_rng(seed, sd.id, "gbays"), gdivs) if gdivs else div
        end = start + L
        cuts = []
        for x, w, _, _ in bays[:-1]:
            c = x + w + div.w / 2              # centre of the divider above
            a, b = c - gdiv.w / 2, c + gdiv.w / 2
            if a > start + PILASTER_END_MARGIN and b < end - PILASTER_END_MARGIN:
                cuts.append((a, b))
        segs, x = [], start
        for a, b in cuts:
            segs.append((x, a - x))
            x = b
        segs.append((x, end - x))
        door_seg = -1
        if door is not None:
            door_seg = len(segs) // 2
            if segs[door_seg][1] < door.w * 0.75:     # middle piece too narrow: use the widest one
                door_seg = max(range(len(segs)), key=lambda k: segs[k][1])
        dsz = h / gdiv.h if abs(h - gdiv.h) > 0.005 else 1.0
        for a, _ in cuts:
            self.add(gdiv, sd.p + sd.t * (a - gdiv.x0) + Vector((0, 0, z)), sd.yaw, 1.0, 1.0, dsz)
        for k, (sx0, sl) in enumerate(segs):
            if sl <= 0.02:
                continue
            units = []
            placed = self.fill_and_place(sd, sx0, sl, h, z, pool, rng, door if k == door_seg else None,
                                         ground=True, units_out=units)
            if placed:
                self.place_extras(i, sd, 0, placed, z, h, seed, part=k, units=units or None)

    def filler(self, sd, start, L, z, h):
        if self.rigid:
            self.fill_strips += 1
        a = sd.p + sd.t * start
        b = sd.p + sd.t * (start + L)
        lo_y, hi_y = self.wall_lo, self.wall_hi
        self.proc.prism([[a + sd.n * lo_y, b + sd.n * lo_y, b + sd.n * hi_y, a + sd.n * hi_y]], z, z + h, MAT_WALL)
