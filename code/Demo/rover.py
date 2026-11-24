#!/usr/bin/env python3
"""
rover.py - D.I.R.T.T. rover Pi (Pi 3 B) program for the December demo.

Built on the team's rover.py (radio link, soil sensor, CSV upload), plus remote control:
    - LoRa link to the base: heartbeat, status, soil results sent with ACK and resent until received
    - driving: the base sends throttle/steering over LoRa; the rover sends R/C pulses to the
      Cytron MDDRC10 from GPIO18/19 (driver switch on MIX); stops if commands stop for 1 s
    - probe: in PROBE mode the linear actuator is plugged into the MDDRC10 instead of the drive
      motors. One command from the base runs the whole cycle: probe down, read the soil, average,
      probe up, save the result, send it to the base

Run on the rover (normally as a service; see README.md):
    python3 rover.py
    python3 rover.py --sim --fast    # on any computer, with base.py --sim: no radio, sensor or motors

Needs on the Pi: adafruit-circuitpython-rfm9x, adafruit-circuitpython-ssd1306, minimalmodbus,
pigpio (python package) and the pigpiod service.
"""
import argparse
import csv
import os
import random
import signal
import struct
import sys
import threading
import time
from datetime import datetime

import link as L

# =================================================================================================
# SETTINGS (check these on the real hardware)
# =================================================================================================
HOME = os.path.expanduser("~")
DATA_DIR = os.path.join(HOME, "soil")
RESULTS_CSV = os.path.join(DATA_DIR, "probe_results.csv")    # one line per probe; sent to the base
SENT_FILE = os.path.join(DATA_DIR, "probe_sent_index.txt")   # lines the base has acknowledged
FONT = os.path.join(HOME, "font5x8.bin")

LINK_TIMEOUT_S = 10          # no packet from the base for this long = link lost (motors stop)
MAX_LINES_PER_CYCLE = 2      # soil lines sent after each heartbeat

# ---- MDDRC10 on GPIO (BCM numbers), driver switch on MIX ----
RC1_PIN = 18                 # throttle
RC2_PIN = 19                 # steering
NEUTRAL_US = 1500
FULLSCALE_US = 435           # full speed at 1500 +/- 435 us (datasheet)
RAMP_US_PER_STEP = 8         # per 20 ms: about 0.5 s from stop to full
DRIVE_DEADMAN_S = 1.0        # stop if no DRIVE packet for this long
MAX_DRIVE_PCT = 60           # speed cap while driving

# ---- linear actuator, on the MDDRC10 in place of the motors (PROBE mode) ----
ACT_PCT = 100                # actuator speed, %
ACT_EXTEND_SIGN = +1         # if "probe down" pulls the probe UP, change this to -1
EXTEND_S = 15.0              # run time down. Its own limit switch stops it at the end of travel,
RETRACT_S = 18.0             #   so a bit too long is fine. Time a full stroke and set these.
SETTLE_S = 3.0               # wait after the probe is in before reading

# ---- soil sensor (RS485 4-in-1), from the team's soil_test.py ----
SENSOR_PORT = "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_BH006RAQ-if00-port0"
SENSOR_ADDR = 1
SENSOR_BAUD = 9600
READ_INTERVAL_S = 2.0
READ_S = 20.0                # how long to read in the ground (the team's survey used 60 s)
AVG_LAST = 5                 # average the last 5 readings
MIN_GOOD = 3                 # fewer good readings than this = probe failed

RESULT_FIELDS = ["timestamp", "probe_id", "x", "y", "moisture_pct", "temp_c", "ec_uScm", "ph",
                 "readings_averaged"]

log_lock = threading.Lock()


def log(msg):
    with log_lock:
        print(f"{datetime.now():%H:%M:%S} {msg}", flush=True)


# =================================================================================================
# MOTOR DRIVER (MDDRC10 via pigpio)
# =================================================================================================
class FakePi:
    """--sim: records pulse widths instead of driving GPIO."""
    connected = True

    def __init__(self):
        self.pulses = {}

    def set_servo_pulsewidth(self, pin, us):
        before = self.pulses.get(pin, 0) not in (0, NEUTRAL_US)
        now = us not in (0, NEUTRAL_US)
        self.pulses[pin] = us
        if now != before:
            log(f"  [sim] GPIO{pin} {'moving' if now else 'stopped'} ({us} us)")

    def stop(self):
        pass


