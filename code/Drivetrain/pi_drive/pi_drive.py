#!/usr/bin/env python3
"""
D.I.R.T.T. demo drive: the rover Pi drives the Cytron MDDRC10 directly.

For the December demo, before the flight controller is in the loop. The Pi sends the same R/C
servo pulses the Arduino motor test did (1500 us = stop, +/-435 us = full speed), timed by the
pigpio daemon so they don't jitter.

    python3 pi_drive.py                 drive with the keyboard (over SSH is fine)
    python3 pi_drive.py --test          automatic wheel check, like the Arduino "test"
    python3 pi_drive.py --dry-run ...   no Pi needed: prints the pulses instead

Driving: hold a key to move, let go to stop (the keyboard's auto-repeat keeps it going).
    w / up      forward            s / down    reverse
    a / left    pivot left         d / right   pivot right
    q / e       arc forward-left / forward-right
    space / x   stop now           + / -       speed up / down 10 %
    Esc or Ctrl+C                  stop and quit

It stops the motors when: a key isn't seen for --deadman seconds, you quit, the program is
killed with Ctrl+C / kill, or the SSH session drops. It CAN'T stop them if the Pi loses power to
its CPU but not pigpiod, or if pigpiod is left running after `kill -9`: then run
`pigs s 18 0 s 19 0`, and always have the e-stop in reach.
"""
import argparse
import curses
import signal
import sys
import threading
import time

NEUTRAL_US = 1500
FULLSCALE_US = 435          # MDDRC10 datasheet: full speed at neutral +/- 435 us
RAMP_US_PER_STEP = 8        # per 20 ms: about 0.5 s from stop to full, same as the Arduino sketch
STEP_S = 0.02


class FakePi:
    """Stands in for pigpio.pi() with --dry-run: records and prints pulse changes."""
    connected = True

    def __init__(self, echo=True):
        self.echo = echo
        self.last = {}

    def set_servo_pulsewidth(self, pin, us):
        if self.last.get(pin) != us:
            self.last[pin] = us
            if self.echo:
                print(f"  GPIO{pin} -> {us} us", flush=True)

    def stop(self):
        pass


class Driver:
    """Two RC channels with ramping and a dead-man timer, updated every 20 ms in a thread."""

    def __init__(self, pi, pin1, pin2, mixed, max_pct, deadman_s):
        self.pi, self.pin1, self.pin2 = pi, pin1, pin2
        self.mixed, self.max_pct, self.deadman_s = mixed, max_pct, deadman_s
        self.lock = threading.Lock()
        self.target = [NEUTRAL_US, NEUTRAL_US]
        self.out = [NEUTRAL_US, NEUTRAL_US]
        self.last_cmd = 0.0
        self.deadman_on = True
        self.running = True
        self._write()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def pct_to_us(self, pct):
        pct = max(-self.max_pct, min(self.max_pct, pct))
        return int(round(NEUTRAL_US + pct * FULLSCALE_US / 100))

    @staticmethod
    def us_to_pct(us):
        return round((us - NEUTRAL_US) * 100 / FULLSCALE_US)

    def set(self, pct1, pct2):
        """Set the two channels in % (-100..100). Refreshes the dead-man timer."""
        with self.lock:
            self.target = [self.pct_to_us(pct1), self.pct_to_us(pct2)]
            self.last_cmd = time.monotonic()

    def move(self, name, v):
        """Named move at speed v %, for the driver's MIX or IND setting."""
        if self.mixed:     # RC1 = throttle, RC2 = steering
            table = {"fwd": (v, 0), "rev": (-v, 0), "left": (0, -v), "right": (0, v),
                     "arc_l": (v, -v / 2), "arc_r": (v, v / 2)}
        else:              # RC1 = left motors, RC2 = right motors
            table = {"fwd": (v, v), "rev": (-v, -v), "left": (-v, v), "right": (v, -v),
                     "arc_l": (v / 2, v), "arc_r": (v, v / 2)}
        self.set(*table[name])

    def stop_now(self):
        """No ramp: straight to neutral."""
        with self.lock:
            self.target = [NEUTRAL_US, NEUTRAL_US]
            self.out = [NEUTRAL_US, NEUTRAL_US]
            self._write()

    def _write(self):
        self.pi.set_servo_pulsewidth(self.pin1, self.out[0])
        self.pi.set_servo_pulsewidth(self.pin2, self.out[1])

    def _loop(self):
        while self.running:
            with self.lock:
                if self.deadman_on and time.monotonic() - self.last_cmd > self.deadman_s:
                    self.target = [NEUTRAL_US, NEUTRAL_US]
                for i in (0, 1):
                    d = self.target[i] - self.out[i]
                    self.out[i] += max(-RAMP_US_PER_STEP, min(RAMP_US_PER_STEP, d))
                self._write()
            time.sleep(STEP_S)

    def shutdown(self):
        """Stop the motors, then stop sending pulses."""
        if not self.running:
            return
        self.running = False
        self.thread.join(timeout=1)
        self.stop_now()
        time.sleep(0.2)                    # a few neutral pulses first
        self.pi.set_servo_pulsewidth(self.pin1, 0)
        self.pi.set_servo_pulsewidth(self.pin2, 0)


