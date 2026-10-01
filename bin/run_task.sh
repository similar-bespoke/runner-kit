#!/usr/bin/env zsh
# Run one task from a project's TASKS.md in fresh, non-interactive agent
# sessions, retrying and resuming on its own until the task's commit lands or
# a failure needs a person.
#
# Usage: run_task.sh <task-id> [max-attempts]   (default 4)
# Settings: the file named by RUNNER_CONF, or runner.conf in the current
# directory (see templates/runner.conf).
#
# The task file is the orchestrator. This script never does any of the work.
# It starts a session with the task's model and effort, shows every step live,
# and afterwards checks that a commit for the task landed and the task is
# marked done. If not, it works out why and acts:
#   - expired sign-in, no credential: stop at once with the one command to run
#   - API error, overload, rate limit, network: wait, then resume the session
#   - session ended without committing: resume it with a firm instruction
#   - session says the task cannot be done as written: stop, that is a decision
# Exit codes, which run_queue.sh acts on:
#   0 done   1 attempts exhausted   2 usage or setup   3 needs the owner
#   (sign-in, the owner's review, held at [~])   4 the session says blocked or
#   asks a question   5 the session split the task
# Every session ends with one line `RUNNER: done <commit>` | `RUNNER: blocked
# <why>` | `RUNNER: question <for the owner>`; a blocked or question line stops
# this script at once, with no further attempt, and the reason is written to
# runs/<id>.stop for the supervising session.
# Each task has one session id (runs/<id>.session); edits live in the working
# tree and survive a crash; a resume continues with full context.
# Everything that differs between agents is in adapters/<name>.sh. The letter
# in the task's M column picks the adapter (ADAPTER_<letter>) and the model
# (MODEL_<letter>) from runner.conf.
set -u
ID="${1:-}"; [ -n "$ID" ] || { echo "usage: run_task.sh <task-id> [max-attempts]" >&2; exit 2; }
MAX="${2:-4}"
BIN="${0:A:h}"; KIT="${BIN:h}"
CONF="${RUNNER_CONF:-$PWD/runner.conf}"
[ -f "$CONF" ] || { echo "no settings file: set RUNNER_CONF or start from the directory that holds runner.conf" >&2; exit 2; }
export RUNNER_CONF="${CONF:A}"; source "$RUNNER_CONF"
export RUNNER_TASK_ID="$ID"   # the git pre-commit hooks run runner_checks.py for this task
DIR="${WORKSPACE:A}"; REPO_LIST=(${=REPOS}); REPO="${REPO_LIST[1]:A}"
TASKS="$DIR/TASKS.md"; PROMPT_FILE="$DIR/SESSION-PROMPT.md"
RUNS="$DIR/runs"; mkdir -p "$RUNS"
STATE="$RUNS/$ID.session"
say() { echo "$@" | tee -a "$LOG"; }

# A short message to the owner, best effort, through the notifier named by
# NOTIFY in runner.conf (bin/runner-notify). It never blocks the runner and
# never fails it.
notify() {
  local text="$1"
  ( "$BIN/runner-notify" "$text" >/dev/null 2>&1 || echo "(notify failed; message was: $text)" ) &
}
remaining() {
  local all model
  all="$(grep -c '^### .*\[ \]' "$TASKS")"; model="$(grep '^### .*\[ \]' "$TASKS" | grep -c 'M: [A-Z] ')"
  echo "$all tasks remain ($model for sessions, $((all-model)) for the owner)"
}

