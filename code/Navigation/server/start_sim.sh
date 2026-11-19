#!/usr/bin/env bash
# D.I.R.T.T. shared navigation sim: ArduPilot SITL + nav_sim.py + Cloudflare tunnel.
# Each one is restarted if it exits. Settings come from ~/.dirtt-sim.env (see sim.env.example).
# Started at boot by the Windows scheduled task (register_task.ps1); fine to run by hand too.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
NAV="$(dirname "$HERE")"
CONF="${DIRTT_SIM_ENV:-$HOME/.dirtt-sim.env}"
CLI_AUTH="${AUTH:-}"                            # AUTH=none on the command line beats the file
[ -f "$CONF" ] && . "$CONF"
[ -n "$CLI_AUTH" ] && AUTH="$CLI_AUTH"
: "${ARDUPILOT:=$HOME/ardupilot}"
: "${HOME_LOCATION:=33.4555,-88.789,100,0}"     # lat,lon,alt,heading where the rover starts
: "${PORT:=8000}"
: "${AUTH:=access}"
: "${ACCESS_TEAM:=}" ; : "${ACCESS_AUD:=}" ; : "${ADMINS:=}" ; : "${TUNNEL_TOKEN:=}"
RUN="${RUN_DIR:-$HOME/dirtt-sim-run}"
mkdir -p "$RUN/logs"

# only one copy at a time (the task can fire at startup and at log-on)
exec 9>"$RUN/.lock"
flock -n 9 || { echo "already running"; exit 0; }

[ -f "$HOME/venv-ardupilot/bin/activate" ] && . "$HOME/venv-ardupilot/bin/activate"
cp "$NAV/dirtt_sitl.parm" "$RUN/dirtt_sitl.parm"

supervise() {                                   # supervise NAME COMMAND...  (restart forever)
  local name=$1; shift
  while true; do
    local log="$RUN/logs/$name.log"
    [ -f "$log" ] && [ "$(stat -c %s "$log")" -gt 10000000 ] && mv -f "$log" "$log.old"
    echo "$(date '+%F %T') starting $name" >> "$RUN/logs/supervisor.log"
    ( "$@" ) >> "$log" 2>&1                     # subshell: the functions below exec
    echo "$(date '+%F %T') $name exited with code $?" >> "$RUN/logs/supervisor.log"
    sleep 3
  done
}

AP="$ARDUPILOT"
DEFAULTS="$AP/Tools/autotest/default_params/rover.parm,$AP/Tools/autotest/default_params/rover-skid.parm,$RUN/dirtt_sitl.parm"
# -w: wipe saved parameters on every start, so each restart is a clean rover at HOME_LOCATION
# The start location can be moved from the sim page ("Move start here"): it writes $RUN/home_location
# SITL writes a flight log (~5 MB a minute while armed) on every start: keep the newest 5
sitl() { ls -1t "$RUN"/logs/*.BIN 2>/dev/null | tail -n +5 | xargs -r rm -f
         local loc="$HOME_LOCATION"; [ -s "$RUN/home_location" ] && loc="$(head -1 "$RUN/home_location")"
         cd "$RUN" && exec "$AP/build/sitl/bin/ardurover" -S -w --model rover-skid --speedup 1 \
           --defaults "$DEFAULTS" --sim-address=127.0.0.1 -I0 --home "$loc"; }
nav() { cd "$NAV" && exec python3 nav_sim.py --connect tcp:127.0.0.1:5760 --host 127.0.0.1 --port "$PORT" \
           --auth "$AUTH" ${ACCESS_TEAM:+--access-team "$ACCESS_TEAM"} ${ACCESS_AUD:+--access-aud "$ACCESS_AUD"} \
           --admins "$ADMINS" --logs "$RUN/runs" --restart-cmd "pkill -x ardurover" \
           --home-file "$RUN/home_location"; }
tunnel() { exec cloudflared tunnel --no-autoupdate run --token "$TUNNEL_TOKEN"; }

trap 'kill 0' EXIT INT TERM
supervise sitl sitl &
supervise nav nav &
if [ -n "$TUNNEL_TOKEN" ] && [ "$AUTH" = "access" ]; then
  supervise tunnel tunnel &
elif [ -n "$TUNNEL_TOKEN" ]; then
  echo "AUTH=$AUTH: NOT starting the tunnel (only AUTH=access is safe on the internet)"
else
  echo "no TUNNEL_TOKEN: local only (http://localhost:$PORT)"
fi
echo "running; logs in $RUN/logs"
wait
