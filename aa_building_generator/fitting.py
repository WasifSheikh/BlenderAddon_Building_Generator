"""Fitting modules into a span: exact width combinations first, gentle stretching otherwise.
With rigid modules: whole modules at their own width only, any leftover reported back."""

import math

from .kit import Mod
from .tuning import MAX_STRETCH


def _copy_mod(m):
    c = Mod()
    for a in Mod.__slots__:
        if hasattr(m, a):
            setattr(c, a, getattr(m, a))
    return c


def bitmask_fill(target_cm, widths_cm):
    """Unbounded subset-sum reachability as a big-int bitset."""
    full = (1 << (target_cm + 2)) - 1
    reach = 1
    for _ in range(target_cm // max(1, min(widths_cm)) + 2):
        new = reach
        for w in widths_cm:
            new |= (reach << w)
        new &= full
        if new == reach:
            break
        reach = new
    return reach


def weighted_choice(rng, items, weights):
    total = sum(weights)
    if total <= 0:
        return rng.choice(items)
    r = rng.random() * total
    for it, w in zip(items, weights):
        r -= w
        if r <= 0:
            return it
    return items[-1]


def fill_span(L, pool, rng, door=None, max_stretch=MAX_STRETCH):
    """Pick modules for a span of length L. Returns (sequence, scale) or (None, 1) when a filler is needed."""
    if L < 0.05:
        return [], 1.0
    pool = [m for m in pool if m.weight > 0 and m.w > 0.05]
    if not pool:
        return None, 1.0
    rest = L - (door.w if door else 0.0)
    seq = []
    if rest > 0.05:
        widths = sorted({int(round(m.w * 100)) for m in pool})
        tcm = int(round(rest * 100))
        hit = None
        if tcm <= 60000:
            reach = bitmask_fill(tcm + 1, widths)
            for cand in (tcm, tcm - 1, tcm + 1):
                if cand > 0 and (reach >> cand) & 1:
                    hit = cand
                    break
        if hit is not None:
            rem = hit
            guard = 0
            while rem > 0 and guard < 10000:
                guard += 1
                opts = [m for m in pool if int(round(m.w * 100)) <= rem and (reach >> (rem - int(round(m.w * 100)))) & 1]
                if not opts:
                    break
                m = weighted_choice(rng, opts, [o.weight for o in opts])
                seq.append(m)
                rem -= int(round(m.w * 100))
            rng.shuffle(seq)
        else:
            avg = sum(m.w * m.weight for m in pool) / max(sum(m.weight for m in pool), 1e-9)
            best = None
            for n in {max(1, int(rest / avg)), max(1, int(round(rest / avg))), int(rest / avg) + 1}:
                for _ in range(12):
                    cand = [weighted_choice(rng, pool, [o.weight for o in pool]) for _ in range(n)]
                    sc = rest / sum(m.w for m in cand)
                    score = abs(math.log(sc))
                    if best is None or score < best[0]:
                        best = (score, cand)
            seq = best[1]
    if door:
        pos = len(seq) // 2 if len(seq) < 3 else rng.randint(1, len(seq) - 1)
        seq.insert(pos, door)
    total = sum(m.w for m in seq)
    if total <= 0:
        return None, 1.0
    scale = L / total
    if scale < 1.0 - max_stretch * 1.4 or scale > 1.0 + max_stretch * 2:
        if len(seq) == 1 and 0.5 < scale < 1.8:
            return seq, scale
        return None, 1.0
    return seq, scale


# ---- rigid modules: every module keeps its own width

def width_cm(m):
    return int(round(m.w * 100))


def rigid_w(m):
    """A module's width on the centimetre grid: rigid layouts add these up, so runs never drift."""
    return width_cm(m) / 100.0


def _walk(rng, pool, reach, total):
    """A random module mix adding up to exactly `total` cm (reach must contain it)."""
    seq = []
    rem = total
    guard = 0
    while rem > 0 and guard < 10000:
        guard += 1
        opts = [m for m in pool if width_cm(m) <= rem and (reach >> (rem - width_cm(m))) & 1]
        if not opts:
            break
        m = weighted_choice(rng, opts, [o.weight for o in opts])
        seq.append(m)
        rem -= width_cm(m)
    rng.shuffle(seq)
    return seq


def rigid_fill(L, pool, rng, door=None, helpers=()):
    """Whole modules at their own width, never stretched.
    Returns (sequence, lead, tail): the modules cover L except `lead` at the start and `tail` at the end
    (both 0 when they fit exactly). `helpers` (wall pieces) are only added when the pool alone can't fit
    exactly: next to the door, or at the ends without one. Returns (None, 0, 0) when nothing fits."""
    pool = [m for m in pool if m.weight > 0 and m.w > 0.05]
    Lcm = int(round(L * 100))
    if Lcm <= 0:
        return [], 0.0, 0.0
    if door is not None and width_cm(door) > Lcm:
        door = None
    T = Lcm - (width_cm(door) if door is not None else 0)
    if not pool and door is None:
        return None, 0.0, 0.0
    seq, extra, got = [], [], 0
    if T > 0 and pool:
        widths = sorted({width_cm(m) for m in pool})
        reach = bitmask_fill(T + 1, widths) if T <= 60000 else 1
        if (reach >> T) & 1:
            got = T
        else:
            hp = [m for m in helpers if m.weight > 0 and m.w > 0.05]
            hw = sorted({width_cm(m) for m in hp})
            combos = [(a,) for a in hw] + [(a, b) for i, a in enumerate(hw) for b in hw[i:]]
            for c in combos:        # fewest helper pieces first
                if sum(c) <= T and (reach >> (T - sum(c))) & 1:
                    for wcm in c:
                        same = [m for m in hp if width_cm(m) == wcm]
                        extra.append(weighted_choice(rng, same, [m.weight for m in same]))
                    got = T - sum(c)
                    break
            else:
                got = next((t for t in range(T, 0, -1) if (reach >> t) & 1), 0)   # most whole modules that fit
        seq = _walk(rng, pool, reach, got) if got > 0 else []
    if door is not None:
        pos = len(seq) // 2 if len(seq) < 3 else rng.randint(1, len(seq) - 1)
        seq[pos:pos] = extra[:1] + [door] + extra[1:]   # walls added for the fit stand next to the entrance
    elif extra:
        seq = extra[:1] + seq + extra[1:]                # no entrance: at the ends of the run
    if not seq:
        return None, 0.0, 0.0
    left = (Lcm - sum(width_cm(m) for m in seq)) / 100.0
    lead = round(left / 2, 4)
    return seq, lead, left - lead
