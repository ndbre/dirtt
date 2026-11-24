"""
D.I.R.T.T. probe holder v2: holds the SEN0604 soil sensor on the 20 mm actuator rod.

What changed from v1 (DIRTT_probe_holder.stl):
  - Rod socket for the real actuator: 20.4 mm bore, 21 mm deep (24 mm of rod shows when fully
    retracted, so 3 mm stays clear of the actuator's end cap). The rod tip pushes on the socket
    floor; an M4 x 16 bolt from the back goes into the rod's 6 mm cross-hole and pulls it back up.
  - Sensor held by bolts instead of a split clamp that PLA is too stiff to close:
      * two M4 x 25 bolts across the bottom, under the ends of the sensor body: it can't slide out
        when the probe is pulled out of the soil
      * two M4 x 12-16 pinch bolts from the back: take up any slack so it doesn't rattle
  - Same sensor pocket cross-section as v1 (45.6 x 15.6 mm), which the team says fits, but the
    sleeve now covers the whole 60 mm body (v1 covered the top 30 mm), so the cross bolts can
    sit under the body's real bottom face.
  - Everything fits inside the tower's base opening (x +/-31, y -14.2..+26 around the rod axis),
    which the holder passes through when the actuator extends.

Coordinates: rod axis = z axis, z = 0 at the v1 pocket's bottom (sensor body from z = -30 to 30), +z up toward the actuator,
+y = back (the side away from the opening's near edge), as in the tower model.

Run:  python3 make_probe_holder_v2.py [out_dir]       (needs trimesh, manifold3d, shapely)
"""
import os
import sys

import numpy as np
import trimesh
from shapely.geometry import Point, box as sbox
from trimesh.creation import cylinder, box

OUT = sys.argv[1] if len(sys.argv) > 1 else "."
SEG = 96

# ---------------- dimensions (mm) ----------------
# sensor pocket (v1, fits)
POCKET_HALF_STRAIGHT = 15.0      # straight part of the rounded slot, each side of centre
POCKET_R = 7.8                   # end radius -> 45.6 x 15.6
POCKET_TOP = 30.0                # ceiling over the sensor (top of the v1 pocket)
BODY_H = 60.0                    # sensor body height; v1 only covered its top 30 mm
BODY_BOTTOM = POCKET_TOP - BODY_H  # z of the sensor's bottom face (-30)
WALL = 3.5
OUT_HALF_STRAIGHT, OUT_R = POCKET_HALF_STRAIGHT, POCKET_R + WALL      # 52.6 x 22.6 outside
SKIRT = 6.0                      # sleeve continues below the sensor body; cross bolts sit here
SLEEVE_BOTTOM = BODY_BOTTOM - SKIRT
CEIL_TOP = 34.0                  # ceiling plate over the sensor, with the cable hole
CABLE_HOLE_D = 12.0
WINDOW_TOP = 59.0                # open window for the cable, between two side pillars
PILLAR_INNER_X = 14.3
TOP_PLATE_TOP = 65.0             # = socket floor (rod tip pushes here)

# rod socket
ROD_D = 20.0
BORE_D = 20.4
SOCKET_DEPTH = 21.0              # < 24 mm of rod showing when retracted
BOSS_R = 13.0                    # 2.8 mm wall; front edge at y = -13 (opening edge at -14.2)
ROD_HOLE_FROM_TIP = 14.5         # centre of the rod's 6 mm hole (24 - 6.5 - 3, from the photos)
PIN_Z = TOP_PLATE_TOP + ROD_HOLE_FROM_TIP
PIN_BLOCK_BACK = 20.5            # back face of the block the rod bolt goes through
PIN_BLOCK_HALF_X = 7.0

# M4
M4_CLEAR = 4.4
M4_TAP = 3.4                     # M4 cuts its own thread in this
NUT_AF, NUT_T = 7.0, 3.2
NUT_SLOT_W = NUT_AF + 0.3
NUT_SLOT_T = NUT_T + 0.25
HEAD_CBORE_D = 8.0               # socket or pan head

