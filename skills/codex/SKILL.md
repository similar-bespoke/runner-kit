---
name: runner-kit
description: Set up, run or supervise a project using the internal runner-kit methodology. Use when Will invokes runner-kit, asks to execute work through runner-kit, or asks to supervise an existing runner workspace. Designs and tasks belong to the supervising session; product implementation belongs to the runner's task sessions.
---

# Runner kit

Use the shared kit at `/Users/wb-m37/coding/workspaces/runner-kit`.
The supervising session designs, writes tasks, orders the queue, records decisions,
verifies delivery and reports. It writes no product code and runs no experiments.
The runner starts fresh task sessions and verifies their commits independently.

This skill belongs to the originating supervising session. A launcher task
session with `RUNNER_TASK_ID` follows its assigned task and injected delivery
instructions instead. It must not take over setup, recurring supervision or
real user reporting. It reports stages and obstructions through the configured
runner events; the originating session owns Coding Coordinator messages.

## Codex client and model selection

Will selected `gpt-6.1-sol` for builders and reviewers on 19 October 2026.
Use the Codex adapter for those task roles even when Claude is the originating
supervisor. Set their `ADAPTER_<letter>=codex` and `MODEL_<letter>=gpt-6.1-sol`.
Keep the task's assigned effort. Do not substitute another model after an error.
Changing or downgrading the selected model requires Will's explicit permission.

Builders, resumed sessions and reviewers must all use the kit's
`bin/runner-codex`. Its default client is
`/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex`.
`CODEX_BIN` may name another explicitly selected absolute client path, version
0.162.0 or newer. Never fall back to the older `codex` on PATH. Account checks
and `runner-doctor` must use the selected client too.

The launcher refreshes the assigned review command and pinned model on resume,
including standard older copied `REVIEW-CODEX.md` prompts. Verify the actual
builder and reviewer commands name `gpt-6.1-sol` and the same client. A model
catalogue or a one-word inference response is insufficient for end-to-end
runner proof: finish a real task, its one assigned review and commit, then
independently exercise its delivered user result before reporting completion.
If the model or client is unavailable, preserve the work and report the exact
blocker. Continue eligible independent work; do not downgrade to release it.

## Active originating-session oversight

For setup, start, resume, supervision or delivery, read
`/Users/wb-m37/coding/workspaces/runner-kit/docs/supervision.md` in full. These current instructions replace older
skill or copied-guide advice about passive watching, completion and messages.
Editing the kit or skills is permitted when Will explicitly requests that
maintenance; ordinary project sessions still leave the shared kit unchanged.

Before unattended work, set `GOAL`, `SUPERVISION_REQUIRED=yes`, `ORIGIN_AGENT`
and `ORIGIN_SESSION` to the full user goal and this actual originating session.
Set `ACCEPTANCE_CMD` to the existing delivered user check, and verify the
`COORDINATOR_CMD` helper without exposing its private webhook settings.
A dashboard's “in charge” label is not active supervision.

Arrange a supported recurring wake-up of this same originating session.
In Codex desktop, use the automation tool to create a heartbeat attached to
this chat. Name the workspace, goal, actual session, review interval and the
procedure below. Verify it is active. In Claude, use a supported recurring
facility belonging to this session, or a verified `SUPERVISOR_CMD` bridge
that obtains this session's actual decision. Do not substitute a new model
session, detached worker or automatic acknowledgement. If this runtime cannot
wake the originating session, supervise in the foreground and state that
unattended oversight is unavailable. Do not claim a watcher exists.

Choose the review interval for the work. The kit defaults request review every
five minutes and yield after fifteen minutes without a review. This is not
a task duration cap. Create and acknowledge the initial review checkpoint
before launch. A skill invocation still does not authorise starting a queue.

At each checkpoint, inspect recent task output, the actual diff, the single
reviewer's findings, waiting tasks and provider availability. Identify what
user result has advanced since the last review. An active process, more tests
or growing logs is not progress. Use retained evidence; do not repeat checks
merely to supervise them. Use `runner_watch.py pending` and acknowledge the
relevant event with `review --agent ... --session ... --action ... --reason ...`.
The reason must state what was checked and why the next move advances the goal.
Never acknowledge automatically or let the builder review itself as supervisor.

