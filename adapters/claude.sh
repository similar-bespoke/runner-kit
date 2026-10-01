# Adapter: Claude Code (command `claude`). Sourced by bin/run_task.sh and
# bin/run_queue.sh; never run by itself. The contract is in TEMPLATE.sh.
#
# Optional settings in runner.conf:
#   CLAUDE_ALLOWED_TOOLS  tools an unattended session may use without asking,
#                         as words (for example 'Bash'). Empty leaves the
#                         choice to the machine's own Claude Code settings.
#   CLAUDE_MIN_VERSION    refuse to start on an older command-line version
#                         (for example 2.1.280), for a model that needs it.
#   CLAUDE_TOOLS          the built-in tools a session is given, as words (for
#                         example 'Bash Read Edit Write Task'; Task is the tool
#                         that starts the one reviewer). Every tool's
#                         description is re-read on every turn, so a short list
#                         is cheaper. Empty gives the session every tool.
#   CLAUDE_MCP            no starts the session without the machine's MCP
#                         servers and connectors (mail, documents and so on),
#                         which an unattended coding session should not hold.
#                         yes, or unset, leaves them as the machine has them.

AGENT_NAME="Claude Code"
AGENT_BIN=claude
AGENT_LOGIN_CMD="claude auth login"
AGENT_PRESET_SESSION=1     # the runner picks the session id (a UUID) before the first start

# The command-line tool's own sign-in is the credential. API key variables in
# the environment would replace it, so they are dropped for the session.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN

# Optional operation: a check that fails in seconds. An alias such as "opus"
# can resolve to an older model on an old command-line version, unnoticed.
adapter_preflight() {
  [ -n "${CLAUDE_MIN_VERSION:-}" ] || return 0
  local ver
  ver="$(command claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
  if ! python3 -c 'import sys; v=lambda s: tuple(int(x) for x in s.split(".")); sys.exit(0 if v(sys.argv[1]) >= v(sys.argv[2]) else 1)' "${ver:-0.0.0}" "$CLAUDE_MIN_VERSION"; then
    echo "STOP: Claude Code ${ver:-(unknown version)} is older than CLAUDE_MIN_VERSION=$CLAUDE_MIN_VERSION; run 'claude update', then start again." >&2
    return 1
  fi
}

# Operation 3: the signed-in check.
adapter_signed_in() { command claude auth status 2>/dev/null | grep -q '"loggedIn": true'; }

_claude_run() {
  local -a flags=("$@"); local r
  for r in "${A_DIRS[@]}"; do [ "$r" = "$PWD" ] || flags+=(--add-dir "$r"); done
  [ -n "${CLAUDE_ALLOWED_TOOLS:-}" ] && flags+=(--allowedTools ${=CLAUDE_ALLOWED_TOOLS})
  [ -n "${CLAUDE_TOOLS:-}" ] && flags+=(--tools ${=CLAUDE_TOOLS})
  [ "${CLAUDE_MCP:-yes}" = no ] && flags+=(--strict-mcp-config)
  command claude -p "$A_PROMPT" "${flags[@]}" --model "$A_MODEL" --effort "$A_EFFORT" \
    --permission-mode acceptEdits \
    --output-format stream-json --verbose
}

# Operation 1: start a session. Operation 2: resume it.
adapter_start()  { _claude_run --session-id "$A_SESSION"; }
adapter_resume() { _claude_run --resume "$A_SESSION"; }

# Operation 4: read the result and the session id from the raw event stream.
# It reads the session's own last words, not tool output (source files and
# logs mention errors and rate limits too). A session whose reviewer ran in
# the background writes more than one result event; the last one is the
# session's end, so the last one is read.
adapter_read_result() {
  eval "$(python3 - "$1" "${2:-RUNNER}" <<'PY'
import sys, json, shlex, re
kind, text, reason, session, usage = "", "", "", "", ""
for line in open(sys.argv[1], errors="replace"):
    try: e = json.loads(line)
    except ValueError: continue
    if not isinstance(e, dict): continue
    if e.get("type") == "system" and e.get("subtype") == "init":
        session = session or str(e.get("session_id") or "")
    elif e.get("type") == "result":
        text = e.get("result") or ""; reason = e.get("terminal_reason") or ""
        if e.get("is_error") or reason == "api_error":
            low = (text + " " + reason).lower()
            if "authenticat" in low or "oauth" in low or "api key" in low: kind = "auth"
            else: kind = "transient"
        else: kind = ""
        u = e.get("usage") or {}
        tokens = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens"))
        usage = "%s turns, %.1fM tokens" % (e.get("num_turns") or "?", tokens / 1e6)
        if e.get("total_cost_usd") is not None: usage += ", $%.2f at list price" % e["total_cost_usd"]
if sys.argv[2] == "SUPERVISOR":
    m = re.findall(r"^\s*(SUPERVISOR: *(?:retry|run|waiting|skip)\b.*)$", text, re.M)
else:
    m = re.findall(r"RUNNER: *(?:done|blocked|question)(?: |$).*", text)
print("RESULT_KIND=%s RESULT_REASON=%s RESULT_TEXT=%s RESULT_VERDICT=%s RESULT_SESSION=%s RESULT_USAGE=%s" % (
    shlex.quote(kind), shlex.quote(reason), shlex.quote(text[:600]),
    shlex.quote(m[-1].strip() if m else ""), shlex.quote(session), shlex.quote(usage)))
PY
)"
}
