#!/usr/bin/env zsh
# The kit's self-test. It builds a toy code repository and a toy workspace in a
# temporary directory, initialises them with the kit, and proves these facts:
#   (a) a dry queue pass picks the first task
#   (b) a real tiny task run by the default builder ends with a commit whose
#       subject starts with the task id, and the heading marked [x]
#   (c) to (g) each commit check refuses the change it exists to refuse: an
#       unnamed new file, a function nothing calls, the four TASKS.md limits,
#       a prerequisite that is not done, a live switch
#   (h) a commit that keeps every rule is accepted
#   (i) to (m) the runner's own logic, driven by a stand-in session that
#       spends nothing (adapters/stub.sh): a task run to done; a commit that
#       breaks the project's check is sent back and repaired; a check already
#       failing is reported once; a stopped task is parked and released only
#       by the owner; three different tasks stopping in a row pause the queue
#   (n) the configured notifier delivered a message
# Standard output is exactly one line per fact, then one final line:
#   SELFTEST: PASS      all proven                            (exit 0)
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
  print -r -- '{"sync_enabled": false}' > "$APP/src/settings.json"
  git -C "$APP" add -A && git -C "$APP" commit -q -m "toy to-do list"
  "$BIN/runner-init" "$WS" "$APP"
  cat > "$WS/runner.conf" <<EOF
PROJECT=selftest
WORKSPACE='$WS'
REPOS='$APP'
PRODUCT_DIRS='src/'
FREE_DIRS='tests/'
REGISTRY_FILE=
LIVE_FLAG_PATTERN='"sync_enabled": true'
LIVE_FLAG_FILE=settings.json
NOTIFY=$NOTIFY_NAME
NOTIFY_CMD=${(q-)NOTIFY_COMMAND}
PREFLIGHT_CMD=
CHECK_CMD='test ! -f src/BROKEN'
STOP_STREAK=3
ADAPTER_S=${ADAPTER:-none}
MODEL_S=${(q-)MODEL}
ADAPTER_T=stub
MODEL_T=none
DEFAULT_BUILDER=S
DEFAULT_EFFORT=$EFFORT
DEFAULT_REVIEWER='S $EFFORT'
SUPERVISOR=T
CLAUDE_ALLOWED_TOOLS=${(q-)ALLOWED}
CLAUDE_MIN_VERSION=${(q-)MINVER}
CLAUDE_TOOLS='Bash Read Edit Write Task'
CLAUDE_MCP=no
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
Build: not built by the self-test; this task exists only for the commit checks.
Done when: not run.
Owner sees: nothing.
Kept in the run order: until the list is saved, the user would see something false if sync were on.

### 2.1 A note is kept beside the list [ ]  M: T medium, R: T medium
G1: the list can be read at a glance. Files: src/notes.txt. Run by the stand-in session.

### 2.2 A change that breaks the project's check is repaired [ ]  M: T medium, R: T medium
G1: the list can be read at a glance. Files: src/BROKEN, src/notes.txt. Run by the stand-in session.

### 2.3 A note is kept while the check already fails [ ]  M: T medium, R: T medium
G1: the list can be read at a glance. Files: src/notes.txt. Run by the stand-in session.

### 3.1 A question for the owner is asked once [ ]  M: T medium, R: T medium
G1: the list can be read at a glance. Files: src/notes.txt. Run by the stand-in session.

### 4.1 A task that stops [ ]  M: T medium, R: T medium
G1: the list can be read at a glance. Files: src/notes.txt. Run by the stand-in session.

### 4.2 A second task that stops [ ]  M: T medium, R: T medium
G1: the list can be read at a glance. Files: src/notes.txt. Run by the stand-in session.

### 4.3 A third task that stops [ ]  M: T medium, R: T medium
G1: the list can be read at a glance. Files: src/notes.txt. Run by the stand-in session.

