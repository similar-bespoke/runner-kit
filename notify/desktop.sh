#!/usr/bin/env zsh
# Notifier "desktop": a desktop notice. macOS uses osascript, Linux uses
# notify-send; with neither, or when the notice fails, the message goes to the
# log only. The log line says which route was taken.
#   desktop.sh <message>  (RUNNER_NOTIFY_LOG and RUNNER_NOTIFY_TITLE are set by bin/runner-notify)
msg="$1"; title="${RUNNER_NOTIFY_TITLE:-runner}"; route="log-fallback"
if command -v osascript >/dev/null 2>&1; then
  osascript -e 'on run argv' -e 'display notification (item 1 of argv) with title (item 2 of argv)' -e 'end run' -- "$msg" "$title" >/dev/null 2>&1 && route="osascript"
elif command -v notify-send >/dev/null 2>&1; then
  notify-send -- "$title" "$msg" >/dev/null 2>&1 && route="notify-send"
fi
print -r -- "$(date '+%Y-%m-%d %H:%M:%S') [desktop:$route] $msg" >> "${RUNNER_NOTIFY_LOG:-/dev/stdout}"
