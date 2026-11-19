# D.I.R.T.T. base station enclosure (Pi 5 + LoRa Radio Bonnet)

92.5 × 64 × 27 mm. Two printed shells + two printed spacers, 6 screws.

## Print
| File | Qty | Orientation | Notes |
|---|---|---|---|
| `DIRTT_pi5_enclosure_base.stl` | 1 | as exported (floor down) | no supports |
| `DIRTT_pi5_enclosure_lid_print_orientation.stl` | 1 | as exported (top face down) | no supports |
| `DIRTT_pi5_enclosure_spacer.stl` | 2 | standing up | 100 % infill |

PLA or PETG, 0.2 mm layers, 3 walls/perimeters (the screws self-tap into the 2.2 mm holes).
STEP files are included for editing; `pi5_enclosure.py` (CadQuery) regenerates everything.

## Hardware
- 6 × M2.5 × 16 mm pan-head screws
- uFL → SMA female bulkhead pigtail (6.6 mm hole, panel 3.5 mm) + 915 MHz SMA antenna

## Assembly
1. Put the SMA bulkhead through the lid from inside, nut on top. Plug the uFL end into the bonnet.
2. Set the Pi in the base. Put a spacer on each GPIO-side hole (the two by the 40-pin header).
3. From underneath, screw the two GPIO-side holes into the spacers (M2.5 × 16).
4. Plug the bonnet onto the GPIO header; it rests on the spacers.
5. Lower the lid on (ports go into their openings), then from underneath screw the two front
   Pi holes into the lid posts and the two back corners into the lid columns.

## Openings
- Front: USB-C power, 2 × micro-HDMI. Right: Ethernet, 2 × USB-A. Left: Pi power button,
  microSD (slot in the base wall).
- Top: OLED window, three flex buttons (press the tabs), vents, SMA antenna hole. Back wall vents.

## Things to check before printing
- `BUTTON_H` (2.5 mm): height of the bonnet's buttons above its PCB. Measure; the nubs leave 0.6 mm.
- `BONNET_GAP` (11 mm): Pi PCB top to bonnet PCB bottom with the stock headers. Measure.
- Cooling is passive (top, back-wall and floor vents). I didn't model the official Active Cooler;
  if you use one, check it fits in the 11 mm under the bonnet.