### 4.4 A task that waits behind three stops [ ]  M: T medium, R: T medium
G1: the list can be read at a glance. Files: src/notes.txt. Run by the stand-in session.
MD
  : > "$WS/REVIEW-STUB.md"
  cat > "$T/stub-session.zsh" <<'STUB'
# The self-test's stand-in for an agent session (adapters/stub.sh). It does by
# rote what a session would do for each toy task, through the same commit hook.
ID="$1"; source "$RUNNER_CONF"; WS="$WORKSPACE"; repos=(${=REPOS}); APP="${repos[1]}"
commit_app() { git -C "$APP" add -A && git -C "$APP" commit -q -m "$ID: $1" || exit 1; }
mark_done() {
  local sha="$(git -C "$APP" rev-parse --short HEAD)"
  sed -i.bak "s|^\\(### $ID .*\\) \\[ \\]|\\1 [x] ($sha)|" "$WS/TASKS.md" && rm -f "$WS/TASKS.md.bak"
  git -C "$WS" add TASKS.md && git -C "$WS" commit -q -m "$ID: done" || exit 1
  print "RUNNER: done $sha"
}
if [[ "$STUB_PROMPT" == *"You are the supervising session for"* ]]; then
  case "$ID" in
    3.1) print -r -- "- Task 3.1 asks the owner whether notes are kept (supervising session, $(date +%Y-%m-%d))" >> "$WS/DECISIONS.md"
         git -C "$WS" add DECISIONS.md && git -C "$WS" commit -q -m "docs: 3.1 waits for the owner" || exit 1
         print "SUPERVISOR: waiting 3.1 Should notes be kept? Recommended: yes.";;
    *)   print "SUPERVISOR: skip $ID the self-test skips it";;
  esac
  exit 0
fi
case "$ID" in
  2.1|2.3|4.4) print -r -- "$ID" >> "$APP/src/notes.txt"; commit_app "a note"; mark_done;;
  2.2) if [ "$STUB_MODE" = start ]; then
         : > "$APP/src/BROKEN"; commit_app "a change that breaks the check"; mark_done
       else
         git -C "$APP" rm -q src/BROKEN && git -C "$APP" commit -q -m "2.2: the check passes again" || exit 1
         print "RUNNER: done $(git -C "$APP" rev-parse --short HEAD)"
       fi;;
  3.1) if grep -q "^- Notes are kept. (owner, " "$WS/DECISIONS.md"; then print -r -- "$ID" >> "$APP/src/notes.txt"; commit_app "notes are kept"; mark_done
       else print "RUNNER: question Should notes be kept? Recommended: yes."; fi;;
  *)   print "RUNNER: blocked the self-test stops this task";;
esac
STUB
  print -r -- "# The queue. The self-test runs task 1.1 only.
1.1" > "$WS/RUN-ORDER.md"
  sed -i.bak 's|^goal_outcomes:.*|goal_outcomes:\
  - id: G1\
    outcome: "The to-do list can be read at a glance."|' "$WS/DELIVERY-RULES.yaml" && rm -f "$WS/DELIVERY-RULES.yaml.bak"
  git -C "$WS" add -A && git -C "$WS" commit -q -m "toy workspace"
} >> "$OUT" 2>&1 || { print -r -- "FAIL (setup) the toy project could not be built; see $OUT"; print "SELFTEST: FAIL"; exit 1; }
export RUNNER_CONF="$WS/runner.conf"
export STUB_SCRIPT="$T/stub-session.zsh"
unset RUNNER_TASK_ID
QLOG="$WS/runs/queue.log"

