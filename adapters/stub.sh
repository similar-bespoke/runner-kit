# Adapter: no agent. For the kit's self-test, and for trying the runner's own
# logic (done test, the project's check, stop sessions, parking, the pause)
# without spending anything. Sourced by bin/run_task.sh and bin/run_queue.sh;
# never run by itself. The contract is in TEMPLATE.sh.
#
# A "session" is one run of the zsh script named by STUB_SCRIPT, which must be
# in the environment. The script receives the task id as its one argument and
# these variables: STUB_MODE (start or resume), STUB_PROMPT (the message the
# runner would have sent), RUNNER_TASK_ID and RUNNER_CONF. Whatever it prints
# is the session's last words, so its last line is the RUNNER: or SUPERVISOR:
# line. It is not a builder: never give a real task's letter this adapter.

AGENT_NAME="the stub (no agent)"
AGENT_BIN=zsh
AGENT_LOGIN_CMD="(nothing to sign in to)"
AGENT_PRESET_SESSION=1

adapter_signed_in() { [ -n "${STUB_SCRIPT:-}" ] && [ -f "$STUB_SCRIPT" ]; }

_stub_run() {
  local words rc
  words="$(RUNNER_TASK_ID="$A_TASK_ID" STUB_MODE="$1" STUB_PROMPT="$A_PROMPT" zsh "$STUB_SCRIPT" "$A_TASK_ID" 2>&1)"; rc=$?
  python3 -c 'import json, sys; print(json.dumps({"type": "result", "result": sys.argv[1], "session_id": sys.argv[2]}))' "$words" "$A_SESSION"
  return $rc
}
adapter_start()  { _stub_run start; }
adapter_resume() { _stub_run resume; }

adapter_read_result() {
  eval "$(python3 - "$1" "${2:-RUNNER}" <<'PY'
import sys, json, shlex, re
text, session = "", ""
for line in open(sys.argv[1], errors="replace"):
    try: e = json.loads(line)
    except ValueError: continue
    if isinstance(e, dict) and e.get("type") == "result":
        text = e.get("result") or ""; session = str(e.get("session_id") or "")
if sys.argv[2] == "SUPERVISOR":
    m = re.findall(r"^\s*(SUPERVISOR: *(?:retry|run|waiting|skip)\b.*)$", text, re.M)
else:
    m = re.findall(r"RUNNER: *(?:done|blocked|question)(?: |$).*", text)
print("RESULT_KIND='' RESULT_REASON='' RESULT_TEXT=%s RESULT_VERDICT=%s RESULT_SESSION=%s" % (
    shlex.quote(text[:600]), shlex.quote(m[-1].strip() if m else ""), shlex.quote(session)))
PY
)"
}
