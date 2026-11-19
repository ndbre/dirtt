# Hosting the nav sim at dirtt-sim.ndbre.com

The sim runs on a Windows 11 PC that stays on, inside WSL (Ubuntu). A Cloudflare Tunnel makes it
reachable at `https://dirtt-sim.ndbre.com` without opening any router ports. Cloudflare Access only
lets listed emails in. One person drives at a time; everyone else watches.

```
browser ── Cloudflare Access (email code) ── tunnel ──> cloudflared ─> nav_sim.py :8000 ─> ArduPilot SITL :5760
                                                        (all inside WSL on the home PC, started at boot)
```

`start_sim.sh` runs SITL, `nav_sim.py` and `cloudflared`, restarting any of them if they exit.
Logs: `~/dirtt-sim-run/logs/`. Survey CSVs: `~/dirtt-sim-run/runs/` (newest 300 files kept).

## 1. WSL and the ArduPilot simulator

PowerShell **as Administrator**:
```
wsl --install -d Ubuntu-24.04
```
Reboot. In Ubuntu, create the user `dirtt`. Then:
```
sudo apt update && sudo apt install -y git
git clone -b Rover-4.6.3 --recurse-submodules https://github.com/ArduPilot/ardupilot.git ~/ardupilot
cd ~/ardupilot
Tools/environment_install/install-prereqs-ubuntu.sh -y
. ~/.profile
./waf configure --board sitl
./waf rover
```

## 2. The sim code, run locally first

```
git clone https://github.com/ndbre/dirtt.git ~/dirtt
~/venv-ardupilot/bin/pip install "pyjwt[crypto]"
cp ~/dirtt/code/Navigation/server/sim.env.example ~/.dirtt-sim.env
chmod 600 ~/.dirtt-sim.env
AUTH=none ~/dirtt/code/Navigation/server/start_sim.sh
```
Open http://localhost:8000 in a browser on the PC. After about 40 s it says *SITL connected*.
Make a grid and run a survey to check that everything works, then press Ctrl+C.

(`AUTH=none` = local mode, no sign-in, you always have control. Never use it with the tunnel running.)

## 3. Cloudflare Access (do this BEFORE the tunnel, so the address is never open)

1. Open https://one.dash.cloudflare.com, pick a **team name** (e.g. `dirtt`), and choose the
   **Free** plan (up to 50 users).
2. **Access → Applications → Add an application → Self-hosted.**
   - Name: `DIRTT nav sim`. Session duration: 24 hours.
   - Public hostname: subdomain `dirtt-sim`, domain `ndbre.com`.
   - Policy: name `Team`, action **Allow**, include **Emails**: the team, Dr. Hudson, graders.
   - Login methods: **One-time PIN** (people get a code by email; no passwords).
3. Open the application's **Overview** and copy the **Application Audience (AUD) Tag**.
4. Put the team name and AUD in `~/.dirtt-sim.env` (`ACCESS_TEAM=`, `ACCESS_AUD=`).
   Also set `ADMINS=` to the emails that can take over control and restart the simulator.

## 4. The tunnel

1. In WSL, install cloudflared:
   ```
   curl -L -o /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   sudo dpkg -i /tmp/cloudflared.deb
   ```
2. Dashboard: **Networks → Tunnels → Create a tunnel → Cloudflared**, name it `dirtt-home`.
   On the install page, copy only the long token after `--token` (don't run their install command;
   `start_sim.sh` runs cloudflared itself). Put it in `~/.dirtt-sim.env` as `TUNNEL_TOKEN=`.
3. Next page, **Public hostname**: subdomain `dirtt-sim`, domain `ndbre.com`,
   service **HTTP** `localhost:8000`. Save.
4. Start everything by hand once:
   ```
   ~/dirtt/code/Navigation/server/start_sim.sh
   ```
   From your phone (off Wi-Fi), open https://dirtt-sim.ndbre.com. It asks for your email, sends a
   code, then shows the sim. Someone not on the list gets "That account does not have access."
   Ctrl+C when done.

## 5. Start at boot (Windows)

1. Copy `register_task.ps1` somewhere on Windows (it's at
   `\\wsl$\Ubuntu-24.04\home\dirtt\dirtt\code\Navigation\server\` in File Explorer), then in
   PowerShell **as Administrator**, in that folder:
   ```
   powershell -ExecutionPolicy Bypass -File .\register_task.ps1 -LinuxUser <your Linux user>
   Start-ScheduledTask -TaskName "DIRTT nav sim"
   ```
   It asks for the Windows password. If the account has none, leave it blank: the sim then starts
   at sign-in, and a password-less account signs in by itself at boot.
2. Settings → System → Power: **Sleep: Never** when plugged in.
3. Settings → Windows Update → Advanced → **Active hours**: cover the times you might demo.
4. BIOS/UEFI: **Restore on AC power loss = Power On** (a.k.a. "AC Back", "After power loss"),
   so the PC turns itself back on after an outage or a kicked cord.
5. Test: restart the PC, **don't log in**, wait ~2 minutes, open the site from your phone.
   If it doesn't come up until someone logs in, the task's "at startup" run isn't starting WSL on
   this PC; it will still start at every log-on (the second trigger).

## Day to day

| Task | How |
|---|---|
| Update the sim code | `cd ~/dirtt && git pull && pkill -f nav_sim.py` (the supervisor restarts it with the new code) |
| Restart the simulator | Admins: **Restart SITL** button. Or `pkill -x ardurover` |
| See what's happening | `tail -f ~/dirtt-sim-run/logs/nav.log` (also `sitl.log`, `tunnel.log`, `supervisor.log`) |
| Add/remove people | Zero Trust → Access → Applications → DIRTT nav sim → policy emails |
| Stop it | `Stop-ScheduledTask -TaskName "DIRTT nav sim"` then `wsl --shutdown` |

## How sharing works

- Everyone signs in with an email code. The server checks Cloudflare's signed token on every
  request, so it can't be faked by sending an email header.
- **Take control**: drive if nobody is; otherwise join the line. The page polls several times a
  second and that is the heartbeat: close the tab and control passes on after 10 s.
- If people are waiting, a turn lasts 15 minutes (`--turn-minutes`). Admins can **Take over**.
- **Start fresh** clears points, obstacles, results and GPS error for the next person.
- Limits: 150 points, 25 obstacles, points within 2 km, 10 commands/s per person.
