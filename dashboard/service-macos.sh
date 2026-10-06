#!/usr/bin/env zsh
# Keep the runner dashboard (dashboard/serve.py) running on a Mac, as a launchd
# agent of the user who runs this: started when that user logs in, started
# again if it ends.
#   service-macos.sh [options] print      show the launchd file it would write; change nothing
#   service-macos.sh [options] install    write it, make a token if there is none, start the service
#   service-macos.sh [options] status     is it loaded, and does it answer?
#   service-macos.sh [options] uninstall  stop it and remove the launchd file; the state directory is kept
# Options, each with a value, before the word:
#   --label       the launchd label (com.runner-kit.dashboard)
#   --port        the port on this machine (8787)
#   --state-dir   where the dashboard keeps its state, its token and its logs (~/.runner-dashboard)
#   --python      the python3 to run it with (the one on the PATH)
#   --allow-host  a name the dashboard is reached by, besides this machine's own (may be given more than once)
#   --home, --prefix, --keep-hours   passed to serve.py as they are
# The dashboard listens on this machine only. Publishing it to a network, by a
# reverse proxy or a tunnel, is a separate step and the owner's to take. The
# token is made here, kept in <state-dir>/token readable by this user only,
# and never printed.
set -u
HERE="${0:A:h}"; LABEL=com.runner-kit.dashboard; PORT=8787; STATE="$HOME/.runner-dashboard"
PY="$(command -v python3)"; HOMEURL=""; PREFIX=""; KEEP=""; NAMES=()
while [[ "${1:-}" == --* ]]; do
  [ $# -ge 2 ] || { print -u2 "$1 needs a value"; exit 2; }
  case "$1" in
    --label) LABEL="$2";; --port) PORT="$2";; --state-dir) STATE="${2:A}";; --python) PY="$2";;
    --home) HOMEURL="$2";; --prefix) PREFIX="$2";; --keep-hours) KEEP="$2";; --allow-host) NAMES+=("$2");;
    *) print -u2 "unknown option: $1 (read the head of $0)"; exit 2;;
  esac
  shift 2
done
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"; DOMAIN="gui/$(id -u)"

plist() {
  local -a args=("$PY" "$HERE/serve.py" --host 127.0.0.1 --port "$PORT" --state-dir "$STATE" --token-file "$STATE/token")
  [ -n "$HOMEURL" ] && args+=(--home "$HOMEURL")
  [ -n "$PREFIX" ] && args+=(--prefix "$PREFIX")
  [ -n "$KEEP" ] && args+=(--keep-hours "$KEEP")
  local n; for n in "${NAMES[@]}"; do args+=(--allow-host "$n"); done
  python3 - "$LABEL" "$STATE" "${args[@]}" <<'PY'
import plistlib, sys
label, state, args = sys.argv[1], sys.argv[2], sys.argv[3:]
sys.stdout.buffer.write(plistlib.dumps({
    "Label": label, "ProgramArguments": args, "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 5,
    "ProcessType": "Background", "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
    "StandardOutPath": state + "/serve.out.log", "StandardErrorPath": state + "/serve.err.log"}))
PY
}

status() {
  launchctl print "$DOMAIN/$LABEL" 2>/dev/null | grep -E '^[[:space:]]*(state|pid) = ' || print "not loaded: $LABEL"
  curl -s -m 5 "http://127.0.0.1:$PORT/healthz" || print -n "no answer on port $PORT"
  print
}

case "${1:-}" in
  print) plist;;
  install)
    mkdir -p "$STATE" "${PLIST:h}" && chmod 700 "$STATE" || exit 1
    [ -s "$STATE/token" ] || ( umask 077; python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$STATE/token" ) || exit 1
    plist > "$PLIST" || exit 1
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null
    launchctl bootstrap "$DOMAIN" "$PLIST" || exit 1
    sleep 2; status
    print "Reports need the token in $STATE/token. On each machine whose runners should report here, write"
    print "the dashboard's address and that token in ~/.config/runner-kit/dashboard.conf, as DASHBOARD_URL= and"
    print "DASHBOARD_TOKEN=, and keep that file readable by its owner only.";;
  status) status;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null
    rm -f "$PLIST" && print "removed $PLIST; kept $STATE";;
  *) print -u2 "usage: service-macos.sh [options] print|install|status|uninstall (read the head of $0)"; exit 2;;
esac
