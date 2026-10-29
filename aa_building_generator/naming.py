"""Module categories and everything read from names: roles, floors, sizes, radii."""

import re
import unicodedata


ROLE_DEFS = [
    ("AUTO", "Auto-detect", "Guess the category from the module and folder names"),
    ("storefront", "Storefront", "Ground-floor shop front (shop doors included)"),
    ("door", "Door / entrance", "Entrance or service door"),
    ("window", "Window façade", "Façade with windows"),
    ("wall", "Plain wall", "Solid wall piece"),
    ("corner", "Corner piece", "Corner module (sharp pier, rounded corner, cap)"),
    ("corner_trim", "Corner trim / quoin", "Decoration placed on sharp corners"),
    ("cornice", "Cornice / belt", "Horizontal trim along the roof line or between floors"),
    ("parapet", "Parapet", "Low wall along the roof edge"),
    ("awning", "Awning / canopy", "Shade above storefronts"),
    ("sign", "Shop sign", "Fascia / sign above storefronts"),
    ("ac", "Wall AC unit", "Air conditioner hung on upper façades"),
    ("light", "Wall light", "Lantern / sconce on storefronts"),
    ("pipe", "Drainpipe", "Downpipe running up the façade"),
    ("balcony", "Balcony", "Balcony on upper windows"),
    ("roof_prop", "Roof prop", "AC unit, vent, chimney, water tank ..."),
    ("roof_tile", "Roof surface", "Gives the roof its material and thickness"),
    ("fire_landing", "Fire-escape landing", "Landing platform on each upper floor"),
    ("fire_stair", "Fire-escape stair", "Stair flight between landings"),
    ("fire_ladder", "Fire-escape ladder", "Drop ladder from the first landing"),
    ("ignore", "Ignore", "Not used by the generator"),
    ("pilaster", "Pilaster / bay divider", "Vertical strip placed between window bays, never at the ends of a side"),
    ("shutter", "Shutter", "Roller shutter placed over closed shop fronts"),
    ("rubble", "Rubble / debris", "Piled along the base of damaged buildings"),
    # new categories go at the end: saved categories are stored by position
    ("areaway", "Areaway / light well", "Sunken basement light well with railing, laid along the base of the facade"),
]


ROLE_LABEL = {k: v for k, v, _ in ROLE_DEFS}


FLOOR_DEFS = [
    ("AUTO", "Auto", "Decide from the module height and name"),
    ("ground", "Ground floor", ""),
    ("upper", "Upper floors", ""),
    ("any", "Any floor", ""),
]


OLD_ROLES = {
    "normal_floor": "window", "storefront": "storefront", "wall": "wall", "corner": "corner",
    "entrance": "door", "stairs": "fire_stair", "stair_landing": "fire_landing", "ac": "ac",
    "roof_prop": "roof_prop", "vent": "roof_prop", "shade": "awning", "shop_asset": "ignore",
    "floor_slab": "ignore", "roof_slab": "roof_tile", "roof_edge": "parapet", "cornice": "cornice",
    "balcony": "balcony", "sign": "sign", "drain": "pipe",
}


