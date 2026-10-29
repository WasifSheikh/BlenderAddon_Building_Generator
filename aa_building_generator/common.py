"""Shared constants, side styles and runtime state."""

import random


MOD_NAME = "AA Building"


GEOM_TYPES = {"MESH", "CURVE", "FONT", "SURFACE", "META"}


EPS = 1e-6


# Side styles stored per outline edge (attribute "aa_style").
STYLE_AUTO, STYLE_SHOP, STYLE_WINDOWS, STYLE_BACK, STYLE_BLANK, STYLE_OPEN = range(6)


STYLE_INFO = {
    STYLE_AUTO: ("Auto", "Uses the building's default ground floor", "DOT", (0.75, 0.75, 0.75, 1.0)),
    STYLE_SHOP: ("Shop", "Storefronts on the ground floor, windows above", "TAG", (0.15, 0.95, 0.55, 1.0)),
    STYLE_WINDOWS: ("Windows", "Windows on every floor, with an entrance", "MOD_LATTICE", (0.3, 0.7, 1.0, 1.0)),
    STYLE_BACK: ("Back", "Plain ground floor with a service door, windows above", "HOME", (1.0, 0.9, 0.2, 1.0)),
    STYLE_BLANK: ("Blank", "Solid walls on every floor", "MESH_PLANE", (0.75, 0.45, 1.0, 1.0)),
    STYLE_OPEN: ("Open", "No wall on this side", "X", (1.0, 0.25, 0.25, 1.0)),
}


GROUND_DEFAULT_ITEMS = [
    ("SHOP", "Shops", "Storefronts on the ground floor"),
    ("WINDOWS", "Windows", "Windows on the ground floor"),
    ("BACK", "Back / service", "Plain wall with a service door"),
    ("BLANK", "Blank", "Solid wall"),
]


GROUND_DEFAULT_STYLE = {"SHOP": STYLE_SHOP, "WINDOWS": STYLE_WINDOWS, "BACK": STYLE_BACK, "BLANK": STYLE_BLANK}


def _rng(*key):
    """Deterministic random generator: same seed, same building, in every Blender session."""
    return random.Random("|".join(str(k) for k in key))


_state = {
    "dirty": set(),
    "busy": False,
    "sigs": {},
    "kits": {},          # kit root name -> Kit
    "kit_objects": {},   # object name -> kit root name
    "kit_cols": {},      # collection name -> kit root name
    "kit_version": 0,
    "failed": {},        # object name -> inputs signature of the last rebuild that raised
}


def is_building(obj):
    return obj is not None and obj.type == "MESH" and getattr(obj, "aa_building", None) is not None and obj.aa_building.enabled
