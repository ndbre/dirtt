"""D.I.R.T.T. wheel v3: the v2 tire rim with a stronger hub and an M4 set screw.

Starts from DIRTT_wheel_v2_tire_rim.stl (same rim, spokes, tire seat and inner-face screw relief)
and only changes the hub:
  - hub boss 24 mm -> 32 mm across, so there is more plastic around the shaft and the nut
  - the M3 set screw + nut is replaced by an M4-0.70 x 5 set screw and an M4 hex nut
  - the nut sits 1.5 mm from the shaft flat, so the 5 mm screw is fully in the nut (3.2 mm of thread)
    when its tip is on the flat
  - same 6 mm D bore as v2 (6.2 mm round, flat 2.55 mm from centre), which already fit the shaft

Coordinates match v2: z = 0 is the inner face (motor side), the shaft goes in from z = 0,
the hub's outer end is at z = 16. The set screw points along +x, at the D flat, between two spokes.

Run:  python3 make_wheel_v3.py DIRTT_wheel_v2_tire_rim.stl DIRTT_wheel_v3_tire_rim.stl
Needs: pip install trimesh manifold3d
"""
import sys
import numpy as np
import trimesh
from trimesh.creation import cylinder, box

SRC, OUT = sys.argv[1], sys.argv[2]

# ---- dimensions (mm) ----
HUB_R = 16.0            # new hub boss radius (v2: 12)
HUB_Z0, HUB_Z1 = 3.6, 16.0   # boss from the floor of the inner-face pocket to the hub's outer end
BORE_R = 3.1            # 6.2 mm bore for the 6 mm shaft (as v2)
FLAT_X = 2.55           # D flat, distance from centre (as v2)
SCREW_Z = 10.0          # set screw height: on the shaft's flat (flat runs about z = 2..14 in the wheel)
SCREW_HOLE_D = 4.4      # clearance for the M4 set screw and a 2 mm hex key
NUT_AF = 7.0            # M4 nut across flats
NUT_T = 3.2             # M4 nut thickness
NUT_GAP = 1.5           # plastic between the shaft flat and the nut
CLEAR = 0.3             # print clearance on the nut slot width
SLOT_W = NUT_AF + CLEAR             # 7.3 mm
SLOT_X0 = FLAT_X + NUT_GAP          # 4.05
SLOT_X1 = SLOT_X0 + NUT_T + 0.25    # 7.5
SLOT_BOTTOM = SCREW_Z - (NUT_AF / np.sqrt(3)) - 0.25   # nut corner (4.04 from centre) + clearance
SEG = 160


def zcyl(r, z0, z1, x=0.0, y=0.0):
    c = cylinder(radius=r, height=z1 - z0, sections=SEG)
    c.apply_translation([x, y, (z0 + z1) / 2])
    return c


def slab(x0, x1, y0, y1, z0, z1):
    b = box(extents=[x1 - x0, y1 - y0, z1 - z0])
    b.apply_translation([(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2])
    return b


wheel = trimesh.load(SRC)
assert wheel.is_watertight

# 1. bigger solid hub boss (fills the old M3 nut slot, screw hole and bore in that height range)
boss = zcyl(HUB_R, HUB_Z0, HUB_Z1)
wheel = trimesh.boolean.union([wheel, boss], engine="manifold")

# 2. D bore, all the way through (same as v2)
bore = trimesh.boolean.intersection(
    [zcyl(BORE_R, -1, HUB_Z1 + 1), slab(-BORE_R - 1, FLAT_X, -BORE_R - 1, BORE_R + 1, -1, HUB_Z1 + 1)],
    engine="manifold")

# 3. set screw hole along +x, from the bore out through the side of the hub
hole = cylinder(radius=SCREW_HOLE_D / 2, height=HUB_R + 2, sections=64)
hole.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
hole.apply_translation([(HUB_R + 2) / 2 + 1.0, 0, SCREW_Z])

# 4. nut slot: drop the nut in from the hub's outer end
slot = slab(SLOT_X0, SLOT_X1, -SLOT_W / 2, SLOT_W / 2, SLOT_BOTTOM, HUB_Z1 + 1)

wheel = trimesh.boolean.difference([wheel, bore, hole, slot], engine="manifold")
assert wheel.is_watertight
wheel.export(OUT)

print(f"{OUT}: hub {2*HUB_R:.0f} mm, nut slot x {SLOT_X0:.2f}-{SLOT_X1:.2f}, "
      f"width {SLOT_W:.1f}, bottom z {SLOT_BOTTOM:.2f}; screw at z {SCREW_Z}")
print(f"outer wall past the nut slot: {HUB_R - np.hypot(SLOT_X1, SLOT_W/2):.1f} mm; "
      f"volume {wheel.volume/1000:.1f} cm3 (v2 rim + hub change)")
