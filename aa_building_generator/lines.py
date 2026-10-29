"""Horizontal lines along every side: belt course, roof cornice and parapet, with their corners."""

from mathutils import Vector

from .common import STYLE_OPEN, _rng
from .geometry import MAT_PARAPET, MAT_WALL, signed_area
from .tuning import LINE_MAX_STRETCH, RIGID_TOL
from .fitting import fill_span, rigid_fill, rigid_w


class LineMixin:
    """Belt, cornice and parapet lines of a Plan."""

    def place_line(self, mods, layer, z, seed, tag):
        """Cornices / belts / parapets along every non-open side, with their corner pieces."""
        band = self.band(layer)
        hh = max((m.hi.z for m in mods), default=0.6)
        mat = MAT_PARAPET if layer == "parapet" else MAT_WALL
        for i, sd in enumerate(self.sides):
            if sd.style == STYLE_OPEN:
                continue
            ci = self.corner_cache[i][layer]
            ce = self.corner_cache[sd.next][layer]
            start = ci["start_B"]
            L = sd.length - start - ce["end_A"]
            rng = _rng(seed, sd.id, tag)
            if L > 0.05:
                exact = False
                if self.rigid:      # whole pieces when they fit exactly; a profile can't take a filler strip
                    seq, lead, tail = rigid_fill(L, mods, rng)
                    exact = seq is not None and lead + tail <= RIGID_TOL
                    if exact:
                        scale = 1.0
                    else:
                        seq, scale = fill_span(L, mods, rng, None, LINE_MAX_STRETCH)
                        self.line_stretch += 1 if seq else 0
                else:
                    seq, scale = fill_span(L, mods, rng, None, LINE_MAX_STRETCH)
                if seq:
                    cursor = start
                    for m in seq:
                        pos = sd.p + sd.t * (cursor - m.x0 * scale) + Vector((0, 0, z))
                        if not self.roofline_gap(layer, pos):
                            self.add(m, pos, sd.yaw, scale)
                        cursor += rigid_w(m) if exact else m.w * scale
            a = self.sides[sd.prev]
            if a.style == STYLE_OPEN:
                continue
            piece = ci["piece"]
            if piece:
                kind, m = piece
                if kind == "rounded":
                    self.add_rounded(m, ci["end_A"], a, sd, z)
                else:
                    self.add(m, sd.p + Vector((0, 0, z)), sd.yaw)
            elif ci["arc"] or ci["post"]:
                self.emit_corner(ci, sd, a, z, hh, layer_h=hh, band=band, mat=mat)
            elif ci.get("block") and layer == "parapet":
                V = sd.p
                sb, ea = ci["start_B"], max(ci["end_A"], 0.05)
                quad = [V, V + sd.t * sb, V + sd.t * sb + sd.n * ea, V + sd.n * ea]
                if signed_area(quad) < 0:
                    quad.reverse()
                self.proc.prism([quad], z, z + hh, MAT_PARAPET)