# cross bolts under the sensor ends
CROSS_X = 19.0                   # under the rounded ends, clear of the four pins (within +/-13)
CROSS_Z = BODY_BOTTOM - M4_CLEAR / 2   # hole top flush with the sensor's bottom face
CROSS_BOSS_BACK = 16.0
CROSS_CBORE_DEPTH = 3.0          # head sits at y = 13 -> M4 x 25 tip ends at y = -12
FRONT_PAD_Y = -12.7              # front wall thickened at the bottom for the tapped holes

# pinch bolts from the back
PINCH_X = 10.0
PINCH_Z = 15.0
PINCH_BOSS_BACK = 19.0
PINCH_BOSS = (8.0, 24.0)         # z range


def obround(half_straight, r):
    return Point(-half_straight, 0).buffer(r, 64).union(Point(half_straight, 0).buffer(r, 64)).convex_hull


def extrude(poly, z0, z1):
    parts = list(poly.geoms) if hasattr(poly, "geoms") else [poly]
    ms = []
    for p in parts:
        m = trimesh.creation.extrude_polygon(p, z1 - z0)
        m.apply_translation([0, 0, z0])
        ms.append(m)
    return ms[0] if len(ms) == 1 else trimesh.boolean.union(ms, engine="manifold")


def blk(x0, x1, y0, y1, z0, z1):
    b = box(extents=[x1 - x0, y1 - y0, z1 - z0])
    b.apply_translation([(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2])
    return b


def zcyl(r, z0, z1, x=0, y=0):
    c = cylinder(radius=r, height=z1 - z0, sections=SEG)
    c.apply_translation([x, y, (z0 + z1) / 2])
    return c


def ycyl(r, y0, y1, x, z):
    c = cylinder(radius=r, height=y1 - y0, sections=48)
    c.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    c.apply_translation([x, (y0 + y1) / 2, z])
    return c


def U(*ms):
    return trimesh.boolean.union(list(ms), engine="manifold")


def D(a, *ms):
    return trimesh.boolean.difference([a] + list(ms), engine="manifold")


outer = obround(OUT_HALF_STRAIGHT, OUT_R)
pocket = obround(POCKET_HALF_STRAIGHT, POCKET_R)

# ---------------- solid body ----------------
sleeve = extrude(outer, SLEEVE_BOTTOM, CEIL_TOP)
pillars = extrude(outer.difference(sbox(-PILLAR_INNER_X, -50, PILLAR_INNER_X, 50)), CEIL_TOP, WINDOW_TOP)
top_plate = extrude(outer, WINDOW_TOP, TOP_PLATE_TOP)
boss = zcyl(BOSS_R, TOP_PLATE_TOP - 0.01, TOP_PLATE_TOP + SOCKET_DEPTH)
# boss flares out of the top plate at 45 degrees (the plate is only 11.3 deep in y)
flare = trimesh.creation.cone(radius=BOSS_R + 3.0, height=BOSS_R + 3.0, sections=SEG)
flare.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
flare.apply_translation([0, 0, TOP_PLATE_TOP + 1.7])
flare = trimesh.boolean.intersection([flare, zcyl(BOSS_R, TOP_PLATE_TOP - 6, TOP_PLATE_TOP + 0.5)],
                                     engine="manifold")
# block behind the socket for the rod bolt, with a 45-degree underside so it prints without support
from shapely.geometry import Polygon
prof = trimesh.creation.extrude_polygon(
    Polygon([(OUT_R - 0.5, WINDOW_TOP), (OUT_R - 0.5, TOP_PLATE_TOP + SOCKET_DEPTH),
             (PIN_BLOCK_BACK, TOP_PLATE_TOP + SOCKET_DEPTH),
             (PIN_BLOCK_BACK, WINDOW_TOP + (PIN_BLOCK_BACK - OUT_R) + 1.0)]),
    2 * PIN_BLOCK_HALF_X)
# drawn as (y, z) and extruded along the third axis: map (a, b, c) -> (x = c - half, y = a, z = b)
v = prof.vertices
prof = trimesh.Trimesh(np.column_stack([v[:, 2] - PIN_BLOCK_HALF_X, v[:, 0], v[:, 1]]), prof.faces)
if prof.volume < 0:
    prof.invert()
pin_block = prof
# cross-bolt bosses (back) and thickened front at the bottom
cross_bosses = [blk(s * CROSS_X - 6, s * CROSS_X + 6, 0, CROSS_BOSS_BACK, SLEEVE_BOTTOM, CROSS_Z + 8) for s in (-1, 1)]
front_pads = [blk(s * CROSS_X - 6, s * CROSS_X + 6, FRONT_PAD_Y, 0, SLEEVE_BOTTOM, CROSS_Z + 8) for s in (-1, 1)]
pinch_bosses = [blk(s * PINCH_X - 5.5, s * PINCH_X + 5.5, 0, PINCH_BOSS_BACK, *PINCH_BOSS) for s in (-1, 1)]

body = U(sleeve, pillars, top_plate, boss, flare, pin_block, *cross_bosses, *front_pads, *pinch_bosses)

# ---------------- cuts ----------------
cuts = [
    extrude(pocket, SLEEVE_BOTTOM - 1, POCKET_TOP),                                   # sensor pocket, open below
    zcyl(CABLE_HOLE_D / 2, POCKET_TOP - 1, CEIL_TOP + 1),                       # cable up through the ceiling
    zcyl(BORE_D / 2, TOP_PLATE_TOP, TOP_PLATE_TOP + SOCKET_DEPTH + 1),          # rod socket
    # rod bolt: from the back face into the bore, M4 nut dropped in from the top
    ycyl(M4_CLEAR / 2, 0, PIN_BLOCK_BACK + 1, 0, PIN_Z),
    blk(-NUT_SLOT_W / 2, NUT_SLOT_W / 2, 12.0, 12.0 + NUT_SLOT_T, PIN_Z - NUT_AF / np.sqrt(3) - 0.25,
        TOP_PLATE_TOP + SOCKET_DEPTH + 1),
]
for s in (-1, 1):
    x = s * CROSS_X
    cuts += [
        ycyl(M4_CLEAR / 2, -POCKET_R, CROSS_BOSS_BACK + 1, x, CROSS_Z),                 # clearance, back half
        ycyl(M4_TAP / 2, -12.0, -POCKET_R + 0.1, x, CROSS_Z),                           # blind, tapped, front
        ycyl(HEAD_CBORE_D / 2, CROSS_BOSS_BACK - CROSS_CBORE_DEPTH, CROSS_BOSS_BACK + 1, x, CROSS_Z),
    ]
    x = s * PINCH_X
    cuts += [
        ycyl(M4_CLEAR / 2, 0, PINCH_BOSS_BACK + 1, x, PINCH_Z),
        blk(x - NUT_SLOT_W / 2, x + NUT_SLOT_W / 2, 12.3, 12.3 + NUT_SLOT_T,
            PINCH_Z - NUT_AF / np.sqrt(3) - 0.25, PINCH_BOSS[1] + 1),
    ]
holder = D(body, *cuts)
assert holder.is_watertight

# put it on the build plate: print upright, skirt down
holder.apply_translation([0, 0, -SLEEVE_BOTTOM])
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "DIRTT_probe_holder_v2.stl")
holder.export(path)

lo, hi = holder.bounds
print(f"{path}: {hi[0]-lo[0]:.1f} x {hi[1]-lo[1]:.1f} x {hi[2]-lo[2]:.1f} mm, "
      f"{holder.volume/1000:.1f} cm3 solid")
print(f"footprint x {lo[0]:.1f}..{hi[0]:.1f}, y {lo[1]:.1f}..{hi[1]:.1f}  "
      f"(tower opening x -31..31, y -14.2..26)")
print(f"rod bolt at z {PIN_Z:.1f} above the socket floor's {TOP_PLATE_TOP:.1f} "
      f"(={ROD_HOLE_FROM_TIP} mm from the rod tip)")