# Stage what is in the working tree of <repo> and try to commit it as task 1.2.
# Sets RC and REFUSAL, and puts the repository back as it was.
try_commit() {
  local repo="$1" before
  before="$(git -C "$repo" rev-parse HEAD)"
  git -C "$repo" add -A
  REFUSAL="$( cd "$repo" && RUNNER_TASK_ID=1.2 git commit -m "1.2: a change the self-test expects to be refused" 2>&1 )"; RC=$?
  note "git commit exit $RC: $REFUSAL"
  [ "$(git -C "$repo" rev-parse HEAD)" = "$before" ] || RC=0
  git -C "$repo" reset -q --hard "$before"; git -C "$repo" clean -q -fd
}
refused() { [ $RC != 0 ] && print -r -- "$REFUSAL" | grep -q "RUNNER CHECK: $1"; }
# Wait up to <seconds> for a line holding <text> in the queue log.
wait_for() { local n=0; while ! grep -qF -- "$1" "$QLOG" 2>/dev/null; do n=$((n+1)); [ $n -gt $(( $2 * 5 )) ] && return 1; sleep 0.2; done; }

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
print -r -- "# a file no task names" > "$APP/src/unnamed_extra.py"
try_commit "$APP"
if refused "new file: src/unnamed_extra.py"; then pass c "the commit check refused a staged new file that the task does not name"
else fail c "the commit check did not refuse an unnamed new file (git commit exit $RC)"; fi

# ---- (d) the caller check refuses a function nothing calls
note ""; note "==== (d) a function nothing calls, in a file task 1.2 names"
print -r -- 'def save_list(items):
    return len(items)' > "$APP/src/store.py"
try_commit "$APP"
if refused "caller: src/store.py adds save_list()"; then pass d "the commit check refused a new function that nothing outside the tests calls"
else fail d "the commit check did not refuse a function with no caller (git commit exit $RC)"; fi

# ---- (e) the four limits on TASKS.md
note ""; note "==== (e) TASKS.md: two new tasks, a sub-task of a sub-task, growth, a start condition"
E_BAD=""
print -r -- "
### 1.3 A second list [ ]  M: S medium, R: S medium
G1.

### 1.4 A third list [ ]  M: S medium, R: S medium
G1." >> "$WS/TASKS.md"
try_commit "$WS"; refused "new task: this commit adds 2 task headings" || E_BAD+=" two-new-tasks"
print -r -- "
### 1.2a1 A part of a part [ ]  M: S medium, R: S medium
G1." >> "$WS/TASKS.md"
try_commit "$WS"; refused "new task: 1.2a1 is a sub-task of a sub-task" || E_BAD+=" second-suffix"
{ print ""; repeat 25 print -r -- "A line of check output that belongs in the commit message."; } >> "$WS/TASKS.md"
try_commit "$WS"; refused "growth: TASKS.md grows by" || E_BAD+=" growth"
print -r -- "Task 4.4 does not start before the owner has read the list." >> "$WS/TASKS.md"
try_commit "$WS"; refused "gate: " || E_BAD+=" start-condition"
if [ -z "$E_BAD" ]; then pass e "the commit check refused a second new task, a sub-task of a sub-task, more than 20 added lines and an unsigned start condition"
else fail e "the commit check did not refuse:$E_BAD"; fi

# ---- (f) a task whose prerequisite is not done does not start
note ""; note "==== (f) a prerequisite that is not done"
print -r -- "
### 1.6 The saved list is read back [ ]  M: S medium, R: S medium
G1. Needs 1.2." >> "$WS/TASKS.md"
START="$( cd "$WS" && python3 "$BIN/runner_checks.py" start 1.6 2>&1 )"; RC=$?
note "runner_checks.py start 1.6 exit $RC: $START"
git -C "$WS" checkout -q -- TASKS.md
if [ $RC != 0 ] && print -r -- "$START" | grep -q "RUNNER CHECK: prerequisite: task 1.6 needs 1.2"; then pass f "a task whose prerequisite is not done is stopped before a session starts"
else fail f "the prerequisite check did not stop task 1.6 (exit $RC)"; fi

# ---- (g) a live write is not switched on while an open task says the user would see something false
note ""; note "==== (g) the live switch"
print -r -- '{"sync_enabled": true}' > "$APP/src/settings.json"
try_commit "$APP"
if refused "live switch: "; then pass g "the commit check refused a live switch while an open task says the user would see something false"
else fail g "the commit check did not refuse the live switch (git commit exit $RC)"; fi

