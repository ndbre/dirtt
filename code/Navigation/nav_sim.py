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
"""
import argparse, collections, csv, json, math, os, queue, random, sys, threading, time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
TRACK_PERIOD_S = 0.5
FENCE_PAD_M = 8.0                          # field boundary = points + home, padded by this
PROBE_REAL = (("settle", 2.0), ("probe down", 15.0), ("reading sensor", 5.0), ("probe up", 15.0))
PROBE_FAST = (("settle", 1.0), ("probe down", 2.0), ("reading sensor", 1.0), ("probe up", 2.0))
GPS_TAU_S = 45.0                           # GPS error correlation time (how slowly it wanders)
SPEEDS = {"real": 0.6, "fast": 2.0}
# SITL's GPS glitch offset (degrees) was renamed when the GPS sim parameters moved into groups:
# ArduPilot 4.6 and earlier: SIM_GPS_GLITCH_X/Y/Z   ArduPilot 4.7 / master: SIM_GPS1_GLTCH_X/Y/Z
GLITCH_NAMES = ("SIM_GPS_GLITCH", "SIM_GPS1_GLTCH")        # m/s. Real: 83 RPM x 0.19 m wheel = 0.83 m/s no-load

# Parameters the simulation needs. (value, needs reboot, why)
WANT = {
    "WP_RADIUS": (1.0, False, "arrival radius the FC uses; the Pi adds 0.5 m"),
    "FENCE_ENABLE": (1, False, "fence holds the field edge and the obstacles"),
    "FENCE_ACTION": (0, False, "report only: avoidance, not the fence, handles obstacles"),
    "AVOID_ENABLE": (0, False, "simple avoidance off: it deadlocks pivot turns near obstacles; BendyRuler avoids"),
    "OA_TYPE": (1, True, "BendyRuler obstacle avoidance"),
    "PRX1_TYPE": (10, True, "SITL proximity sensor = simulated LiDAR"),
}


def now_s():
    return time.time()


def dist_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(min(1.0, a)))


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
        self.speed_choice = "fast"
        self.results = []
        self.log_lines = collections.deque(maxlen=200)
        self.track = []            # [(t, est_lat, est_lon, true_lat, true_lon)]
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
                "speed_choice": self.speed_choice,
                "results": self.results, "log": list(self.log_lines)[-80:],
                "track_from": since, "track": self.track[since:], "track_len": len(self.track),
                "lidar": self.lidar, "warnings": self.warnings, "fence_status": self.fence_status,
                "stats": {"planned": len(self.points), "sampled": len(ok),
                          "skipped": sum(r["status"] != "OK" for r in self.results),
                          "mean_true": sum(errs) / len(errs) if errs else None,
                          "max_true": max(errs) if errs else None,
                          "within3": sum(e <= 3.0 for e in errs)},
                "editable": self.state in ("IDLE", "DONE", "CONNECTING"),
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
        names = list(WANT) + ["WP_SPEED", "CRUISE_SPEED"] + [g + "_X" for g in GLITCH_NAMES]
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
        self.set_speed(self.speed_choice)
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

    def set_param(self, name, value):
        self.m.mav.param_set_send(self.m.target_system, self.m.target_component, name.encode(),
                                  float(value), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)

    def pump(self, wait=0.1):
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
        if self.est and self.true and now_s() >= self.next_track:
            with self.lock:
                self.track.append((round(now_s(), 2), round(self.est[0], 7), round(self.est[1], 7),
                                   round(self.true[0], 7), round(self.true[1], 7)))
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

    def set_speed(self, choice):
        self.speed_choice = choice
        self.set_param("WP_SPEED", SPEEDS[choice])
        self.log(f"Drive speed {SPEEDS[choice]} m/s ({choice})")

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
        o = -10.0                        # rover starts 10 m inside the SW corner: room to turn, and the
                                         # first point is not right next to it (rovers circle tight targets)
        corners = [offset_ll(lat, lon, x, y) for x, y in ((o, o), (o, o + size), (o + size, o + size), (o + size, o))]
        try:
            pts, path, _, rows = grid_planner.plan(corners, spacing, margin, (lat, lon))
        except SystemExit as e:
            self.log(f"Grid planner: {e}")
            return
        self.set_points([{"lat": a, "lon": b} for a, b in pts], field=corners)
        self.log(f"Grid: {len(pts)} points in {rows} rows, {spacing:g} m apart, {path:.0f} m of driving")

    # ------------------------------------------------------------ mission
    def open_logs(self):
        self.stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sf = open(os.path.join(self.out_dir, f"survey_{self.stamp}_samples.csv"), "w", newline="")
        tf = open(os.path.join(self.out_dir, f"survey_{self.stamp}_track.csv"), "w", newline="")
        self._files = (sf, tf)
        self.samples_w, self.track_w = csv.writer(sf), csv.writer(tf)
        self.samples_w.writerow(["n", "status", "time", "planned_lat", "planned_lon", "lat", "lon", "error_m",
                                 "ph", "ec_uScm", "temp_c", "moisture_pct", "true_lat", "true_lon",
                                 "true_error_m", "gps_error_setting_m"])
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
        row.update(reading or {"ph": "", "ec_uScm": "", "temp_c": "", "moisture_pct": ""})
        with self.lock:
            self.results.append(row)
        if self.samples_w:
            self.samples_w.writerow([p["n"], status, datetime.now().isoformat(timespec="seconds"),
                                     p["lat"], p["lon"], f"{est[0]:.7f}", f"{est[1]:.7f}", row["error_m"],
                                     row["ph"], row["ec_uScm"], row["temp_c"], row["moisture_pct"],
                                     f"{tru[0]:.7f}", f"{tru[1]:.7f}", row["true_error_m"], self.gps_sigma])
            self._files[0].flush()

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
        d0 = dist_m(*self.est, p["lat"], p["lon"])
        v = max(0.3, SPEEDS[self.speed_choice])
        self.limit = 30 + 3 * d0 / v
        self.t_leg, self.next_send, self.sends_left = now_s(), 0.0, 3
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
        if not self.field_contains(self.home):
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
                self.reading = simulated_probe(self.points[self.idx]["n"])
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
        elif name == "come_home":
            if self.state in ("DRIVING", "PROBING", "STOPPED", "PAUSED"):
                self.come_home()
        elif name == "set_points" and self.state in ("IDLE", "DONE"):
            self.set_points(c.get("points", []))
        elif name == "grid" and self.state in ("IDLE", "DONE"):
            self.make_grid(float(c.get("size", 60)), float(c.get("spacing", 15)), float(c.get("margin", 4)))
        elif name == "add_obstacle":
            lat, lon, r = float(c["lat"]), float(c["lon"]), float(c.get("r", 1.0))
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
            if c.get("value") in SPEEDS:
                self.set_speed(c["value"])
        elif name == "reset" and self.state in ("IDLE", "DONE"):
            with self.lock:
                self.results, self.track = [], []
            self.home = self.est
            self.go("IDLE", "Ready")

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
                if self.fence_dirty and self.field and self.state not in ("CONNECTING",):
                    self.upload_fence()
                self.gps_tick()
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


def simulated_probe(n):
    """Stand-in for: actuator down -> read SEN0604 over RS-485 -> actuator up."""
    return {"ph": round(random.gauss(6.4 + 0.03 * n, 0.25), 2),
            "ec_uScm": int(max(50, random.gauss(600 + 15 * n, 120))),
            "temp_c": round(random.gauss(14.0, 1.5), 1),
            "moisture_pct": round(min(60, max(5, random.gauss(28, 4))), 1)}


# ---------------------------------------------------------------- web server
def make_handler(sim):
    page_path = os.path.join(HERE, "nav_sim_ui.html")

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

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                with open(page_path, "rb") as f:
                    self.send(200, f.read(), "text/html; charset=utf-8")
            elif u.path == "/api/state":
                since = int(parse_qs(u.query).get("since", ["0"])[0])
                self.send(200, json.dumps(sim.snapshot(since)))
            elif u.path == "/api/points.csv":
                rows = ["n,lat,lon"] + [f"{p['n']},{p['lat']:.7f},{p['lon']:.7f}" for p in sim.points]
                self.send(200, "\n".join(rows) + "\n", "text/csv")
            else:
                self.send(404, '{"error":"not found"}')

        def do_POST(self):
            if urlparse(self.path).path != "/api/cmd":
                return self.send(404, '{"error":"not found"}')
            n = int(self.headers.get("Content-Length", 0))
            try:
                c = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self.send(400, '{"error":"bad json"}')
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
    a = ap.parse_args(argv)

    sim = Sim(a.connect, a.baud, a.logs)
    if a.points:
        with open(a.points) as f:
            pts = [{"lat": float(r["lat"]), "lon": float(r["lon"])} for r in csv.DictReader(f)]
        sim.cmds.put({"cmd": "set_points", "points": pts})
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(sim))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"UI: http://localhost:{a.port}   (Ctrl+C to quit)", flush=True)
    try:
        sim.run()
    except KeyboardInterrupt:
        print("\nCtrl+C - putting the rover in HOLD and clearing the GPS error", flush=True)
    finally:
        sim.shutdown()


if __name__ == "__main__":
    main()
