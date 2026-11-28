#!/usr/bin/env python3
"""
base.py - D.I.R.T.T. base station (Pi 5 + LoRa Bonnet) program for the December demo.

    - keeps the LoRa link up with heartbeats and shows the rover's status
    - drive the rover from the keyboard (hold w/a/s/d), run the automatic soil probe at a grid
      square you type in, nudge the actuator, stop everything
    - every soil result the rover sends is saved to ~/soil/base_results.csv and the heat map is
      redrawn to ~/soil/base_web/heatmap.png
    - a small web page shows the latest map and readings: http://<base>.local:8080 on the laptop

Run on the base Pi (or over SSH from the laptop):
    python3 base.py
    python3 base.py --sim         # with rover.py --sim on the same computer, no radios needed

Needs: adafruit-circuitpython-rfm9x, adafruit-circuitpython-ssd1306, numpy, matplotlib.
"""
import argparse
import collections
import csv
import curses
import functools
import http.server
import os
import queue
import struct
import sys
import threading
import time
from datetime import datetime

import link as L

HOME = os.path.expanduser("~")
DATA_DIR = os.path.join(HOME, "soil")
FONT = os.path.join(HOME, "font5x8.bin")

HEARTBEAT_S = 2.0        # heartbeat every 2 s when not driving
LINK_OK_S = 8.0          # no STATUS for this long = link shown as LOST
DRIVE_PERIOD_S = 0.2     # DRIVE packets 5 times a second while a drive key is held
HOLD_S = 0.6             # a key counts as held this long after its last repeat
JOG_S = 1.0              # actuator nudge per u / j press
FULL_RETRACT_S = 25.0    # R: run the actuator up long enough to reach its top limit switch
WEB_PORT = 8080

BASE_FIELDS = ["received", "rover_line", "timestamp", "probe_id", "x", "y", "moisture_pct",
               "temp_c", "ec_uScm", "ph", "readings_averaged"]


