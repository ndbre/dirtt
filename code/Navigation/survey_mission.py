#!/usr/bin/env python3
"""D.I.R.T.T. stop-and-probe survey - the mission-computer (Pi 3) navigation loop.

For every sample point from grid_planner.py:
    GUIDED -> drive to the point -> HOLD -> probe cycle -> log -> next point
then RTL (return to start). This is the same code the Pi 3 will run on the
rover; only the connection string changes:

    SITL (WSL/Linux, on the same machine):  --connect tcp:127.0.0.1:5762
    Real rover (Pi 3 UART to the MicoAir743): --connect /dev/serial0 --baud 57600

The probe cycle is SIMULATED here (timed waits + plausible fake readings).
The real rover replaces simulated_probe() with the actuator + SEN0604 code.

Safety behaviour (worth demonstrating):
  * If the mode changes to anything this script didn't ask for (failsafe,
    geofence, or a person switching to HOLD/MANUAL), the script PAUSES and
    waits. Put the rover back in GUIDED to resume the same point.
  * A point that isn't reached within its time limit is logged as SKIPPED
    and the survey moves on.
  * Ctrl+C puts the rover in HOLD before exiting.

Run:  python3 survey_mission.py test_points.csv
Writes: survey_<time>_samples.csv (one row per point) and survey_<time>_track.csv
        (position every 0.5 s) - plot both with plot_survey.py.
"""
import argparse, collections, csv, math, random, sys, time
from datetime import datetime
from pymavlink import mavutil

ARRIVE_M = 1.5          # fallback "at the point" distance; normally WP_RADIUS + 0.5 m (read from the FC)
STOPPED_S = 3.0         # ...or: within 2 x that distance and not moving for this long
SETTLE_S = 2.0          # wait after stopping before the probe goes down
PROBE_DOWN_S = 15.0     # actuator: 8 in stroke at ~14 mm/s -> ~15 s each way
PROBE_READ_S = 5.0      # SEN0604 settle + Modbus read
PROBE_UP_S = 15.0
TRACK_PERIOD_S = 0.5
POS_MASK = 0b110111111000   # SET_POSITION_TARGET: use position only


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def dist_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(a))