Intervene when tests or reviews repeat without new evidence, proposed machinery
has no real consumer, a requirement was invented, or a blocked task prevents
independent work. Use `yield` to preserve and interrupt that task, then resolve
the narrow cause or reorder eligible work. Keep the one assigned reviewer.
Require concrete wrong behaviour and the smallest repair. Do not impose a
fixed number of review rounds. Reconcile unknown external effects before retry.
Release engineering waits through the originating session's review, rather
than inventing an owner decision. Ask Will only for an actual product decision
or an action only he can take. Preserve and track the open question.

Communicate for someone who remembers none of the conversation. State the full
goal, usable result achieved, why it advances the goal and the next useful move.
Use ordinary words and explain necessary technical terms. Do not copy invented
agent jargon or raw logs. Use “we” for shared responsibility, and name the main
agent when it acted alone. Routine progress stays in this chat and the local
record. Will's current Coding Coordinator policy permits only completion,
blocker and question messages through `~/.local/bin/notify-coordinator`.
Each includes the goal, clear result or question, recommended action and what
continues independently. Check the receipt. Webhook acceptance does not prove
that the bot displayed a message. Surface a failed route here and reconcile
uncertain sends before retrying. Do not ask an already open question again.

A task's `[x]`, passing checks and an empty queue establish builds, not delivery
of the goal. Run `runner_watch.py verify` against the actual delivered interface
as its intended user. Inspect the saved journey, expected and observed result,
revision, environment and coverage of every agreed G outcome. A mocked test,
health check, deployment or screenshot alone is insufficient. Acknowledge that
specific evidence review, then run `runner_watch.py deliver`. Reuse retained
proof to reconcile a failed message without repeating the user operation.
Name any missing authority, input or evidence and continue independent work.

Before ending supervision, preserve the verified state, pending event ids,
open questions and the supported continuation mechanism in the handoff. Keep
that mechanism active until delivery or an authorised stop. Without one, stop
the queue and say exactly what remains. Older pinned checkouts and already
running sessions require explicit migration; do not silently restart them.

## Scope and authority

Creating or editing this skill does not invoke a runner or start a queue.
On invocation, identify whether the request is to set up a new project, supervise
an existing workspace, or explicitly start, stop or run work in that workspace.
Resolve the workspace and named code repositories from the request and context.
Ask only for missing information that materially affects the outcome or authority.
Ask product questions one at a time, with a recommended answer.
Settle engineering choices and record the reasons.

Read the kit's `PROTOCOL.md` in full before acting. For setup, also read
`manifest.yaml` and `interview.yaml` in full. Follow the live protocol and valid
owner-signed decisions in the project's `DECISIONS.md`. Report any difference
between this skill, the source guide and the installed kit. The current user's
instructions and higher-priority runtime instructions take precedence.

Apply the shared delivery instructions in protocol section 7 during task
design and supervision. Prepare named inputs, file scope and existing
admission before paid execution. Keep the task contract stable during a run.
State the observable outcome and sufficient evidence in `Done when:`.
Reuse valid evidence and justify optional repeated checks by a specific
unresolved failure. Honour every acceptance condition and explicit stop
instruction before claiming completion. Do not add routine worksheets.
The current launchers include these instructions for all adapters, including
resumes and older workspace prompts. Other pinned kit copies need a separate
update; do not silently switch a project's pinned checkout. A stop supervisor
uses retained evidence and does not repeat product checks or start a review.

The source guide is preserved in [references/invocation-guide.md](references/invocation-guide.md).
It was supplied by Will from
`/Users/wb-m37/AETIDIGM_SYNC/Aetidigm Master/engineering/runner_kit_invocation_guide_2026-10-06.md`
on 6 October 2026. The reference preserves the workflow; distributable copies redact private network addresses.
Read section 1 for setup, section 2 for supervision, and section 3 when dashboard
reporting is relevant. Its versions, addresses and availability statements are
dated observations, not current facts. Check the installed files before relying
on them. Do not pull, reset, edit or upgrade the shared kit during project work.

Stay within the workspace and named repositories. Preserve other queues, services,
repositories and their tmux sockets. Use a project's documented launcher unchanged.
For a new project alongside existing runners, use its own tmux socket and session.
Never write secrets into `runner.conf`, tracked files or output.
Review commands and hooks before execution and honour applicable v2 admission
requirements. Reuse existing applicable authorisation; do not ask for it again.
This skill does not authorise unrelated deployment, credentials or external writes.

## Set up a new project

Use the guide's section 1 in order, applying the following requirements:

1. Run `<kit>/bin/runner-doctor` and show its output. A line starting `MISSING`
   blocks setup. Name the missing prerequisite and continue independent preparation.
