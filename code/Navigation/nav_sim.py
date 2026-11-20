#!/usr/bin/env python3
"""D.I.R.T.T. navigation simulation: the Pi's survey mission against ArduPilot SITL, with a browser UI.

    Terminal 1:  sim_vehicle.py -v Rover -f rover-skid --console --map \
                     --add-param-file=dirtt_sitl.parm --custom-location=LAT,LON,ALT,0
    Terminal 2:  python3 nav_sim.py
    Browser:     http://localhost:8000

This is the same mission logic as survey_mission.py (GUIDED -> arrive -> HOLD -> probe -> next,
then RTL), restructured as a state machine so the operator can STOP or send COME HOME at any time,
plus the things only a simulator can show:

  * TRUE position (from SITL's SIMSTATE) next to the GPS/EKF position the Pi navigates on, so each
    arrival is scored both ways: "the Pi thought it was 1.2 m away" vs "it was really 2.4 m away".
  * GPS error: a slow random walk pushed into SIM_GPS_GLITCH_X/Y, or SIM_GPS1_GLTCH_X/Y on newer
    ArduPilot (SITL's SIM_GPS_NOISE only moves
    altitude). Real GPS error is a wandering bias, not jitter, so this is the realistic model.
  * Obstacles: circles you click onto the map are uploaded as geofence exclusion zones. SITL's
    simulated proximity sensor (PRX1_TYPE 10) "sees" them, and ArduPilot's BendyRuler avoidance
    (OA_TYPE 1) steers around them - the same path the real RPLIDAR -> flight controller takes.

Moving to the real rover: the mission logic is the same; use survey_mission.py with
--connect /dev/serial0. The GPS-error and obstacle tools only exist in simulation.

Shared on the web (dirtt-sim.ndbre.com, see server/SETUP.md): run with --auth access. Everyone
signs in through Cloudflare Access; one person drives at a time, everyone else watches. The page
polls /api/state several times a second, and that doubles as the driver's heartbeat: close the tab
and control passes to the next person in line after --driver-timeout seconds.
"""
import argparse, collections, csv, glob, json, math, os, queue, random, subprocess, sys, threading, time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from urllib.parse import urlparse, parse_qs

from pymavlink import mavutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    import grid_planner                     # same folder: reuse the real planner for "Make grid"
except Exception:                           # noqa: BLE001 - UI still works without it
    grid_planner = None

R_EARTH = 6378137.0
POS_MASK = 0b110111111000                  # SET_POSITION_TARGET: position only
STOPPED_S = 3.0                            # "not moving" = < 0.2 m in this long
STUCK_S = 30.0                             # no 1 m of progress toward the point in this long = stuck
TRACK_PERIOD_S = 0.5
MAX_TRACK_POINTS = 20000                   # in memory for the page (~2.8 h of driving); CSVs keep it all
TRACK_STATES = ("DRIVING", "PROBING", "HOMING", "STOPPED", "PAUSED")   # record the path only during a survey
FENCE_PAD_M = 8.0                          # field boundary = points + home, padded by this
PROBE_REAL = (("settle", 2.0), ("probe down", 15.0), ("reading sensor", 5.0), ("probe up", 15.0))
PROBE_FAST = (("settle", 1.0), ("probe down", 2.0), ("reading sensor", 1.0), ("probe up", 2.0))
GPS_TAU_S = 45.0                           # GPS error correlation time (how slowly it wanders)
SPEEDS = {"real": 0.6, "fast": 2.0}         # presets (m/s); any value in SPEED_RANGE works
SPEED_RANGE = (0.2, 3.0)                   # SITL skid-steer model is tuned for ~3 m/s
# SITL's GPS glitch offset (degrees) was renamed when the GPS sim parameters moved into groups:
# ArduPilot 4.6 and earlier: SIM_GPS_GLITCH_X/Y/Z   ArduPilot 4.7 / master: SIM_GPS1_GLTCH_X/Y/Z
GLITCH_NAMES = ("SIM_GPS_GLITCH", "SIM_GPS1_GLTCH")
# Limits, so one visitor can't bog the shared sim down
MAX_POINTS = 150
MAX_OBSTACLES = 25
MAX_CORNERS = 20
KEEP_LOG_FILES = 300                       # newest survey CSVs kept in --logs        # m/s. Real: 83 RPM x 0.19 m wheel = 0.83 m/s no-load

# Parameters the simulation needs. (value, needs reboot, why)
WANT = {
    "WP_RADIUS": (1.0, False, "arrival radius the FC uses; the Pi adds 0.5 m"),
    "FENCE_ENABLE": (1, False, "fence holds the field edge and the obstacles"),
    "FENCE_ACTION": (0, False, "report only: avoidance, not the fence, handles obstacles"),
    "AVOID_ENABLE": (0, False, "simple avoidance off: it deadlocks pivot turns near obstacles; BendyRuler avoids"),
    "OA_TYPE": (1, True, "BendyRuler obstacle avoidance"),
    "OA_MARGIN_MAX": (1.0, False, "avoidance keeps the rover this far beyond an obstacle's fence margin"),
    "FENCE_MARGIN": (1.0, False, "added to every obstacle's radius by the avoidance"),
    "PRX1_TYPE": (10, True, "SITL proximity sensor = simulated LiDAR"),
}


def now_s():
    return time.time()


def dist_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(min(1.0, a)))


def pad_polygon(corners, pad):
    """Grow a lat/lon polygon outward by `pad` metres (mitred corners, capped at 3x pad).

    The geofence gets the field outline plus this pad: SITL's simulated LiDAR sees the fence as a
    wall, so points near an exact outline get skipped. The real LiDAR doesn't see field edges."""
    lat0, lon0 = corners[0]
    k = math.cos(math.radians(lat0))
    xy = [(math.radians(lo - lon0) * R_EARTH * k, math.radians(la - lat0) * R_EARTH) for la, lo in corners]
    n = len(xy)
    area2 = sum(xy[i - 1][0] * xy[i][1] - xy[i][0] * xy[i - 1][1] for i in range(n))
    sgn = 1.0 if area2 > 0 else -1.0                 # counter-clockwise: outward normal is to the right
    out = []
    for i in range(n):
        (ax, ay), (bx, by), (cx, cy) = xy[i - 1], xy[i], xy[(i + 1) % n]
        normals = []
        for (x1, y1), (x2, y2) in (((ax, ay), (bx, by)), ((bx, by), (cx, cy))):
            L = math.hypot(x2 - x1, y2 - y1) or 1.0
            normals.append((sgn * (y2 - y1) / L, -sgn * (x2 - x1) / L))
        (n1x, n1y), (n2x, n2y) = normals
        d = 1.0 + n1x * n2x + n1y * n2y
        mx, my = (n1x + n2x) / max(d, 1e-6), (n1y + n2y) / max(d, 1e-6)
        m = math.hypot(mx, my)
        if m > 3.0:
            mx, my = mx * 3.0 / m, my * 3.0 / m
        out.append((bx + pad * mx, by + pad * my))
    return [(lat0 + math.degrees(y / R_EARTH), lon0 + math.degrees(x / (R_EARTH * k))) for x, y in out]


def offset_ll(lat, lon, east_m, north_m):
    return (lat + math.degrees(north_m / R_EARTH),
            lon + math.degrees(east_m / (R_EARTH * math.cos(math.radians(lat)))))


