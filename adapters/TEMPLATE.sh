# Adapter template: copy to adapters/<name>.sh and fill it in to add another
# coding agent. Then map a letter to it in runner.conf (ADAPTER_X=<name>,
# MODEL_X=<model id>), write a reviewer step as templates/REVIEW-<NAME>.md
# (upper case, copied into each workspace), and record the adapter's status in
# manifest.yaml with exactly what was run.
#
# An adapter is a zsh file that is sourced, never run. It holds no logic about
# tasks, queues or commits: only how to drive one agent's command-line tool.
#
# THE CONTRACT
#
# Four variables:
#   AGENT_NAME            the agent's name, for messages
#   AGENT_BIN             the command that must be installed
#   AGENT_LOGIN_CMD       the one command a person runs to sign in
#   AGENT_PRESET_SESSION  1 if the tool accepts a session id chosen by the
#                         runner (a UUID in A_SESSION) on its first start;
#                         0 if the tool names the session itself
#
# Inputs, set by the runner before each call:
#   A_PROMPT    the first message (start) or the resume instruction (resume)
#   A_MODEL     the model id from runner.conf for the task's letter
#   A_EFFORT    the effort word from the task's M column (medium, high, ...)
#   A_SESSION   the session id: a new UUID on start when AGENT_PRESET_SESSION
#               is 1, empty on start otherwise, the saved id on resume
#   A_DIRS      array of directories the session must be able to read and
#               write: the workspace and every repository
#   A_TASK_ID   the task id; the session's shell commands must see it as
#               RUNNER_TASK_ID, and RUNNER_CONF as it is, or the commit hook
#               does nothing
#   The current directory is the first code repository (a task session) or the
#   workspace (a stop session).
#
# Four operations:
#   1 adapter_start         run one new, unattended session to its end. Write
#                           the tool's raw event stream to stdout, one event
#                           per line. Return the tool's exit code. No prompt
#                           to a person, ever: a session nobody is watching
#                           must not wait for an answer.
#   2 adapter_resume        the same, continuing session A_SESSION with its
#                           context.
#   3 adapter_signed_in     return 0 when the tool is signed in, without
#                           spending anything.
#   4 adapter_read_result <raw-file> <RUNNER|SUPERVISOR>
#                           read the saved event stream and set:
#       RESULT_TEXT     the session's own last words (first 600 characters),
#                       never tool output
#       RESULT_VERDICT  the last line of those words that starts with the
#                       given word and a colon, in the forms PROTOCOL.md lists
#       RESULT_KIND     auth (sign-in failed), transient (network, overload,
#                       rate limit: worth a wait and a resume) or empty
#       RESULT_REASON   the tool's own reason for a failure, or empty
#       RESULT_SESSION  the session id, read from the stream
#
# One optional operation:
#   adapter_preflight       a check that fails in seconds (for example a
#                           minimum version); print why and return non-zero.
#
# Also teach bin/render_stream.py the tool's event types, or its log lines are
# printed raw.

AGENT_NAME="Example agent"
AGENT_BIN=example-agent
AGENT_LOGIN_CMD="example-agent login"
AGENT_PRESET_SESSION=0

adapter_signed_in() {
  command example-agent whoami >/dev/null 2>&1
}

adapter_start() {
  command example-agent run --json --model "$A_MODEL" "$A_PROMPT" </dev/null
}

adapter_resume() {
  command example-agent run --json --model "$A_MODEL" --continue "$A_SESSION" "$A_PROMPT" </dev/null
}

adapter_read_result() {
  # Parse "$1" here. This placeholder reports nothing, which the runner treats
  # as a session that ended without a verdict.
  RESULT_KIND=""; RESULT_REASON=""; RESULT_TEXT=""; RESULT_VERDICT=""; RESULT_SESSION=""
}