# ---- task line -> adapter, model and effort
HEADING="$(grep -m1 "^### $ID " "$TASKS")" || { echo "task $ID not in TASKS.md" >&2; exit 2; }
case "$HEADING" in *"[x]"*) echo "task $ID is already marked done"; exit 0;; esac
MCOL="$(echo "$HEADING" | sed -n 's/.*M: \([A-Z]\) \([a-z]*\).*/\1 \2/p')"
[ -n "$MCOL" ] || { echo "task $ID has no M column: it is the owner's, not a session's" >&2; exit 3; }
LETTER="${MCOL%% *}"; EFFORT="${MCOL##* }"
VAR="MODEL_$LETTER"; MODEL="${(P)VAR:-}"
VAR="ADAPTER_$LETTER"; ADAPTER="${(P)VAR:-}"
[ -n "$ADAPTER" ] || { echo "STOP: runner.conf has no adapter for the letter $LETTER (ADAPTER_$LETTER)" >&2; exit 2; }
[ -n "$MODEL" ] || { echo "STOP: runner.conf has no model id for the letter $LETTER (MODEL_$LETTER)" >&2; exit 2; }
[ -f "$KIT/adapters/$ADAPTER.sh" ] || { echo "STOP: no adapter file $KIT/adapters/$ADAPTER.sh (ADAPTER_$LETTER=$ADAPTER)" >&2; exit 2; }
REFFORT="$(echo "$HEADING" | sed -n 's/.*R: [A-Z] \([a-z]*\).*/\1/p')"; REFFORT="${REFFORT:-high}"

# ---- pre-flight: fail in seconds, not minutes
source "$KIT/adapters/$ADAPTER.sh"
AGENT="$AGENT_NAME"; LOGIN_CMD="$AGENT_LOGIN_CMD"
command -v "$AGENT_BIN" >/dev/null || { echo "STOP: the $AGENT_BIN command is not installed." >&2; exit 2; }
if (( $+functions[adapter_preflight] )); then adapter_preflight || exit 2; fi
if ! adapter_signed_in; then
  echo "not signed in to $AGENT. Run:  $LOGIN_CMD   (this script waits and checks every ten minutes)." >&2
  LOG=/dev/null; notify "$PROJECT runner: this machine is not signed in to $AGENT. Run '$LOGIN_CMD' there; the runner waits."; wait
  while ! adapter_signed_in; do sleep 600; done
fi
# A task's commit may land in a code repository or in the repository that
# holds the workspace (TASKS.md lives there), so all are checked.
WSREPO="$(git -C "$DIR" rev-parse --show-toplevel 2>/dev/null)" || { echo "STOP: the workspace $DIR is not inside a git repository" >&2; exit 2; }
typeset -A BASE; ALL=()
for r in "${REPO_LIST[@]}" "$WSREPO"; do
  r="${r:A}"
  git -C "$r" rev-parse --git-dir >/dev/null 2>&1 || { echo "STOP: repo not found at $r" >&2; exit 3; }
  (( ${ALL[(Ie)$r]} )) || { ALL+=("$r"); BASE[$r]="$(git -C "$r" rev-parse HEAD)"; }
done
if [ -n "${PREFLIGHT_CMD:-}" ]; then
  ${=PREFLIGHT_CMD} >/dev/null 2>&1 || echo "warning: the pre-flight command failed: $PREFLIGHT_CMD"
fi

LOG="$RUNS/$ID-$(date +%Y%m%d-%H%M%S).log"
say "task $ID  builder=$AGENT model=$MODEL effort=$EFFORT  max attempts=$MAX  repo HEAD ${BASE[$REPO]}"
say "log $LOG"

# ---- runner checks before a first session: a task whose named prerequisite
# is not done does not start; the supervising session runs the prerequisite
# first.
if [ ! -f "$STATE" ] && ! CHECK="$(python3 "$BIN/runner_checks.py" start "$ID")"; then
  printf 'RUNNER: blocked %s\n' "$(echo "$CHECK" | tr '\n' ' ')" > "$RUNS/$ID.stop"
  say ""; say "STOP: $CHECK"
  notify "$PROJECT runner: task $ID not started. $CHECK"
  wait; exit 4
fi

check_done() {
  local r
  COMMIT="$( for r in "${ALL[@]}"; do git -C "$r" log --format='%h %s' "${BASE[$r]}..HEAD"; done | grep -m1 "^[0-9a-f]* ${ID}[ :]" || true)"
  MARKED="$(grep -m1 "^### $ID " "$TASKS" | grep -c '\[x\]' || true)"
  DIRTY="$( for r in "${REPO_LIST[@]}"; do git -C "$r" status --short | grep -v '^??'; done | wc -l | tr -d ' ')"
  [ -n "$COMMIT" ] && [ "$MARKED" = 1 ]
}