class Mddrc10:
    """Two R/C channels, ramped, with a dead-man timer for driving."""

    def __init__(self, pi):
        self.pi = pi
        self.lock = threading.Lock()
        self.target = [NEUTRAL_US, NEUTRAL_US]
        self.out = [NEUTRAL_US, NEUTRAL_US]
        self.deadman_until = None            # None = no dead-man (actuator moves are timed)
        self.running = True
        self._write()
        threading.Thread(target=self._loop, name="pwm", daemon=True).start()

    @staticmethod
    def _us(pct, cap):
        pct = max(-cap, min(cap, pct))
        return int(round(NEUTRAL_US + pct * FULLSCALE_US / 100))

    def drive(self, throttle, steering):
        with self.lock:
            self.target = [self._us(throttle, MAX_DRIVE_PCT), self._us(steering, MAX_DRIVE_PCT)]
            self.deadman_until = time.monotonic() + DRIVE_DEADMAN_S

    def actuator(self, direction):
        """+1 = probe down, -1 = probe up, 0 = stop. MIX mode: throttle only drives both outputs."""
        with self.lock:
            self.target = [self._us(direction * ACT_EXTEND_SIGN * ACT_PCT, 100), NEUTRAL_US]
            self.deadman_until = None

    def stop_now(self):
        with self.lock:
            self.target = [NEUTRAL_US, NEUTRAL_US]
            self.out = [NEUTRAL_US, NEUTRAL_US]
            self.deadman_until = None
            self._write()

    def moving(self):
        with self.lock:
            return self.out != [NEUTRAL_US, NEUTRAL_US] or self.target != [NEUTRAL_US, NEUTRAL_US]

    def _write(self):
        self.pi.set_servo_pulsewidth(RC1_PIN, self.out[0])
        self.pi.set_servo_pulsewidth(RC2_PIN, self.out[1])

    def _loop(self):
        while self.running:
            with self.lock:
                if self.deadman_until is not None and time.monotonic() > self.deadman_until:
                    self.target = [NEUTRAL_US, NEUTRAL_US]
                    self.deadman_until = None
                for i in (0, 1):
                    d = self.target[i] - self.out[i]
                    self.out[i] += max(-RAMP_US_PER_STEP, min(RAMP_US_PER_STEP, d))
                self._write()
            time.sleep(0.02)

    def shutdown(self):
        self.running = False
        time.sleep(0.05)
        self.stop_now()
        time.sleep(0.2)
        self.pi.set_servo_pulsewidth(RC1_PIN, 0)
        self.pi.set_servo_pulsewidth(RC2_PIN, 0)


# =================================================================================================
# SOIL SENSOR (from the team's soil_test.py)
# =================================================================================================
class SoilSensor:
    IDX_MOIST, IDX_TEMP, IDX_EC, IDX_PH = 0, 1, 2, 3

    def __init__(self, sim=False):
        self.sim = sim
        self._s = None
        self.sim_xy = (0, 0)

    def _open(self):
        if self._s is None:
            import minimalmodbus
            import serial
            s = minimalmodbus.Instrument(SENSOR_PORT, SENSOR_ADDR)
            s.mode = minimalmodbus.MODE_RTU
            s.serial.baudrate = SENSOR_BAUD
            s.serial.bytesize = 8
            s.serial.parity = serial.PARITY_NONE
            s.serial.stopbits = 1
            s.serial.timeout = 1.0
            s.clear_buffers_before_each_transaction = True
            self._s = s
        return self._s

    def close(self):
        try:
            if self._s is not None:
                self._s.serial.close()
        except Exception:
            pass
        self._s = None

    def read(self):
        if self.sim:
            x, y = self.sim_xy                     # made-up field so the base's map has a shape
            return {"moisture_pct": round(18 + 3.0 * x + random.uniform(-1, 1), 1),
                    "temp_c": round(17 + random.uniform(-0.3, 0.3), 1),
                    "ec_uScm": int(250 + 60 * y + random.uniform(-20, 20)),
                    "ph": round(min(7.4, 5.4 + 0.25 * (x + y)) + random.uniform(-0.1, 0.1), 1)}
        import serial
        try:
            raw = self._open().read_registers(0, 4, functioncode=3)   # some sensors need 4
        except serial.SerialException:
            self.close()                         # unplugged or reset: reopen next time
            raise
        temp = raw[self.IDX_TEMP] - 0x10000 if raw[self.IDX_TEMP] >= 0x8000 else raw[self.IDX_TEMP]
        return {"moisture_pct": raw[self.IDX_MOIST] / 10.0, "temp_c": temp / 10.0,
                "ec_uScm": raw[self.IDX_EC], "ph": raw[self.IDX_PH] / 10.0}