class Base:
    """The radio side. Owns the radio in one thread; the keyboard UI only sets fields and queues."""

    def __init__(self, radio, display, data_dir):
        self.radio, self.display = radio, display
        self.data_dir = data_dir
        self.web_dir = os.path.join(data_dir, "base_web")
        os.makedirs(self.web_dir, exist_ok=True)
        self.results_csv = os.path.join(data_dir, "base_results.csv")
        self.heatmap_png = os.path.join(self.web_dir, "heatmap.png")

        self.lock = threading.Lock()
        self.cmds = queue.Queue()
        self.stop_event = threading.Event()
        self.log = collections.deque(maxlen=12)
        self.seq = 0

        self.status = None              # last STATUS from the rover (dict)
        self.status_time = None
        self.base_rssi = None
        self.last_event = (L.EV_NONE, 0)
        self.speed = 40
        self.drive_vec = (0, 0)
        self.drive_key_time = 0.0
        self.was_driving = False

        self.seen = set()
        self.rows = []
        self._load_results()
        self.next_probe_id = max([int(r["probe_id"]) for r in self.rows if r.get("probe_id")] + [0]) + 1
        self.map_dirty = threading.Event()
        if self.rows:
            self.map_dirty.set()

    # ---------------- results ----------------
    def _load_results(self):
        if not os.path.exists(self.results_csv):
            return
        with open(self.results_csv, newline="") as f:
            for r in csv.DictReader(f):
                self.rows.append(r)
                self.seen.add((r.get("rover_line"), r.get("timestamp")))

    def _save_result(self, line_no, line):
        parts = next(csv.reader([line]))
        if len(parts) < 9:
            self.say(f"odd result line from rover: {line!r}")
            return
        key = (str(line_no), parts[0])
        if key in self.seen:                   # a resend we already have
            return
        self.seen.add(key)
        row = dict(zip(BASE_FIELDS, [datetime.now().isoformat(timespec="seconds"), line_no] + parts[:9]))
        new = not os.path.exists(self.results_csv)
        with open(self.results_csv, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=BASE_FIELDS)
            if new:
                w.writeheader()
            w.writerow(row)
        with self.lock:
            self.rows.append(row)
        self.say(f"RESULT probe {row['probe_id']} at ({row['x']}, {row['y']}): pH {row['ph']}  "
                 f"moist {row['moisture_pct']}%  EC {row['ec_uScm']}  {row['temp_c']} C")
        self.map_dirty.set()

    def say(self, msg):
        with self.lock:
            self.log.append(f"{datetime.now():%H:%M:%S} {msg}")

    # ---------------- what the keyboard calls ----------------
    def hold_drive(self, throttle, steering):
        with self.lock:
            self.drive_vec = (throttle, steering)
            self.drive_key_time = time.monotonic()

    def release_drive(self):
        with self.lock:
            self.drive_key_time = 0.0

    def send_cmd(self, cmd, args=b"", label=""):
        self.cmds.put((cmd, args, label))

    def stop(self):
        self.release_drive()
        with self.cmds.mutex:                  # STOP jumps the queue
            self.cmds.queue.clear()
        self.send_cmd(L.CMD_STOP, label="STOP")

    def set_mode(self, mode):
        self.send_cmd(L.CMD_MODE, struct.pack("<B", mode), f"mode {L.MODE_NAMES[mode]}")

    def probe(self, x, y):
        pid = self.next_probe_id
        self.next_probe_id += 1
        self.send_cmd(L.CMD_PROBE, struct.pack("<Hhh", pid, x, y), f"probe {pid} at ({x}, {y})")
        return pid

    def jog(self, direction, seconds):
        tenths = max(1, min(255, int(round(seconds * 10))))
        self.send_cmd(L.CMD_ACT, struct.pack("<bB", direction, tenths),
                      f"actuator {'down' if direction > 0 else 'up'} {tenths / 10:g} s")

    def link_ok(self):
        return self.status_time is not None and time.monotonic() - self.status_time < LINK_OK_S

    # ---------------- radio thread ----------------
    def _next_seq(self):
        self.seq = (self.seq + 1) & 0xFF
        return self.seq

    def _handle(self, p):
        if p is None or len(p) < 2:            # nothing, or a bare ACK
            return
        if p[0] == L.MSG_STATUS:
            st = L.unpack_status(p)
            if st is None:
                return
            with self.lock:
                self.status, self.status_time = st, time.monotonic()
                self.base_rssi = self.radio.last_rssi
            ev = (st["event"], st["event_id"])
            if ev != self.last_event and st["event"] != L.EV_NONE:
                name = L.EVENT_NAMES.get(st["event"], str(st["event"]))
                self.say(f"rover: {name}" + (f" (probe {st['event_id']})" if st["event"] in
                         (L.EV_PROBE_STARTED, L.EV_PROBE_SAVED, L.EV_PROBE_FAILED,
                          L.EV_PROBE_BLOCKED) else ""))
            self.last_event = ev
            L.show(self.display, FONT, f"LINK OK {L.MODE_NAMES.get(st['mode'], '?')}",
                   L.PHASE_NAMES.get(st["phase"], "") or L.STATE_NAMES.get(st["state"], ""),
                   f"RSSI {self.radio.last_rssi}  pts {len(self.rows)}")
        elif p[0] == L.MSG_DATA:
            d = L.unpack_data(p)
            if d:
                self._save_result(*d)

    def run(self):
        last_hb = 0.0
        last_drive = 0.0
        last_error = None
        while not self.stop_event.is_set():
            try:
                now = time.monotonic()
                with self.lock:
                    driving = now - self.drive_key_time < HOLD_S
                    vec = self.drive_vec
                if not self.cmds.empty():
                    cmd, args, label = self.cmds.get()
                    ok = L.reliable_send(self.radio, L.pack_cmd(self._next_seq(), cmd, args), self._handle)
                    self.say(f"sent {label}" + ("" if ok else "  -- NO ACK, try again"))
                elif driving:
                    if now - last_drive >= DRIVE_PERIOD_S:
                        self.radio.send(L.pack_drive(*vec), destination=L.BROADCAST)
                        last_drive = now
                    self.was_driving = True
                elif self.was_driving:
                    for _ in range(3):         # key released: make sure the rover hears "stop"
                        self.radio.send(L.pack_drive(0, 0), destination=L.BROADCAST)
                        time.sleep(0.05)
                    self.was_driving = False
                elif now - last_hb >= HEARTBEAT_S:
                    last_hb = now
                    L.reliable_send(self.radio, L.pack_heartbeat(self._next_seq()), self._handle)
                self._handle(self.radio.receive(with_ack=True, timeout=0.05))
                last_error = None
            except Exception as e:
                if str(e) != last_error:
                    self.say(f"radio error: {e}")
                    last_error = str(e)
                time.sleep(0.5)

    # ---------------- heat map + web page ----------------
    def map_worker(self):
        import heatmap
        while not self.stop_event.is_set():
            if not self.map_dirty.wait(0.5):
                continue
            self.map_dirty.clear()
            try:
                if heatmap.save_heatmap(self.results_csv, self.heatmap_png, "D.I.R.T.T. demo survey"):
                    self.say(f"heat map updated ({len(self.rows)} points)")
            except Exception as e:
                self.say(f"heat map failed: {e}")
            self.write_page()

    def write_page(self):
        with self.lock:
            rows = list(self.rows)
        trs = "\n".join(
            f"<tr><td>{r['probe_id']}</td><td>({r['x']}, {r['y']})</td><td>{r['ph']}</td>"
            f"<td>{r['moisture_pct']}</td><td>{r['ec_uScm']}</td><td>{r['temp_c']}</td>"
            f"<td>{r['timestamp']}</td></tr>" for r in reversed(rows))
        img = ('<img src="heatmap.png?t=%d" alt="soil heat maps">' % int(time.time())
               if os.path.exists(self.heatmap_png) else "<p>No readings yet.</p>")
        page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="5"><title>D.I.R.T.T. base</title>