# The first message of a new session: SESSION-PROMPT.md below its --- line,
# with the reviewer step for this adapter and the settings filled in.
session_prompt() {
  local p review repos="" r
  for r in "${ALL[@]}"; do repos+="${repos:+ and }\`$r\`"; done
  p="$(awk 'f{print} /^---$/{f=1}' "$PROMPT_FILE")"
  review="$(cat "$DIR/REVIEW-${(U)ADAPTER}.md")"
  p="${p//'<REVIEW>'/$review}"
  p="${p//'<ID>'/$ID}"; p="${p//'<PROJECT>'/$PROJECT}"; p="${p//'<WORKSPACE>'/$DIR}"
  p="${p//'<REPOS>'/$repos}"; p="${p//'<RUNNER>'/$BIN}"
  p="${p//'<MODEL>'/$MODEL}"; p="${p//'<REFFORT>'/$REFFORT}"
  print -r -- "$p"
}

# start_session runs one session through the adapter (new when RESUME=0, the
# saved one when RESUME=1) in the first repository, writes its raw event stream
# to $RAW and its exit code to $STATUS, reads the session's result, and leaves
# the session id in $STATE.
start_session() {
  local EXITF="$RUNS/$ID.exit" op=adapter_start; rm -f "$EXITF"
  A_PROMPT="$PROMPT"; A_MODEL="$MODEL"; A_EFFORT="$EFFORT"; A_SESSION="$SESSION"; A_TASK_ID="$ID"
  A_DIRS=("$DIR" "${ALL[@]}")
  if [ "$RESUME" = 1 ]; then op=adapter_resume
  elif [ "${AGENT_PRESET_SESSION:-0}" = 1 ]; then echo "$SESSION" > "$STATE"; fi
  ( cd "$REPO" && $op 2>&1; echo $? > "$EXITF" ) \
    | tee "$RAW" | python3 -u "$BIN/render_stream.py" | tee -a "$LOG"
  STATUS="$(cat "$EXITF" 2>/dev/null || echo 1)"; rm -f "$EXITF"
  adapter_read_result "$RAW" RUNNER
  if [ ! -f "$STATE" ] && [ -n "${RESULT_SESSION:-}" ]; then   # the agent named the session itself
    SESSION="$RESULT_SESSION"; echo "$SESSION" > "$STATE"
  fi
}

