#!/usr/bin/env zsh
# Notifier "none": the message goes to the log only.
#   none.sh <message>     (RUNNER_NOTIFY_LOG names the log; set by bin/runner-notify)
print -r -- "$(date '+%Y-%m-%d %H:%M:%S') [none] $1" >> "${RUNNER_NOTIFY_LOG:-/dev/stdout}"
