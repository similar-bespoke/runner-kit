#!/usr/bin/env zsh
# Run the tasks in a project's RUN-ORDER.md, unattended, one at a time, until
# told to stop. A task that stops goes to a supervising session, which decides
# engineering stops itself and parks product questions for the owner.
#
# Settings: the file named by RUNNER_CONF, or runner.conf in the current
# directory (see templates/runner.conf).
# Start (the owner, once, from the workspace directory):
#   tmux new -d -s <project>-runner <kit>/bin/run_queue.sh
# Stop (takes effect when the current task or supervising session ends):
#   touch runs/queue.stop
# Log: runs/queue.log
#
# Each pass re-reads RUN-ORDER.md and takes the first task that is in TASKS.md,
# not [x] and not waiting. A task waits while runs/waiting/<id> exists; its
# first line is a shasum of DECISIONS.md when it was parked, and it is tried
# again once that hash changes (the owner answers by appending to DECISIONS.md). The
# hash is taken over the entries only (not headings or blank lines), leaves out
# any entry signed "(supervising session, <date>)", and is taken before the
# stop session starts, so one supervising session's decision does not release
# every parked task and an answer written while a stop session runs is not
# lost. A task whose prerequisite is parked is parked with it, with no session. A task
# with no M column, or built at [~] with R: owner, is parked at once. Any exit
# of run_task.sh but 0 starts a supervising session (SUPERVISOR-PROMPT.md, on
# the adapter and model of the letter named by SUPERVISOR in runner.conf) and
# acts on its last line, SUPERVISOR: retry | run <ids> then <id> | waiting <id>
# <sentence> | skip <id> <why>. A task gets two supervising rounds
# (runs/<id>.rounds, cleared when it is done); its third stop parks it for the
# owner.
#
# When STOP_STREAK different tasks stop one after another (3 unless runner.conf
# says otherwise; 0 switches this off), a cause they share is likelier than
# that many separate faults, so the queue pauses and tells the owner once. It
# starts again when TASKS.md, RUN-ORDER.md, DECISIONS.md, either prompt or
# runner.conf changes, or on `touch runs/queue.go`.
#
# Test switches (no model call, no notice): QUEUE_DRY=1 logs what would run,
# QUEUE_ONCE=1 does one pass and exits, QUEUE_ORDER and QUEUE_RUNS point at
# another queue file and runs directory, QUEUE_POLL is the seconds between
# looks while idle or paused (15). Sourcing this file defines the
# functions without running the loop.
set -u
BIN="${0:A:h}"; KIT="${BIN:h}"
CONF="${RUNNER_CONF:-$PWD/runner.conf}"
[ -f "$CONF" ] || { echo "no settings file: set RUNNER_CONF or start from the directory that holds runner.conf" >&2; exit 2; }
export RUNNER_CONF="${CONF:A}"; source "$RUNNER_CONF"
DIR="${WORKSPACE:A}"; REPO_LIST=(${=REPOS})
TASKS="$DIR/TASKS.md"; DECISIONS="$DIR/DECISIONS.md"
ORDER="${QUEUE_ORDER:-$DIR/RUN-ORDER.md}"
RUNS="${QUEUE_RUNS:-$DIR/runs}"; WAITING="$RUNS/waiting"
QLOG="$RUNS/queue.log"; STOPFILE="$RUNS/queue.stop"; LOCK="$RUNS/queue.lock"
DRY="${QUEUE_DRY:-0}"; ONCE="${QUEUE_ONCE:-0}"; POLL="${QUEUE_POLL:-15}"
GOFILE="$RUNS/queue.go"
mkdir -p "$RUNS" "$WAITING"

log() {
  local line="$(date '+%Y-%m-%d %H:%M:%S') $*"
  print -r -- "$line"; print -r -- "$line" >> "$QLOG"
}

# A short message to the owner, best effort, through the notifier named by
# NOTIFY in runner.conf (bin/runner-notify). The message is always in the log.
notify() {
  local text="$1"
  log "notify: $text"
  [ "$DRY" = 1 ] && return 0
  ( "$BIN/runner-notify" "$text" >/dev/null 2>&1 || log "(notify failed)" ) &!
}

sha() { if command -v shasum >/dev/null; then shasum; else sha1sum; fi; }

decisions_hash() {
  python3 - "$DECISIONS" <<'PY' | sha | cut -d' ' -f1
import re, sys
out, block = [], []
def flush():
    text = " ".join(" ".join(block).split())
    if text and not text.startswith("#") and not re.search(r"(?i)\((?:supervising|stop) session, [^()]*\)", text):
        out.append(text)
    block.clear()
for line in open(sys.argv[1]):
    if line.startswith(("- ", "#")) or not line.strip(): flush()
    block.append(line)
flush()
sys.stdout.write("\n".join(out))
PY
}
heading() { grep -m1 "^### ${1//./\\.} " "$TASKS"; }

