#!/usr/bin/env zsh
# The only way anything goes live (PROTOCOL.md section 9).
#   deploy.sh <commit>   deploy that commit, then prove it is live
#   deploy.sh check      report the state now; change nothing
#
# THE ONE FIXED RULE, which the project must not weaken: this script prints
# LIVE, and writes runs/live-sha, only after it has verified that the running
# system reports the deployed commit AND that the running process started
# after the deploy began. A restart that did not happen, or an old process
# still serving, is NOT LIVE. Everything between the PROJECT markers is the
# project's own and must be written before the first deploy.
set -u
HERE="${0:A:h}"
source "${RUNNER_CONF:-$HERE/runner.conf}"
RUNS="${WORKSPACE:A}/runs"; mkdir -p "$RUNS"
REPO_LIST=(${=REPOS}); REPO="${REPO_LIST[1]:A}"
WAIT_SECONDS=60        # how long to wait for the new process to report

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>> PROJECT: start <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

# 1. Can the host be reached? Return non-zero to stop before anything is pushed.
project_reachable() {
  print -u2 "deploy.sh: project_reachable is not written yet"; return 1
  # Example: ssh -o ConnectTimeout=5 app-host true
}

# 2. Put commit $1 (a full hash) on the host and restart every service.
#    Return non-zero on any failure.
project_deploy() {
  print -u2 "deploy.sh: project_deploy is not written yet"; return 1
  # Example: git -C "$REPO" push production "$1":main && ssh app-host 'systemctl restart todo-app'
}

# 3. Print the commit the RUNNING system reports (not the commit on disk).
#    By default this is the first word LIVE_CHECK_CMD prints.
live_commit() {
  [ -n "${LIVE_CHECK_CMD:-}" ] || { print -u2 "deploy.sh: LIVE_CHECK_CMD is empty in runner.conf"; return 1; }
  ${=LIVE_CHECK_CMD} 2>/dev/null | head -1 | awk '{print $1}'
  # Example LIVE_CHECK_CMD: 'curl -s -m 5 https://todo.example/version'
}

# 4. Print the time the RUNNING process started, in seconds since the epoch,
#    read from the host itself. With several services, print the oldest start.
live_started_at() {
  print -u2 "deploy.sh: live_started_at is not written yet"; return 1
  # Example: ssh app-host 'date -d "$(systemctl show -p ActiveEnterTimestamp --value todo-app)" +%s'
}

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>> PROJECT: end <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

# ---- the fixed rule. Do not edit below this line.
# proven <commit> <since>: the running system reports <commit> and its process
# started at or after <since>. Sets WHY when it is not so.
proven() {
  local want="$1" since="$2" got started
  got="$(live_commit)" || { WHY="the live check failed"; return 1; }
  [ ${#got} -ge 7 ] || { WHY="the live check printed no commit"; return 1; }
  [[ "$want" == "$got"* || "$got" == "$want"* ]] || { WHY="the running system reports $got, not $want"; return 1; }
  started="$(live_started_at)" || { WHY="the process start time could not be read"; return 1; }
  [[ "$started" == <-> ]] || { WHY="the process start time is not a number: $started"; return 1; }
  (( started >= since )) || { WHY="the running process started at $started, before the deploy began at $since"; return 1; }
  return 0
}

case "${1:-}" in
  check)
    if [ ! -f "$RUNS/live-sha" ]; then print "NOT LIVE: no deploy is recorded (runs/live-sha is missing)"; exit 1; fi
    SHA="$(cat "$RUNS/live-sha")"; SINCE="$(cat "$RUNS/live-since" 2>/dev/null || print 0)"
    if proven "$SHA" "$SINCE"; then print "LIVE $SHA"; exit 0; fi
    print "NOT LIVE: recorded $SHA, but $WHY"; exit 1;;
  "")
    print "usage: deploy.sh <commit> | deploy.sh check" >&2; exit 2;;
  *)
    SHA="$(git -C "$REPO" rev-parse --verify "$1^{commit}" 2>/dev/null)" || { print "NOT LIVE: $1 is not a commit in $REPO"; exit 2; }
    project_reachable || { print "NOT LIVE: the host cannot be reached; nothing was pushed"; exit 1; }
    SINCE="$(date +%s)"
    project_deploy "$SHA" || { print "NOT LIVE: the deploy of $SHA failed"; exit 1; }
    WHY="not checked"; n=0
    until proven "$SHA" "$SINCE"; do
      n=$((n+5)); [ $n -le $WAIT_SECONDS ] || { print "NOT LIVE: $WHY"; exit 1; }
      sleep 5
    done
    print -r -- "$SHA" > "$RUNS/live-sha"; print -r -- "$SINCE" > "$RUNS/live-since"
    print "LIVE $SHA";;
esac