# (role, token combos, tokens that veto the rule). Order matters.
NAME_RULES = [
    ("ignore", [("label",), ("assembly",), ("street",), ("sidewalk",), ("curb",), ("kerb",), ("bin",),
                ("mailbox",), ("planter",), ("tree",), ("bench",), ("bollard",), ("hydrant",),
                ("specification",), ("floor", "slab"), ("extra",), ("preview",), ("reference",)], ()),
    ("pilaster", [("pilaster",), ("lesene",), ("divider",)], ()),
    ("shutter", [("shutter",), ("rollershutter",)], ()),
    ("rubble", [("rubble",), ("debris",)], ()),
    ("areaway", [("areaway",), ("area", "way"), ("lightwell",), ("light", "well")], ("corner",)),
    ("fire_landing", [("landing",), ("fire", "platform"), ("fire", "balcony")], ()),
    ("fire_ladder", [("ladder",)], ()),
    ("fire_stair", [("stair",), ("fire", "escape"), ("fireescape",), ("staircase",)], ()),
    ("corner_trim", [("quoin",)], ()),
    ("corner", [("corner",), ("rounded",), ("outside",), ("pier",), ("pillar",), ("return",), ("column",)], ()),
    ("corner", [("round",), ("curved",), ("curve",)],
     ("awning", "canopy", "shade", "sign", "balcony", "lamp", "light", "pipe", "tank", "table", "window", "door")),
    ("parapet", [("parapet",), ("roofedge",), ("roof", "edge")], ()),
    ("cornice", [("cornice",), ("belt",), ("course",), ("molding",), ("moulding",)], ()),
    ("cornice", [("trim",)], ("window", "door", "frame", "sill", "architrave")),
    ("roof_tile", [("roof", "tile"), ("roof", "slab"), ("roof", "strip"), ("roof", "surface"),
                   ("roofslab",), ("membrane",), ("roofing",)], ()),
    ("roof_prop", [("roof",), ("chimney",), ("tank",), ("watertank",), ("hvac",), ("vent",),
                   ("antenna",), ("skylight",), ("dish",), ("exhaust",)], ()),
    ("wall", [("between",), ("spacer",)], ()),   # Wall_Between_Window: the wall piece set between windows
    ("window", [("balcony", "door"), ("balcony", "window"), ("french", "door"), ("french", "window")], ()),
    ("awning", [("awning",), ("canopy",), ("shade",)], ()),
    ("sign", [("sign",), ("fascia",), ("signage",), ("billboard",)],
     ("shopfront", "storefront", "display", "window", "door")),
    ("storefront", [("storefront",), ("shopfront",), ("shop",), ("store",), ("display",), ("retail",)], ()),
    ("door", [("door",), ("entrance",), ("entry",), ("service",), ("gate",)], ()),
    ("light", [("lantern",), ("light",), ("sconce",), ("lamp",)], ()),
    ("pipe", [("pipe",), ("drainpipe",), ("downpipe",), ("gutter",), ("drain",)], ()),
    ("ac", [("ac",), ("aircon",), ("condenser",), ("airconditioner",)], ()),
    ("balcony", [("balcony",), ("railing",)], ()),
    ("window", [("window",), ("facade",)], ()),
    ("wall", [("wall",), ("blank",), ("solid",), ("infill",), ("plaster",), ("brick",)], ()),
]


SOCKET_RULES = [
    ("awning", {"shade", "awning", "canopy"}),
    ("sign", {"sign", "fascia"}),
    ("ac", {"ac", "aircon"}),
    ("light", {"light", "lamp", "lantern"}),
    ("balcony", {"balcony"}),
    ("pipe", {"pipe", "drain", "gutter"}),
]


def tokens(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"\.\d{3}$", "", s)
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    out = set()
    for w in re.findall(r"[A-Za-z]+", s.lower()):
        out.add(w)
        if w.endswith("ies") and len(w) > 4:
            out.add(w[:-3] + "y")
        elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
            out.add(w[:-1])
    return out


def role_from_tokens(t):
    for role, combos, veto in NAME_RULES:
        if veto and t.intersection(veto):
            continue
        for combo in combos:
            if all(c in t for c in combo):
                return role
    return None


def name_numbers(name):
    s = re.sub(r"\.\d{3}$", "", name)
    m = re.search(r"(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)(?:\s*[xX×]\s*(\d+(?:\.\d+)?))?", s)
    if m:
        vals = [float(v) for v in m.groups() if v]
    else:
        vals = [float(v) for v in re.findall(r"(?<![A-Za-z\d.])(\d+(?:\.\d+)?)(?![\d.])", s)]
    return [v / 100.0 if v >= 10 else v for v in vals if v > 0]


def name_radius(name):
    m = re.search(r"(?:^|[_\s\-|])R(\d+(?:\.\d+)?)", name)
    if not m:
        return None
    v = float(m.group(1))
    return v / 100.0 if v >= 10 else v


ROUND_WORDS = {"round", "rounded", "curved", "curve"}

# a module whose name (or folder) holds one of these is a damaged variant of the undamaged module of the same width
DAMAGE_WORDS = {"broken", "damaged", "boarded", "burnt", "burned", "ruined", "ruin", "destroyed", "cracked",
                "wrecked", "charred", "smashed"}

# a corner piece with one of these in its name (or folder) belongs to the areaway line
AREAWAY_WORDS = {"areaway", "lightwell"}


def is_areaway_tokens(t):
    return bool(t & AREAWAY_WORDS) or {"area", "way"} <= t or {"light", "well"} <= t


# wall pieces made to stand between windows: preferred as dividers in "Wall" mode
BETWEEN_WORDS = {"between", "spacer", "divider", "narrow"}