def run_test(drv, speed):
    """Same sequence as the Arduino sketch's "test"."""
    drv.deadman_on = False
    v = speed
    if drv.mixed:
        steps = [("1. FORWARD: all 4 wheels roll forward", (v, 0)),
                 ("2. REVERSE: all 4 wheels backward", (-v, 0)),
                 ("3. PIVOT LEFT: left wheels back, right wheels forward", (0, -v)),
                 ("4. PIVOT RIGHT: left wheels forward, right wheels back", (0, v)),
                 ("5. ARC: forward while turning right", (v, v / 2))]
    else:
        steps = [("1. LEFT motors forward only", (v, 0)),
                 ("2. LEFT motors reverse only", (-v, 0)),
                 ("3. RIGHT motors forward only", (0, v)),
                 ("4. RIGHT motors reverse only", (0, -v))]
    print("Automatic test (Ctrl+C to stop). Watch every wheel:")
    for text, (a, b) in steps:
        print("  " + text, flush=True)
        drv.set(a, b)
        time.sleep(2.5)
        drv.set(0, 0)
        time.sleep(1.2)
    print(f"  6. RAMP: forward 0 -> {drv.max_pct} % (the --max cap) -> 0 "
          "(listen for rough or noisy gearboxes)", flush=True)
    for p in list(range(0, 101, 5)) + list(range(100, -1, -5)):
        if drv.mixed:
            drv.set(p, 0)
        else:
            drv.set(p, p)
        time.sleep(0.15)
    drv.stop_now()
    print("Done. A whole side backwards: swap that side's pair at the driver (MLA<->MLB or MRA<->MRB).")
    print("Only ONE wheel of a side wrong: swap that motor's two wires.")


KEYS = {
    ord("w"): "fwd", curses.KEY_UP: "fwd",
    ord("s"): "rev", curses.KEY_DOWN: "rev",
    ord("a"): "left", curses.KEY_LEFT: "left",
    ord("d"): "right", curses.KEY_RIGHT: "right",
    ord("q"): "arc_l", ord("e"): "arc_r",
}


def teleop(stdscr, drv, args):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    speed = args.speed
    last_move = "stopped"
    while True:
        k = stdscr.getch()
        while k != -1:                       # drain the queue, keep the newest key
            if k in KEYS:
                last_move = KEYS[k]
                drv.move(last_move, speed)
            elif k in (ord(" "), ord("x")):
                drv.stop_now()
                last_move = "stopped"
            elif k in (ord("+"), ord("=")):
                speed = min(args.max, speed + 10)
            elif k in (ord("-"), ord("_")):
                speed = max(10, speed - 10)
            elif k == 27:                    # Esc
                return
            k = stdscr.getch()
        with drv.lock:
            o1, o2 = drv.out
            idle = time.monotonic() - drv.last_cmd > drv.deadman_s
        if idle and last_move != "stopped" and (o1, o2) == (NEUTRAL_US, NEUTRAL_US):
            last_move = "stopped"
        stdscr.erase()
        stdscr.addstr(0, 0, "D.I.R.T.T. demo drive" + ("  [DRY RUN]" if args.dry_run else ""))
        stdscr.addstr(1, 0, f"driver switch: {'MIX' if drv.mixed else 'IND'}   speed {speed} %   "
                            f"(max {args.max} %)")
        stdscr.addstr(3, 0, f"RC1 GPIO{drv.pin1}: {o1} us ({drv.us_to_pct(o1):+d} %)   "
                            f"RC2 GPIO{drv.pin2}: {o2} us ({drv.us_to_pct(o2):+d} %)")
        stdscr.addstr(4, 0, f"moving: {last_move}")
        stdscr.addstr(6, 0, "hold w/a/s/d or arrows to drive, q/e arcs, let go = stop")
        stdscr.addstr(7, 0, "space/x stop now   +/- speed   Esc or Ctrl+C quit")
        stdscr.refresh()
        time.sleep(0.02)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--test", action="store_true", help="run the automatic wheel test and exit")
    ap.add_argument("--mode", choices=["mix", "ind"], default="mix",
                    help="must match the MDDRC10's MIX/IND switch (default mix)")
    ap.add_argument("--speed", type=int, default=30, help="starting speed, %% (default 30)")
    ap.add_argument("--max", type=int, default=60,
                    help="speed cap, %% (default 60; raise it once the demo route is known)")
    ap.add_argument("--pins", type=int, nargs=2, default=[18, 19], metavar=("RC1", "RC2"),
                    help="GPIO (BCM) numbers for RC1 and RC2 (default 18 19)")
    ap.add_argument("--deadman", type=float, default=0.8,
                    help="stop if no key for this many seconds (default 0.8)")
    ap.add_argument("--dry-run", action="store_true", help="no Pi: print pulses instead")
    args = ap.parse_args()
    args.max = max(10, min(100, args.max))
    args.speed = max(10, min(args.max, args.speed))

    if args.dry_run:
        pi = FakePi(echo=args.test)
    else:
        try:
            import pigpio
        except ImportError:
            sys.exit("pigpio isn't installed: sudo apt install pigpio python3-pigpio")
        pi = pigpio.pi()
        if not pi.connected:
            sys.exit("Can't reach the pigpio daemon: sudo systemctl enable --now pigpiod")

    drv = Driver(pi, args.pins[0], args.pins[1], args.mode == "mix", args.max, args.deadman)

    def bail(signum, frame):
        raise KeyboardInterrupt
    for sig in (signal.SIGTERM, signal.SIGHUP):    # kill, or the SSH session dropping
        signal.signal(sig, bail)

    print(f"Sending STOP (1500 us) on GPIO{args.pins[0]} / GPIO{args.pins[1]}. "
          f"Driver switch must be on {args.mode.upper()}.")
    try:
        if args.test:
            print("Wheels off the ground? Switch on the 12 V to the MDDRC10 now; starting in 5 s.")
            time.sleep(5)
            run_test(drv, args.speed)
        else:
            print("Switch on the 12 V to the MDDRC10 now, then press Enter to start driving.")
            input()
            curses.wrapper(teleop, drv, args)
    except KeyboardInterrupt:
        pass
    finally:
        drv.shutdown()
        pi.stop()
        print("Motors stopped, pulses off.")


if __name__ == "__main__":
    main()
