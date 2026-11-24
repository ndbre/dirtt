# Demo drive: rover Pi → MDDRC10

For the December demo, before the flight controller is in the loop. The rover Pi takes the
Arduino's place and sends the MDDRC10 the same R/C pulses (1500 µs = stop, ±435 µs = full
speed). You drive it from a laptop over SSH with the keyboard.

This is a stopgap. The real design is Pi → MAVLink → flight controller → MDDRC10 (requirement NV1),
which adds ArduPilot's navigation, geofence and failsafes.

## Wiring

| Pi pin (physical) | MDDRC10 |
|---|---|
| 12 (GPIO18) | RC1 signal |
| 35 (GPIO19) | RC2 signal |
| 14 (GND) | RC GND |
| — | RC +5V: **not connected** |

Motors, battery and fuse as in `../motor_test/README.md`. The Pi's 3.3 V signal is what normal
R/C receivers send too. If the driver's ERR LED blinks twice (no pulses), check the three wires
and that `pigpiod` is running.

## Install (once, on the rover Pi)

```
sudo apt install pigpio python3-pigpio
sudo systemctl enable --now pigpiod
```

(`pigpio` supports the Pi 3 B and 4, not the Pi 5.)

## Run

1. Rover on blocks first. Driver switch on **MIX**, 12 V off.
2. From the laptop: `ssh <user>@dirttrover.local`, then `python3 pi_drive.py`.
3. When it says so, switch on the 12 V (the driver captures "stop" at power-up), then press Enter.

| Key | Does |
|---|---|
| hold `w`/`s` or ↑/↓ | forward / reverse |
| hold `a`/`d` or ←/→ | pivot left / right |
| hold `q`/`e` | arc forward-left / forward-right |
| let go | stops (after `--deadman`, 0.8 s) |
| space or `x` | stop now |
| `+` / `-` | speed ±10 % |
| Esc or Ctrl+C | stop and quit |

| Option | |
|---|---|
| `--test` | the Arduino sketch's automatic wheel check |
| `--mode ind` | driver switch on IND (RC1 = left side, RC2 = right side) |
| `--speed 40` | starting speed, % (default 30) |
| `--max 80` | speed cap, % (default 60) |
| `--deadman 1.0` | raise it if driving stutters when you first hold a key |
| `--dry-run` | no Pi or driver: prints the pulses |

## Safety

- It stops the motors when no key arrives for 0.8 s, when you quit, on `kill`, and when the SSH
  session drops. Then it stops sending pulses.
- It can't stop them if `pigpiod` keeps running after `kill -9` of the script. Then run
  `pigs s 18 0 s 19 0`. **Keep the e-stop in reach during the demo.**
- `--max` defaults to 60 %. Raise it once you've driven the demo route.

## For the demo

- Campus Wi-Fi often blocks laptop-to-Pi connections. A phone hotspot that both join is simplest.
- Wi-Fi lag shows up as the rover coasting for up to the dead-man time after you let go. Drive
  slowly near people.