2. Create `/Users/wb-m37/coding/workspaces/<project>` unless another authorised
   workspace was supplied. It must be tracked by a Git repository. The coding
   root ignores `workspaces/*`, so initialise the workspace itself when it has
   no repository of its own. Inspect first and preserve existing files.
3. Run `<kit>/bin/runner-init [--deploy] <workspace> <repo> [<repo> ...]`.
   Use `--deploy` only when deployment is part of the requested project.
   If product code lives in the workspace, name it as a repository too.
   Show all output. Add a suggested line to an existing hook or `.gitignore`
   only with the owner's yes, as the guide requires. Write a protocol pointer
   to another instruction file only with applicable owner authorisation.
4. Write `DESIGN.md` with the owner. Put the requested outcomes in
   `DELIVERY-RULES.yaml` as `goal_outcomes`, each with an id such as `G1` and
   an `outcome`. Set `meta.written` to today's date. Add no new rule without
   an observed failure. Preserve the kit's carrying rules.
5. Edit the existing `KEY=value` lines in `runner.conf`. Use one per line,
   no spaces around `=`, no trailing comment, and single quotes around values
   with spaces or symbols. Fill `PROJECT`, `PRODUCT_DIRS`, `FREE_DIRS`,
   `CHECK_CMD`, `NOTIFY`, `ADAPTER_<letter>`, `MODEL_<letter>`,
   `DEFAULT_BUILDER`, `DEFAULT_REVIEWER`, `SUPERVISOR`, `DEPLOYS` and
   `LIVE_CHECK_CMD`. Pin exact model ids. Reuse ids explicitly supplied for
   this work; ask for missing ids rather than copying historical examples.
   Leave `DASHBOARD_URL` empty to use the machine setting. Configure a message
   notifier only within the owner's authorised recipient and channel scope.
6. Run `<kit>/bin/runner-doctor <workspace>/runner.conf` and show its output.
   Stop dependent execution if any line starts `MISSING`.
7. Run `<kit>/selftest/run.sh --conf <workspace>/runner.conf` and show its
   output exactly. It spends one small real agent session. Success requires
   the final line `SELFTEST: PASS`. On `PARTIAL` or `FAIL`, show the failing
   or skipped line and log path. Do not call setup working or start the queue.
8. For a deploying project, fill the project section of `deploy.sh` and run
   `./deploy.sh check` within authorised scope. Otherwise record no deployment
   in the delivery rules. A deploy check does not itself deploy a candidate.
9. Delete the example task. Write the first tasks using the contract below
   and put their ids in `RUN-ORDER.md`, one per line.
10. Record decisions as they occur. Commit only the workspace's task changes,
    naming paths explicitly. Preserve unrelated changes.
11. From the workspace, run and show the dry pass:
    `QUEUE_DRY=1 QUEUE_ONCE=1 <kit>/bin/run_queue.sh`.
12. Record the supervising session through the reporter if supported, as below.
13. Finish at the dry pass. Give the exact project start command and wait for
    the owner's instruction to start. Merely invoking setup does not start it.

## Write tasks and decisions

A task is the smallest change that delivers an outcome the owner can use.
Use `schema/task-heading.json` for the heading and `PROTOCOL.md` section 4
for its content. Keep each entry to at most 15 lines. Include:

- An outcome sentence, task id, status, builder and reviewer with effort.
- At least one `G` outcome and an observed failure reference or owner order.
- Every permitted file, including new files by name.
- A build instruction at the nearest existing boundary.
- A done-when check on real or copied data and what the owner will see.

Only missing code establishes a `Needs <id>` prerequisite. A new model question
is measured on stored cases before product code. Do not turn a review suggestion
or hunch into a task. Do not add unused machinery or unrequested approval rules.
Use the live protocol's model and effort defaults unless the owner specifies
otherwise. Exactly one reviewer reviews the diff. A task with no `M:` belongs
to the owner and parks. With `R: owner`, it stops at `[~]`; only the owner marks
it `[x]`. A completed heading records its commit hash.

Append one dated decision line with its reason. Sign your decisions
`(supervising session, <date>)`. Use `(owner, <date>)` only for an answer or
instruction actually given by the owner. Commit each decision before the next
question. Never fabricate an owner entry to release a task.

## Resume and supervise

From the workspace, read the newest `HANDOFF-<date>.md`, delivery rules, recent
decisions, queue and project `OPERATIONS.md` or README. Verify retained claims:

```sh
<kit>/bin/runner-queue once
tail -40 runs/queue.log
git log -10 --format='%h %s'
```

