#!/usr/bin/env zsh
# The kit's self-test. It builds a toy code repository and a toy workspace in a
# temporary directory, initialises them with the kit, and proves four facts:
#   (a) a dry queue pass picks the first task
#   (b) a real tiny task run by the default builder ends with a commit whose
#       subject starts with the task id, and the heading marked [x]
#   (c) a deliberately bad staged change (an unnamed new file) is refused by
#       the commit check
#   (d) the configured notifier delivered a message
# Standard output is exactly four lines, one per fact, then one final line:
#   SELFTEST: PASS      all four proven                       (exit 0)
#   SELFTEST: PARTIAL   (b) skipped with --no-agent, rest ok  (exit 2)
#   SELFTEST: FAIL      at least one fact not proven          (exit 1)
# Details go to selftest.log in the temporary directory; its path is printed on
# standard error.
#
# Usage:
#   selftest/run.sh --conf <runner.conf>          builder, model and notifier
#                                                 from an installed project
#   selftest/run.sh --adapter <name> --model <id> [--effort medium]
#                   [--notify none|desktop|command] [--notify-cmd '<command>']
#   selftest/run.sh --no-agent                    skip (b); needs no agent
#   Also: --dir <directory> to build the toy project there (default: a new
#   temporary directory); --keep to leave it in place after a pass.
# (b) starts one real agent session and so spends a little of the agent's
# usage. Nothing outside the temporary directory is changed.
set -u
KIT="${0:A:h:h}"; BIN="$KIT/bin"
ADAPTER=""; MODEL=""; EFFORT="medium"; NOTIFY_NAME=""; NOTIFY_COMMAND=""; AGENT=1; BASE=""; KEEP=0; FROM=""
ALLOWED="Bash"; MINVER=""
while [ $# -gt 0 ]; do
  case "$1" in
    --conf) FROM="$2"; shift 2;;
    --adapter) ADAPTER="$2"; shift 2;;
    --model) MODEL="$2"; shift 2;;
    --effort) EFFORT="$2"; shift 2;;
    --notify) NOTIFY_NAME="$2"; shift 2;;
    --notify-cmd) NOTIFY_COMMAND="$2"; shift 2;;
    --dir) BASE="$2"; shift 2;;
    --no-agent) AGENT=0; shift;;
    --keep) KEEP=1; shift;;
    *) print -u2 "unknown argument: $1 (read the head of $0)"; exit 2;;
  esac
done
if [ -n "$FROM" ]; then
  [ -f "$FROM" ] || { print -u2 "no settings file at $FROM"; exit 2; }
  eval "$( source "$FROM"
    L="${DEFAULT_BUILDER:-S}"; AV="ADAPTER_$L"; MV="MODEL_$L"
    print -r -- "C_ADAPTER=${(q)${(P)AV:-}} C_MODEL=${(q)${(P)MV:-}} C_EFFORT=${(q)${DEFAULT_EFFORT:-medium}}"
    print -r -- "C_NOTIFY=${(q)${NOTIFY:-none}} C_NOTIFY_CMD=${(q)${NOTIFY_CMD:-}}"
    print -r -- "C_ALLOWED=${(q)${CLAUDE_ALLOWED_TOOLS-Bash}} C_MINVER=${(q)${CLAUDE_MIN_VERSION:-}}" )"
  ADAPTER="${ADAPTER:-$C_ADAPTER}"; MODEL="${MODEL:-$C_MODEL}"; EFFORT="$C_EFFORT"
  NOTIFY_NAME="${NOTIFY_NAME:-$C_NOTIFY}"; NOTIFY_COMMAND="${NOTIFY_COMMAND:-$C_NOTIFY_CMD}"
  ALLOWED="$C_ALLOWED"; MINVER="$C_MINVER"
fi
NOTIFY_NAME="${NOTIFY_NAME:-none}"
if [ $AGENT = 1 ] && { [ -z "$ADAPTER" ] || [ -z "$MODEL" ]; }; then
  print -u2 "the self-test needs a builder: give --conf <runner.conf>, or --adapter <name> --model <id>, or --no-agent"; exit 2
fi

if [ -n "$BASE" ]; then mkdir -p "$BASE" || exit 2; T="$(mktemp -d "${BASE:A}/selftest-XXXXXX")"
else T="$(mktemp -d "${TMPDIR:-/tmp}/runner-kit-selftest-XXXXXX")"; fi
T="${T:A}"; APP="$T/app"; WS="$T/work"; OUT="$T/selftest.log"
print -u2 "self-test directory: $T   (details: $OUT)"
FAILED=0; SKIPPED=0
pass() { print -r -- "PASS ($1) $2"; }
fail() { print -r -- "FAIL ($1) $2"; FAILED=1; }
note() { print -r -- "$*" >> "$OUT"; }

