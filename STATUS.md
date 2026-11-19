# STATUS

Where D.I.R.T.T. stands. Update this when a decision is made or something changes.

_Last updated: 2026-11-18 (after the FDR)._

## Deliverables

- FDR presented 2026-11-17. Deck and PDF: `docs/FDR/2026-11-17_FDR.*` (all deliverables live in `docs/`). An editable copy lives as a Claude Slides artifact:
  https://claude.ai/artifact/HWR3RGkAxLph8hyWFwR5JS
- Website: https://dirtt.ndbre.com (domain `ndbre.com` on Cloudflare). Copy draft for the site:
  https://claude.ai/artifact/5z8jnc6e7pbV1vibVTBp2V

## Hardware by subsystem

**Navigation (Nolan).** MicoAir743v2 flight controller on ArduPilot Rover, Holybro M10 GPS,
RPLIDAR C1 feeding FC proximity with BendyRuler avoidance. The rover Pi sends one GUIDED target
per grid point (sent 3 times only; re-sending cancels the avoidance detour), declares arrival at
≤ 1.5 m by its own haversine distance (WP_RADIUS 1 m + 0.5 m), then switches to HOLD and probes.
`AVOID_ENABLE 0` (simple avoidance deadlocks pivot turns). SITL simulator with a browser UI is in
`code/Navigation/` (`NAV_SIM.md` explains how to run it); works on ArduPilot 4.6 and 4.7+/master.
**Live at https://dirtt-sim.ndbre.com** (since 2026-11-19): runs on Nolan's home PC (Windows 11,
WSL Ubuntu 24.04, Linux user `functor`), Cloudflare Tunnel `dirtt-home`, Access team `dirtt` with
an email allow-list and one-time PIN. One driver at a time. Setup and upkeep:
`code/Navigation/server/SETUP.md`. To deploy sim code changes: merge to master, then on the PC
`cd ~/dirtt && git pull && pkill -f nav_sim.py`.

**Drivetrain and Chassis (Rebecca).** Four FIT0185 gearmotors, Cytron MDDRC10 driver in RC/mixed
mode (1500 µs neutral captured at power-up). The FC drives it; for bench demos an Arduino can
send the same RC pulses with the Servo library. Chassis rev E:
- Ribs are 1x6 pine ripped to the motor-mount height (~50 mm), replacing the printed ribs
  (`cad/Drivetrain and Chassis/Structure/DIRTT_rib_*.stl` are superseded).
  Long ribs 560 mm ×2 at Y ±90.5 mm, each with two 1-1/8" cable holes 140 mm from the ends;
  end ribs 420 mm ×2; optional side ribs 280 mm ×2.
- Cable hole G moved to (−140, 120) mm from the plate centre instead of chamfering a rib.
- Removable lid: 8 M4 inserts in the rib ends + 8 M3 heat-set inserts in the motor mounts
  (2 per mount), M4×16 pan-head machine screws with washers. Only those 16 holes go through both
  plates. Ribs to bottom plate: #6×3/4" flat-head wood screws, 3/32" pilot, 5/32" clearance.
- Motor mounts are not screwed to the lid; fine for demos.

**Soil Sensing (Zachary).** SEN0604 4-in-1 RS485 probe on an ECO-WORTHY linear actuator.
pH acceptance: ±0.5 pH against a reference (lab 1:1 water pH, or a Bluelab Soil pH Pen in the
field), not ±20 %.

**Power and Charging (George).** Design battery: WattCycle LiFePO4 12.8 V 20 Ah, Lensun 30 W
panel, Renogy Wanderer 10 A PWM. Solar parts arrive next semester. **Demo battery now: 12 V 8 Ah
AGM** (Renogy set to Sealed). Bench charging: 14.4 V absorb / 13.6 V float, or feed the Renogy
18 V / 1.7 A from a bench supply to stand in for the panel.

**Data Backup and Control (Cara).** Pi 3 B on the rover, Pi 5 base station, RFM95W LoRa Bonnets.
Base station enclosure (Pi 5 + LoRa Bonnet, OLED window, flex buttons, SMA antenna hole):
`cad/Data and Communication/Base Station Enclosure/`. Not printed yet; check button height and
header stack height first (see its README).

## Open items

- Website text is out of date: Home says sampling points "about 100 m apart" and "multi-day
  operation" on solar; About still says "Temporary Text"; "Project status" predates the FDR;
  team bios are empty.
- Add Dr. Hudson and graders to the nav sim's Access policy as needed (Zero Trust → Access →
  Applications → DIRTT nav sim).
- `cad/Unsorted/` (jigs, mounts) could be filed under the subsystems.
- Archive the old `ndbre/dirtt-files` repo (merged here 2026-11-18).