class Sim:
    """Owns the MAVLink link and the mission. Runs in one worker thread; the web server only reads
    snapshot() and drops commands into self.cmds."""

    def __init__(self, conn, baud, out_dir):
        self.conn_str, self.baud = conn, baud
        self.out_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)
        self.lock = threading.Lock()
        self.cmds = queue.Queue()
        self.m = None
        self.connected = False
        self.last_hb = 0.0
        # vehicle state
        self.est = None            # (lat, lon) EKF estimate: what the Pi navigates on
        self.gps = None            # raw GPS fix (includes the injected error)
        self.true = None           # SITL ground truth
        self.true_yaw = 0.0
        self.heading = 0.0
        self.speed = 0.0
        self.mode = None
        self.armed = False
        self.params = {}
        self.acks = {}
        self.mission_msgs = collections.deque()
        self.hist = collections.deque()
        self.lidar = {}            # sector (0-7) -> metres, from DISTANCE_SENSOR
        self.next_hb = 0.0
        # mission
        self.points = []           # [{"n", "lat", "lon"}]
        self.field = []            # inclusion polygon [(lat, lon)]
        self.field_from_grid = False
        self.obstacles = []        # [{"id", "lat", "lon", "r"}]
        self.next_obs_id = 1
        self.home = None
        self.state = "CONNECTING"
        self.detail = "Waiting for SITL"
        self.idx = 0
        self.t_leg = 0.0
        self.limit = 0.0
        self.next_send = 0.0
        self.sends_left = 0
        self.phase = 0
        self.phase_end = 0.0
        self.phase_left = None     # seconds left in a probe phase when STOP froze it
        self.held_from = None      # state to go back to after STOP / external pause
        self.home_after_probe = False  # COME HOME arrived mid-test: retract, then RTL
        self.hold_reason = ""
        self.probe_steps = PROBE_FAST
        self.wp_speed = SPEEDS["fast"]  # WP_SPEED (m/s) we ask for; self.speed is the measured one
        self.results = []
        self.log_lines = collections.deque(maxlen=200)
        self.track = []            # [(t, est_lat, est_lon, true_lat, true_lon)]
        self.track_base = 0        # points trimmed off the front of self.track (keeps indices absolute)
        self.next_track = 0.0
        self.warnings = []
        self.arrive_m = 1.5
        self.fence_dirty = True
        self.fence_status = "not uploaded"
        # GPS error injection
        self.gps_sigma = 0.0       # typical horizontal error the user asked for (m, RMS)
        self.gps_err = [0.0, 0.0]  # current injected error (north, east) m
        self.next_gps = 0.0
        self.glitch_param = None   # resolved name prefix for the glitch vector
        # logs
        self.samples_w = self.track_w = None
        self.stamp = None
        self.reinit_needed = False  # SITL restarted under us: re-request streams, params, fence
        self.restart_cmd = None    # shell command that restarts SITL (server mode)
        self.home_file = None      # file start_sim.sh reads the SITL start location from
        self.corners = []          # field outline drawn by the user, for "Make grid": [(lat, lon)]
        self.soil = None           # SoilField: the made-up truth the probe "measures"

    # ------------------------------------------------------------ logging / snapshot
    def log(self, msg):
        line = f"[{datetime.now():%H:%M:%S}] {msg}"
        print(line, flush=True)
        with self.lock:
            self.log_lines.append(line)

    def snapshot(self, since=0):
        with self.lock:
            p = self.points[self.idx] if self.state in ("DRIVING", "PROBING") and self.idx < len(self.points) else None
            d_est = dist_m(*self.est, p["lat"], p["lon"]) if p and self.est else None
            d_true = dist_m(*self.true, p["lat"], p["lon"]) if p and self.true else None
            gps_off = dist_m(*self.est, *self.true) if self.est and self.true else None
            ok = [r for r in self.results if r["status"] == "OK"]
            errs = [r["true_error_m"] for r in ok]
            return {
                "connected": self.connected, "mode": self.mode, "armed": self.armed,
                "state": self.state, "detail": self.detail, "hold_reason": self.hold_reason,
                "idx": self.idx, "points": self.points, "field": self.field,
                "obstacles": self.obstacles, "home": self.home,
                "est": self.est, "gps": self.gps, "true": self.true,
                "true_yaw": self.true_yaw, "heading": self.heading, "speed": round(self.speed, 2),
                "target": p, "d_est": d_est, "d_true": d_true, "gps_offset": gps_off,
                "arrive_m": self.arrive_m, "wp_radius": self.params.get("WP_RADIUS"),
                "gps_sigma": self.gps_sigma, "fast_probe": self.probe_steps is PROBE_FAST,
                "speed_set": self.wp_speed, "speed_range": SPEED_RANGE,
                "corners": self.corners, "can_move_start": bool(self.home_file and self.restart_cmd),
                "results": self.results, "log": list(self.log_lines)[-80:],
                "track_from": self.track_base + max(0, since - self.track_base),
                "track": self.track[max(0, since - self.track_base):],
                "track_len": self.track_base + len(self.track),
                "lidar": self.lidar, "warnings": self.warnings, "fence_status": self.fence_status,
                "stats": {"planned": len(self.points), "sampled": len(ok),
                          "skipped": sum(r["status"] != "OK" for r in self.results),
                          "mean_true": sum(errs) / len(errs) if errs else None,
                          "max_true": max(errs) if errs else None,
                          "within3": sum(e <= 3.0 for e in errs)},
                "editable": self.state in ("IDLE", "DONE", "CONNECTING"),
                "keepout_extra": round(self.keepout_extra(), 2),
                "soil_seed": self.soil_field().seed if (self.home or self.est) else None,
                "can_skip": self.state == "DRIVING" or (self.state in ("STOPPED", "PAUSED") and self.held_from == "DRIVING"),
                "has_planner": grid_planner is not None,
                "logfile": f"survey_{self.stamp}_samples.csv" if self.stamp else None,
            }

    # ------------------------------------------------------------ link
    def connect(self):
        self.log(f"Connecting to SITL on {self.conn_str} ...")
        while True:                                # SITL may not be up yet: keep trying
            try:
                self.m = mavutil.mavlink_connection(self.conn_str, baud=self.baud, source_system=1,
                                                    source_component=191, autoreconnect=True)
                break
            except OSError as e:
                self.log(f"  can't reach SITL yet ({e.strerror or e}) - is sim_vehicle.py running? retrying")
                time.sleep(3)
        while self.m.wait_heartbeat(timeout=5) is None:
            self.log("  no heartbeat yet - is SITL running? (sim_vehicle.py -v Rover -f rover-skid)")
        self.connected = True
        self.last_hb = now_s()
        self.log(f"Connected to system {self.m.target_system}")
        self.request_streams()
        t0 = now_s()
        while self.est is None and now_s() - t0 < 30:
            self.pump(0.2)
        if self.est is None:
            self.log("No position from the flight controller yet (GPS/EKF still settling?)")
        names = list(WANT) + ["WP_SPEED", "CRUISE_SPEED"] + [g + "_X" for g in GLITCH_NAMES]   # WANT has the margins
        for attempt in range(3):                   # ask again for anything that didn't answer
            for name in names:
                if name not in self.params:
                    self.m.mav.param_request_read_send(self.m.target_system, self.m.target_component,
                                                       name.encode(), -1)
            t0 = now_s()
            while now_s() - t0 < 2:
                self.pump(0.2)
            if any(g + "_X" in self.params for g in GLITCH_NAMES) and all(n in self.params for n in WANT):
                break
        self.check_params()
        self.glitch_param = next((g for g in GLITCH_NAMES if g + "_X" in self.params), None)
        if self.glitch_param is None:
            self.warn("Could not find SITL's GPS glitch parameter (tried " +
                      ", ".join(g + "_X" for g in GLITCH_NAMES) + "): the GPS-error slider is disabled.")
        else:
            self.log(f"GPS error is injected through {self.glitch_param}_X/Y")
            self.push_gps_error(0.0, 0.0)
        self.set_speed(self.wp_speed)
        with self.lock:
            self.home = self.est
            self.state, self.detail = "IDLE", "Add sample points, then press Start"
        if self.true:
            self.log(f"Rover at {self.true[0]:.6f}, {self.true[1]:.6f}. Mode {self.mode}.")

    def request_streams(self):
        for msg_id, hz in ((33, 5), (164, 5), (24, 5), (74, 4), (132, 4)):
            # GLOBAL_POSITION_INT, SIMSTATE, GPS_RAW_INT, VFR_HUD, DISTANCE_SENSOR
            self.m.mav.command_long_send(self.m.target_system, self.m.target_component,
                                         mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                                         msg_id, int(1e6 / hz), 0, 0, 0, 0, 0)

    def warn(self, text):
        with self.lock:
            if text not in self.warnings:
                self.warnings.append(text)
        self.log("WARNING: " + text)

    def check_params(self):
        wp = self.params.get("WP_RADIUS")
        if wp is not None:
            self.arrive_m = wp + 0.5
            self.log(f"WP_RADIUS = {wp:.2f} m -> the Pi counts a point as reached within {self.arrive_m:.2f} m")
            if wp > 1.01:
                self.warn(f"WP_RADIUS is {wp:g} m (SITL's default is 3). The design uses 1 m; with {wp:g} m "
                          f"the rover can stop up to {wp + 0.5:g} m away. Load dirtt_sitl.parm.")
        reboot = []
        for name, (val, needs_reboot, why) in WANT.items():
            have = self.params.get(name)
            if have is None:
                continue
            if abs(have - val) > 1e-3:
                if needs_reboot:
                    reboot.append(f"{name}={val:g} ({why})")
                else:
                    self.set_param(name, val)
                    self.log(f"  set {name} = {val:g} ({why})")
        if "PRX1_TYPE" not in self.params:
            reboot.append("PRX1_TYPE=10")
        if reboot:
            self.warn("Obstacle avoidance is OFF until SITL restarts with: " + ", ".join(reboot) +
                      ". Restart sim_vehicle.py with --add-param-file=dirtt_sitl.parm (once).")
            for name, (val, needs_reboot, _) in WANT.items():
                if needs_reboot:
                    self.set_param(name, val)       # saved now, active after the restart

    def reinit(self):
        """SITL came back (crashed and restarted, or someone restarted it): the mission is gone,
        the fence and the GPS error are cleared, and the rover is back at its start."""
        self.reinit_needed = False
        self.log("SITL restarted: re-reading parameters and re-uploading the fence")
        if self.state in ("DRIVING", "PROBING", "HOMING", "STOPPED", "PAUSED"):
            self.log("  the survey in progress was cancelled")
            self.close_logs()
        self.params.clear()
        self.lidar = {}
        names = list(WANT) + ["WP_SPEED"] + [g + "_X" for g in GLITCH_NAMES]
        for _ in range(3):
            for name in names:
                if name not in self.params:
                    self.m.mav.param_request_read_send(self.m.target_system, self.m.target_component,
                                                       name.encode(), -1)
            end = now_s() + 2
            while now_s() < end:
                self.pump(0.2)
            if all(n in self.params for n in WANT):
                break
        self.check_params()
        self.gps_err = [0.0, 0.0]
        self.push_gps_error(0.0, 0.0)
        self.set_speed(self.wp_speed)
        self.fence_dirty = True
        t0 = now_s()                     # wait for a position from the (possibly moved) rover
        self.est = self.true = None
        while (self.est is None or self.true is None) and now_s() - t0 < 30:
            self.pump(0.2)
        with self.lock:
            self.home = self.est
            self.state, self.detail = "IDLE", "SITL restarted - ready"

    def set_param(self, name, value):
        self.m.mav.param_set_send(self.m.target_system, self.m.target_component, name.encode(),
                                  float(value), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)

    def link_lost(self, err):
        """SITL went away (restarted or crashed): reconnect, then reinit() on the next loop."""
        self.connected = False
        self.log(f"Lost the link to SITL ({err}) - reconnecting")
        with self.lock:
            self.detail = "Simulator restarting - reconnecting"
        while True:
            try:
                try:
                    self.m.close()
                except Exception:                   # noqa: BLE001
                    pass
                self.m = mavutil.mavlink_connection(self.conn_str, baud=self.baud, source_system=1,
                                                    source_component=191, autoreconnect=True)
                if self.m.wait_heartbeat(timeout=5) is not None:
                    break
            except OSError:
                pass
            time.sleep(2)
        self.connected, self.last_hb = True, now_s()
        self.log(f"Reconnected to system {self.m.target_system}")
        self.request_streams()
        if self.state != "CONNECTING":
            self.reinit_needed = True

    def pump(self, wait=0.1):
        try:
            self._pump(wait)
        except OSError as e:
            self.link_lost(e)

    def _pump(self, wait):
        now = now_s()
        if now >= self.next_hb:
            self.m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
                                      mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
            self.next_hb = now + 1.0
        end = now + wait
        while True:
            msg = self.m.recv_match(blocking=True, timeout=max(0.0, end - now_s()))
            if msg is None:
                break
            self.handle(msg)
            if now_s() >= end:
                break
        if self.connected and now_s() - self.last_hb > 5:
            self.connected = False
            self.log("Lost the SITL heartbeat")
        if self.est and self.true and now_s() >= self.next_track and self.state in TRACK_STATES:
            # Only while a survey runs: recording an idle rover forever made the list grow without
            # bound, and a fresh page then downloaded (and drew) hours of the same point.
            with self.lock:
                self.track.append((round(now_s(), 2), round(self.est[0], 7), round(self.est[1], 7),
                                   round(self.true[0], 7), round(self.true[1], 7)))
                if len(self.track) > MAX_TRACK_POINTS:
                    cut = MAX_TRACK_POINTS // 4
                    del self.track[:cut]
                    self.track_base += cut
            if self.track_w:
                self.track_w.writerow([f"{now_s():.2f}", f"{self.est[0]:.7f}", f"{self.est[1]:.7f}",
                                       self.mode, f"{self.true[0]:.7f}", f"{self.true[1]:.7f}"])
            self.next_track = now_s() + TRACK_PERIOD_S

    def handle(self, msg):
        t = msg.get_type()
        if t == "GLOBAL_POSITION_INT":
            if msg.lat == 0 and msg.lon == 0:      # no EKF origin yet
                return
            self.est = (msg.lat / 1e7, msg.lon / 1e7)
            self.hist.append((now_s(), *self.est))
            while self.hist and now_s() - self.hist[0][0] > STOPPED_S + 1:
                self.hist.popleft()
        elif t == "SIMSTATE":
            self.true = (msg.lat / 1e7, msg.lng / 1e7)
            self.true_yaw = math.degrees(msg.yaw) % 360
        elif t == "GPS_RAW_INT":
            if msg.fix_type >= 3:
                self.gps = (msg.lat / 1e7, msg.lon / 1e7)
        elif t == "VFR_HUD":
            self.heading, self.speed = msg.heading, msg.groundspeed
        elif t == "DISTANCE_SENSOR":
            if msg.orientation <= 7:              # proximity sectors: 0 = forward, 45 deg steps
                self.lidar[msg.orientation] = round(msg.current_distance / 100.0, 2)
        elif t == "HEARTBEAT" and msg.get_srcSystem() == self.m.target_system and msg.get_srcComponent() == 1:
            new_mode = mavutil.mode_string_v10(msg)
            if new_mode != self.mode and self.mode is not None:
                self.log(f"  mode: {self.mode} -> {new_mode}")
            self.mode = new_mode
            self.armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            self.last_hb = now_s()
            if not self.connected:
                self.connected = True
                self.log("SITL heartbeat back")
                self.request_streams()
                if self.state != "CONNECTING":
                    self.reinit_needed = True
        elif t == "PARAM_VALUE":
            self.params[msg.param_id] = msg.param_value
        elif t == "COMMAND_ACK":
            self.acks[msg.command] = msg.result
        elif t in ("MISSION_REQUEST_INT", "MISSION_REQUEST", "MISSION_ACK"):
            self.mission_msgs.append(msg)
        elif t == "HOME_POSITION":
            if self.armed:
                self.home = (msg.latitude / 1e7, msg.longitude / 1e7)
        elif t == "STATUSTEXT":
            self.log(f"  FC: {msg.text}")

    # ------------------------------------------------------------ commands to the FC
    def set_mode(self, name, timeout=5.0):
        mapping = self.m.mode_mapping()
        if name not in mapping:
            self.log(f"Mode {name} unknown to this vehicle")
            return False
        if self.mode == name:
            return True
        before = self.mode
        cmd = mavutil.mavlink.MAV_CMD_DO_SET_MODE
        for _ in range(3):
            self.acks.pop(cmd, None)
            self.m.mav.command_long_send(self.m.target_system, self.m.target_component, cmd, 0,
                                         mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                                         mapping[name], 0, 0, 0, 0, 0)
            end = now_s() + 1.5
            while now_s() < end and cmd not in self.acks:
                self.pump(0.1)
            if cmd in self.acks:
                break
        if self.acks.get(cmd) != mavutil.mavlink.MAV_RESULT_ACCEPTED:
            self.log(f"  {name} refused or no reply (result {self.acks.get(cmd)})")
            return False
        end = now_s() + timeout
        while now_s() < end:
            self.pump(0.1)
            if self.mode == name:
                return True
            if self.mode != before:
                break
        self.log(f"  rover is in {self.mode}, not {name}; not overriding")
        return False

    def arm(self, timeout=45.0):        # a fresh SITL needs ~30 s before the EKF uses GPS
        t0 = now_s()
        while not self.armed:
            if now_s() - t0 > timeout:
                return False
            self.m.mav.command_long_send(self.m.target_system, self.m.target_component,
                                         mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
                                         1, 0, 0, 0, 0, 0, 0)
            self.pump(1.0)
        self.log("Armed")
        # RTL drives to the FC's home (set at arming), so use exactly that point as "home"
        self.m.mav.command_long_send(self.m.target_system, self.m.target_component,
                                     mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 0, 242, 0, 0, 0, 0, 0, 0)
        return True

    def disarm(self):
        self.m.mav.command_long_send(self.m.target_system, self.m.target_component,
                                     mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
                                     0, 0, 0, 0, 0, 0, 0)
        self.pump(1.0)

    def goto(self, lat, lon):
        self.m.mav.set_position_target_global_int_send(
            0, self.m.target_system, self.m.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT, POS_MASK,
            int(lat * 1e7), int(lon * 1e7), 0, 0, 0, 0, 0, 0, 0, 0, 0)

    def set_speed(self, value):
        if isinstance(value, str):
            value = SPEEDS.get(value, self.wp_speed)
        self.wp_speed = round(min(SPEED_RANGE[1], max(SPEED_RANGE[0], float(value))), 2)
        self.set_param("WP_SPEED", self.wp_speed)
        self.log(f"Drive speed {self.wp_speed:g} m/s")

    def upload_fence(self):
        """Field edge as an inclusion polygon + every obstacle as an exclusion circle."""
        items = []
        F = mavutil.mavlink
        for lat, lon in self.field:
            items.append((F.MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION, len(self.field), lat, lon))
        for o in self.obstacles:
            items.append((F.MAV_CMD_NAV_FENCE_CIRCLE_EXCLUSION, o["r"], o["lat"], o["lon"]))
        ftype = F.MAV_MISSION_TYPE_FENCE
        for attempt in range(2):
            self.mission_msgs.clear()
            self.m.mav.mission_count_send(self.m.target_system, self.m.target_component, len(items), ftype)
            end = now_s() + 4
            while now_s() < end:
                self.pump(0.05)
                while self.mission_msgs:
                    msg = self.mission_msgs.popleft()
                    if getattr(msg, "mission_type", 0) != ftype:
                        continue
                    if msg.get_type() == "MISSION_ACK":
                        ok = msg.type == F.MAV_MISSION_ACCEPTED
                        self.fence_status = (f"{len(self.field)}-corner field + {len(self.obstacles)} obstacle(s)"
                                             if ok else f"rejected (code {msg.type})")
                        self.log(f"Fence upload: {self.fence_status}")
                        self.fence_dirty = not ok
                        return ok
                    seq = msg.seq
                    if seq < len(items):
                        cmd, p1, lat, lon = items[seq]
                        self.m.mav.mission_item_int_send(
                            self.m.target_system, self.m.target_component, seq,
                            F.MAV_FRAME_GLOBAL, cmd, 0, 1, p1, 0, 0, 0,
                            int(lat * 1e7), int(lon * 1e7), 0, ftype)
                        end = now_s() + 4
        self.fence_status = "upload timed out"
        self.log("Fence upload timed out")
        return False

    # ------------------------------------------------------------ GPS error
    def push_gps_error(self, north, east):
        if not self.glitch_param or not self.true:
            return
        lat = self.true[0]
        self.set_param(self.glitch_param + "_X", math.degrees(north / R_EARTH))
        self.set_param(self.glitch_param + "_Y", math.degrees(east / (R_EARTH * math.cos(math.radians(lat)))))

    def gps_tick(self):
        if now_s() < self.next_gps or not self.glitch_param:
            return
        dt = 1.0
        self.next_gps = now_s() + dt
        s = self.gps_sigma / math.sqrt(2)              # per axis
        if s <= 0:
            if abs(self.gps_err[0]) + abs(self.gps_err[1]) < 0.01:
                return
            self.gps_err = [e * 0.7 for e in self.gps_err]   # fade out over a few seconds
        else:
            a = math.exp(-dt / GPS_TAU_S)
            self.gps_err = [a * e + s * math.sqrt(1 - a * a) * random.gauss(0, 1) for e in self.gps_err]
        self.push_gps_error(*self.gps_err)

    # ------------------------------------------------------------ points / field
    def make_field(self):
        pts = [(p["lat"], p["lon"]) for p in self.points]
        if self.home:
            pts.append(self.home)
        if len(self.corners) >= 3:      # the user's outline (padded), if the points and the start are inside it
            self.field = pad_polygon(self.corners, FENCE_PAD_M)
            if all(self.field_contains(ll) for ll in pts):
                return                  # otherwise fall through to a box around everything
        if not pts:
            self.field = []
            return
        lat0, lon0 = pts[0]
        k = math.cos(math.radians(lat0))
        xy = [(math.radians(lo - lon0) * R_EARTH * k, math.radians(la - lat0) * R_EARTH) for la, lo in pts]
        x0, x1 = min(p[0] for p in xy) - FENCE_PAD_M, max(p[0] for p in xy) + FENCE_PAD_M
        y0, y1 = min(p[1] for p in xy) - FENCE_PAD_M, max(p[1] for p in xy) + FENCE_PAD_M
        self.field = [offset_ll(lat0, lon0, x, y) for x, y in ((x0, y0), (x0, y1), (x1, y1), (x1, y0))]

    def set_points(self, pts, field=None):
        if len(pts) > MAX_POINTS:
            self.log(f"Too many points ({len(pts)}); the limit is {MAX_POINTS}")
            return
        with self.lock:
            self.points = [{"n": i + 1, "lat": float(p["lat"]), "lon": float(p["lon"])}
                           for i, p in enumerate(pts)]
        if field:
            self.field = field
        else:
            self.make_field()
        self.fence_dirty = True
        self.log(f"{len(self.points)} sample point(s) set")

    def make_grid(self, size, spacing, margin):
        if grid_planner is None:
            self.log("grid_planner.py is not next to nav_sim.py")
            return
        if not self.est:
            return
        lat, lon = self.home or self.est
        if len(self.corners) >= 3:       # the user's field outline
            corners = list(self.corners)
        else:
            o = -10.0                    # rover starts 10 m inside the SW corner: room to turn, and the
                                         # first point is not right next to it (rovers circle tight targets)
            corners = [offset_ll(lat, lon, x, y) for x, y in ((o, o), (o, o + size), (o + size, o + size), (o + size, o))]
        try:
            pts, path, _, rows = grid_planner.plan(corners, spacing, margin, (lat, lon))
        except SystemExit as e:
            self.log(f"Grid planner: {e}")
            return
        self.set_points([{"lat": a, "lon": b} for a, b in pts], field=pad_polygon(corners, FENCE_PAD_M))
        self.log(f"Grid: {len(pts)} points in {rows} rows, {spacing:g} m apart, {path:.0f} m of driving")

    # ------------------------------------------------------------ mission
    def prune_logs(self):
        files = sorted(glob.glob(os.path.join(self.out_dir, "survey_*.csv")), key=os.path.getmtime)
        for f in files[:-KEEP_LOG_FILES]:
            try:
                os.remove(f)
            except OSError:
                pass

    def open_logs(self):
        self.prune_logs()
        self.stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sf = open(os.path.join(self.out_dir, f"survey_{self.stamp}_samples.csv"), "w", newline="")
        tf = open(os.path.join(self.out_dir, f"survey_{self.stamp}_track.csv"), "w", newline="")
        self._files = (sf, tf)
        self.samples_w, self.track_w = csv.writer(sf), csv.writer(tf)
        self.samples_w.writerow(["n", "status", "time", "planned_lat", "planned_lon", "lat", "lon", "error_m",
                                 "ph", "ec_uScm", "temp_c", "moisture_pct", "true_lat", "true_lon",
                                 "true_error_m", "gps_error_setting_m",
                                 "true_ph", "true_ec_uScm", "true_temp_c", "true_moisture_pct", "soil_seed"])
        self.track_w.writerow(["t", "lat", "lon", "mode", "true_lat", "true_lon"])
        with open(os.path.join(self.out_dir, f"survey_{self.stamp}_points.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["n", "lat", "lon"])
            for p in self.points:
                w.writerow([p["n"], f"{p['lat']:.7f}", f"{p['lon']:.7f}"])

    def close_logs(self):
        if self.samples_w:
            for f in self._files:
                f.close()
            self.samples_w = self.track_w = None
            self.log(f"Logs saved: {self.out_dir}/survey_{self.stamp}_*.csv")

    def record(self, status, p, probe_pos=None, true_pos=None, reading=None):
        est = probe_pos or self.est
        tru = true_pos or self.true
        row = {"n": p["n"], "status": status, "time": datetime.now().strftime("%H:%M:%S"),
               "error_m": round(dist_m(*est, p["lat"], p["lon"]), 2),
               "true_error_m": round(dist_m(*tru, p["lat"], p["lon"]), 2),
               "lat": est[0], "lon": est[1], "true_lat": tru[0], "true_lon": tru[1]}
        row.update(reading or {k: "" for v in SOIL_VARS for k in (v, "true_" + v)})
        with self.lock:
            self.results.append(row)
        if self.samples_w:
            self.samples_w.writerow([p["n"], status, datetime.now().isoformat(timespec="seconds"),
                                     p["lat"], p["lon"], f"{est[0]:.7f}", f"{est[1]:.7f}", row["error_m"],
                                     row["ph"], row["ec_uScm"], row["temp_c"], row["moisture_pct"],
                                     f"{tru[0]:.7f}", f"{tru[1]:.7f}", row["true_error_m"], self.gps_sigma,
                                     row["true_ph"], row["true_ec_uScm"], row["true_temp_c"], row["true_moisture_pct"],
                                     self.soil.seed if self.soil else ""])
            self._files[0].flush()

    def soil_field(self, renew=False):
        """The current made-up soil, centred on the rover's start. New on Start fresh, New soil,
        or when the start moves."""
        origin = self.home or self.est
        if origin and (renew or self.soil is None or dist_m(*origin, *self.soil.origin) > 500):
            self.soil = SoilField(origin)
        return self.soil

    def keepout_extra(self):
        """Avoidance keeps the rover's centre this far beyond an obstacle circle's radius."""
        return (self.params.get("FENCE_MARGIN", 2.0) or 0.0) + (self.params.get("OA_MARGIN_MAX", 1.5) or 0.0)

    def blocked_by(self, lat, lon):
        """The obstacle whose avoidance keep-out zone contains this point (the rover can't get there)."""
        extra = self.keepout_extra()
        for o in self.obstacles:
            if dist_m(lat, lon, o["lat"], o["lon"]) < o["r"] + extra - 0.5:   # some slack: arrival is 1.5 m
                return o
        return None

    def stopped(self):
        if not self.hist or now_s() - self.hist[0][0] < STOPPED_S:
            return False
        old = next((h for h in self.hist if now_s() - h[0] <= STOPPED_S), self.hist[0])
        return dist_m(old[1], old[2], *self.est) < 0.2

    def go(self, state, detail=""):
        with self.lock:
            self.state, self.detail = state, detail

    def start_leg(self):
        p = self.points[self.idx]
        if self.blocked_by(p["lat"], p["lon"]):
            self.skip_blocked(p)
            return
        d0 = dist_m(*self.est, p["lat"], p["lon"])
        v = max(0.3, self.wp_speed)
        self.limit = 30 + 3 * d0 / v
        self.t_leg, self.next_send, self.sends_left = now_s(), 0.0, 3
        self.best_d, self.t_best = d0, now_s()      # stuck detection
        self.go("DRIVING", f"Point {p['n']}/{len(self.points)}")
        self.log(f"Point {p['n']}/{len(self.points)}: {d0:.1f} m away (time limit {self.limit:.0f} s)")

    def start(self):
        if not self.points:
            self.log("No sample points - click the map or make a grid first")
            return
        if self.state not in ("IDLE", "DONE"):
            return
        with self.lock:
            self.results, self.track = [], []
        self.home = self.est
        if not (self.field_contains(self.home) and all(self.field_contains((p["lat"], p["lon"])) for p in self.points)):
            self.make_field()
        if not self.upload_fence():
            self.log("Could not upload the fence; starting anyway (no obstacle avoidance)")
        self.open_logs()
        if not self.set_mode("GUIDED"):
            self.go("IDLE", "Could not enter GUIDED")
            return
        if not self.arm():
            self.go("IDLE", "Rover refused to arm - see the FC messages in the log")
            return
        self.idx = 0
        self.start_leg()

    def field_contains(self, ll):
        if not self.field or not ll:
            return False
        lat0, lon0 = ll
        k = math.cos(math.radians(lat0))
        poly = [(math.radians(lo - lon0) * R_EARTH * k, math.radians(la - lat0) * R_EARTH) for la, lo in self.field]
        hit = False
        for i in range(len(poly)):
            (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
            if (y1 > 0) != (y2 > 0) and 0 < x1 + (0 - y1) * (x2 - x1) / (y2 - y1):
                hit = not hit
        return hit

    def skip_blocked(self, p):
        o = self.blocked_by(p["lat"], p["lon"])
        self.log(f"  BLOCKED point {p['n']}: inside an obstacle's keep-out zone ({o['r']:g} m obstacle "
                 f"{dist_m(p['lat'], p['lon'], o['lat'], o['lon']):.1f} m away; the rover must stay "
                 f"{o['r'] + self.keepout_extra():.1f} m from its centre). Skipping it")
        self.record("BLOCKED", p)
        self.next_point()

    def next_point(self):
        self.idx += 1
        if self.idx < len(self.points):
            if not self.set_mode("GUIDED"):
                self.hold("PAUSED", "DRIVING", f"could not return to GUIDED (mode {self.mode})")
                return
            self.start_leg()
        else:
            self.log("Survey complete - returning to start (RTL)")
            self.come_home(finished=True)

    def hold(self, kind, came_from, reason):
        self.held_from = came_from
        with self.lock:
            self.hold_reason = reason
        if came_from == "PROBING":
            self.phase_left = max(0.0, self.phase_end - now_s())
        self.go(kind, reason)
        self.log(f"{kind}: {reason}")

    def come_home(self, finished=False):
        probing = self.state == "PROBING" or (self.state in ("STOPPED", "PAUSED") and self.held_from == "PROBING")
        if probing and self.phase < len(self.probe_steps) and not self.home_after_probe:
            if self.probe_steps[self.phase][0] != "settle":      # probe is (or may be) in the ground
                self.log("COME HOME during a test: retracting the probe first")
                last = len(self.probe_steps) - 1
                if self.phase != last or self.state != "PROBING":   # already retracting? let it finish
                    self.phase = last
                    self.phase_end = now_s() + self.probe_steps[last][1]
                self.home_after_probe = True
                self.set_mode("HOLD")
                self.go("PROBING", "Retracting probe, then home")
                return
        self.home_after_probe = False
        if not finished:
            self.log("COME HOME: abandoning the survey")
        if self.set_mode("RTL"):
            self.go("HOMING", "Returning to start")
        else:
            self.hold("PAUSED", "HOMING", f"RTL refused (mode {self.mode})")

    def resume(self):
        if self.state not in ("STOPPED", "PAUSED"):
            return
        frm = self.held_from
        if frm == "DRIVING":
            if self.set_mode("GUIDED"):
                self.log("Resumed")
                self.start_leg()
        elif frm == "PROBING":
            if self.set_mode("HOLD"):
                self.phase_end = now_s() + (self.phase_left or 0)
                self.go("PROBING", self.probe_steps[self.phase][0])
                self.log("Resumed the probe cycle")
        elif frm == "HOMING":
            if self.set_mode("RTL"):
                self.go("HOMING", "Returning to start")

    def step(self):
        st = self.state
        if st == "DRIVING":
            if self.mode != "GUIDED":
                self.hold("PAUSED", "DRIVING", f"mode changed to {self.mode} (failsafe, fence or operator)")
                return
            p = self.points[self.idx]
            if self.blocked_by(p["lat"], p["lon"]):       # an obstacle was dropped next to it mid-leg
                self.skip_blocked(p)
                return
            if self.sends_left and now_s() >= self.next_send:
                # Send the target 3 times, 1 s apart, then STOP sending. Every SET_POSITION_TARGET
                # cancels ArduPilot's obstacle-avoidance detour (AR_WPNav_OA::set_desired_location),
                # so re-sending it every second keeps pulling the rover back toward the obstacle.
                # In SITL that cut the clearance from 3.6 m to 0.2 m.
                self.goto(p["lat"], p["lon"])
                self.sends_left -= 1
                self.next_send = now_s() + 1.0
            d = dist_m(*self.est, p["lat"], p["lon"])
            with self.lock:
                self.detail = f"Point {p['n']}/{len(self.points)}: {d:.1f} m to go (GPS)"
            if d < self.best_d - 1.0:
                self.best_d, self.t_best = d, now_s()
            elif now_s() - self.t_best > STUCK_S:
                # Obstacle avoidance can dither forever (back and forth, never closer). Don't burn
                # through the rest of the points skipping them one time limit at a time: stop and
                # let the operator decide (remove an obstacle, Resume, Skip point, or COME HOME).
                self.set_mode("HOLD")
                self.hold("PAUSED", "DRIVING", f"Stuck: no closer to point {p['n']} in {STUCK_S:.0f} s "
                          f"({d:.1f} m away). Move or delete obstacles near it, then Resume - or Skip point")
                return
            settled = now_s() - self.t_leg > STOPPED_S + 2      # don't count the stillness before the leg
            if d <= self.arrive_m or (d <= 2 * self.arrive_m and settled and self.stopped()):
                self.set_mode("HOLD")
                self.phase, self.phase_end = 0, now_s() + self.probe_steps[0][1]
                self.home_after_probe = False
                self.go("PROBING", self.probe_steps[0][0])
                self.log(f"  arrived: {d:.2f} m by GPS, {dist_m(*self.true, p['lat'], p['lon']):.2f} m really")
            elif now_s() - self.t_leg > self.limit:
                self.log(f"  SKIPPED point {p['n']}: not reached in {self.limit:.0f} s ({d:.1f} m short)")
                self.record("SKIPPED", p)
                self.next_point()
        elif st == "PROBING":
            if self.mode != "HOLD":
                self.hold("PAUSED", "PROBING", f"mode changed to {self.mode} during the probe cycle")
                return
            if now_s() < self.phase_end:
                return
            name = self.probe_steps[self.phase][0]
            if name == "settle":
                self.probe_pos, self.probe_true = self.est, self.true      # where the probe goes in
            if name == "reading sensor" and not self.home_after_probe:
                pos = self.probe_true or self.true                     # the soil where the probe really went in
                self.reading = self.soil_field().measure(*pos)
            self.phase += 1
            if self.phase < len(self.probe_steps):
                self.phase_end = now_s() + self.probe_steps[self.phase][1]
                with self.lock:
                    self.detail = self.probe_steps[self.phase][0]
                return
            p = self.points[self.idx]
            if self.home_after_probe:
                self.record("ABORTED", p)
                self.home_after_probe = False
                self.come_home()
                return
            self.record("OK", p, self.probe_pos, self.probe_true, self.reading)
            r = self.results[-1]
            self.log(f"  SAMPLED point {p['n']}: pH {r['ph']}  (Pi: {r['error_m']:.2f} m, true: {r['true_error_m']:.2f} m)")
            self.next_point()
        elif st == "HOMING":
            if self.mode not in ("RTL", "HOLD"):
                self.hold("PAUSED", "HOMING", f"mode changed to {self.mode} on the way home")
                return
            d = dist_m(*self.est, *self.home)
            with self.lock:
                self.detail = f"Returning to start: {d:.1f} m"
            # No "stopped" test here: at home, RTL keeps nudging the rover as the GPS drifts, so it
            # may never sit still. Close enough (by the same GPS the FC uses) -> HOLD and disarm.
            if d <= self.arrive_m + 1.0:
                self.set_mode("HOLD")
                self.disarm()
                self.close_logs()
                self.go("DONE", "Home. Disarmed.")
                self.log("Home. Disarmed.")
        elif st == "PAUSED" and self.held_from == "DRIVING" and self.mode == "GUIDED":
            self.log("Back in GUIDED - resuming")
            self.start_leg()

    def move_start(self, c):
        """Move the rover's start (SITL's home): write it where start_sim.sh reads it and restart SITL."""
        if not (self.home_file and self.restart_cmd):
            self.log("Moving the start needs the server setup (start_sim.sh). Locally: restart "
                     "sim_vehicle.py with --custom-location=LAT,LON,100,0")
            return
        if self.state not in ("IDLE", "DONE"):
            self.log("Finish or stop the survey before moving the start")
            return
        if c.get("default"):
            try:
                os.remove(self.home_file)
            except FileNotFoundError:
                pass
            where = "the default location"
        else:
            lat, lon = float(c["lat"]), float(c["lon"])
            if not (-85 <= lat <= 85 and -180 <= lon <= 180):
                self.log("That start location is off the map")
                return
            hdg = float(c.get("heading", 0)) % 360
            with open(self.home_file, "w") as f:
                f.write(f"{lat:.7f},{lon:.7f},100,{hdg:.0f}\n")
            where = f"{lat:.6f}, {lon:.6f}"
        with self.lock:                  # the old points/obstacles/field are somewhere else now
            self.points, self.obstacles, self.corners, self.field = [], [], [], []
            self.results, self.track = [], []
        self.log(f"Moving the start to {where}: restarting SITL (about 40 s)")
        subprocess.Popen(self.restart_cmd, shell=True)

    # ------------------------------------------------------------ UI commands
    def handle_cmd(self, c):
        name = c.get("cmd")
        if name == "start":
            self.start()
        elif name == "stop":
            if self.state in ("DRIVING", "PROBING", "HOMING"):
                frm = self.state
                self.set_mode("HOLD")
                self.hold("STOPPED", frm, "STOP from the operator")
        elif name == "resume":
            self.resume()
        elif name == "skip":
            driving = self.state == "DRIVING" or (self.state in ("STOPPED", "PAUSED") and self.held_from == "DRIVING")
            if driving and self.idx < len(self.points):
                p = self.points[self.idx]
                self.log(f"  SKIPPED point {p['n']} (operator)")
                self.record("SKIPPED", p)
                self.next_point()
        elif name == "come_home":
            if self.state in ("DRIVING", "PROBING", "STOPPED", "PAUSED"):
                self.come_home()
        elif name == "set_points" and self.state in ("IDLE", "DONE"):
            pts = [{"lat": float(p["lat"]), "lon": float(p["lon"])} for p in c.get("points", [])[:MAX_POINTS + 1]]
            ref = self.true or self.est
            if ref and any(dist_m(p["lat"], p["lon"], *ref) > 2000 for p in pts):
                self.log("Points must be within 2 km of the rover")
                return
            self.set_points(pts)
        elif name == "grid" and self.state in ("IDLE", "DONE"):
            size = min(300.0, max(10.0, float(c.get("size", 60))))
            spacing = min(100.0, max(3.0, float(c.get("spacing", 15))))
            margin = min(20.0, max(0.0, float(c.get("margin", 4))))
            if len(self.corners) >= 3:
                lat0, lon0 = self.corners[0]
                k = math.cos(math.radians(lat0))
                xy = [(math.radians(lo - lon0) * R_EARTH * k, math.radians(la - lat0) * R_EARTH) for la, lo in self.corners]
                area = abs(sum(xy[i][0] * xy[i - 1][1] - xy[i - 1][0] * xy[i][1] for i in range(len(xy)))) / 2
                est = area / spacing ** 2
            else:
                est = (size / spacing + 1) ** 2
            if est > MAX_POINTS * 1.5:
                self.log(f"That grid is too dense (limit about {MAX_POINTS} points): use a bigger spacing")
                return
            self.make_grid(size, spacing, margin)
        elif name == "set_corners" and self.state in ("IDLE", "DONE"):
            corners = [(float(p["lat"]), float(p["lon"])) for p in c.get("corners", [])[:MAX_CORNERS + 1]]
            if len(corners) > MAX_CORNERS:
                self.log(f"Too many corners (limit {MAX_CORNERS})")
                return
            ref = self.true or self.est
            if ref and any(dist_m(la, lo, *ref) > 2000 for la, lo in corners):
                self.log("Field corners must be within 2 km of the rover")
                return
            with self.lock:
                self.corners = corners
            if c.get("announce"):
                self.log(f"Field outline: {len(corners)} corner(s)" + ("" if len(corners) >= 3 else " (need 3+)"))
        elif name == "set_start":
            self.move_start(c)
        elif name == "new_soil" and self.state in ("IDLE", "DONE"):
            self.soil_field(renew=True)
            with self.lock:
                self.results = []
            self.log(f"New made-up soil (layout #{self.soil.seed}). Previous readings cleared")
        elif name == "add_obstacle":
            lat, lon = float(c["lat"]), float(c["lon"])
            r = min(10.0, max(0.3, float(c.get("r", 1.0))))
            if len(self.obstacles) >= MAX_OBSTACLES:
                self.log(f"Obstacle limit reached ({MAX_OBSTACLES})")
                return
            if self.true and dist_m(lat, lon, *self.true) > 2000:
                self.log("Obstacle too far from the rover")
                return
            if self.true and dist_m(lat, lon, *self.true) < r + 1.0:
                self.log("Not placing an obstacle on top of the rover")
                return
            with self.lock:
                self.obstacles.append({"id": self.next_obs_id, "lat": lat, "lon": lon, "r": r})
                self.next_obs_id += 1
            self.fence_dirty = True
            self.log(f"Obstacle added ({r:g} m radius)")
        elif name == "remove_obstacle":
            with self.lock:
                self.obstacles = [o for o in self.obstacles if o["id"] != c.get("id")]
            self.fence_dirty = True
        elif name == "clear_obstacles":
            with self.lock:
                self.obstacles = []
            self.fence_dirty = True
        elif name == "gps_error":
            self.gps_sigma = max(0.0, min(10.0, float(c.get("sigma", 0))))
            self.log(f"GPS error set to ~{self.gps_sigma:g} m")
        elif name == "fast_probe":
            self.probe_steps = PROBE_FAST if c.get("on") else PROBE_REAL
            self.log("Probe cycle: " + ("fast (6 s)" if c.get("on") else "real timing (37 s)"))
        elif name == "speed":
            if c.get("value") in SPEEDS or isinstance(c.get("value"), (int, float)):
                self.set_speed(c["value"])
        elif name == "reset" and self.state in ("IDLE", "DONE"):           # (keeps the same soil)
            with self.lock:
                self.results, self.track = [], []
            self.home = self.est
            self.go("IDLE", "Ready")
        elif name == "reset_all" and self.state in ("IDLE", "DONE"):
            # fresh start for the next driver: no points, obstacles, results, GPS error
            with self.lock:
                self.results, self.track, self.obstacles = [], [], []
                self.points, self.corners = [], []
            self.field, self.fence_dirty = [], True
            self.gps_sigma = 0.0
            self.home = self.est
            self.upload_fence()
            self.go("IDLE", "Cleared - add sample points, then press Start")
            self.soil_field(renew=True)
            self.log("Cleared points, obstacles, results and GPS error; new made-up soil")
        elif name == "restart_sitl":
            if not self.restart_cmd:
                self.log("Restarting SITL is not set up on this server")
            elif self.state in ("DRIVING", "PROBING", "HOMING"):
                self.log("STOP or finish the survey before restarting SITL")
            else:
                self.log("Restarting SITL (rover goes back to its start) ...")
                subprocess.Popen(self.restart_cmd, shell=True)

    def run(self):
        try:
            self.connect()
            while True:
                self.pump(0.1)
                while not self.cmds.empty():
                    try:
                        self.handle_cmd(self.cmds.get_nowait())
                    except Exception as e:     # noqa: BLE001 - keep the sim alive, report it
                        self.log(f"Command error: {e!r}")
                try:
                    if self.reinit_needed and self.connected:
                        self.reinit()
                    if self.fence_dirty and self.field and self.state not in ("CONNECTING",):
                        self.upload_fence()
                    self.gps_tick()
                except Exception as e:         # noqa: BLE001 - keep the sim alive, report it
                    self.fence_dirty = False
                    self.log(f"Housekeeping error: {e!r}")
                if self.est and self.true:
                    try:
                        self.step()
                    except Exception as e:     # noqa: BLE001 - never leave the rover driving blind
                        import traceback; traceback.print_exc()
                        self.log(f"Mission error: {e!r} - holding")
                        self.set_mode("HOLD")
                        self.hold("STOPPED", self.state if self.state in ("DRIVING", "PROBING", "HOMING")
                                  else "DRIVING", f"internal error: {e!r}")
        finally:
            self.shutdown()

    def shutdown(self):
        try:
            if self.m and self.glitch_param:
                self.push_gps_error(0.0, 0.0)
            if self.m and self.state in ("DRIVING", "PROBING", "HOMING"):
                self.m.mav.command_long_send(self.m.target_system, self.m.target_component,
                                             mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0,
                                             mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                                             self.m.mode_mapping()["HOLD"], 0, 0, 0, 0, 0)
        except Exception:                      # noqa: BLE001
            pass
        self.close_logs()


# ---------------------------------------------------------------- simulated soil
SOIL_VARS = ("ph", "ec_uScm", "temp_c", "moisture_pct")
# SEN0604 (datasheets/Soil Sensing/Sensor Specs.pdf): resolution, and the noise we give it
#   moisture +/-2 % (0-50 %), temp +/-0.5 C, EC +/-3 % of 10000 uS/cm full scale, pH: no accuracy listed
#   (the project requirement is +/-0.5 pH vs lab). Sigma ~ half the spec, so ~95 % of readings are in spec.
SENSOR = {"ph": (0.1, 0.20), "ec_uScm": (1, 150.0), "temp_c": (0.1, 0.25), "moisture_pct": (0.1, 1.0)}
SOIL_LIMITS = {"ph": (3.5, 9.0), "ec_uScm": (50, 3000), "temp_c": (5, 35), "moisture_pct": (3, 60)}


class SoilField:
    """A made-up but field-like soil: a gentle trend across the field, a wet low spot, an acidic
    patch, a salty/fertilised strip, and some small-scale texture. Smooth in space, so nearby points
    read alike and the heat map shows real-looking zones. Each new field gets a new random layout."""

    def __init__(self, origin, seed=None):
        self.origin = origin
        self.seed = seed if seed is not None else random.randrange(1, 10 ** 6)
        rng = random.Random(self.seed)
        u = rng.uniform
        self.k = math.cos(math.radians(origin[0]))
        ang = u(0, 2 * math.pi)
        self.trend = (math.cos(ang), math.sin(ang), u(-0.4, 0.4), u(-5, 5), u(-1.0, 1.0))  # dir, dpH, dmoist, dtemp per 100 m
        # features land mostly NE of the start, where "Make grid" puts the field (start = SW corner + 10 m)
        self.wet = (u(-10, 60), u(-10, 60), u(12, 25))                # x, y, radius (m)
        self.acid = (u(-10, 60), u(-10, 60), u(12, 28), u(0.8, 1.5))  # x, y, radius, pH drop
        a2 = u(0, math.pi)
        self.strip = (u(0, 50), u(0, 50), math.cos(a2), math.sin(a2), u(5, 9), u(400, 900))  # point, dir, width, +EC
        self.waves = [(u(12, 25), u(0, 2 * math.pi), u(0, 2 * math.pi)) for _ in range(3)]
        self.bias = u(-0.1, 0.1)                                      # this probe's pH calibration offset
        self.base = {"ph": u(6.1, 6.8), "ec_uScm": u(300, 550), "temp_c": u(13, 19), "moisture_pct": u(18, 28)}

    def xy(self, lat, lon):
        return (math.radians(lon - self.origin[1]) * R_EARTH * self.k,
                math.radians(lat - self.origin[0]) * R_EARTH)

    def truth(self, lat, lon):
        x, y = self.xy(lat, lon)
        dx, dy, tph, tmo, tte = self.trend
        along = (x * dx + y * dy) / 100.0
        v = dict(self.base)
        v["ph"] += tph * along
        v["moisture_pct"] += tmo * along
        v["temp_c"] += tte * along
        wx, wy, wr = self.wet
        g = math.exp(-((x - wx) ** 2 + (y - wy) ** 2) / (2 * wr ** 2))
        v["moisture_pct"] += 18 * g
        v["ec_uScm"] += 350 * g
        v["temp_c"] -= 1.5 * g
        v["ph"] += 0.2 * g
        ax, ay, ar, drop = self.acid
        g = math.exp(-((x - ax) ** 2 + (y - ay) ** 2) / (2 * ar ** 2))
        v["ph"] -= drop * g
        v["ec_uScm"] -= 80 * g
        sx, sy, ux, uy, w, dec = self.strip
        off = (x - sx) * -uy + (y - sy) * ux            # distance across the strip
        g = math.exp(-off ** 2 / (2 * w ** 2))
        v["ec_uScm"] += dec * g
        v["ph"] += 0.35 * g
        for i, (lam, a, ph0) in enumerate(self.waves):
            t = math.sin(2 * math.pi * (x * math.cos(a) + y * math.sin(a)) / lam + ph0)
            v["ph"] += 0.08 * t
            v["moisture_pct"] += 1.2 * t
            v["ec_uScm"] += 30 * t
        for key, (lo, hi) in SOIL_LIMITS.items():
            v[key] = min(hi, max(lo, v[key]))
        return v

    def measure(self, lat, lon):
        """What the probe reports at this spot, plus the truth it's trying to measure."""
        t = self.truth(lat, lon)
        out = {}
        for key, (res, sigma) in SENSOR.items():
            m = t[key] + random.gauss(0, sigma) + (self.bias if key == "ph" else 0.0)
            lo, hi = SOIL_LIMITS[key]
            m = min(hi, max(lo, m))
            out[key] = int(round(m)) if res == 1 else round(round(m / res) * res, 1)
            out["true_" + key] = int(round(t[key])) if res == 1 else round(t[key], 2)
        return out


# ---------------------------------------------------------------- who is driving
class Control:
    """One driver at a time. Everyone else watches; "Take control" joins the line.

    Every page poll (several per second) counts as a heartbeat. A driver whose page goes quiet for
    `timeout` seconds (closed the tab, lost connection) loses control to the next person in line.
    If people are waiting, a driver also hands over after `turn_s` seconds. Admins can take over.
    With auth "none" (running locally) there is a single user who always has control."""

    VIEWER_GONE_S = 30.0

    def __init__(self, log, admins=(), timeout=10.0, turn_s=900.0, open_mode=False):
        self.log = log
        self.admins = {a.strip().lower() for a in admins if a.strip()}
        self.timeout, self.turn_s, self.open_mode = timeout, turn_s, open_mode
        self.lock = threading.Lock()
        self.driver, self.driver_since = None, 0.0
        self.line = []                 # emails waiting, in order
        self.seen = {}                 # email -> last poll time

    def _tidy(self):
        t = now_s()
        for who, ts in list(self.seen.items()):
            if t - ts > self.VIEWER_GONE_S:
                del self.seen[who]
        self.line = [w for w in self.line if t - self.seen.get(w, 0) <= self.timeout]
        if self.driver and t - self.seen.get(self.driver, 0) > self.timeout:
            self._hand_over(f"{self.driver} left")
        elif self.driver and self.line and t - self.driver_since > self.turn_s:
            self._hand_over(f"{self.driver}'s turn is up")
        if not self.driver and self.line:
            self._hand_over(None)

    def _hand_over(self, why):
        prev = self.driver
        self.driver = self.line.pop(0) if self.line else None
        self.driver_since = now_s()
        msg = f"Control: {why}. " if why else "Control: "
        self.log(msg + (f"{self.driver} is driving" if self.driver else "nobody is driving"))
        return prev

    def touch(self, who):
        with self.lock:
            self.seen[who] = now_s()
            self._tidy()

    def can_drive(self, who):
        if self.open_mode:
            return True
        with self.lock:
            self._tidy()
            return who == self.driver

    def command(self, who, name):
        if self.open_mode:
            return
        with self.lock:
            self.seen[who] = now_s()
            self._tidy()
            if name == "take":
                if self.driver is None:
                    self.driver, self.driver_since = who, now_s()
                    self.log(f"Control: {who} is driving")
                elif who != self.driver and who not in self.line:
                    self.line.append(who)
                    self.log(f"Control: {who} is waiting (#{len(self.line)} in line)")
            elif name == "release":
                if who == self.driver:
                    self._hand_over(f"{who} handed over")
                elif who in self.line:
                    self.line.remove(who)
            elif name == "takeover" and who in self.admins and who != self.driver:
                if who in self.line:
                    self.line.remove(who)
                if self.driver:
                    self.line.insert(0, self.driver)
                self.log(f"Control: {who} (admin) took over from {self.driver or 'nobody'}")
                self.driver, self.driver_since = who, now_s()

    def info(self, who):
        if self.open_mode:
            return {"you": who, "role": "driver", "can_control": True, "open": True,
                    "driver": who, "line": [], "watching": 1, "turn_left_s": None, "admin": True}
        with self.lock:
            self._tidy()
            role = ("driver" if who == self.driver else
                    "waiting" if who in self.line else "viewer")
            left = (max(0.0, self.turn_s - (now_s() - self.driver_since))
                    if self.driver and self.line else None)
            return {"you": who, "role": role, "can_control": role == "driver", "open": False,
                    "driver": self.driver, "line": list(self.line),
                    "place": self.line.index(who) + 1 if who in self.line else None,
                    "watching": len(self.seen), "turn_left_s": left,
                    "admin": who in self.admins, "timeout_s": self.timeout}


class AccessVerifier:
    """Checks the Cloudflare Access token on each request (Cf-Access-Jwt-Assertion header or the
    CF_Authorization cookie) and returns the signed-in email. Needs: pip install "pyjwt[crypto]"."""

    def __init__(self, team, aud, certs_url=None):
        import jwt                                   # noqa: PLC0415 - only needed in this mode
        self.jwt = jwt
        self.aud = aud
        self.issuer = f"https://{team}.cloudflareaccess.com"
        self.keys = jwt.PyJWKClient(certs_url or self.issuer + "/cdn-cgi/access/certs",
                                    cache_keys=True, lifespan=3600)

    def email(self, token):
        if not token:
            return None
        try:
            key = self.keys.get_signing_key_from_jwt(token).key
            claims = self.jwt.decode(token, key, algorithms=["RS256"], audience=self.aud,
                                     issuer=self.issuer, options={"require": ["exp", "aud", "iss"]})
        except Exception:                            # noqa: BLE001 - any failure = not signed in
            return None
        email = claims.get("email")
        return email.lower() if email else None


# ---------------------------------------------------------------- web server
def _no_nan(name):
    raise ValueError(f"{name} not allowed")


SIM_CMDS = {"start", "stop", "resume", "skip", "come_home", "set_points", "grid", "add_obstacle", "set_corners", "set_start",
            "remove_obstacle", "clear_obstacles", "gps_error", "fast_probe", "speed", "reset",
            "reset_all", "restart_sitl", "new_soil"}
ADMIN_CMDS = {"restart_sitl"}


def make_handler(sim, control, auth, verifier=None, rate=10.0):
    page_path = os.path.join(HERE, "nav_sim_ui.html")
    buckets = {}                                     # email -> [tokens, last time]

    def allowed(who):
        t = now_s()
        tok, last = buckets.get(who, [rate * 2, t])
        tok = min(rate * 2, tok + (t - last) * rate)
        ok = tok >= 1
        buckets[who] = [tok - 1 if ok else tok, t]
        return ok

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def who(self):
            if auth == "none":
                return "local"
            if auth == "header":                     # trust Cloudflare's header (testing only)
                e = self.headers.get("Cf-Access-Authenticated-User-Email")
                return e.strip().lower() if e else None
            token = self.headers.get("Cf-Access-Jwt-Assertion")
            if not token and self.headers.get("Cookie"):
                c = SimpleCookie()
                try:
                    c.load(self.headers["Cookie"])
                except Exception:                    # noqa: BLE001
                    pass
                token = c["CF_Authorization"].value if "CF_Authorization" in c else None
            return verifier.email(token)

        def do_GET(self):
            u = urlparse(self.path)
            who = self.who()
            if who is None:
                return self.send(401, '{"error":"not signed in"}')
            if u.path in ("/", "/index.html"):
                with open(page_path, "rb") as f:
                    self.send(200, f.read(), "text/html; charset=utf-8")
            elif u.path == "/api/state":
                try:
                    since = max(0, int(parse_qs(u.query).get("since", ["0"])[0]))
                except ValueError:
                    since = 0
                control.touch(who)
                snap = sim.snapshot(since)
                snap["control"] = control.info(who)
                self.send(200, json.dumps(snap))
            elif u.path == "/api/soil":
                # the made-up "true" soil on a grid, for the page's "true field" heat map
                q = parse_qs(u.query)
                try:
                    s_, w_, n_, e_ = (float(q[k][0]) for k in ("s", "w", "n", "e"))
                    var = q.get("var", ["ph"])[0]
                    nx = min(160, max(8, int(q.get("nx", ["100"])[0])))
                    ny = min(160, max(8, int(q.get("ny", ["100"])[0])))
                except (KeyError, ValueError):
                    return self.send(400, '{"error":"need s, w, n, e"}')
                soil = sim.soil_field()
                if var not in SOIL_VARS or soil is None or not (s_ < n_ and w_ < e_) \
                        or dist_m(s_, w_, n_, e_) > 3000:
                    return self.send(400, '{"error":"bad request"}')
                vals = [round(soil.truth(s_ + (n_ - s_) * (j + 0.5) / ny, w_ + (e_ - w_) * (i + 0.5) / nx)[var], 3)
                        for j in range(ny) for i in range(nx)]
                self.send(200, json.dumps({"seed": soil.seed, "var": var, "nx": nx, "ny": ny,
                                           "s": s_, "w": w_, "n": n_, "e": e_, "values": vals}))
            elif u.path == "/api/points.csv":
                rows = ["n,lat,lon"] + [f"{p['n']},{p['lat']:.7f},{p['lon']:.7f}" for p in sim.points]
                self.send(200, "\n".join(rows) + "\n", "text/csv")
            else:
                self.send(404, '{"error":"not found"}')

        def do_POST(self):
            if urlparse(self.path).path != "/api/cmd":
                return self.send(404, '{"error":"not found"}')
            who = self.who()
            if who is None:
                return self.send(401, '{"error":"not signed in"}')
            try:
                n = int(self.headers.get("Content-Length", 0))
            except ValueError:
                n = 0
            if n > 200_000:
                return self.send(413, '{"error":"too big"}')
            try:
                c = json.loads(self.rfile.read(n) or b"{}", parse_constant=_no_nan)
            except ValueError:
                return self.send(400, '{"error":"bad json"}')
            if not isinstance(c, dict):
                return self.send(400, '{"error":"bad command"}')
            if not allowed(who):
                return self.send(429, '{"error":"slow down"}')
            name = c.get("cmd")
            if name in ("take", "release", "takeover"):
                control.command(who, name)
                return self.send(200, '{"ok":true}')
            if name not in SIM_CMDS:
                return self.send(400, '{"error":"unknown command"}')
            if name in ADMIN_CMDS and auth != "none" and not control.info(who)["admin"]:
                return self.send(403, '{"error":"admins only"}')
            if not control.can_drive(who):
                return self.send(403, '{"error":"you are not driving"}')
            sim.cmds.put(c)
            self.send(200, '{"ok":true}')

    return H


def main(argv=None):
    ap = argparse.ArgumentParser(description="D.I.R.T.T. navigation simulation (ArduPilot SITL + browser UI)")
    ap.add_argument("--connect", default="tcp:127.0.0.1:5762",
                    help="SITL's spare SERIAL1 port, so MAVProxy keeps working (default tcp:127.0.0.1:5762)")
    ap.add_argument("--baud", type=int, default=57600)
    ap.add_argument("--port", type=int, default=8000, help="web UI port (default 8000)")
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to open the UI from another device")
    ap.add_argument("--points", help="optional <out>_points.csv from grid_planner.py to load at start")
    ap.add_argument("--logs", default="runs", help="folder for the survey CSVs (default ./runs)")
    g = ap.add_argument_group("shared web server (see server/SETUP.md)")
    g.add_argument("--auth", choices=("none", "access", "header"), default="none",
                   help="none: local, one user (default). access: Cloudflare Access sign-in, one driver "
                        "at a time. header: like access but trusts the email header (testing only)")
    g.add_argument("--access-team", help="Cloudflare Zero Trust team name (<team>.cloudflareaccess.com)")
    g.add_argument("--access-aud", help="the Access application's Audience (AUD) tag")
    g.add_argument("--access-certs-url", help=argparse.SUPPRESS)          # tests
    g.add_argument("--admins", default="", help="comma-separated emails that can take over and restart SITL")
    g.add_argument("--driver-timeout", type=float, default=10.0, help="seconds without a poll before the driver loses control")
    g.add_argument("--turn-minutes", type=float, default=15.0, help="driving turn length when someone is waiting")
    g.add_argument("--restart-cmd", help="shell command that restarts SITL (e.g. 'pkill -x ardurover' when a supervisor restarts it)")
    g.add_argument("--home-file", help="file the SITL launcher reads the start location from; enables 'Move start here'")
    a = ap.parse_args(argv)

    verifier = None
    if a.auth == "access":
        if not (a.access_team and a.access_aud):
            ap.error("--auth access needs --access-team and --access-aud")
        try:
            verifier = AccessVerifier(a.access_team, a.access_aud, a.access_certs_url)
        except ImportError:
            ap.error('--auth access needs PyJWT: pip install "pyjwt[crypto]"')
    if a.auth == "header" and a.host not in ("127.0.0.1", "localhost"):
        print("WARNING: --auth header trusts a header anyone can send; keep --host 127.0.0.1", flush=True)

    sim = Sim(a.connect, a.baud, a.logs)
    sim.restart_cmd = a.restart_cmd
    sim.home_file = a.home_file
    control = Control(sim.log, a.admins.split(","), a.driver_timeout, a.turn_minutes * 60,
                      open_mode=(a.auth == "none"))
    if a.points:
        with open(a.points) as f:
            pts = [{"lat": float(r["lat"]), "lon": float(r["lon"])} for r in csv.DictReader(f)]
        sim.cmds.put({"cmd": "set_points", "points": pts})
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(sim, control, a.auth, verifier))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"UI: http://localhost:{a.port}   (auth: {a.auth})   (Ctrl+C to quit)", flush=True)
    try:
        sim.run()
    except KeyboardInterrupt:
        print("\nCtrl+C - putting the rover in HOLD and clearing the GPS error", flush=True)
    finally:
        sim.shutdown()


if __name__ == "__main__":
    main()
