# December demo: LoRa remote control, soil probe, heat map

Two programs talk over the LoRa Bonnets:

- **`rover.py`** on the rover Pi (Pi 3 B). Answers heartbeats, drives the MDDRC10 from
  GPIO18/19, runs the automatic soil probe, and sends each result to the base until it's
  acknowledged.
- **`base.py`** on the base Pi (Pi 5). Keyboard control, link status, saves the results, and
  redraws the heat map with every new reading. It also serves a web page with the map and a
  table of readings.

`link.py` (the message format) goes on **both** Pis. `heatmap.py` (the team's plotting code) goes
on the base. This builds on the team's `rover.py`: the radio setup, the soil-sensor reading, the
results-file upload and the heat maps all come from it.

## What the operator can do

| Key (on the base) | Does |
|---|---|
| hold `w`/`s` or ↑/↓ | drive forward / reverse (DRIVE mode) |
| hold `a`/`d` or ←/→ | pivot left / right |
| hold `q`/`e` | arc forward-left / forward-right |
| let go | stop (the rover also stops by itself 1 s after the last drive packet) |
| `+` / `-` | speed ±10 % (the rover caps driving at 60 %) |
| `m` | switch DRIVE ↔ PROBE mode |
| `p`, then `x y`, Enter | **probe**: probe down, settle, read the soil for 20 s, average the last 5 readings, probe up, save, send to the base |
| `j` / `u` | probe down / up for 1 s (PROBE mode) |
| `R` | probe all the way up (runs up for 25 s; the actuator's limit switch stops it) |
| SPACE or `x` | **STOP everything** (motors and actuator) |
| `h` | redraw the heat map |
| Esc | quit (sends STOP first) |

The rover refuses driving in PROBE mode and probing in DRIVE mode, and says so on the base's
screen.

## Hardware for the demo

- MDDRC10 switch on **MIX**. RC1 ← rover Pi **GPIO18**, RC2 ← **GPIO19**, RC GND ← **GND**.
  Use the holes labelled 18, 19 and GND on the LoRa Bonnet's breakout row. RC +5V not connected.
- **DRIVE mode:** drive motors on the MDDRC10 outputs as in `../Drivetrain/motor_test/README.md`.
- **PROBE mode:** linear actuator on one MDDRC10 output instead of the motors. Either side works:
  in MIX mode the rover sends throttle only, and that drives both outputs the same.
- **Swapping plugs:** switch the 12 V off first. Switch back on with `rover.py` running: it sends
  "stop" pulses the whole time, so the MDDRC10 captures the right neutral at power-up.
- Soil sensor: the USB–RS485 adapter, same as before.
- **Tilt sensor: MPU-6050 (GY-521 board).**
  - **Wiring:** VCC to Pi 3.3 V, GND to GND, SDA and SCL to the SDA/SCL holes on the Bonnet. It
    shares I2C with the OLED: the OLED is at 0x3C and the MPU-6050 at 0x68. `i2cdetect -y 1` should
    show both.
  - **Mounting:** screw it **flat and tight to the chassis**, not the tower. Foam tape or a loose
    mount turns actuator vibration into fake tilt.

## Install

On **both** Pis (inside the venv the team already uses):
```
pip install adafruit-circuitpython-rfm9x adafruit-circuitpython-ssd1306
```
Rover Pi, also (and turn on I2C: `sudo raspi-config` → Interface Options → I2C):
```
pip install minimalmodbus pigpio smbus2
sudo apt install pigpio && sudo systemctl enable --now pigpiod
```
Base Pi, also:
```
pip install numpy matplotlib
```
Copy `link.py` + `rover.py` to the rover's home folder, and `link.py` + `base.py` + `heatmap.py`
to the base's. Or clone the repo and run them from `code/Demo/`. Keep `font5x8.bin` in the home
folder on both, as before.

## Check before the demo (settings at the top of `rover.py`)

| Setting | Why |
|---|---|
| `EXTEND_S`, `RETRACT_S` (15 s / 18 s) | Time one full actuator stroke and set these a little longer. The actuator's limit switches stop it at the ends. |
| `ACT_EXTEND_SIGN` (+1) | If "probe down" pulls it up, set -1 (or swap the actuator's two wires). |
| `READ_S` (20 s) | How long it reads in the ground. The team's survey used 60 s; pH drifts at first. |
| `SENSOR_PORT` | Your adapter's `/dev/serial/by-id/...` name (from the team's code). |
| `MAX_DRIVE_PCT` (60) | Speed cap while driving. |
| `TILT_LIMIT_DEG` (0.75°) | Tilt that stops the probe. Run `python3 rover.py --tilt-test` (stop the service first). It prints the live angle: watch it while you lift the front a few mm by hand and while the probe goes into soft ground, then set the limit between the two. |
| `TILT_REQUIRED` (True) | With True, the rover refuses to probe if the MPU-6050 isn't answering. Set False only to test without it. |

## Run

Rover (over SSH, or as a service; see below):
```
python3 rover.py
```
Base (on the base Pi, or over SSH from the laptop):
```
python3 base.py
```
Then open `http://<base hostname>.local:8080` on the laptop or projector for the live map and
table. Campus Wi-Fi often blocks laptop-to-Pi connections. A phone hotspot that all three join is
simplest.

Files:
- **rover:** `~/soil/probe_results.csv`, kept even after it's sent.
- **base:** `~/soil/base_results.csv` (duplicates removed) and `~/soil/base_web/heatmap.png`.

### Rover as a service (starts at boot, restarts if it crashes)

`/etc/systemd/system/dirtt-rover.service`, with your user name and venv path:
```
[Unit]
Description=D.I.R.T.T. rover
After=pigpiod.service network.target
Wants=pigpiod.service

[Service]
User=<user>
WorkingDirectory=/home/<user>
ExecStart=/home/<user>/<venv>/bin/python /home/<user>/rover.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```
Then run `sudo systemctl enable --now dirtt-rover`, and see its output with
`journalctl -u dirtt-rover -f`. Stop the service before running the team's old `rover.py`: both
use the radio.

## How the link works

- **Heartbeat:** the base sends one every 2 s. The rover answers with its status (mode, what it's
  doing, the last event, results waiting to send), then up to 2 result lines.
- **Results:** sent with ACK, and resent after every heartbeat until the base has them. The base
  ignores repeats, so a lost ACK can't create a duplicate point.
- **Driving:** while a drive key is held, the base sends a drive packet 5 times a second, with no
  ACK, and pauses heartbeats so the rover never transmits over it.
  - The rover stops if no drive packet arrives for 1 s.
  - No packet of any kind for 10 s means the link is lost: the drive motors stop. A probe already
    running finishes and saves its result.
- **Commands** (STOP, mode, probe, actuator) are sent with ACK and retries.
  - The Adafruit library's `send_with_ack()` ignores everything else while it waits. A command
    and a status reply sent at the same moment then cancel each other out for about 4 s.
  - `link.reliable_send()` keeps answering while it waits, so that can't happen.
- **Compatibility:** message types 1–4 and the first five status bytes match the team's original
  `bot.py`.

## Testing without radios

Run both on one computer, in two terminals:
```
python3 rover.py --sim --fast --data-dir /tmp/r
python3 base.py  --sim --data-dir /tmp/b
```
- `--sim` replaces the radios with UDP and behaves like the Adafruit library.
- `--sim-loss 0.2` drops 20 % of packets.
- `--fast` shortens the probe timings.
- A probe at grid x = 9 plays "hit a rock": the simulated tilt sensor tips 2° partway down.
- The simulated soil sensor makes up a field from the grid position.

Tested this way with no loss and with 20 % loss:
- 9 probes on a 3 × 3 grid: all saved, no duplicates.
- Heat map and web page drawn.
- Driving starts, then stops on key release.
- Wrong-mode commands refused.
- STOP mid-probe works.
- A blocked probe is raised again and nothing is saved.
- Link loss stops the motors.

**Not yet run on the real radios, sensor or MDDRC10.**

## Known limits (demo version)

- **The grid position is what the operator types.** There's no GPS yet.
- **After a STOP mid-probe, the probe stays where it stopped.** Press `R` to bring it up.
- **The tilt guard stands in for stall detection.**
  - The actuator is far stronger than the job, so its current barely rises and it never stalls.
    If the probe hits something hard, the rover's front lifts first.
  - Before each probe, the rover takes 1 s of "level" readings. If the tilt goes past
    `TILT_LIMIT_DEG` for 0.2 s while the probe goes down, it stops, raises the probe, saves
    nothing, and the base shows "probe stopped: rover started to tip".
  - **The force limit is therefore about the rover's weight on the probe side.** Ballast raises
    it.
  - A load cell would measure the actual force; that's the next step.
- **No battery reading yet.** The base shows "n/a".
