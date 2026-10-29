"""Tuning values used while planning a building. Changing one changes every building that uses it."""

# fitting modules into a span
MAX_STRETCH = 0.3              # how far facade modules may stretch or squash to fill a span
LINE_MAX_STRETCH = 0.45        # the same for cornices, belts and parapets
WALL_MIX_WEIGHT = 2.0          # at "Blank wall mix" 0.5 a blank wall is as likely as a window

# rigid modules (modules keep their own width, the footprint snaps to whole modules)
RIGID_TOL = 0.005              # a leftover narrower than this (m) needs no filler strip
SNAP_MIN_SIDE = 0.3            # snapping never makes a side shorter than this (m)
SNAP_MAX_STEP = 2400           # the snap step never grows past this (cm), however the floors combine

# entrances
ENTRANCE_MIN_EXTRA = 2.0       # a Windows side gets an entrance when it is this much longer than the door
SHOP_ENTRANCE_MIN_SIDE = 6.0   # a Shop side without storefront modules gets an entrance when longer than this

# pilasters
PILASTER_STRETCH = (0.6, 1.6)  # window bays may stretch this much between pilasters
PILASTER_END_MARGIN = 0.3      # ground pilasters keep this far from the ends of the ground floor

# horizontal lines and slabs
BELT_DROP = 0.08               # the belt course sits this far below the top of the ground floor
PARAPET_FALLBACK_H = 0.6       # procedural parapet (kit has none): height
PARAPET_FALLBACK_T = 0.22      # ... and thickness
FLOOR_SLAB_T = 0.12            # interior floor slab thickness

# extras (heights as a share of the floor height)
SIGN_Z = 0.84
AWNING_Z = 0.77
LIGHT_Z = 0.73
AC_Z = 0.12
AC_ALONG = 0.66                # wall AC units sit at this share of the window width
DECOR_FIT = 0.16               # a sign / awning fits a run of shop fronts within this width tolerance
BALCONY_FIT = (0.8, 1.25)      # balconies stretch within this range, otherwise keep their own width
FIRE_MIN_EXTRA = 0.5           # a fire escape needs the side to be this much longer than its landing
PIPE_MIN_SIDE = 4.0
PIPE_CHANCE = 0.6
PIPE_INSET = 0.25              # drainpipes sit this far from the corner
ROOF_PROP_AREA = 45.0          # roof area per prop at "Roof props" 0.5
ROOF_PROP_GAP = 0.4            # minimum gap between roof props

# ground-floor variety
UNIT_SIGN_STRETCH = (0.45, 2.2)  # a shop unit's sign / awning may stretch this much to span the unit
SHUTTER_INSET = 0.06             # generated roller shutter: side inset as a share of the shop front width
SHUTTER_HEIGHT_SHARE = 0.75      # ... its height as a share of the floor height
SHUTTER_MAX_H = 3.0              # ... but never taller than this
RECESS_REVEAL_T = 0.08           # side walls of a recessed entrance
RECESS_SOFFIT_T = 0.1            # ceiling of a recessed entrance

# damage
ROOFLINE_GAP_SHARE = 0.45        # at Damage 1, this share of cornice / parapet pieces is missing
BOARDED_SHARE = 0.5              # at Damage 1, this share of windows is boarded up
RUBBLE_SPACING = 5.0             # at Damage 1, one rubble pile per this many metres of side

# floor stack (segments with chosen modules)
BAY_STRETCH = (0.55, 1.8)        # chosen modules stretch at most this much to share bays with the floors above / below
DOOR_BAY_STRETCH = (0.75, 1.34)  # an entrance stretches to fill its bay within this range, otherwise walls fill around it

# areaways (basement light wells)
AREAWAY_ENTRANCE_CLEAR = 0.15    # areaways stop this far from either side of an entrance
AREAWAY_MIN_SHARE = 0.6          # a gap shorter than this share of the narrowest areaway module stays empty
