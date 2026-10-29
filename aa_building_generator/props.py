"""Property groups stored on objects, collections and scenes."""

import bpy

from .common import GROUND_DEFAULT_ITEMS, _state
from .naming import FLOOR_DEFS, ROLE_DEFS
from .runtime import invalidate_kits, request


def _upd_building(self, context):
    request(self.id_data.name)


def _upd_kit(self, context):
    invalidate_kits(None)


LAYOUT_ITEMS = [
    ("AUTO", "Kit mix", "Let the generator mix the kit's modules, as before"),
    ("SINGLE", "One module", "Use one module across the whole floor"),
    ("CORNER", "Corner + middle", "One module next to the corners, another one in between"),
]


def _module_poll(roles):
    """Pointer filter: only module collections of the building's kit with one of these categories."""
    def poll(self, col):
        obj = self.id_data
        b = getattr(obj, "aa_building", None)
        root = b.kit if b is not None else None
        if root is None or col == root or col not in root.children_recursive:
            return False
        kit = _state["kits"].get(root.name)
        if kit is None:
            return True
        m = kit.by_name.get(col.name)
        r = roles(self) if callable(roles) else roles
        return m is not None and m.role in r
    return poll


FLOOR_ROLES = ("window", "wall")
GROUND_ROLES = ("window", "wall", "storefront", "door")
DOOR_ROLES = ("door", "storefront")


class AAB_SegmentProps(bpy.types.PropertyGroup):
    """One segment of the upper-floor stack: a run of floors that share their modules."""
    floors: bpy.props.IntProperty(name="Floors", default=1, min=1, max=60, update=_upd_building,
                                  description="How many floors this segment covers")
    layout: bpy.props.EnumProperty(name="Modules", items=LAYOUT_ITEMS, default="SINGLE", update=_upd_building)
    module: bpy.props.PointerProperty(name="Module", type=bpy.types.Collection, update=_upd_building,
                                      poll=_module_poll(FLOOR_ROLES),
                                      description="Window or wall module for this floor (the middle bays with Corner + middle)")
    corner_module: bpy.props.PointerProperty(name="Corner module", type=bpy.types.Collection, update=_upd_building,
                                             poll=_module_poll(FLOOR_ROLES),
                                             description="Module for the bays next to the corners (empty = the middle module)")
    height: bpy.props.FloatProperty(name="Floor height", default=0.0, min=0.0, max=20, unit="LENGTH", update=_upd_building,
                                    description="0 = the building's upper floor height")
    belt_below: bpy.props.BoolProperty(name="Belt cornice below", default=False, update=_upd_building,
                                       description="Run a belt cornice along the bottom of this segment")


class AAB_ModuleProps(bpy.types.PropertyGroup):
    category: bpy.props.EnumProperty(name="Category", items=ROLE_DEFS, default="AUTO", update=_upd_kit)
    floor: bpy.props.EnumProperty(name="Floor", items=FLOOR_DEFS, default="AUTO", update=_upd_kit)
    weight: bpy.props.FloatProperty(name="Frequency", default=1.0, min=0.0, soft_max=5.0, update=_upd_kit,
                                    description="How often this module is picked (0 = never)")


class AAB_KitProps(bpy.types.PropertyGroup):
    front: bpy.props.EnumProperty(
        name="Modules face", default="NEG_Y", update=_upd_kit,
        items=[("NEG_Y", "-Y (front view)", "Outside of each module faces -Y"),
               ("POS_Y", "+Y", "Outside faces +Y"),
               ("NEG_X", "-X", "Outside faces -X"),
               ("POS_X", "+X", "Outside faces +X")])
    scale_mode: bpy.props.EnumProperty(name="Units", default="AUTO", update=_upd_kit,
                                       items=[("AUTO", "Auto", "Metres, or centimetres when modules are huge"),
                                              ("CUSTOM", "Custom scale", "")])
    scale: bpy.props.FloatProperty(name="Scale", default=1.0, min=1e-5, update=_upd_kit)
    grid: bpy.props.FloatProperty(name="Grid", default=0.5, min=0.01, unit="LENGTH",
                                  description="Check Kit expects facade module widths to be multiples of this")


def _divider_roles(self):
    return ("wall",) if self.divider_type == "WALL" else ("pilaster",)