# =================================================================================================
# ROVER
# =================================================================================================
class Rover:
    def __init__(self, radio, display, motors, sensor):
        self.radio, self.display, self.motors, self.sensor = radio, display, motors, sensor
        self.mode = L.MODE_DRIVE
        self.state = L.STATE_IDLE
        self.phase = L.PHASE_NONE
        self.event, self.event_id = L.EV_NONE, 0
        self.abort = threading.Event()
        self.stop_event = threading.Event()
        self.job = None
        self.last_from_base = time.monotonic()
        self.link_lost = False
        self.sent_index = self._load_sent_index()
        self.hb_pending = None

    # ---------- results file and upload (the team's soil_data.csv mechanism) ----------
    def _load_sent_index(self):
        try:
            with open(SENT_FILE) as f:
                return int(f.read().strip())
        except Exception:
            return 0

    def _save_sent_index(self):
        tmp = SENT_FILE + ".tmp"
        with open(tmp, "w") as f:
            f.write(str(self.sent_index))
        os.replace(tmp, SENT_FILE)               # atomic: survives a power cut mid-write

    @staticmethod
    def _result_lines():
        try:
            with open(RESULTS_CSV) as f:
                data = f.read()
        except FileNotFoundError:
            return []
        return [l.rstrip("\r") for l in data.split("\n")[:-1]]   # last piece may be half-written

    def pending(self):
        return max(0, len(self._result_lines()) - self.sent_index)

    def send_pending(self):
        lines = self._result_lines()
        sent = 0
        while self.sent_index < len(lines) and sent < MAX_LINES_PER_CYCLE:
            line = lines[self.sent_index]
            if not line[:1].isdigit():           # header or blank line
                self.sent_index += 1
                self._save_sent_index()
                continue
            if not L.reliable_send(self.radio, L.pack_data(self.sent_index, line), self.dispatch):
                log(f"result line {self.sent_index} not acknowledged; will retry")
                break
            self.sent_index += 1
            self._save_sent_index()
            sent += 1
        if sent:
            log(f"sent {sent} result line(s), {self.pending()} waiting")

    def save_result(self, row):
        new = not os.path.exists(RESULTS_CSV)
        with open(RESULTS_CSV, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(RESULT_FIELDS)
            w.writerow(row)

    # ---------- jobs: probe cycle and actuator moves ----------
    def busy(self):
        return self.job is not None and self.job.is_alive()

    def _set_event(self, ev, ev_id=None):
        self.event = ev
        if ev_id is not None:
            self.event_id = ev_id

    def _run_for(self, seconds):
        """Wait while the actuator runs; False if a STOP came in."""
        return not self.abort.wait(seconds)

    def _probe_job(self, probe_id, x, y):
        self.state = L.STATE_PROBING
        self.sensor.sim_xy = (x, y)
        log(f"probe {probe_id} at ({x}, {y}): going down")
        try:
            self.phase = L.PHASE_EXTENDING
            self.motors.actuator(+1)
            if not self._run_for(EXTEND_S):
                return
            self.motors.actuator(0)
            self.phase = L.PHASE_READING
            if not self._run_for(SETTLE_S):
                return
            readings = []
            n = max(1, int(READ_S / READ_INTERVAL_S))
            for i in range(n):
                try:
                    readings.append(self.sensor.read())
                except Exception as e:
                    log(f"  sensor read {i + 1}/{n} failed: {e}")
                if not self._run_for(READ_INTERVAL_S):
                    return
            log(f"probe {probe_id}: coming up ({len(readings)}/{n} good readings)")
            self.phase = L.PHASE_RETRACTING
            self.motors.actuator(-1)
            if not self._run_for(RETRACT_S):
                return
            self.motors.actuator(0)

            last = readings[-AVG_LAST:]
            if len(last) < MIN_GOOD:
                self._set_event(L.EV_PROBE_FAILED, probe_id)
                log(f"probe {probe_id}: FAILED, only {len(last)} good readings")
                return
            avg = {k: sum(r[k] for r in last) / len(last)
                   for k in ("moisture_pct", "temp_c", "ec_uScm", "ph")}
            self.save_result([datetime.now().isoformat(timespec="seconds"), probe_id, x, y,
                              round(avg["moisture_pct"], 2), round(avg["temp_c"], 2),
                              round(avg["ec_uScm"], 1), round(avg["ph"], 2), len(last)])
            self._set_event(L.EV_PROBE_SAVED, probe_id)
            log(f"probe {probe_id} saved: pH {avg['ph']:.2f}  moisture {avg['moisture_pct']:.1f}%  "
                f"EC {avg['ec_uScm']:.0f}  temp {avg['temp_c']:.1f} C")
        finally:
            self.motors.actuator(0)
            self.phase = L.PHASE_NONE
            self.state = L.STATE_IDLE

    def _jog_job(self, direction, seconds):
        self.state = L.STATE_JOGGING
        try:
            self.motors.actuator(direction)
            self._run_for(seconds)
        finally:
            self.motors.actuator(0)
            self.state = L.STATE_IDLE

    def _start(self, target, *args):
        self.abort.clear()
        self.job = threading.Thread(target=target, args=args, daemon=True)
        self.job.start()

    # ---------- commands from the base ----------
    def stop_all(self):
        self.abort.set()
        self.motors.stop_now()

    def handle_cmd(self, p):
        if len(p) < 3:
            return
        cmd, args = p[2], p[3:]
        if cmd in (L.CMD_STOP, L.CMD_RETURN_HOME):
            self.stop_all()
            self._set_event(L.EV_STOPPED)
            log("STOP from base")
        elif cmd == L.CMD_MODE and len(args) >= 1:
            if self.busy():
                self._set_event(L.EV_BUSY)
                return
            self.motors.stop_now()
            self.mode = L.MODE_PROBE if args[0] == L.MODE_PROBE else L.MODE_DRIVE
            self._set_event(L.EV_MODE_CHANGED)
            log(f"mode: {L.MODE_NAMES[self.mode]}")
        elif cmd == L.CMD_PROBE and len(args) >= 6:
            probe_id, x, y = struct.unpack("<Hhh", args[:6])
            if self.mode != L.MODE_PROBE:
                self._set_event(L.EV_WRONG_MODE, probe_id)
            elif self.busy():
                self._set_event(L.EV_BUSY, probe_id)
            else:
                self._set_event(L.EV_PROBE_STARTED, probe_id)
                self._start(self._probe_job, probe_id, x, y)
        elif cmd == L.CMD_ACT and len(args) >= 2:
            direction, tenths = struct.unpack("<bB", args[:2])
            if self.mode != L.MODE_PROBE:
                self._set_event(L.EV_WRONG_MODE)
            elif self.busy():
                self._set_event(L.EV_BUSY)
            else:
                self._set_event(L.EV_JOG)
                self._start(self._jog_job, 1 if direction > 0 else -1, tenths / 10.0)

    def handle_drive(self, p):
        if len(p) < 3 or self.mode != L.MODE_DRIVE or self.busy():
            return
        throttle, steering = struct.unpack("<bb", p[1:3])
        self.motors.drive(throttle, steering)        # 0, 0 ramps down to a stop

    # ---------- radio loop ----------
    def status_packet(self, seq, rssi):
        return L.pack_status(seq, L.BATTERY_UNKNOWN, self.state, rssi, self.mode, self.phase,
                             self.event, self.event_id, self.pending())

    def dispatch(self, p):
        """Handle one packet from the base. Never transmits (the heartbeat reply is queued)."""
        if p is None or len(p) < 2:                # nothing, or a bare ACK
            return
        self.last_from_base = time.monotonic()
        if self.link_lost:
            self.link_lost = False
            log("link restored")
        t = p[0]
        if t == L.MSG_DRIVE:
            self.handle_drive(p)
        elif t == L.MSG_CMD:
            self.handle_cmd(p)
        elif t == L.MSG_HEARTBEAT:
            self.hb_pending = (p[1], self.radio.last_rssi)

    def run(self):
        log("radio link running")
        last_error = None
        self.hb_pending = None
        while not self.stop_event.is_set():
            try:
                self.dispatch(self.radio.receive(with_ack=True, timeout=0.2))
                if self.hb_pending:
                    seq, rssi = self.hb_pending
                    self.hb_pending = None
                    L.reliable_send(self.radio, self.status_packet(seq, rssi), self.dispatch)
                    self.send_pending()
                    L.show(self.display, FONT,
                           f"LINK OK {L.MODE_NAMES[self.mode]}",
                           L.PHASE_NAMES[self.phase] or L.STATE_NAMES.get(self.state, ""),
                           f"RSSI {rssi}  wait {self.pending()}")
                if not self.link_lost and time.monotonic() - self.last_from_base > LINK_TIMEOUT_S:
                    self.link_lost = True
                    if not self.busy():                     # a probe in progress finishes by itself
                        self.motors.stop_now()
                    self._set_event(L.EV_LINK_LOST)
                    log("LINK LOST: no packets from the base; drive motors stopped")
                    L.show(self.display, FONT, "LINK LOST", "motors stopped")
                last_error = None
            except Exception as e:
                if str(e) != last_error:
                    log(f"radio error: {e}")
                    last_error = str(e)
                time.sleep(1.0)


def main():
    global EXTEND_S, RETRACT_S, SETTLE_S, READ_S, READ_INTERVAL_S, DATA_DIR, RESULTS_CSV, SENT_FILE
    ap = argparse.ArgumentParser(description="D.I.R.T.T. rover program (demo)")
    ap.add_argument("--sim", action="store_true", help="no radio, sensor or motors: UDP on this computer")
    ap.add_argument("--sim-loss", type=float, default=0.0, help="--sim: fraction of packets to drop")
    ap.add_argument("--fast", action="store_true", help="--sim: short probe timings for testing")
    ap.add_argument("--data-dir", help="where results are kept (default ~/soil)")
    args = ap.parse_args()

    if args.data_dir:
        DATA_DIR = args.data_dir
        RESULTS_CSV = os.path.join(DATA_DIR, "probe_results.csv")
        SENT_FILE = os.path.join(DATA_DIR, "probe_sent_index.txt")
    os.makedirs(DATA_DIR, exist_ok=True)
    if args.fast:
        EXTEND_S, RETRACT_S, SETTLE_S, READ_S, READ_INTERVAL_S = 1.0, 1.0, 0.2, 1.0, 0.2

    if args.sim:
        pi = FakePi()
    else:
        try:
            import pigpio
        except ImportError:
            sys.exit("pigpio isn't installed: sudo apt install pigpio python3-pigpio "
                     "(or pip install pigpio in your venv)")
        pi = pigpio.pi()
        if not pi.connected:
            sys.exit("Can't reach the pigpio daemon: sudo systemctl enable --now pigpiod")
    motors = Mddrc10(pi)        # sends 1500 us right away, so the MDDRC10 captures "stop"

    try:
        radio, display = L.make_radio(L.ROVER_NODE, sim=args.sim, sim_loss=args.sim_loss)
    except Exception as e:
        motors.shutdown()
        sys.exit(f"Could not start the radio: {e}\nCheck SPI is on and the Bonnet is seated.")

    rover = Rover(radio, display, motors, SoilSensor(sim=args.sim))

    def bail(signum, frame):
        rover.stop_event.set()
    signal.signal(signal.SIGTERM, bail)
    signal.signal(signal.SIGHUP, bail)

    log(f"sending STOP (1500 us) on GPIO{RC1_PIN}/{RC2_PIN}; mode {L.MODE_NAMES[rover.mode]}")
    try:
        rover.run()
    except KeyboardInterrupt:
        pass
    finally:
        rover.stop_all()
        motors.shutdown()
        rover.sensor.close()
        pi.stop()
        L.show(display, FONT, "STOPPED")
        log("stopped: motors off")


if __name__ == "__main__":
    main()
