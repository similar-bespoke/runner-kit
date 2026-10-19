# Supervision and verified delivery

A hook is a call made when work reaches a known point. The kit calls the same
supervision code for Claude, Codex and other adapters. It covers the builder
(including its reviewer), the runner's project check and the stop session.
It does not depend on either agent's optional native hook system.

The originating coding session remains responsible for the goal. A dashboard
label, a fresh stop session and a process that is alive do not demonstrate
that the originating session is overseeing useful progress.

## Selected Codex client and model

The default builder and reviewer use `gpt-6.1-sol` through
`bin/runner-codex`. The wrapper selects
`/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex`, version
0.162.0 or newer. A project may explicitly set `CODEX_BIN` to another absolute
newer client path. It never falls back to the older executable on PATH.
Builder, resume, reviewer and account checks use the same selection.

Every task and review passes its pinned model explicitly. Model errors stop
for a supervisor decision. They never trigger a client fallback or model
downgrade. Will's explicit permission is required to change the selected model.
Older workspaces keep their files; configure their selected model before an
authorised launch. Standard copied review commands receive the current wrapper
and assigned model from the launcher on both first starts and resumes.

## Set up before starting work

In `runner.conf`, set:

```sh
GOAL='The complete result the intended user must be able to use.'
SUPERVISION_REQUIRED=yes
ORIGIN_AGENT=codex
ORIGIN_SESSION=<actual originating session identifier>
SUPERVISION_INTERVAL=300
SUPERVISION_TIMEOUT=900
COORDINATOR_CMD=~/.local/bin/notify-coordinator
ACCEPTANCE_CMD='<the existing command that exercises the delivered user journey>'
```

Choose the review interval for the work. The defaults request review every five
minutes and allow fifteen minutes without an acknowledgement. This is a check
on missing supervision, not a maximum task duration. Useful work can continue
for as long as it needs while the originating session reviews it.

The session needs a working recurring wake-up before an unattended queue starts.
In Codex desktop, create a heartbeat automation attached to that same chat with
the automation tool. Its prompt must name the workspace, real originating
session, goal and the review procedure below. Verify the automation is active.
In Claude, use a supported recurring facility attached to the originating
session, or a verified bridge through `SUPERVISOR_CMD`. Do not invent a native
hook, detached worker or new Claude conversation and call it the original
supervisor. If the runtime cannot wake that session, supervise in the foreground
and report that unattended oversight is unavailable. Ending the foreground
session requires a working continuation mechanism or stopping the queue.

An optional `SUPERVISOR_CMD` is an executable with arguments, split as shell
words without evaluation. It receives the event JSON on standard input.
It must obtain a decision from the exact originating session, returning:

```json
{"agent":"codex","session":"<actual id>","action":"continue","reason":"<evidence checked and why the next action advances the goal>"}
```

A transport acknowledgement or an automatic `continue` is not a review.
Task sessions and reviewers must never acknowledge their own work as the
originating session. The recorded identity prevents accidental cross-session
acknowledgements; it is not a security boundary against an agent with file access.

Before launch, the originating session reads the goal and first task, creates
an initial checkpoint and acknowledges it using the commands below. Never
fabricate a session id, use a process id, or substitute the stop session.

## Review and intervene

From the workspace, with `<kit>` resolved to the installed checkout:

```sh
python3 <kit>/bin/runner_watch.py event review --summary 'Review the goal, first task and available evidence before starting.'
python3 <kit>/bin/runner_watch.py pending
python3 <kit>/bin/runner_watch.py review <event-id> --agent <claude-or-codex> --session <actual-id> --action continue --reason '<what was checked and why this work advances the goal>'
```

At each wake-up, inspect the newest checkpoints, the recent task output, the
actual diff, the single reviewer's unresolved findings, provider availability
(`runs/available-<adapter>`) and waiting tasks. Name the usable result gained
since the last review. A growing log or a passing test count is not that result.
Read enough output to distinguish useful work from repeated attempts at the
same check or review finding. Do not rerun checks merely to supervise them.

For each unresolved finding, require a concrete wrong user result, its input,
and the smallest necessary repair. Reject speculative abstractions, extra
frameworks, invented requirements and repeated reviews that reveal no new
failure. Preserve valid completed work and the single assigned reviewer.
When no real blocking finding remains, finish the task. Do not demand a second
reviewer or require a fixed number of review rounds.

Use `--action yield` on a checkpoint for the active task to interrupt an
unproductive builder, reviewer, check or stop session. The wrapper terminates
that command's process group, retains files and logs, and makes the task wait
for the originating session. It does not kill another queue or reset Git.
Investigate any interrupted external operation before retrying it. A timeout
does not prove that a payment, deployment or message did not take effect.

Use `--action stop` only to stop the queue as well. An ordinary
`touch runs/queue.stop` retains its existing meaning: stop after current work.
If reviews cease, the active command yields when the supervision timeout
expires. Merely being quiet does not interrupt a command.