attempt=0; backoff=60
while [ $attempt -lt $MAX ]; do
  attempt=$((attempt+1))
  RAW="$RUNS/$ID-$(date +%Y%m%d-%H%M%S)-a$attempt.jsonl"
  if [ -f "$STATE" ]; then
    SESSION="$(cat "$STATE")"; RESUME=1
    PROMPT="Resume task $ID. The previous session on this task stopped before its commit landed. First run git status and git diff in $REPO to see what is already done, re-read task $ID in $DIR/TASKS.md, then continue from where the work stopped. Do not redo finished work. Finish the done-when check, the review, the commit with the task id first in the subject, and mark the task done in TASKS.md. All rules of the original session prompt still apply."
    say ""; say "attempt $attempt of $MAX: resuming session $SESSION"
  else
    RESUME=0; SESSION=""
    [ "${AGENT_PRESET_SESSION:-0}" = 1 ] && SESSION="$(python3 -c 'import uuid;print(uuid.uuid4())')"
    PROMPT="$(session_prompt)"
    say ""; say "attempt $attempt of $MAX: new session $SESSION"
  fi
  say "raw $RAW"

  start_session
  say "--- session exit $STATUS"

  # A session may close a task as "split" in TASKS.md with no commit: that is
  # a stop for a restart on the new ids, not a resume.
  if grep -m1 "^### $ID " "$TASKS" | grep -qi '\[x\].*split'; then
    say ""; say "STOP: task $ID was split by its session (see TASKS.md); start the new ids."
    notify "$PROJECT runner stopped: task $ID split by its session into new ids; see TASKS.md. $(remaining)."
    wait; exit 5
  fi
  if check_done; then
    # The hooks refuse a commit that breaks DELIVERY-RULES.yaml; this catches
    # one made with --no-verify. The task stays done; the supervisor decides.
    CHECK="$(for r in "${ALL[@]}"; do python3 "$BIN/runner_checks.py" commits "$ID" "$r" "${BASE[$r]}"; done)"
    if [ -n "$CHECK" ]; then
      printf 'RUNNER: blocked runner checks failed on the task commit: %s\n' "$(echo "$CHECK" | tr '\n' ' ' | cut -c1-600)" > "$RUNS/$ID.stop"
      say ""; say "STOP: $CHECK"
      notify "$PROJECT runner stopped on task $ID: its commit breaks a runner check. $(remaining)."
      wait; exit 4
    fi
    rm -f "$STATE"
    say ""; say "result for task $ID: OK"
    say "  commit:      $COMMIT"; say "  attempts:    $attempt"; say "  marked done: yes"
    # Progress the owner can open: how much built work is not live yet, and the
    # one command that puts it live. Only for a project whose workspace has a
    # deploy.sh.
    PENDING=""
    if [ -f "$DIR/deploy.sh" ]; then
      PENDING=" Live commit unknown: run deploy.sh check."
      if [ -f "$RUNS/live-sha" ]; then
        N="$(git -C "$REPO" rev-list --count "$(cat "$RUNS/live-sha")..HEAD" -- ${=PRODUCT_DIRS:-.} 2>/dev/null || echo 0)"
        PENDING=""; [ "${N:-0}" -gt 0 ] && PENDING=" $N built change(s) are not live; to open them: deploy.sh $(git -C "$REPO" rev-parse --short HEAD)."
        [ "${N:-0}" -ge 10 ] && PENDING=" DEPLOY NEEDED.$PENDING"
      fi
    fi
    say "  not live:   ${PENDING:- nothing}"
    notify "$PROJECT task $ID done: $COMMIT ($attempt attempt$([ $attempt = 1 ] || echo s)). $(remaining).$PENDING"
    wait; exit 0
  fi

  # A task whose reviewer is the owner stops at [~] once its commit is in: the
  # [x] is the owner's to add after reading the work, not a session's. Any
  # other task that commits and leaves [~] has built the thing and found it
  # does not ship as written: stop and say so, do not resume.
  if [ -n "$COMMIT" ] && grep -m1 "^### $ID " "$TASKS" | grep -q '\[~\]'; then
    if echo "$HEADING" | grep -q "R: owner"; then
      say ""; say "STOP: task $ID is built ($COMMIT) and waits for the owner's yes. The owner marks it [x]."
      notify "$PROJECT task $ID built: $COMMIT. It waits for your yes before it counts as done. $(remaining)."
    else
      say ""; say "STOP: task $ID is built ($COMMIT) but the session left it [~]: built, does not ship as written. Read its Done line in TASKS.md."
      notify "$PROJECT task $ID built but held at [~]: $COMMIT. Does not ship as written; see TASKS.md. $(remaining)."
    fi
    wait; exit 3
  fi

  # ---- classify the failure from the session's own result (adapter_read_result)
  if [ "$RESULT_KIND" = auth ]; then
    say "STOP: authentication failed. Run:  $LOGIN_CMD   then run this again (the session resumes)."
    notify "$PROJECT runner stopped on task $ID: $AGENT sign-in expired. Run '$LOGIN_CMD' on this machine, then run the task again."
    wait; exit 3
  fi
  # The session's own verdict line. A blocked or question verdict never succeeds
  # on a resume: stop now, write the reason, hand it to the supervising session.
  VERDICT="$RESULT_VERDICT"
  case "$VERDICT" in
    RUNNER:*blocked*|RUNNER:*question*)
      printf '%s\n' "$VERDICT" > "$RUNS/$ID.stop"
      say ""; say "STOP: $VERDICT"
      notify "$PROJECT runner stopped on task $ID. $VERDICT $(remaining)."
      wait; exit 4;;
  esac
  # No progress twice running (no commit, no changed files, same exit): a third
  # resume would do the same. Stop instead of burning the remaining attempts.
  if [ "$DIRTY" = 0 ] && [ -z "$COMMIT" ] && [ "$RESULT_KIND" != transient ]; then
    NOPROG=$((${NOPROG:-0}+1))
    if [ $NOPROG -ge 2 ]; then
      printf 'RUNNER: blocked the session ended twice with no commit and no changed files; its last words: %s\n' "$(echo "$RESULT_TEXT" | tr '\n' ' ' | cut -c1-400)" > "$RUNS/$ID.stop"
      say ""; say "STOP: task $ID made no progress on two attempts running. $(cat "$RUNS/$ID.stop")"
      notify "$PROJECT runner stopped on task $ID: two attempts with no progress. $(remaining)."
      wait; exit 4
    fi
  else
    NOPROG=0
  fi
  if echo "$RESULT_TEXT" | grep -qiE "cannot be done|can't be done|could not be done|was not done|cannot do task $ID|proposed a split|split (it )?(in|into) .?TASKS\.md|split it in|did not build( task)? $ID|is a question for the owner|no answer in DECISIONS|has no answer|stopped rather than|stopped at the Files line"; then
    printf 'RUNNER: blocked (inferred from prose) %s\n' "$(echo "$RESULT_TEXT" | tr '\n' ' ' | cut -c1-500)" > "$RUNS/$ID.stop"
    say "STOP: the session says task $ID cannot be done as written. Its reason is above and in TASKS.md."
    notify "$PROJECT runner stopped on task $ID: the session says it cannot be done as written. $(remaining)."
    wait; exit 4
  fi
  # A plan usage limit names its reset time ("session limit · resets 4:20am").
  # Sleep until then plus five minutes; the wait is not an attempt.
  if echo "$RESULT_TEXT" | grep -qi "limit.*resets"; then
    WAIT="$(python3 - "$RESULT_TEXT" <<'PY2'