# ---- (h) a commit that keeps every rule is accepted
note ""; note "==== (h) a clean commit under task 1.2: the function, and a call to it"
print -r -- 'def save_list(items):
    return len(items)' > "$APP/src/store.py"
python3 - "$APP/src/todo.py" <<'PY'
import sys
path = sys.argv[1]; text = open(path).read()
text = text.replace("import sys\n", "import sys\n\nfrom store import save_list\n", 1)
open(path, "w").write(text.rstrip("\n") + "\n    save_list(sys.argv[1:])\n")
PY
git -C "$APP" add -A
ACCEPT="$( cd "$APP" && RUNNER_TASK_ID=1.2 git commit -m "1.2: the list is counted on its way out" 2>&1 )"; RC=$?
note "git commit exit $RC: $ACCEPT"
if [ $RC = 0 ]; then pass h "the commit check accepted a commit that keeps every rule"
else fail h "the commit check refused a commit that keeps every rule: $(print -r -- "$ACCEPT" | grep -m1 'RUNNER CHECK')"; fi

# ---- (i) the stand-in session runs a task to done
note ""; note "==== (i) task 2.1 through run_task.sh with the stand-in session"
( cd "$WS" && "$BIN/run_task.sh" 2.1 2 ) >> "$OUT" 2>&1; RC=$?
if [ $RC = 0 ] && grep -m1 '^### 2\.1 ' "$WS/TASKS.md" | grep -q '\[x\]' && git -C "$APP" log -1 --format=%s | grep -q '^2\.1:'; then
  pass i "run_task.sh counted a task done on its commit and its [x], with no agent"
else fail i "run_task.sh did not finish task 2.1 with the stand-in session (exit $RC)"; fi

# ---- (j) a commit that breaks the project's check is sent back and repaired
note ""; note "==== (j) task 2.2: its first commit breaks the check"
( cd "$WS" && "$BIN/run_task.sh" 2.2 3 ) >> "$OUT" 2>&1; RC=$?
J_LOG="$(ls -t "$WS"/runs/2.2-*.log 2>/dev/null | head -1)"
if [ $RC = 0 ] && grep -q "fails on its commit" "$J_LOG" && grep -q "attempts:    2" "$J_LOG" && [ ! -e "$APP/src/BROKEN" ]; then
  pass j "a commit that broke the project's check was sent back to its session, and the task ended done only once the check passed"
else fail j "the project's check did not send task 2.2 back for repair (exit $RC)"; fi

# ---- (k) a check that already fails is reported once and does not stop the task
note ""; note "==== (k) task 2.3 with the check failing before it starts"
: > "$APP/src/BROKEN"; git -C "$APP" add -A && git -C "$APP" commit -q -m "a commit made outside the runner that breaks the check"
( cd "$WS" && "$BIN/run_task.sh" 2.3 2 ) >> "$OUT" 2>&1; RC=$?
sleep 1
if [ $RC = 0 ] && grep -q "check fails before task 2.3 starts" "$WS/runs/notify.log" && grep -q "task 2.3 done.*was not judged against it" "$WS/runs/notify.log"; then
  pass k "a check that already failed was reported to the owner, and the task ran and was marked as not judged against it"
else fail k "a failing check before task 2.3 was not handled (exit $RC)"; fi
git -C "$APP" rm -q src/BROKEN && git -C "$APP" commit -q -m "the check passes again"

