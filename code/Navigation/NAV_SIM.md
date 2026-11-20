# D.I.R.T.T. Navigation Sim (SITL + browser UI)

`nav_sim.py` runs the Pi's survey mission against ArduPilot SITL and shows it live in a browser on satellite imagery.

It uses the same mission logic as `survey_mission.py`: GUIDED, then arrive, then HOLD, then probe, then the next point, and finally RTL. It adds:

- **STOP / Resume / COME HOME** buttons. COME HOME retracts the probe first if it is in the ground.
- **True vs GPS position.** Each arrival is scored two ways. *Pi err* is what the Pi believed. *True err* is SITL ground truth, and NV2 is graded on that.
- A **GPS-error slider.** It sets a slow, wandering error like real GPS, injected through `SIM_GPS_GLITCH_X/Y`. SITL's `SIM_GPS_NOISE` only moves altitude, so it can't be used for this.
- **Click-to-place obstacles.** They are uploaded as geofence exclusion circles. SITL's simulated proximity sensor sees them, and ArduPilot's BendyRuler avoidance steers around them, which is the same path the real RPLIDAR → flight controller takes. The map also draws the 8 LiDAR sectors.
- **Point editing.** Click to add, drag to move, right-click to delete. You can also make a grid with `grid_planner.py`, or load and save a `*_points.csv`.

## Files (put them all in the same folder as `grid_planner.py`)

