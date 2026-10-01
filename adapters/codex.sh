# Adapter: Codex (command `codex`). Sourced by bin/run_task.sh and
# bin/run_queue.sh; never run by itself. The contract is in TEMPLATE.sh.
# Status: experimental. The known limits are listed in manifest.yaml.

AGENT_NAME="Codex"
AGENT_BIN=codex
AGENT_LOGIN_CMD="codex login"
AGENT_PRESET_SESSION=0     # Codex names the session itself, in its first event

# Operation 3: the signed-in check.
adapter_signed_in() { command codex login status 2>&1 | grep -q "Logged in"; }

# Codex runs non-interactively with its events as JSON lines, in its
# workspace-write sandbox. The directories in A_DIRS and the .git directory of
# each repository they belong to are writable (a commit fails without .git).
# Anything outside that goes to Codex's automatic approval review, never to a
# person. The two task variables are set by name because a Codex configuration
# may pass only core variables to shell commands, and the commit hook needs
# them. `exec resume` takes no sandbox flags, so every setting is a -c
# override, the same for a start and a resume.
_codex_flags() {
  local r g; local -a roots gits
  for r in "${A_DIRS[@]}"; do
    roots+=("$r")
    g="$(git -C "$r" rev-parse --absolute-git-dir 2>/dev/null)" || continue
    (( ${gits[(Ie)$g]} )) || gits+=("$g")
  done
  roots+=("${gits[@]}")
  CODEX_FLAGS=(--json -m "$A_MODEL" -c "model_reasoning_effort=\"$A_EFFORT\""
    -c 'sandbox_mode="workspace-write"' -c 'approval_policy="on-request"' -c 'approvals_reviewer="auto_review"'
    -c "sandbox_workspace_write.writable_roots=[\"${(j:",":)roots}\"]"
    -c "shell_environment_policy.set={RUNNER_TASK_ID=\"$A_TASK_ID\",RUNNER_CONF=\"$RUNNER_CONF\"}")
}

# Operation 1: start a session. Operation 2: resume it.
adapter_start()  { local -a CODEX_FLAGS; _codex_flags; command codex exec "${CODEX_FLAGS[@]}" "$A_PROMPT" </dev/null; }
adapter_resume() { local -a CODEX_FLAGS; _codex_flags; command codex exec resume "$A_SESSION" "${CODEX_FLAGS[@]}" "$A_PROMPT" </dev/null; }

# Operation 4: read the result and the session id from the raw event stream.
# The session id is the thread_id of the first event; the last words are the
# last agent_message; a turn.failed event is the failure.
adapter_read_result() {
  eval "$(python3 - "$1" "${2:-RUNNER}" <<'PY'
import sys, json, shlex, re
kind, text, reason, session = "", "", "", ""
for line in open(sys.argv[1], errors="replace"):
    try: e = json.loads(line)
    except ValueError: continue
    if not isinstance(e, dict): continue
    item = e.get("item") or {}
    if e.get("type") == "thread.started":
        session = session or str(e.get("thread_id") or "")
    elif e.get("type") == "item.completed" and item.get("type") == "agent_message":
        text = item.get("text") or ""
    elif e.get("type") == "turn.failed":
        reason = str((e.get("error") or {}).get("message") or "turn failed")[:300]
        low = reason.lower()
        kind = "auth" if ("401" in low or "unauthorized" in low or "authenticat" in low or "log in" in low or "login" in low) else "transient"
        text = text or reason
if sys.argv[2] == "SUPERVISOR":
    m = re.findall(r"^\s*(SUPERVISOR: *(?:retry|run|waiting|skip)\b.*)$", text, re.M)
else:
    m = re.findall(r"RUNNER: *(?:done|blocked|question)(?: |$).*", text)
print("RESULT_KIND=%s RESULT_REASON=%s RESULT_TEXT=%s RESULT_VERDICT=%s RESULT_SESSION=%s" % (
    shlex.quote(kind), shlex.quote(reason), shlex.quote(text[:600]),
    shlex.quote(m[-1].strip() if m else ""), shlex.quote(session)))
PY
)"
}