<style>body{{font-family:sans-serif;margin:16px;background:#f5f1e8;color:#1e1b16}}
img{{max-width:100%;background:#fff}}table{{border-collapse:collapse}}
td,th{{padding:4px 10px;border-bottom:1px solid #d9cfbb;text-align:left}}</style></head><body>
<h1>D.I.R.T.T. soil survey</h1><p>{len(rows)} reading(s). Updates every 5 s.</p>{img}
<table><tr><th>Probe</th><th>Grid</th><th>pH</th><th>Moisture %</th><th>EC µS/cm</th>
<th>Temp °C</th><th>Taken</th></tr>{trs}</table></body></html>"""
        tmp = os.path.join(self.web_dir, "index.html.tmp")
        with open(tmp, "w") as f:
            f.write(page)
        os.replace(tmp, os.path.join(self.web_dir, "index.html"))

    def start_web(self, port):
        class Handler(http.server.SimpleHTTPRequestHandler):
            def end_headers(self):
                self.send_header("Cache-Control", "no-store")
                super().end_headers()

            def log_message(self, *a):
                pass
        handler = functools.partial(Handler, directory=self.web_dir)
        srv = http.server.ThreadingHTTPServer(("0.0.0.0", port), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv


# =================================================================================================
# KEYBOARD UI
# =================================================================================================
DRIVE_KEYS = {
    ord("w"): (1, 0), curses.KEY_UP: (1, 0),
    ord("s"): (-1, 0), curses.KEY_DOWN: (-1, 0),
    ord("a"): (0, -1), curses.KEY_LEFT: (0, -1),
    ord("d"): (0, 1), curses.KEY_RIGHT: (0, 1),
    ord("q"): (1, -0.5), ord("e"): (1, 0.5),
}

HELP = [
    "Drive: hold w/a/s/d or arrows (q/e arcs), let go = stop     +/- speed",
    "Probe: p = probe at a grid square   j/u = probe down/up 1 s   R = probe all the way up",
    "SPACE or x = STOP   Esc = quit   m = DRIVE/PROBE (only if the actuator is on the MDDRC10)",
]


def ask(stdscr, row, prompt):
    """One line of typed input inside curses. Esc cancels (returns None)."""
    stdscr.nodelay(False)
    curses.curs_set(1)
    text = ""
    try:
        while True:
            stdscr.move(row, 0)
            stdscr.clrtoeol()
            stdscr.addstr(row, 0, prompt + text, curses.A_BOLD)
            stdscr.refresh()
            k = stdscr.getch()
            if k in (10, 13, curses.KEY_ENTER):
                return text
            if k == 27:
                return None
            if k in (curses.KEY_BACKSPACE, 127, 8):
                text = text[:-1]
            elif 32 <= k < 127 and len(text) < 20:
                text += chr(k)
    finally:
        curses.curs_set(0)
        stdscr.nodelay(True)


def put(stdscr, row, text, attr=0):
    h, w = stdscr.getmaxyx()
    if row < h:
        stdscr.addstr(row, 0, text[:w - 1], attr)


def ui(stdscr, base, web_url):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    try:
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_RED, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        GOOD, BAD, WARN = curses.color_pair(1), curses.color_pair(2), curses.color_pair(3)
    except curses.error:
        GOOD = BAD = WARN = curses.A_BOLD
    moving = ""
    while True:
        k = stdscr.getch()
        while k != -1:
            st = base.status
            mode = st["mode"] if st else None
            if k in DRIVE_KEYS:
                t, s = DRIVE_KEYS[k]
                base.hold_drive(t * base.speed, s * base.speed)
                moving = {(1, 0): "forward", (-1, 0): "reverse", (0, -1): "pivot left",
                          (0, 1): "pivot right", (1, -0.5): "arc left", (1, 0.5): "arc right"}[(t, s)]
                if mode == L.MODE_PROBE:
                    base.say("rover is in PROBE mode: press m for DRIVE")
            elif k in (ord(" "), ord("x")):
                base.stop()
            elif k in (ord("+"), ord("=")):
                base.speed = min(100, base.speed + 10)
            elif k in (ord("-"), ord("_")):
                base.speed = max(10, base.speed - 10)
            elif k == ord("m"):
                new = L.MODE_DRIVE if mode == L.MODE_PROBE else L.MODE_PROBE
                base.release_drive()
                base.set_mode(new)
            elif k == ord("p"):
                base.release_drive()
                txt = ask(stdscr, 9, "Probe at grid x y (Esc cancels): ")
                if txt:
                    parts = txt.replace(",", " ").split()
                    try:
                        x, y = int(parts[0]), int(parts[1])
                        pid = base.probe(x, y)
                        base.say(f"asked for probe {pid} at ({x}, {y})")
                    except (ValueError, IndexError):
                        base.say("type two whole numbers, like: 2 3")
            elif k == ord("j"):
                base.jog(+1, JOG_S)
            elif k == ord("u"):
                base.jog(-1, JOG_S)
            elif k == ord("R"):
                base.jog(-1, FULL_RETRACT_S)
            elif k == ord("h"):
                base.map_dirty.set()
            elif k == 27:
                return
            k = stdscr.getch()

        # ---------- screen ----------
        now = time.monotonic()
        driving = now - base.drive_key_time < HOLD_S
        if not driving:
            moving = ""
        st = base.status
        stdscr.erase()
        put(stdscr, 0, "D.I.R.T.T. base station", curses.A_BOLD)
        if base.link_ok():
            put(stdscr, 1, f"LINK OK   rover hears us at {st['rssi']} dBm, we hear it at "
                           f"{base.base_rssi} dBm   ({now - base.status_time:.0f} s ago)", GOOD)
        elif base.status_time is None:
            put(stdscr, 1, "waiting for the rover...", WARN)
        else:
            put(stdscr, 1, f"LINK LOST   no status for {now - base.status_time:.0f} s", BAD)
        if st:
            phase = L.PHASE_NAMES.get(st["phase"], "")
            state = phase or L.STATE_NAMES.get(st["state"], "?")
            batt = "n/a" if st["battery"] == L.BATTERY_UNKNOWN else f"{st['battery']}%"
            put(stdscr, 2, f"Rover: {L.MODE_NAMES.get(st['mode'], '?')} mode   {state}   "
                           f"results waiting to send: {st['pending']}   battery {batt}",
                WARN if st["state"] != L.STATE_IDLE else 0)
        put(stdscr, 3, f"Speed {base.speed}%   " + (f"DRIVING: {moving}" if moving else "stopped"),
            GOOD if moving else 0)
        put(stdscr, 4, f"Soil results: {len(base.rows)}   map + table: {web_url}")
        for i, line in enumerate(HELP):
            put(stdscr, 6 + i, line)
        with base.lock:
            lines = list(base.log)
        for i, line in enumerate(lines):
            put(stdscr, 11 + i, line)
        stdscr.refresh()
        time.sleep(0.03)


def main():
    global DATA_DIR
    ap = argparse.ArgumentParser(description="D.I.R.T.T. base station (demo)")
    ap.add_argument("--sim", action="store_true", help="no radio: talk to rover.py --sim over UDP")
    ap.add_argument("--sim-loss", type=float, default=0.0, help="--sim: fraction of packets to drop")
    ap.add_argument("--port", type=int, default=WEB_PORT, help="web page port (0 = no web page)")
    ap.add_argument("--data-dir", help="where results are kept (default ~/soil)")
    args = ap.parse_args()
    if args.data_dir:
        DATA_DIR = args.data_dir
    os.makedirs(DATA_DIR, exist_ok=True)

    try:
        radio, display = L.make_radio(L.BASE_NODE, sim=args.sim, sim_loss=args.sim_loss)
    except Exception as e:
        sys.exit(f"Could not start the radio: {e}\nCheck SPI is on and the Bonnet is seated.")
    base = Base(radio, display, DATA_DIR)
    base.write_page()
    web_url = "off"
    if args.port:
        try:
            base.start_web(args.port)
            import socket
            web_url = f"http://{socket.gethostname()}.local:{args.port}"
        except OSError as e:
            web_url = f"off ({e})"
    threading.Thread(target=base.run, name="radio", daemon=True).start()
    threading.Thread(target=base.map_worker, name="map", daemon=True).start()
    try:
        curses.wrapper(ui, base, web_url)
    except KeyboardInterrupt:
        pass
    finally:
        base.stop()
        time.sleep(1.0)                        # let the STOP go out
        base.stop_event.set()
        L.show(display, FONT, "BASE STOPPED")
        print(f"Stopped. Results: {base.results_csv}   Map: {base.heatmap_png}")


if __name__ == "__main__":
    main()
