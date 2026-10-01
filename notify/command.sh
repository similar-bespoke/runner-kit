#!/usr/bin/env zsh
# Notifier "command": runs the owner's own command (NOTIFY_CMD in runner.conf)
# with the message as its one, last argument. The log line says whether the
# command succeeded.
#   command.sh <message>  (RUNNER_NOTIFY_LOG and NOTIFY_CMD are set by bin/runner-notify)
msg="$1"; rc=0
if [ -z "${NOTIFY_CMD:-}" ]; then
  route="failed: NOTIFY_CMD is empty"; rc=1
elif ${=NOTIFY_CMD} "$msg" >/dev/null 2>&1; then
  route="ok"
else
  rc=$?; route="failed: exit $rc"
fi
print -r -- "$(date '+%Y-%m-%d %H:%M:%S') [command:$route] $msg" >> "${RUNNER_NOTIFY_LOG:-/dev/stdout}"
exit $rc
