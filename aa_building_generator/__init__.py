"""AA Building Generator: live modular buildings from an editable outline and a module kit.

How it works
* A building is one mesh object: its outline (edges or flat faces) is the footprint.
  A Geometry Nodes modifier shows the generated building on top of it, live.
* Each side (outline edge) carries a style stored as an edge attribute, so styles
  survive vertex edits, extrudes and subdivides.
* Python plans the building (which module goes where) and writes the plan into a
  hidden "data" mesh; the modifier instances the kit modules from that data.
* Nothing needs to fit exactly: spans are filled with the best module mix and
  gently stretched; corners, roof, slabs and parapets are handled automatically.
  With Rigid modules on, modules keep their exact width and the footprint snaps
  to whole modules instead.

Package layout (each module only imports the ones listed before it)
  common      shared constants, side styles, runtime state
  naming      categories and name parsing
  geometry    2D helpers, procedural mesh builder
  kit         kit analysis
  outline     footprint reading
  tuning      named tuning values (stretch limits, extra heights, margins)
  fitting     filling a span with modules
  storefronts ground-floor variety: shop units, shutters, recessed entrances
  damage      damaged variants, boarded windows, broken roofline, rubble
  facades     facade spans, bays with dividers, chosen modules, ground floor
  lines       belt course, cornice, parapet
  extras      signs, awnings, lights, AC, balconies, fire escapes, pipes, roof props
  areaways    basement light wells along the base of the facade
  rigid       rigid modules: footprint snapping to whole modules
  planner     the Plan: floor stack, corners, roof, and the order everything is placed in
  nodes       data mesh, Geometry Nodes group, modifier
  runtime     rebuild queue and handlers
  props       property groups
  export      FBX export for Unity with a collider shell
  operators   operators
  validate    kit checker (Check Kit)
  sample_kit  placeholder kit
  ui          panels and overlay
  selftest    regression self-test (F3: AA Buildings: Self-Test)
"""

if "bpy" in locals():   # "Reload Scripts" / re-enable: pick up edits in every module, in dependency order
    import importlib
    from . import common, naming, geometry, kit, outline, tuning, fitting, storefronts, damage, facades, lines, extras, areaways, rigid, planner, nodes, runtime, props, export, operators, validate, sample_kit, ui, selftest
    for _m in (common, naming, geometry, kit, outline, tuning, fitting, storefronts, damage, facades, lines, extras, areaways, rigid, planner, nodes, runtime, props, export, operators, validate, sample_kit, ui, selftest):
        importlib.reload(_m)

import bpy

from .common import _state
from .runtime import _on_depsgraph, _on_load, _on_undo, _tick, request_all
from .props import AAB_BuildingProps, AAB_KitProps, AAB_ModuleProps, AAB_SceneProps, AAB_SegmentProps
from .operators import (
    AAB_OT_add,
    AAB_OT_bake,
    AAB_OT_fire,
    AAB_OT_fix_uvs,
    AAB_OT_hide_kit,
    AAB_OT_make,
    AAB_OT_make_modules,
    AAB_OT_move_out,
    AAB_OT_refresh,
    AAB_OT_remove,
    AAB_OT_reseed,
    AAB_OT_round,
    AAB_OT_segment_add,
    AAB_OT_snap_outline,
    AAB_OT_segment_move,
    AAB_OT_segment_remove,
    AAB_OT_style,
)
from .sample_kit import AAB_OT_sample_kit
from .export import AAB_OT_export_unity
from .validate import AAB_OT_check_kit
from .selftest import AAB_OT_self_test
from .ui import AAB_PT_kit, AAB_PT_main, AAB_UL_segments, _draw_handles, _draw_px, _draw_view


CLASSES = (
    AAB_ModuleProps, AAB_KitProps, AAB_SegmentProps, AAB_BuildingProps, AAB_SceneProps,
    AAB_OT_add, AAB_OT_make, AAB_OT_remove, AAB_OT_style, AAB_OT_fire, AAB_OT_round, AAB_OT_reseed, AAB_OT_snap_outline,
    AAB_OT_refresh, AAB_OT_bake, AAB_OT_make_modules, AAB_OT_hide_kit, AAB_OT_sample_kit,
    AAB_OT_move_out, AAB_OT_fix_uvs, AAB_OT_segment_add, AAB_OT_segment_remove, AAB_OT_segment_move,
    AAB_OT_self_test, AAB_OT_export_unity, AAB_OT_check_kit,
    AAB_UL_segments, AAB_PT_main, AAB_PT_kit,
)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Collection.aa_module = bpy.props.PointerProperty(type=AAB_ModuleProps)
    bpy.types.Collection.aa_kit = bpy.props.PointerProperty(type=AAB_KitProps)
    bpy.types.Object.aa_building = bpy.props.PointerProperty(type=AAB_BuildingProps)
    bpy.types.Scene.aa_build = bpy.props.PointerProperty(type=AAB_SceneProps)
    for h, lst in ((_on_depsgraph, bpy.app.handlers.depsgraph_update_post), (_on_load, bpy.app.handlers.load_post),
                   (_on_undo, bpy.app.handlers.undo_post), (_on_undo, bpy.app.handlers.redo_post)):
        if h not in lst:
            lst.append(h)
    _draw_handles.append((bpy.types.SpaceView3D.draw_handler_add(_draw_view, (), "WINDOW", "POST_VIEW"), "WINDOW"))
    _draw_handles.append((bpy.types.SpaceView3D.draw_handler_add(_draw_px, (), "WINDOW", "POST_PIXEL"), "WINDOW"))
    bpy.app.timers.register(lambda: (request_all(), None)[1], first_interval=0.2)


def unregister():
    for h, region in _draw_handles:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(h, region)
        except Exception:
            pass
    _draw_handles.clear()
    for h, lst in ((_on_depsgraph, bpy.app.handlers.depsgraph_update_post), (_on_load, bpy.app.handlers.load_post),
                   (_on_undo, bpy.app.handlers.undo_post), (_on_undo, bpy.app.handlers.redo_post)):
        while h in lst:
            lst.remove(h)
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    for attr, typ in (("aa_module", bpy.types.Collection), ("aa_kit", bpy.types.Collection),
                      ("aa_building", bpy.types.Object), ("aa_build", bpy.types.Scene)):
        if hasattr(typ, attr):
            delattr(typ, attr)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
    _state["kits"].clear()
    _state["sigs"].clear()