class Rover:
    """Thin wrapper over a pymavlink connection that keeps the latest state."""

    def __init__(self, conn, baud, track_writer):
        self.m = mavutil.mavlink_connection(conn, baud=baud, source_system=1, source_component=191)
        self.lat = self.lon = None
        self.mode = None
        self.armed = False
        self.track = track_writer
        self.next_track = 0.0
        self.next_hb = 0.0
        self.acks = {}
        self.params = {}
        self.hist = collections.deque()          # (time, lat, lon) for the last few seconds

    # ---------------- link
    def connect(self):
        log("Waiting for the flight controller heartbeat ...")
        hb = self.m.wait_heartbeat(timeout=30)
        if hb is None:
            sys.exit("No heartbeat - check the connection string / that SITL is running.")
        log(f"Connected to system {self.m.target_system} (type {hb.type}, autopilot {hb.autopilot})")
        # Ask for position at 5 Hz and heartbeat/status at the usual rate
        for msg_id, hz in ((mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT, 5),):
            self.m.mav.command_long_send(self.m.target_system, self.m.target_component,
                                         mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                                         msg_id, int(1e6 / hz), 0, 0, 0, 0, 0)
        t0 = time.time()
        while self.lat is None:
            self.pump(0.2)
            if time.time() - t0 > 20:
                sys.exit("No GPS position from the flight controller.")
        log(f"Position {self.lat:.6f}, {self.lon:.6f}  mode {self.mode}  {'ARMED' if self.armed else 'disarmed'}")
        self.m.mav.param_request_read_send(self.m.target_system, self.m.target_component, b"WP_RADIUS", -1)
        t0 = time.time()
        while "WP_RADIUS" not in self.params and time.time() - t0 < 3:
            self.pump(0.2)
        if "WP_RADIUS" in self.params:
            self.arrive_m = self.params["WP_RADIUS"] + 0.5
            log(f"WP_RADIUS = {self.params['WP_RADIUS']:.2f} m -> counting a point as reached within "
                f"{self.arrive_m:.2f} m")
        else:
            self.arrive_m = ARRIVE_M
            log(f"Could not read WP_RADIUS; using {ARRIVE_M} m")

    def stopped(self):
        """True if the rover has moved < 0.2 m in the last STOPPED_S seconds."""
        if not self.hist or time.time() - self.hist[0][0] < STOPPED_S:
            return False
        old = next((h for h in self.hist if time.time() - h[0] <= STOPPED_S), self.hist[0])
        return dist_m(old[1], old[2], self.lat, self.lon) < 0.2

    def pump(self, wait=0.1):
        """Read everything waiting; keep state, track log and our heartbeat up to date."""
        now = time.time()
        if now >= self.next_hb:                       # companion-computer heartbeat
            self.m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
                                      mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
            self.next_hb = now + 1.0
        end = now + wait
        while True:
            msg = self.m.recv_match(blocking=True, timeout=max(0.0, end - time.time()))
            if msg is None:
                break
            t = msg.get_type()
            if t == "GLOBAL_POSITION_INT":
                self.lat, self.lon = msg.lat / 1e7, msg.lon / 1e7
                self.hist.append((time.time(), self.lat, self.lon))
                while self.hist and time.time() - self.hist[0][0] > STOPPED_S + 1:
                    self.hist.popleft()
            elif t == "HEARTBEAT" and msg.get_srcSystem() == self.m.target_system \
                    and msg.get_srcComponent() == 1:
                new_mode = mavutil.mode_string_v10(msg)
                if new_mode != self.mode and self.mode is not None:
                    log(f"  mode: {self.mode} -> {new_mode}")
                self.mode = new_mode
                self.armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            elif t == "PARAM_VALUE":
                self.params[msg.param_id] = msg.param_value
            elif t == "COMMAND_ACK":
                self.acks[msg.command] = msg.result
            elif t == "STATUSTEXT":
                log(f"  FC: {msg.text}")
            if time.time() >= end:
                break
        if self.lat is not None and time.time() >= self.next_track:
            self.track.writerow([f"{time.time():.2f}", f"{self.lat:.7f}", f"{self.lon:.7f}", self.mode])
            self.next_track = time.time() + TRACK_PERIOD_S

    # ---------------- commands
    def set_mode(self, name, timeout=5.0):
        """Ask for a mode. Re-send ONLY while the mode is still what it was
        (i.e. our command got lost). If anything else changes the mode in the
        meantime - a failsafe, the fence, a person - give up immediately so we
        never override it."""
        mapping = self.m.mode_mapping()
        if name not in mapping:
            sys.exit(f"Mode {name} unknown to this vehicle ({sorted(mapping)})")
        if self.mode == name:
            return True
        before = self.mode
        cmd = mavutil.mavlink.MAV_CMD_DO_SET_MODE
        accepted = False
        for _ in range(3):                                   # re-send only if NOT acknowledged
            self.acks.pop(cmd, None)
            self.m.mav.command_long_send(self.m.target_system, self.m.target_component, cmd, 0,
                                         mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                                         mapping[name], 0, 0, 0, 0, 0)
            end = time.time() + 1.5
            while time.time() < end and cmd not in self.acks:
                self.pump(0.1)
            if cmd in self.acks:
                if self.acks[cmd] != mavutil.mavlink.MAV_RESULT_ACCEPTED:
                    log(f"  {name} refused by the flight controller (result {self.acks[cmd]})")
                    return False
                accepted = True
                break
        if not accepted:
            log(f"  no reply to the {name} request")
            return False
        # Accepted. Now confirm from the heartbeat; never send it again.
        end = time.time() + timeout
        while time.time() < end:
            self.pump(0.2)
            if self.mode == name:
                return True
            if self.mode != before:
                break
        log(f"  rover is in {self.mode}, not {name} - something else changed the mode; not overriding it")
        return False

    def arm(self, timeout=15.0):
        t0 = time.time()
        while not self.armed:
            if time.time() - t0 > timeout:
                sys.exit("Rover refused to arm - see the FC messages above (PreArm: ...).")
            self.m.mav.command_long_send(self.m.target_system, self.m.target_component,
                                         mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
                                         1, 0, 0, 0, 0, 0, 0)
            self.pump(1.0)
        log("Armed")

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

    def wait_while_paused(self, expected):
        """If someone/something else changed the mode, wait until GUIDED comes back."""
        if self.mode in expected:
            return False
        log(f"PAUSED: rover is in {self.mode} (failsafe, fence or operator). "
            f"Switch back to GUIDED to resume.")
        while self.mode != "GUIDED":
            self.pump(0.5)
        log("Resumed (GUIDED)")
        return True


def simulated_probe(point_no):
    """Stand-in for: actuator down -> read SEN0604 over RS-485 -> actuator up."""
    return {"ph": round(random.gauss(6.4 + 0.03 * point_no, 0.25), 2),
            "ec_uScm": int(max(50, random.gauss(600 + 15 * point_no, 120))),
            "temp_c": round(random.gauss(14.0, 1.5), 1),
            "moisture_pct": round(min(60, max(5, random.gauss(28, 4))), 1)}


def timed(rover, seconds, label):
    log(f"  {label} ({seconds:.0f} s)")
    end = time.time() + seconds
    while time.time() < end:
        rover.pump(0.2)
        rover.wait_while_paused({"HOLD", "GUIDED"})   # an operator could still intervene