import re, sys, datetime
m = re.search(r"resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)", sys.argv[1], re.I)
if not m:
    print(3600); sys.exit()
h, mi, ap = int(m.group(1)) % 12, int(m.group(2) or 0), m.group(3).lower()
h += 12 if ap == "pm" else 0
now = datetime.datetime.now()
at = now.replace(hour=h, minute=mi, second=0, microsecond=0)
if at <= now:
    at += datetime.timedelta(days=1)
print(int((at - now).total_seconds()) + 300)
PY2
)"
    say "usage limit reached; sleeping ${WAIT}s until it resets (not an attempt)."
    notify "$PROJECT runner on task $ID: $AGENT usage limit reached; it resumes by itself after the reset."
    sleep "$WAIT"; attempt=$((attempt-1)); continue
  fi
  if [ "$RESULT_KIND" = transient ]; then
    say "transient failure ($RESULT_REASON). Waiting ${backoff}s, then resuming."
    sleep $backoff; backoff=$((backoff*2)); continue
  fi
  say "session ended without the task's commit (exit $STATUS, uncommitted changed files: $DIRTY). Resuming."
  sleep 5
done

printf 'RUNNER: blocked %s attempts used without the commit landing; last words: %s\n' "$MAX" "$(echo "${RESULT_TEXT:-}" | tr '\n' ' ' | cut -c1-400)" > "$RUNS/$ID.stop"
say ""; say "STOP: task $ID not completed after $MAX attempts. Session $SESSION is kept; run again to resume, or read the logs in $RUNS."
notify "$PROJECT runner stopped on task $ID after $MAX attempts. Work is kept; run the task again to resume. Log: $(basename "$LOG")."
wait; exit 1