# ---- (l) a stopped task is parked, and only the owner's answer releases it
note ""; note "==== (l) task 3.1: a question, a stop session, parking, release"
print -r -- "3.1" > "$T/order-l"
qpass() { ( cd "$WS" && QUEUE_ONCE=1 QUEUE_ORDER="$T/order-l" "$BIN/run_queue.sh" ) >> "$OUT" 2>&1; }
L_BAD=""
qpass
[ -f "$WS/runs/waiting/3.1" ] && grep -q "task 3.1 parked: SUPERVISOR: waiting 3.1" "$QLOG" || L_BAD+=" not-parked"
L_RUNS="$(grep -c "task 3.1: running" "$QLOG")"
print -r -- "- A note by a supervising session, not an answer (supervising session, $(date +%Y-%m-%d))" >> "$WS/DECISIONS.md"
qpass
[ "$(grep -c "task 3.1: running" "$QLOG")" = "$L_RUNS" ] && [ -f "$WS/runs/waiting/3.1" ] || L_BAD+=" released-by-a-supervising-entry"
print -r -- "- Notes are kept. (owner, $(date +%Y-%m-%d))" >> "$WS/DECISIONS.md"
qpass
grep -q "task 3.1: DECISIONS.md changed since it was parked" "$QLOG" && grep -m1 '^### 3\.1 ' "$WS/TASKS.md" | grep -q '\[x\]' || L_BAD+=" not-released-by-the-owner"
if [ -z "$L_BAD" ]; then pass l "a task that asked a question went to a stop session and was parked; a supervising entry did not release it and the owner's answer did"
else fail l "parking and release went wrong:$L_BAD"; fi

# ---- (m) three different tasks stopping in a row pause the queue
note ""; note "==== (m) tasks 4.1 to 4.3 stop; 4.4 waits behind the pause"
print -rl -- 4.1 4.2 4.3 4.4 > "$T/order-m"
( cd "$WS" && QUEUE_POLL=1 QUEUE_ORDER="$T/order-m" "$BIN/run_queue.sh" ) >> "$OUT" 2>&1 &
QPID=$!
M_BAD=""
wait_for "queue paused: 3 different tasks stopped one after another (4.1 4.2 4.3)" 60 || M_BAD+=" no-pause"
sleep 3
grep -q "task 4.4: running" "$QLOG" && M_BAD+=" ran-through-the-pause"
touch "$WS/runs/queue.go"
wait_for "task 4.4: run_task.sh exit 0" 60 || M_BAD+=" not-resumed"
touch "$WS/runs/queue.stop"
n=0; while kill -0 $QPID 2>/dev/null && [ $n -lt 150 ]; do sleep 0.2; n=$((n+1)); done
kill -0 $QPID 2>/dev/null && { kill $QPID; M_BAD+=" did-not-stop"; }
if [ -z "$M_BAD" ]; then pass m "three different tasks stopping one after another paused the queue and told the owner; it ran the next task only when told to go on"
else fail m "the pause after three stops went wrong:$M_BAD"; fi

# ---- (n) the configured notifier delivered a message
note ""; note "==== (n) notifier $NOTIFY_NAME"
wait; sleep 1
MSG="selftest message $$"
( cd "$WS" && "$BIN/runner-notify" "$MSG" ) >> "$OUT" 2>&1; RC=$?
LINE="$(grep -F "$MSG" "$WS/runs/notify.log" 2>/dev/null | tail -1)"
note "runner-notify exit $RC; log line: ${LINE:-none}"
note "notify.log:"; cat "$WS/runs/notify.log" >> "$OUT" 2>/dev/null
ROUTE="${${LINE#*\[}%%\]*}"
if [ $RC != 0 ] || [ -z "$LINE" ]; then
  fail n "the $NOTIFY_NAME notifier did not deliver the message (exit $RC)"
elif [[ "$ROUTE" == *failed* ]]; then
  fail n "the $NOTIFY_NAME notifier failed ($ROUTE)"
elif [ $AGENT = 1 ] && [ $SKIPPED = 0 ] && ! grep -q "task 1.1 done" "$WS/runs/notify.log"; then
  fail n "the runner's own done message for task 1.1 is not in runs/notify.log"
else
  pass n "the configured notifier delivered a message"
fi

if [ $FAILED = 1 ]; then print "SELFTEST: FAIL"; exit 1; fi
[ $KEEP = 1 ] || [ -n "$BASE" ] || rm -rf "$T"
if [ $SKIPPED = 1 ]; then print "SELFTEST: PARTIAL"; exit 2; fi
print "SELFTEST: PASS"; exit 0