class AAB_BuildingProps(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(default=False)
    kit: bpy.props.PointerProperty(name="Kit", type=bpy.types.Collection, update=_upd_building,
                                   description="Collection holding your modules (one child collection per module)")
    floors: bpy.props.IntProperty(name="Floors", default=4, min=1, max=60, update=_upd_building)
    seed: bpy.props.IntProperty(name="Variation", default=1, min=0, update=_upd_building)
    ground_default: bpy.props.EnumProperty(name="Ground floor", items=GROUND_DEFAULT_ITEMS, default="SHOP", update=_upd_building,
                                           description="Ground floor for sides left on Auto")
    vary_floors: bpy.props.BoolProperty(name="Vary each floor", default=False, update=_upd_building,
                                        description="Off: upper floors repeat so windows line up")
    wall_mix: bpy.props.FloatProperty(name="Blank wall mix", default=0.0, min=0, max=1, subtype="FACTOR", update=_upd_building,
                                      description="Mix some solid wall pieces in among the windows. 0 = window sides get windows only")
    rigid: bpy.props.BoolProperty(name="Rigid modules", default=False, update=_upd_building,
                                  description="Modules keep their exact width and are never stretched: the building snaps to whole modules "
                                              "as you edit the outline (new buildings start with this on)")
    round_all: bpy.props.BoolProperty(name="Round all outside corners", default=False, update=_upd_building)
    corner_radius: bpy.props.FloatProperty(name="Corner radius", default=1.5, min=0.2, max=10, unit="LENGTH", update=_upd_building,
                                           description="Used when the kit has no rounded corner modules")
    corner_pieces: bpy.props.BoolProperty(name="Use kit corner pieces", default=True, update=_upd_building)
    cornice: bpy.props.BoolProperty(name="Crown cornice", default=True, update=_upd_building,
                                    description="Cornice along the roof line")
    belt: bpy.props.BoolProperty(name="Belt cornice above ground floor", default=True, update=_upd_building,
                                 description="Belt cornice between the ground floor and the floors above (segments can add more)")
    cornice_module: bpy.props.PointerProperty(name="Crown module", type=bpy.types.Collection, update=_upd_building,
                                              poll=_module_poll(("cornice",)),
                                              description="Crown cornice design (empty = the kit's crown cornices)")
    belt_module: bpy.props.PointerProperty(name="Belt module", type=bpy.types.Collection, update=_upd_building,
                                           poll=_module_poll(("cornice",)),
                                           description="Belt cornice design (empty = the kit's belt cornices, or the crown cornice when the kit has none)")
    parapet: bpy.props.BoolProperty(name="Parapet", default=True, update=_upd_building)
    roof_props: bpy.props.FloatProperty(name="Roof props", default=0.5, min=0, max=1, subtype="FACTOR", update=_upd_building)
    ac: bpy.props.FloatProperty(name="Wall AC units", default=0.2, min=0, max=1, subtype="FACTOR", update=_upd_building)
    awnings: bpy.props.FloatProperty(name="Awnings", default=0.7, min=0, max=1, subtype="FACTOR", update=_upd_building)
    signs: bpy.props.BoolProperty(name="Shop signs", default=True, update=_upd_building)
    sign_chance: bpy.props.FloatProperty(name="Shop signs", default=1.0, min=0, max=1, subtype="FACTOR", update=_upd_building,
                                         description="Share of shop fronts (and sign sockets) that get a sign")
    lights: bpy.props.FloatProperty(name="Wall lights", default=0.4, min=0, max=1, subtype="FACTOR", update=_upd_building)
    balconies: bpy.props.FloatProperty(name="Balconies", default=0.0, min=0, max=1, subtype="FACTOR", update=_upd_building)
    pipes: bpy.props.BoolProperty(name="Drainpipes", default=True, update=_upd_building)
    quoins: bpy.props.BoolProperty(name="Corner trims", default=True, update=_upd_building)
    pilasters: bpy.props.BoolProperty(name="Dividers between windows", default=True, update=_upd_building,
                                      description="Put a divider (pilaster or wall piece) between window bays, never at the ends of a side")
    divider_type: bpy.props.EnumProperty(name="Divider", default="PILASTER", update=_upd_building, items=[
        ("PILASTER", "Pilaster", "The kit's pilaster modules between windows"),
        ("WALL", "Wall", "A wall piece between windows (Wall_Between_... modules, or the narrowest wall)")])
    divider_module: bpy.props.PointerProperty(name="Divider module", type=bpy.types.Collection, update=_upd_building,
                                              poll=_module_poll(_divider_roles),
                                              description="Divider design (empty = picked from the kit)")
    pilaster_ground: bpy.props.BoolProperty(name="Run through ground floor", default=True, update=_upd_building,
                                            description="Continue the dividers down through the ground floor")
    # ground floor: shop fronts, or a ground floor of chosen modules
    ground_mode: bpy.props.EnumProperty(name="Ground floor type", default="STOREFRONT", update=_upd_building, items=[
        ("STOREFRONT", "Storefront", "Shop fronts on Shop sides; the side styles decide each side"),
        ("GROUND", "Ground floor", "No shops: a ground floor built from the modules you choose, with an entrance")])
    ground_layout: bpy.props.EnumProperty(name="Modules", items=LAYOUT_ITEMS, default="AUTO", update=_upd_building)
    ground_module: bpy.props.PointerProperty(name="Module", type=bpy.types.Collection, update=_upd_building,
                                             poll=_module_poll(GROUND_ROLES),
                                             description="Ground floor module (the middle bays with Corner + middle)")
    ground_corner_module: bpy.props.PointerProperty(name="Corner module", type=bpy.types.Collection, update=_upd_building,
                                                    poll=_module_poll(GROUND_ROLES),
                                                    description="Module for the ground bays next to the corners (empty = the middle module)")
    ground_entrance: bpy.props.BoolProperty(name="Entrance", default=True, update=_upd_building,
                                            description="One entrance near the middle of each Windows side")
    ground_door: bpy.props.PointerProperty(name="Entrance module", type=bpy.types.Collection, update=_upd_building,
                                           poll=_module_poll(DOOR_ROLES),
                                           description="Entrance design (empty = picked from the kit's doors)")
    # floor stack: segments of upper floors
    segments: bpy.props.CollectionProperty(type=AAB_SegmentProps)
    segment_index: bpy.props.IntProperty(default=0)
    segment_repeat: bpy.props.BoolProperty(name="Repeat segments", default=False, update=_upd_building,
                                           description="On: the segments repeat up the building. Off: the last segment continues to the roof")
    # areaways
    areaways: bpy.props.BoolProperty(name="Areaways / light wells", default=False, update=_upd_building,
                                     description="Lay the kit's areaway modules along the base of the facade, clear of entrances")
    areaway_shops: bpy.props.BoolProperty(name="Also on shop sides", default=False, update=_upd_building,
                                          description="Put areaways in front of shop fronts too")
    shop_units: bpy.props.BoolProperty(name="Matching shop units", default=False, update=_upd_building,
                                       description="Group shop fronts into units of a few bays that share one design, one sign and one awning style")
    shop_unit_max: bpy.props.IntProperty(name="Bays per unit", default=3, min=1, max=6, update=_upd_building,
                                         description="Largest shop unit, in shop-front bays")
    closed_shops: bpy.props.FloatProperty(name="Closed shops", default=0.0, min=0, max=1, subtype="FACTOR", update=_upd_building,
                                          description="Share of shop fronts behind a shutter (the kit's Shutter modules, or a generated roller shutter)")
    recessed_doors: bpy.props.FloatProperty(name="Recessed entrances", default=0.0, min=0, max=1, subtype="FACTOR", update=_upd_building,
                                            description="Share of entrances set back into the facade, lined with side walls and a soffit")
    recess_depth: bpy.props.FloatProperty(name="Recess depth", default=0.8, min=0.2, max=3.0, unit="LENGTH", update=_upd_building)
    damage: bpy.props.FloatProperty(name="Damage", default=0.0, min=0, max=1, subtype="FACTOR", update=_upd_building,
                                    description="Wear and ruin: damaged module variants, boarded windows, a broken roofline and rubble")
    boarded_windows: bpy.props.BoolProperty(name="Boarded windows", default=True, update=_upd_building)
    broken_roofline: bpy.props.BoolProperty(name="Broken roofline", default=True, update=_upd_building,
                                            description="Leave gaps in the cornice and parapet")
    rubble: bpy.props.BoolProperty(name="Rubble", default=True, update=_upd_building,
                                   description="Pile rubble along the base (the kit's Rubble modules, or generated chunks)")
    interior_floors: bpy.props.BoolProperty(name="Interior floor slabs", default=True, update=_upd_building)
    ground_height: bpy.props.FloatProperty(name="Ground floor height", default=0.0, min=0.0, max=20, unit="LENGTH", update=_upd_building,
                                           description="0 = from the kit")
    upper_height: bpy.props.FloatProperty(name="Upper floor height", default=0.0, min=0.0, max=20, unit="LENGTH", update=_upd_building,
                                          description="0 = from the kit")
    wall_material: bpy.props.PointerProperty(name="Wall material", type=bpy.types.Material, update=_upd_building)
    roof_material: bpy.props.PointerProperty(name="Roof material", type=bpy.types.Material, update=_upd_building)
    data_obj: bpy.props.PointerProperty(type=bpy.types.Object)
    status: bpy.props.StringProperty()
    show_extras: bpy.props.BoolProperty(name="Details & extras", default=False)


class AAB_SceneProps(bpy.types.PropertyGroup):
    kit: bpy.props.PointerProperty(name="Kit for new buildings", type=bpy.types.Collection)
    show_kit: bpy.props.BoolProperty(name="Kit modules", default=False)
    show_overlay: bpy.props.BoolProperty(name="Show side labels in Edit Mode", default=True)
    export_dir: bpy.props.StringProperty(name="Export folder", default="//Unity_Export/", subtype="DIR_PATH",
                                         description="Where Export FBX for Unity writes its files (// = next to the .blend)")
    export_at_origin: bpy.props.BoolProperty(name="At origin", default=True,
                                             description="Export each building at the world origin (prefab friendly)")
    export_collider: bpy.props.EnumProperty(name="Collider", default="SHELL", items=[
        ("SHELL", "Collider shell", "Add a closed low-poly shell around the footprint, named <Building>_Collider"),
        ("NONE", "No collider", "Export the visible mesh only")])