def main(argv=None):
    ap = argparse.ArgumentParser(description="D.I.R.T.T. stop-and-probe survey")
    ap.add_argument("points", help="<out>_points.csv from grid_planner.py")
    ap.add_argument("--connect", default="tcp:127.0.0.1:5762")
    ap.add_argument("--baud", type=int, default=57600)
    ap.add_argument("--speed", type=float, default=0.5, help="only used for the per-point time limit")
    ap.add_argument("--fast", action="store_true", help="shorten the probe waits (for quick tests)")
    a = ap.parse_args(argv)

    global SETTLE_S, PROBE_DOWN_S, PROBE_READ_S, PROBE_UP_S
    if a.fast:
        SETTLE_S, PROBE_DOWN_S, PROBE_READ_S, PROBE_UP_S = 1.0, 2.0, 1.0, 2.0

    with open(a.points) as f:
        points = [(int(r["n"]), float(r["lat"]), float(r["lon"])) for r in csv.DictReader(f)]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sf = open(f"survey_{stamp}_samples.csv", "w", newline="")
    tf = open(f"survey_{stamp}_track.csv", "w", newline="")
    samples, track = csv.writer(sf), csv.writer(tf)
    samples.writerow(["n", "status", "time", "planned_lat", "planned_lon", "lat", "lon", "error_m",
                      "ph", "ec_uScm", "temp_c", "moisture_pct"])
    track.writerow(["t", "lat", "lon", "mode"])

    rover = Rover(a.connect, a.baud, track)
    try:
        rover.connect()
        home = (rover.lat, rover.lon)
        log(f"{len(points)} sample points loaded from {a.points}")
        if not rover.set_mode("GUIDED"):
            sys.exit("Could not enter GUIDED.")
        rover.arm()

        for n, lat, lon in points:
            d0 = dist_m(rover.lat, rover.lon, lat, lon)
            limit = 30 + 3 * d0 / a.speed
            log(f"Point {n}/{len(points)}: {d0:.1f} m away (limit {limit:.0f} s)")
            if rover.mode != "GUIDED":
                rover.wait_while_paused({"GUIDED"})
            t0, next_send, reached, sends_left = time.time(), 0.0, False, 3
            while True:
                if sends_left and time.time() >= next_send:
                    # Send the target 3 times, 1 s apart, then stop. Every new target cancels
                    # ArduPilot's obstacle-avoidance detour, so re-sending it every second keeps
                    # pulling the rover back toward the obstacle (SITL: 3.6 m clearance -> 0.2 m).
                    rover.goto(lat, lon)
                    sends_left -= 1
                    next_send = time.time() + 1.0
                rover.pump(0.2)
                if rover.wait_while_paused({"GUIDED"}):
                    t0 = time.time()                      # restart the clock after a pause
                    next_send, sends_left = 0.0, 3
                    continue
                d = dist_m(rover.lat, rover.lon, lat, lon)
                settled = time.time() - t0 > STOPPED_S + 2      # ignore the stillness before the leg
                if d <= rover.arrive_m or (d <= 2 * rover.arrive_m and settled and rover.stopped()):
                    reached = True
                    break
                if time.time() - t0 > limit:
                    break

            if not reached:
                log(f"  SKIPPED point {n}: not reached in {limit:.0f} s")
                samples.writerow([n, "SKIPPED", datetime.now().isoformat(timespec="seconds"),
                                  lat, lon, f"{rover.lat:.7f}", f"{rover.lon:.7f}",
                                  f"{dist_m(rover.lat, rover.lon, lat, lon):.2f}", "", "", "", ""])
                sf.flush()
                continue

            rover.set_mode("HOLD")
            timed(rover, SETTLE_S, "settle")
            plat, plon = rover.lat, rover.lon          # where the probe actually goes in
            timed(rover, PROBE_DOWN_S, "probe down")
            r = simulated_probe(n)
            timed(rover, PROBE_READ_S, "reading sensor")
            timed(rover, PROBE_UP_S, "probe up")
            err = dist_m(plat, plon, lat, lon)
            samples.writerow([n, "OK", datetime.now().isoformat(timespec="seconds"), lat, lon,
                              f"{plat:.7f}", f"{plon:.7f}", f"{err:.2f}",
                              r["ph"], r["ec_uScm"], r["temp_c"], r["moisture_pct"]])
            sf.flush()
            log(f"  SAMPLED point {n}: pH {r['ph']}  EC {r['ec_uScm']}  {r['temp_c']} C  "
                f"{r['moisture_pct']}%  (stopped {err:.2f} m from target)")
            if not rover.set_mode("GUIDED"):
                rover.wait_while_paused({"GUIDED"})

        log("Survey complete - returning to start (RTL)")
        rover.set_mode("RTL")
        t0 = time.time()
        while dist_m(rover.lat, rover.lon, *home) > 2.0 and time.time() - t0 < 600:
            rover.pump(0.5)
        rover.set_mode("HOLD")
        rover.disarm()
        log("Home. Disarmed.")
    except KeyboardInterrupt:
        log("Ctrl+C - putting the rover in HOLD")
        rover.set_mode("HOLD")
    finally:
        sf.close(); tf.close()
        log(f"Logs: survey_{stamp}_samples.csv, survey_{stamp}_track.csv")


if __name__ == "__main__":
    main()
