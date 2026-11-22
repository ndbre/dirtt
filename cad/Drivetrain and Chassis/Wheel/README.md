# Wheel

| File | What it is |
|---|---|
| `DIRTT_wheel_v3_tire_rim.stl` | **Current.** v2 rim with a 32 mm hub and an M4 set screw + nut |
| `DIRTT_wheel_v2_tire_rim.stl` | Rim for the TPU tire, 24 mm hub, M3 set screw (hub cracked in use) |
| `DIRTT_tire.stl` | TPU tire for the v2 / v3 rim |
| `DIRTT_wheel_v1.stl` | First one-piece wheel |
| `make_wheel_v3.py` | Makes v3 from v2: `python3 make_wheel_v3.py DIRTT_wheel_v2_tire_rim.stl DIRTT_wheel_v3_tire_rim.stl` (needs `pip install trimesh manifold3d`) |

## v3 hub

Only the hub changed; the rim, spokes, tire seat and inner-face screw relief are the same as v2.

- Hub 32 mm across (v2: 24 mm). 7.7 mm of plastic outside the nut (v2: about 2 mm).
- Same 6 mm D bore as v2.
- **Hardware per wheel:** one M4-0.70 × 5 mm set screw (cup point) and one M4 hex nut (7 mm across flats, 3.2 mm thick). 2 mm hex key.
- The nut sits 1.5 mm from the shaft flat, so the 5 mm screw is in the full 3.2 mm of nut thread when its tip is on the flat.

### Assembly

1. Drop the M4 nut into the slot in the hub's outer face, flats against the slot walls. Push it to the bottom.
2. From the side, thread the set screw through the 4.4 mm hole into the nut with the 2 mm key. Stop before the tip shows in the bore.
3. Slide the wheel onto the shaft with the shaft's flat facing the screw.
4. Tighten the screw onto the flat. Recheck it after the first drive; plastic settles.

### Printing

- Same orientation as v2 (inner face down, bore vertical).
- Walls matter more than infill here: around the bore and nut, the slicer prints mostly perimeters. Use **5–6 walls** (about 2–2.5 mm); 50–75 % infill is plenty for the rest.
- PETG is tougher than PLA if you have it; PLA cracks rather than bends.
- Check the nut slides in before printing four: print one hub first.