After resolving an engineering obstruction, acknowledge the event named in
`runs/oversight/yielded/<task>.json` with `continue`. The queue releases that
task without inventing an owner decision. Other eligible tasks can run while
it waits. Provider resets and transient provider failures defer only that
adapter until its stated availability time. A rejected model or invalid request
requires a supervisor decision instead of a timed retry. Missing sign-in raises a question
instead of holding the queue inside a login wait.

Task sessions report material changes of stage through:

```sh
python3 <kit>/bin/runner_watch.py event progress --task <id> --summary '<what has been achieved and how it advances the goal>' --next '<remaining user result>' --evidence '<retained result reference>'
```

Report a repeated failed check, review disagreement or missing input immediately.
Progress events stay with the supervising session. Do not write a routine
worksheet, repeat an unchanged update or pass raw technical logs to Will.

## Coding Coordinator

The existing helper `~/.local/bin/notify-coordinator` sends through its private
webhook settings. Never copy its URL or key into the kit, `runner.conf`, a task,
an event or an agent prompt. `COORDINATOR_CMD` names the executable only.

Will's current standing instruction permits messages only for a completed goal,
a blocker or a question. Those events use the helper's `done`, `blocker` and
`question` cases. Starts, ordinary progress and commits stay in the local record
for the supervisor. A committed task is not a delivered goal.

Every message states the project, complete goal and concrete result or decision.
A question states exactly what Will must do, why it matters, the recommended
answer and what work continues. A delivery message states what the intended
user can now do and where that was tested. Assume Will remembers none of the
conversation. Explain necessary technical terms. Prefer “we” for shared work;
name the main agent when it acted alone. Do not use invented project jargon.

Notices are saved before sending under `runs/oversight/events/`. Acceptance
receipts live in `runs/oversight/messages/`. A successful helper response
`sent (2xx)` proves webhook acceptance only. It does not prove that the bot
displayed the message or Will read it. Verify one message in Coding Coordinator
before claiming that the full communication route works.

`pending` shows messages lacking a receipt. `flush` sends unsent notices.
A lost response is marked uncertain and is not blindly resent. Reconcile it
with the recipient before `flush --retry-uncertain`. The stable message reference
lets the recipient identify an earlier delivery. A supervisor must surface a
failed route in the originating chat. Do not report “Will has been alerted”
from a local log alone. Do not replace an undelivered question with a new one.

## Completion requires the delivered user journey

Task `[x]` and exit 0 remain records of a committed, independently checked build.
They cannot establish delivery of the complete goal. An empty queue is not
completion. The originating session reconciles every goal outcome and acceptance
condition with real delivered behaviour before calling:

```sh
python3 <kit>/bin/runner_watch.py verify
```

`ACCEPTANCE_CMD` must use the actual delivered interface, data, identity and
environment appropriate to the project. For a local tool, run the installed
command on representative real input. For a website, use the served site as its
intended user and inspect the resulting saved or sent output. A mocked provider,
fixture-only test, health route, screenshot alone or source checkout test is
insufficient. Use existing acceptance tooling; add no parallel test framework.

It exits 0 and emits one JSON object:

```json
{"passed":true,"revision":"<full delivered Git SHA>","target":"<delivered interface and environment>","journey":"<actions the intended user took>","expected":"<required result>","observed":"<actual result in plain user language>","outcomes":["G1","G2"]}
```

The runner executes it independently, retains the output and requires a matching
candidate revision. Deploying projects must also pass `deploy.sh check` with
`LIVE` and the candidate in `runs/live-sha`. The originating session verifies
that the reported outcomes cover the whole agreed goal and the evidence is real.
The JSON format cannot judge whether a test has told the truth.

After `verify`, the originating session inspects the saved evidence, acknowledges
that specific review event with `continue`, and runs:

```sh
python3 <kit>/bin/runner_watch.py deliver
```

`deliver` reuses the retained proof and message identity. It does not rerun the
user operation. Only this verified delivery path creates a `delivered` event
and a `done` message.
If the command, target, authority or real evidence is missing, report the precise
gap and continue independent work. Do not weaken the goal or mark it delivered.
If the user check passes but its notice fails, retain that proof and reconcile
the message; do not repeat the user operation just to resend a message.

## Existing runners and rollback

The new template requires supervision. Older configurations without
`SUPERVISION_REQUIRED` retain their behaviour and produce an explicit warning.
Migrate them by recording the real origin, setting the goal and acceptance
command, verifying the communication route and enabling supervision before
their next launch. Do not silently replace a pinned kit or restart a live queue.
Already running commands retain their original code and prompts.

Rollback uses the previous committed kit and skill versions at the next
controlled launch. Preserve `runs/`, receipts, edits and outstanding external
operations. Do not delete locks, waiting markers or completed work.