| File | What it is |
|---|---|
| `nav_sim.py` | Mission + MAVLink + web server (standard library + pymavlink only) |
| `nav_sim_ui.html` | The page. `nav_sim.py` serves it; you don't open it directly |
| `dirtt_sitl.parm` | SITL parameters: 1 m arrival radius, fence, simulated LiDAR, obstacle avoidance |
| `survey_mission.py` | **Updated.** Two bug fixes found while testing; see the bugs section below |
| `grid_planner.py` | Field outline → ordered sample grid (the sim's **Make grid** uses it) |
| `plot_survey.py` | Plots a survey's CSVs |
| `server/` | Hosting the sim on the web for the team: see [`server/SETUP.md`](server/SETUP.md) |

## Run it (WSL)

```bash
cd ~/dirtt_nav            # same folder as grid_planner.py
python3 -c "import pymavlink" || pip3 install --user pymavlink
```

**Terminal 1: SITL.** Put in your field's coordinates so the satellite map shows the real field.
```bash
sim_vehicle.py -v Rover -f rover-skid --console --map \
    --add-param-file=dirtt_sitl.parm --custom-location=LAT,LON,100,0
```
The first time, `PRX1_TYPE` and `OA_TYPE` only take effect after a reboot. If the UI shows the "Obstacle avoidance is OFF until SITL restarts" warning, quit SITL and run the same command once more. After that the values are saved.

**Terminal 2: the sim.**
```bash
python3 nav_sim.py
```
Then open **http://localhost:8000** in your Windows browser. WSL forwards localhost.

- It connects on `tcp:127.0.0.1:5762` (SITL's spare port), so MAVProxy and Mission Planner keep working alongside it.
- `--host 0.0.0.0` lets you open the UI from another device on the same network.
- `--points field1_points.csv` preloads a plan.
- The satellite tiles (Esri World Imagery) and the map library load from the internet. Without internet, the panel still works but the map is blank.

## Shared on the web

`server/` runs the same sim on an always-on PC at **https://dirtt-sim.ndbre.com**: Cloudflare Access
sign-in (email code), one driver at a time, everyone else watches. Setup and day-to-day commands are in
[`server/SETUP.md`](server/SETUP.md). Run locally (as above) nothing changes: no sign-in, you always
have control.

## Using it

1. **Make the points.** Three ways:
   - **Field tool:** click the field's corners in order around the edge (drag to move, click one to delete), or open *Type or paste corner coordinates* and enter `lat, lon` per line. Then set the spacing and how far in from the edge, and press **Make grid**: `grid_planner.py` fills the outline.
   - **Make grid** with no outline: a square of the given size, with the rover 10 m in from the south-west corner.
   - **Points tool:** click to add, drag to move, click a point to delete it. Or **Load CSV** with a `grid_planner.py` plan.

   The point and obstacle lists in the panel also have a × on every row.
2. **Set up the run.** GPS error; drive speed (slider 0.2 to 3 m/s, presets include 0.6 m/s, the real rover); fast or real probe cycle.
3. **Press Start survey.** To add obstacles, pick **Obstacles** and click on the map. You can do this mid-run.
4. **Read the results.** The NV2 card fills in as points are sampled. The CSVs go to `runs/survey_<time>_*.csv`, with the true-position columns added. `plot_survey.py` still reads them.

**Rover start:** on the shared server (`server/`), the **Start** tool moves the rover anywhere on the map; the simulator restarts there (about 40 s). Running it yourself, start `sim_vehicle.py` with `--custom-location=LAT,LON,100,0` instead.

**Geofence:** the flight controller's fence is your outline grown by 8 m (the white dashed line). SITL's simulated LiDAR sees the fence as a wall, and with the fence right on the outline, points near the edge got skipped.

### Suggested recording for the FDR (NV2)

1. **Baseline:** GPS error 0 m, Fast speed, no obstacles. Every point lands well inside 3 m. These are your SITL arrival numbers.
2. **Realistic GPS:** GPS error 2 m. The Pi still reports ~1 m, but the true error grows to 2–3 m. That's the "1.5 m on the GPS ≠ 1.5 m in reality" point from the slide.
3. **Obstacle mid-leg:** drop an obstacle in front of the rover while it is driving. The orange path bends around it.
4. **Operator commands:** press STOP during "probe down", then Resume. Next, press COME HOME during "reading sensor": the log shows the probe retracting first, then RTL.

## Bugs testing turned up (fixed)

1. **Re-sending the GUIDED target every second (old `survey_mission.py`).** Each new target cancels ArduPilot's avoidance detour (`AR_WPNav_OA::set_desired_location`). In SITL the rover passed **0.2 m** from an obstacle's edge with re-sending, against **3.6 m** without it. The target is now sent 3 times, 1 s apart, then left alone. This matters on the real rover too, once the LiDAR is in use.
2. **Arrival counted too early.** The "stopped within 2× the radius" rule counted the rover sitting still *before* the leg started. A point within 3 m of the start was marked "reached" without the rover moving. The rule now only applies after the leg has run for 5 s.

## Things to know (SITL vs the real rover)

- **Obstacles keep the rover further away than they look.** Avoidance keeps the rover's centre
  `radius + FENCE_MARGIN + OA_MARGIN_MAX` from an obstacle's centre: the dashed ring around each
  obstacle on the map. With ArduPilot's defaults (2 m + 1.5 m) a 1 m obstacle 3–4 m from a sample point
  made the point unreachable and BendyRuler drove back and forth forever. `dirtt_sitl.parm` now uses
  1 m + 1 m. Points inside a ring are flagged on the map and in the list and skipped as BLOCKED.
- **Stuck detection.** If the rover gets no closer to its point for 30 s, the sim pauses with a
  "Stuck" message instead of skipping the rest of the survey one time limit at a time. Move or delete
  the obstacle, then **Resume**, or press **Skip point**. The real `survey_mission.py` should get the
  same check before field testing.
- **BendyRuler is a local planner.** In a dense obstacle field it prefers to keep its current heading
  and can pick the wrong way round an obstacle into a corner. (Dijkstra's planner, `OA_TYPE 2/3`, did
  no better on the same layout.)

- **`AVOID_ENABLE 0`.** ArduPilot's *simple* avoidance refused to pivot whenever something was within ~3 m ahead. A rover facing a corner sat still forever. BendyRuler (`OA_TYPE 1`) still does the avoiding. Re-check this on the real rover with the real LiDAR before trusting it.
- **The field edge looks like a wall to the simulated LiDAR**, because SITL builds its proximity readings from the fence. The real LiDAR won't see a field edge.
- **Obstacles also exist as GPS-placed fence zones.** With 2–2.5 m of GPS error, the rover's clearance around an obstacle sometimes shrank to ~0.1 m, because the flight controller thinks the obstacle is somewhere else. The real LiDAR measures relative to the rover, so it doesn't have this problem.
- **SITL's skid-steer model is tuned for 3 m/s.** At 0.6 m/s it can circle a target that starts within ~3 m until the time limit skips it. Steering and speed tuning has to be done on the real rover anyway.
- **On the real rover, run `survey_mission.py --connect /dev/serial0`.** The GPS-error and obstacle tools only exist in simulation.