# ---- the toy project: a to-do list printer and a workspace, two repositories
toy_repo() {
  git init -q -b main "$1" && git -C "$1" config user.name "runner-kit selftest" \
    && git -C "$1" config user.email "runner-kit@users.noreply.github.com" \
    && git -C "$1" config commit.gpgsign false \
    && git -C "$1" config core.hooksPath "$1/.git/hooks"
}
{
  toy_repo "$APP" && toy_repo "$WS" || exit 1
  mkdir -p "$APP/src"
  cat > "$APP/src/todo.py" <<'PY'
"""Print a to-do list, one item per line."""
import sys


def format_item(number, text):
    return text


def main(argv):
    for number, text in enumerate(argv[1:], 1):
        print(format_item(number, text))


if __name__ == "__main__":
    main(sys.argv)
PY
  git -C "$APP" add -A && git -C "$APP" commit -q -m "toy to-do list"
  "$BIN/runner-init" "$WS" "$APP"
  cat > "$WS/runner.conf" <<EOF
PROJECT=selftest
WORKSPACE='$WS'
REPOS='$APP'
PRODUCT_DIRS='src/'
FREE_DIRS='tests/'
REGISTRY_FILE=
LIVE_FLAG_PATTERN=
LIVE_FLAG_FILE=
NOTIFY=$NOTIFY_NAME
NOTIFY_CMD=${(q-)NOTIFY_COMMAND}
PREFLIGHT_CMD=
ADAPTER_S=${ADAPTER:-none}
MODEL_S=${(q-)MODEL}
DEFAULT_BUILDER=S
DEFAULT_EFFORT=$EFFORT
DEFAULT_REVIEWER='S $EFFORT'
SUPERVISOR=S
CLAUDE_ALLOWED_TOOLS=${(q-)ALLOWED}
CLAUDE_MIN_VERSION=${(q-)MINVER}
DEPLOYS=no
LIVE_CHECK_CMD=
EOF
  cat > "$WS/DESIGN.md" <<'MD'
# Design

A command-line to-do list. `python3 src/todo.py <item> [<item> ...]` prints the
items, one per line. There is no deploy.
MD
  cat > "$WS/TASKS.md" <<MD
# Tasks

## How a task is run

One fresh session per task, started by \`run_task.sh\`. The rules are
\`DELIVERY-RULES.yaml\`. The order is \`RUN-ORDER.md\`. M is the builder's letter
and effort, R the one reviewer's. Status: [ ] not started, [~] built but held,
[x] done (commit).

## Tasks

### 1.1 Each to-do item is shown with its number [ ]  M: S $EFFORT, R: S $EFFORT
G1: the list can be read at a glance.
Ordered by the owner. Observed: \`python3 src/todo.py "buy milk" "post letter"\` prints the two items with no numbers.
Files: src/todo.py.
Build: in format_item, put the item's number and a full stop before its text. About 1 line.
Done when: \`python3 src/todo.py "buy milk" "post letter"\` prints \`1. buy milk\` and then \`2. post letter\`.
Owner sees: numbered items.

### 1.2 The list is saved to a file [ ]  M: S $EFFORT, R: S $EFFORT
G1: the list can be read at a glance.
Ordered by the owner. Observed: the list is gone when the command ends.
Files: src/store.py.
Build: not built by the self-test; this task exists only for the commit check.
Done when: not run.
Owner sees: nothing.
MD
  print -r -- "# The queue. The self-test runs task 1.1 only.
1.1" > "$WS/RUN-ORDER.md"
  sed -i.bak 's|^goal_outcomes:.*|goal_outcomes:\
  - id: G1\
    outcome: "The to-do list can be read at a glance."|' "$WS/DELIVERY-RULES.yaml" && rm -f "$WS/DELIVERY-RULES.yaml.bak"
  git -C "$WS" add -A && git -C "$WS" commit -q -m "toy workspace"
} >> "$OUT" 2>&1 || { print -r -- "FAIL (setup) the toy project could not be built; see $OUT"; print "SELFTEST: FAIL"; exit 1; }
export RUNNER_CONF="$WS/runner.conf"
unset RUNNER_TASK_ID

# ---- (a) a dry queue pass picks the first task
note ""; note "==== (a) dry queue pass"
( cd "$WS" && QUEUE_DRY=1 QUEUE_ONCE=1 "$BIN/run_queue.sh" ) >> "$OUT" 2>&1
if grep -q "(dry: would run task 1.1)" "$WS/runs/queue.log" 2>/dev/null; then pass a "a dry queue pass picks the first task"
else fail a "a dry queue pass did not pick task 1.1"; fi

# ---- (b) a real tiny task, run by the default builder
note ""; note "==== (b) task 1.1 through run_task.sh"
if [ $AGENT = 0 ]; then
  SKIPPED=1; print -r -- "SKIP (b) no agent session was started (--no-agent); a real task run is not proven"
elif [ ! -f "$KIT/adapters/$ADAPTER.sh" ]; then
  fail b "there is no adapter named $ADAPTER in $KIT/adapters"
elif ! ( source "$KIT/adapters/$ADAPTER.sh"; command -v "$AGENT_BIN" >/dev/null && adapter_signed_in ) >> "$OUT" 2>&1; then
  fail b "the $ADAPTER agent is not installed or not signed in; sign in, or run with --no-agent"
else
  BASE_APP="$(git -C "$APP" rev-parse HEAD)"; BASE_WS="$(git -C "$WS" rev-parse HEAD)"
  ( cd "$WS" && "$BIN/run_task.sh" 1.1 2 ) >> "$OUT" 2>&1; RC=$?
  SUBJECT="$( { git -C "$APP" log --format='%h %s' "$BASE_APP..HEAD"; git -C "$WS" log --format='%h %s' "$BASE_WS..HEAD"; } | grep -m1 -E '^[0-9a-f]+ 1\.1[ :]' )"
  MARKED="$(grep -m1 '^### 1\.1 ' "$WS/TASKS.md" | grep -c '\[x\]')"
  RESULT="$(cd "$APP" && python3 src/todo.py "buy milk" "post letter" 2>&1 | tr '\n' '|')"
  note "run_task.sh exit $RC; commit: ${SUBJECT:-none}; heading marked: $MARKED; program prints: $RESULT"
  if [ $RC = 0 ] && [ -n "$SUBJECT" ] && [ "$MARKED" = 1 ]; then
    pass b "the default builder ran a task to a commit whose subject starts with the task id, and the heading is marked [x]"
  else
    fail b "task 1.1 did not finish (run_task.sh exit $RC, commit: ${SUBJECT:-none}, heading marked: $MARKED)"
  fi
fi

# ---- (c) the commit check refuses a new file the task does not name
note ""; note "==== (c) an unnamed new file, staged under task 1.2"
HEAD_BEFORE="$(git -C "$APP" rev-parse HEAD)"
print -r -- "# a file no task names" > "$APP/src/unnamed_extra.py"
git -C "$APP" add src/unnamed_extra.py
REFUSAL="$( cd "$APP" && RUNNER_TASK_ID=1.2 git commit -m "1.2: a file the task does not name" 2>&1 )"; RC=$?
note "git commit exit $RC: $REFUSAL"
if [ $RC != 0 ] && [ "$(git -C "$APP" rev-parse HEAD)" = "$HEAD_BEFORE" ] && print -r -- "$REFUSAL" | grep -q "RUNNER CHECK: new file: src/unnamed_extra.py"; then
  pass c "the commit check refused a staged new file that the task does not name"
else
  fail c "the commit check did not refuse an unnamed new file (git commit exit $RC)"
fi
git -C "$APP" reset -q -- src/unnamed_extra.py; rm -f "$APP/src/unnamed_extra.py"

# ---- (d) the configured notifier delivered a message
note ""; note "==== (d) notifier $NOTIFY_NAME"
wait; sleep 1
MSG="selftest message $$"
( cd "$WS" && "$BIN/runner-notify" "$MSG" ) >> "$OUT" 2>&1; RC=$?
LINE="$(grep -F "$MSG" "$WS/runs/notify.log" 2>/dev/null | tail -1)"
note "runner-notify exit $RC; log line: ${LINE:-none}"
note "notify.log:"; cat "$WS/runs/notify.log" >> "$OUT" 2>/dev/null
ROUTE="${${LINE#*\[}%%\]*}"
if [ $RC != 0 ] || [ -z "$LINE" ]; then
  fail d "the $NOTIFY_NAME notifier did not deliver the message (exit $RC)"
elif [[ "$ROUTE" == *failed* ]]; then
  fail d "the $NOTIFY_NAME notifier failed ($ROUTE)"
elif [ $AGENT = 1 ] && [ $FAILED = 0 ] && ! grep -q "task 1.1 done" "$WS/runs/notify.log"; then
  fail d "the runner's own done message for task 1.1 is not in runs/notify.log"
else
  pass d "the configured notifier delivered a message"
fi

if [ $FAILED = 1 ]; then print "SELFTEST: FAIL"; exit 1; fi
[ $KEEP = 1 ] || [ -n "$BASE" ] || rm -rf "$T"
if [ $SKIPPED = 1 ]; then print "SELFTEST: PARTIAL"; exit 2; fi
print "SELFTEST: PASS"; exit 0