Run `./deploy.sh check` if present and within authorised scope.
Inspect `runs/queue.lock/pid` and check its process with `kill -0`.
A missing or dead process does not authorise deleting the lock.
Record yourself as in charge if supported. Report what is live, what is running,
how many built changes are not live, and what waits for the owner.
For a project without deployment, report delivered local outcomes instead.

Start only on an owner instruction covering that queue. Run the dry pass first.
Use the documented project launcher unchanged. Otherwise use the guide's tmux
command, with a project-specific socket where isolation is required:

```sh
tmux -L <project> new-session -d -s <project>-runner -c <workspace> <kit>/bin/run_queue.sh
```

Inspect that socket with `tmux -L <project> ls`. Do not start a second queue.
Use `runner-queue once` for bounded status, `runner-queue` for its ten-second
display or `runner-queue log` to follow the queue log. Collect pending results
without blocking the conversation. Edit `RUN-ORDER.md` to change order;
the queue re-reads it without a restart.

Run an explicitly authorised single task, with no queue running, from the workspace:
`<kit>/bin/run_task.sh <task-id> [max-attempts]`.
Exit codes: `0` done, `1` attempts exhausted, `2` usage or setup,
`3` needs owner, `4` blocked or question, `5` split task.
Use the installed runner's retry policy; do not add an arbitrary attempt limit.

Stop after the current task with `touch runs/queue.stop` when requested.
Do not hand-edit `runs/`. The named stop/go commands and reporter writes are
exceptions. Never remove locks or waiting markers.

When paused, identify the shared cause in the prompt, model, `CHECK_CMD` or
machine. Preserve a deliberate owner pause. Resume only within existing
authorisation after resolving the cause, using the documented change triggers
or `touch runs/queue.go`. Do not modify the shared kit as a repair.

List parked tasks with `ls runs/waiting/`; read a reason with
`sed -n 2p runs/waiting/<id>`. Ask an owner question once with a recommendation.
On the answer, append and commit the genuine owner decision. Let the runner
release the task. Never rerun it manually or restate an already open question.

## Deployment and proof

Never bypass a commit hook. The runner independently runs `CHECK_CMD`;
an agent's claim that checks passed is insufficient.
Deploy only within explicit applicable authority, through `deploy.sh <full-sha>`.
At a task's deploy point, use a background watcher as specified in the live
protocol, subject to the runtime's delegation rules. Give it the task id,
authorised target and stop conditions. It deploys once, checks afterwards and
returns the exact commit, full output and failures. Do not invent model ids
or claim a watcher exists when the runtime cannot create it.

Call a change live only when `deploy.sh` prints `LIVE`. Then independently
compare the first live result with its source. A deployment is not proof of
the full outcome. Apply the live protocol's stop at ten built changes awaiting
deployment to deploying projects. Report observable delivery rather than test counts.
Before ending supervision, write and commit `HANDOFF-<date>.md` with verified
state, open questions, pending operation identifiers and a continuation prompt.

## Reporter and dashboard

Dashboard support is optional and version-dependent. If `bin/runner_report.py`
exists, record the supervising session from the workspace:

```sh
python3 <kit>/bin/runner_report.py --in-charge
```

If the shell does not identify the agent session, use
`--in-charge --agent <claude|codex> --session <actual-session-id>`.
Use a real runtime session identifier. Never invent one or substitute a process id.
If unavailable, report this gap and continue independent work.

When dashboard checking is requested or needed, follow section 3 of the saved
guide. Verify the installed version and reporter launch lines, machine config
presence and owner-only permissions, URL precedence, the actual queue's Python
interpreter, reporter logs/process and the dashboard pane. Do not print tokens.
The machine file is `~/.config/runner-kit/dashboard.conf`; token storage belongs
there or in `RUNNER_DASHBOARD_TOKEN`, never tracked `runner.conf`.
`RUNNER_DASHBOARD_URL` overrides project `DASHBOARD_URL`, which overrides the
machine setting. `off`, `none` and `no` disable reporting.

Use `python3 <kit>/bin/runner_report.py --check`: exit `0` usable,
`3` unconfigured, `1` configured but unusable. Check interpreter reachability
rather than assuming the dated guide's Mac result still holds.
A dry pass starts no reporter. Attach one to an existing queue only within
authorised reporting scope, using the guide's documented invocation and any
actual `RUNNER_CONF`, `QUEUE_ORDER` or `QUEUE_RUNS` overrides.
Do not provision, upgrade or publish a dashboard as a side effect of setup.
`TASKS.md` and logs remain the record; the dashboard is only a view.