# Park a task for the owner: the waiting file holds the DECISIONS.md hash, then why.
park() {
  local id="$1" why="$2" hash="${3:-}"
  { print -r -- "${hash:-$(decisions_hash)}"; print -r -- "$why"; } > "$WAITING/$id"
  log "task $id parked: $why"
}

# Insert ids into the queue file immediately before the line naming <target>,
# skipping ids already in the queue. If <target> is not in it, the new ids and
# <target> are appended at the end.
insert_before() {
  local file="$1" target="$2"; shift 2
  local -a present new words
  local line id placed=0
  while IFS= read -r line || [ -n "$line" ]; do
    words=(${=line}); [ ${#words} -gt 0 ] || continue
    [[ "${words[1]}" == \#* ]] && continue
    present+=("${words[1]}")
  done < "$file"
  for id in "$@"; do
    (( ${present[(Ie)$id]} || ${new[(Ie)$id]} )) || [ "$id" = "$target" ] || new+=("$id")
  done
  [ ${#new} -gt 0 ] || { log "queue: ${*} already in $(basename "$file")"; return 0; }
  local tmp="$file.tmp.$$"
  {
    while IFS= read -r line || [ -n "$line" ]; do
      words=(${=line})
      if [ $placed = 0 ] && [ ${#words} -gt 0 ] && [ "${words[1]}" = "$target" ]; then
        print -rl -- "${new[@]}"; placed=1
      fi
      print -r -- "$line"
    done < "$file"
    [ $placed = 1 ] || print -rl -- "${new[@]}" "$target"
  } > "$tmp" && mv "$tmp" "$file"
  log "queue: inserted ${new[*]} before $target"
}

# Start one stop session through the adapter of the SUPERVISOR letter and
# leave its last SUPERVISOR: line in SUPERVISE_VERDICT.
supervise() {
  local id="$1" stop="$2" tasklog="$3"
  local stamp="$(date +%Y%m%d-%H%M%S)" uuid prompt raw r repos="" letter var adapter model
  local -a dirs
  SUPERVISE_VERDICT=""
  letter="${SUPERVISOR:-O}"
  var="ADAPTER_$letter"; adapter="${(P)var:-}"; var="MODEL_$letter"; model="${(P)var:-}"
  if [ -z "$adapter" ] || [ -z "$model" ] || [ ! -f "$KIT/adapters/$adapter.sh" ]; then
    log "no stop session: runner.conf needs ADAPTER_$letter and MODEL_$letter (SUPERVISOR=$letter)"; return 0
  fi
  uuid="$(python3 -c 'import uuid;print(uuid.uuid4())')"
  raw="$RUNS/supervise-$id-$stamp.jsonl"
  dirs=("$DIR")
  for r in "${REPO_LIST[@]}"; do repos+="${repos:+ and }\`${r:A}\`"; dirs+=("${r:A}"); done
  prompt="$(awk 'f{print} /^---$/{f=1}' "$DIR/SUPERVISOR-PROMPT.md")"
  prompt="${prompt//'<ID>'/$id}"; prompt="${prompt//'<STOP>'/$stop}"; prompt="${prompt//'<LOG>'/$tasklog}"
  prompt="${prompt//'<PROJECT>'/$PROJECT}"; prompt="${prompt//'<WORKSPACE>'/$DIR}"
  prompt="${prompt//'<REPOS>'/$repos}"; prompt="${prompt//'<RUNNER>'/$BIN}"
  log "supervising session $uuid for task $id; raw $raw"
  if [ "$DRY" = 1 ]; then log "(dry: no session started)"; : > "$raw"; return 0; fi
  ( cd "$DIR" && export RUNNER_TASK_ID="$id" && source "$KIT/adapters/$adapter.sh" \
      && A_PROMPT="$prompt" && A_MODEL="$model" && A_EFFORT=medium && A_TASK_ID="$id" && A_DIRS=("${dirs[@]}") \
      && { [ "${AGENT_PRESET_SESSION:-0}" = 1 ] && A_SESSION="$uuid" || A_SESSION=""; } \
      && adapter_start 2>&1 ) \
    | tee "$raw" | python3 -u "$BIN/render_stream.py" | tee -a "$QLOG"
  SUPERVISE_VERDICT="$( source "$KIT/adapters/$adapter.sh"; adapter_read_result "$raw" SUPERVISOR; print -r -- "$RESULT_VERDICT" )"
}

# A task stopped with a non-zero exit: hand it to a supervising session, or
# park it when its rounds are used, and act on the verdict.
handle_stop() {
  local id="$1" rc="$2" stop rounds tasklog verdict kind
  local -a w logs ids
  if [ -s "$RUNS/$id.stop" ]; then stop="$(head -1 "$RUNS/$id.stop")"; else stop="RUNNER: blocked run_task.sh exit $rc"; fi
  log "task $id stopped (exit $rc): $stop"
  if heading "$id" | grep -q '\[~\]' && heading "$id" | grep -q 'R: owner'; then
    park "$id" "built, waits for the owner's yes at [~]"; return 0   # run_task.sh has already told the owner
  fi
  LAST_STOP="$id"
  rounds="$(cat "$RUNS/$id.rounds" 2>/dev/null || echo 0)"
  if [ "$rounds" -ge 2 ]; then
    park "$id" "third stop after two supervising rounds: $stop"
    notify "$PROJECT queue: task $id stopped a third time and is parked for you. $stop"
    return 0
  fi
  print $((rounds+1)) > "$RUNS/$id.rounds"
  logs=("$RUNS"/$id-*.log(Nom)); tasklog="${logs[1]:-(no log)}"
  local before="$(decisions_hash)"   # an answer written while the stop session runs must still release the task
  supervise "$id" "$stop" "$tasklog"
  verdict="$SUPERVISE_VERDICT"
  log "verdict: ${verdict:-(none)}"
  w=(${=verdict}); kind="${w[2]:-}"
  case "$kind" in
    retry) rm -f "$RUNS/$id.stop";;
    run)
      ids=(); local i=3
      while [ $i -le ${#w} ] && [ "${w[$i]}" != then ]; do ids+=("${w[$i]}"); i=$((i+1)); done
      if [ $i -lt ${#w} ] && [ ${#ids} -gt 0 ]; then
        insert_before "$ORDER" "${w[$((i+1))]}" "${ids[@]}"; rm -f "$RUNS/$id.stop"
      else
        park "$id" "supervisor verdict unreadable: $verdict"
        notify "$PROJECT queue: task $id parked; its supervising session gave an unreadable verdict: $verdict"
      fi;;
    waiting)
      park "$id" "$verdict" "$before"
      notify "$PROJECT queue: task $id waits for you. ${w[4,-1]}";;
    skip) park "$id" "$verdict" "$before";;
    *)
      park "$id" "no supervisor verdict: $stop" "$before"
      notify "$PROJECT queue: task $id stopped and its supervising session gave no verdict; parked for you. $stop";;
  esac
}

# One pass over the queue. Returns 0 if a task ran, 1 if nothing was runnable.
typeset -A SEEN
WAITING_IDS=()
LAST_STOP=""     # the task one_pass ran, if it stopped; empty if it finished or nothing ran
SETUP_FAULT=""   # why run_task.sh could not start a task (exit 2), if it could not
one_pass() {
  local line id head hash why need
  local -a words
  WAITING_IDS=(); LAST_STOP=""; SETUP_FAULT=""
  [ -f "$ORDER" ] || { log "no queue file at $ORDER"; return 1; }
  local -a queue=()
  while IFS= read -r line || [ -n "$line" ]; do
    words=(${=line}); [ ${#words} -gt 0 ] || continue
    [[ "${words[1]}" == \#* ]] && continue
    queue+=("${words[1]}")
  done < "$ORDER"
  for id in "${queue[@]}"; do
    head="$(heading "$id")" || head=""
    if [ -z "$head" ]; then
      [ -n "${SEEN[missing:$id]:-}" ] || { log "task $id is in the queue but not in TASKS.md; skipping"; SEEN[missing:$id]=1; }
      continue
    fi
    case "$head" in *"[x]"*)
      [ -n "${SEEN[done:$id]:-}" ] || { log "task $id already done; skipping"; SEEN[done:$id]=1; }
      rm -f "$WAITING/$id"
      continue;;
    esac
    if [ -f "$WAITING/$id" ]; then
      hash="$(head -1 "$WAITING/$id")"
      if [ "$hash" = "$(decisions_hash)" ]; then WAITING_IDS+=("$id"); continue; fi
      why="$(sed -n 2p "$WAITING/$id")"; rm -f "$WAITING/$id"
      log "task $id: DECISIONS.md changed since it was parked; trying it again"
    else
      why=""
    fi
    if ! print -r -- "$head" | grep -q 'M: [A-Z] '; then
      park "$id" "the owner's task (no M column)"; WAITING_IDS+=("$id")
      [ "$why" = "the owner's task (no M column)" ] || notify "$PROJECT queue: task $id is yours and is parked. $head"
      continue
    fi
    if print -r -- "$head" | grep -q '\[~\]' && print -r -- "$head" | grep -q 'R: owner'; then
      park "$id" "built, waits for the owner's yes at [~]"; WAITING_IDS+=("$id")
      [ "$why" = "built, waits for the owner's yes at [~]" ] || notify "$PROJECT queue: task $id is built and waits for your yes; parked. $head"
      continue
    fi
    need="$(python3 "$BIN/runner_checks.py" start "$id" 2>/dev/null | sed -n 's/.*: task [^ ]* needs \([^, ]*\), which is not done.*/\1/p' | head -1)"
    if [ -n "$need" ] && [ -f "$WAITING/$need" ]; then
      park "$id" "needs $need, which waits"; WAITING_IDS+=("$id")
      continue
    fi
    log "task $id: running run_task.sh $id"
    if [ "$DRY" = 1 ]; then log "(dry: would run task $id)"; return 0; fi
    rm -f "$RUNS/$id.stop"
    local rc=0
    "$BIN/run_task.sh" "$id" 2>"$RUNS/$id.err" || rc=$?
    [ -s "$RUNS/$id.err" ] && cat "$RUNS/$id.err" >&2
    log "task $id: run_task.sh exit $rc"
    if [ $rc = 0 ]; then rm -f "$RUNS/$id.rounds" "$RUNS/$id.stop"
    elif [ $rc = 2 ]; then
      # run_task.sh could not start the task: a setting, a missing command, a
      # missing file. No session can put that right, so none is started.
      SETUP_FAULT="task $id could not be started: $(tail -1 "$RUNS/$id.err" 2>/dev/null)"
      log "$SETUP_FAULT"
    else handle_stop "$id" "$rc"; fi
    return 0
  done
  return 1
}

# The files a person or a supervising session changes to put a shared fault right.
workspace_hash() {
  cat "$TASKS" "$ORDER" "$DECISIONS" "$DIR/SESSION-PROMPT.md" "$DIR/SUPERVISOR-PROMPT.md" "$RUNNER_CONF" 2>/dev/null | sha | cut -d' ' -f1
}

# Pause: tell the owner once why, and wait for a change to the workspace, the go
# file or the stop file.
pause() {
  local before="$(workspace_hash)"
  notify "$PROJECT queue paused: $1 The queue starts again when TASKS.md, RUN-ORDER.md, DECISIONS.md, a prompt or runner.conf changes, or on: touch $GOFILE"
  while [ ! -f "$STOPFILE" ] && [ ! -f "$GOFILE" ] && [ "$(workspace_hash)" = "$before" ]; do sleep "$POLL"; done
  rm -f "$GOFILE"
  [ -f "$STOPFILE" ] || log "queue resumed after its pause"
}

main() {
  if ! mkdir "$LOCK" 2>/dev/null; then
    local pid="$(cat "$LOCK/pid" 2>/dev/null)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      echo "run_queue.sh is already running (pid $pid); not starting a second copy." >&2; exit 2
    fi
    rm -rf "$LOCK"; mkdir "$LOCK" || { echo "cannot take the lock $LOCK" >&2; exit 2; }
  fi
  print $$ > "$LOCK/pid"
  trap 'rm -rf "$LOCK"' EXIT
  trap 'rm -rf "$LOCK"; exit 130' INT TERM HUP
  [ -f "$STOPFILE" ] && { rm -f "$STOPFILE"; log "removed an old stop file"; }
  log "queue started (pid $$), queue file $ORDER"
  local idle_sent=0 n limit="${STOP_STREAK:-3}"
  local -aU streak=()
  rm -f "$GOFILE"
  while [ ! -f "$STOPFILE" ]; do
    if one_pass; then
      idle_sent=0
      if [ -n "$LAST_STOP" ]; then streak+=("$LAST_STOP"); elif [ "$DRY" != 1 ]; then streak=(); fi
      if [ "$limit" -gt 0 ] && [ ${#streak} -ge "$limit" ] && [ "$ONCE" != 1 ]; then
        pause "${#streak} different tasks stopped one after another (${streak[*]}). A cause they share is likelier than ${#streak} separate faults: look at SESSION-PROMPT.md, the model, the project's check and this machine."; streak=()
      fi
      if [ -n "$SETUP_FAULT" ] && [ "$ONCE" != 1 ]; then pause "$SETUP_FAULT"; streak=(); fi
    else
      if [ $idle_sent = 0 ]; then
        notify "$PROJECT queue idle. Waiting: ${WAITING_IDS[*]:-none}."
        idle_sent=1
      fi
      [ "$ONCE" = 1 ] && break
      n=0; while [ $n -lt 20 ] && [ ! -f "$STOPFILE" ]; do sleep "$POLL"; n=$((n+1)); done
      continue
    fi
    [ "$ONCE" = 1 ] && break
  done
  [ -f "$STOPFILE" ] && log "stop file found; queue stopped" || log "queue pass done (once)"
}

[[ "$ZSH_EVAL_CONTEXT" == toplevel ]] && main
