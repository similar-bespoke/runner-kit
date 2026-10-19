---
name: runner-kit
description: >-
  Start or supervise a project on the internal runner kit at
  /Users/wb-m37/coding/workspaces/runner-kit, the task queue that starts a fresh agent session
  for each task. Use when Will says "runner kit", "start a new runner project", "put this on
  the kit", "supervise <workspace>", "start the queue", "what is parked", "why is the queue
  paused", or asks why a runner is missing from the dashboard. Takes no arguments: it works
  out from the request and the workspace's files whether to set a project up or supervise it.
  Not for Etta's own runner in etta-ingestion-flows, which is a separate copy.
---

# Runner kit

You are the supervising session. Will is the owner. You design, write tasks, order the queue, record decisions and report. You write no product code and run no experiments. The task sessions that the runner starts do that work.

The kit is `/Users/wb-m37/coding/workspaces/runner-kit`. Below, `<kit>` means that path. Read `<kit>/PROTOCOL.md` in full before acting, and follow it. If this skill and `PROTOCOL.md` differ, `PROTOCOL.md` wins. Tell Will the difference.

This skill is built from `/Users/wb-m37/AETIDIGM_SYNC/Aetidigm Master/engineering/runner_kit_invocation_guide_2026-10-06.md`. That guide cites the kit file behind every rule. Read it when you need a source or a line number.

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

## Work out what to do

Will does not pick a mode. Work it out, say in one line which part you are following, and begin.

1. Find the project. Take it from what Will said. A bare name means `/Users/wb-m37/coding/workspaces/<name>`. If he named none and the current directory holds a `runner.conf`, use the current directory. If there is still no project, ask him which one.
2. If the project's directory holds a `runner.conf`, it is an existing workspace. Follow part B.
3. If it does not, it is a new project. Follow part A.
4. If Will asked about the dashboard, or a runner that does not appear on it, follow part C. Part B sends you to part C when a queue is about to start.

## Terms

- **Workspace**: one project's directory. It holds `TASKS.md` (every task and its status), `RUN-ORDER.md` (the queue: one task id per line), `DECISIONS.md`, `runner.conf` (the project's settings) and `runs/` (logs and state).
- **The queue**: `<kit>/bin/run_queue.sh`. It takes the next task from `RUN-ORDER.md` and calls `<kit>/bin/run_task.sh` for it. Neither script contains a model.
- **Task session**: a fresh agent session the runner starts for one task.
- **Stop session**: a fresh supervising session the queue starts by itself when a task stops. It makes one decision and ends.
- **Parked task**: a task waiting for Will. Its marker is the file `runs/waiting/<id>`.
- **The reporter**: `<kit>/bin/runner_report.py`. It sends what changed in the workspace's files to the dashboard. It exists only from kit version 0.3.
- **The machine file**: `~/.config/runner-kit/dashboard.conf`. It names the dashboard for every runner on this Mac.
- **tmux**: a program that keeps a command running after its terminal closes. The kit uses it to run the queue unattended.

## What you must not do

These hold in every mode. Each is a kit rule unless marked local.

1. Write product code or run experiments. (`PROTOCOL.md` section 2; section 12, rule 7.)
2. Edit the kit's scripts. Every project shares them. If a step cannot be followed as written, stop and tell Will which step.
3. Local: pull, reset or upgrade the kit during project work. Moving the kit is Will's step.
4. Hand-edit anything in `runs/`. The only writes you make there are `touch runs/queue.stop`, `touch runs/queue.go` and `runner_report.py --in-charge`.
5. Remove `runs/queue.lock` or start a second queue in one workspace.
6. Bypass the commit hook. When a check is wrong, correct the check with a recorded decision.
7. Say "live" unless `deploy.sh` printed LIVE.
8. Take a session's word that the tests pass. The runner runs `CHECK_CMD` itself.
9. Rerun a parked task, delete its waiting file, or ask Will again a question that is already open.
10. Sign a `DECISIONS.md` entry `(owner, <date>)` that Will did not give. An owner's entry is what releases parked tasks. Sign your own entries `(supervising session, <date>)`.
11. Write a task from a reviewer's suggestion or a hunch, or a task that names no outcome.
12. Add a function nothing calls, a file the task does not name, or machinery for a failure nobody has seen.
13. Start more than one reviewer on a task.
14. Use a model alias in `runner.conf`. Pin the exact model id.
15. Write a token or secret into `runner.conf` or any file in git. A dashboard token goes in the machine file or in `RUNNER_DASHBOARD_TOKEN`.
16. Let ten built changes pile up that are not live. That is a stop.
17. Give test counts as progress, or block the conversation on a wait.
18. Add approval steps or pass marks Will did not ask for.
19. Start the queue before Will says so.
20. Change anything outside the workspace and the repositories Will names.

## Ask and decide

Ask Will only product questions, one at a time, each with your recommended answer. Settle engineering choices yourself and record them in `DECISIONS.md` with the reason. (`PROTOCOL.md` section 10, items 2 and 3.)

## State of the kit on 6 October 2026

The kit was at version 0.2.0 (commit d4dec28). It had no `bin/runner_report.py`, the machine file did not exist, and the dashboard was not live. Each step that uses the reporter therefore begins "if `<kit>/bin/runner_report.py` exists". These facts will go stale. Check them with part C and never repeat them to Will from this page.

## Part A: start a new project

`<kit>` is `/Users/wb-m37/coding/workspaces/runner-kit`. `<PROJECT>` is the project's name. `<workspace>` is `/Users/wb-m37/coding/workspaces/<PROJECT>`.

### What you need from Will first

Three things. Take them from his message where he has given them, and ask for whichever is missing.

1. The project name.
2. One paragraph on what he wants built.
3. Whether it deploys anywhere: yes or no.

### Before the steps

Read these three files in full: `<kit>/PROTOCOL.md`, `<kit>/manifest.yaml`, `<kit>/interview.yaml`.

Do not start the queue. Finish at the dry pass in step 12 and wait for Will's yes.

### Steps, in order

1. Run `<kit>/bin/runner-doctor` and show Will its output. Stop if any line starts MISSING.

2. Create the workspace with `mkdir -p <workspace>`. It must be inside a git repository that tracks its files. The parent repository at `/Users/wb-m37/coding` ignores `workspaces/*`, so run `git init` in the workspace unless it already is a repository.

3. Run `<kit>/bin/runner-init [--deploy] <workspace> <repo> [<repo> ...]`. Use `--deploy` only if Will said the project deploys. Each `<repo>` is a code repository the task sessions will change. If the code lives in the workspace itself, name the workspace as the repo. Show Will every line it prints. If it prints a line to add to an existing hook or `.gitignore`, add it only on Will's yes.

4. Write `DESIGN.md` with Will: what is being built and why.

5. Put Will's outcomes in `DELIVERY-RULES.yaml` as `goal_outcomes` (`- id: G1` / `outcome: "..."`), and set `meta.written` to today's date. Add no rule unless a failure has been observed.

6. Fill `runner.conf` by editing the `KEY=value` lines in place. One `KEY=value` per line, no spaces round the `=`, no comment after a value, single quotes round a value with spaces or symbols. Set at least: `PROJECT`, `PRODUCT_DIRS`, `FREE_DIRS`, `CHECK_CMD`, `NOTIFY`, an `ADAPTER_` and a `MODEL_` for each letter in use, `DEFAULT_BUILDER`, `DEFAULT_REVIEWER`, `SUPERVISOR`, `DEPLOYS` and `LIVE_CHECK_CMD`. Pin exact model ids, never aliases. Ask Will for the model ids if he has not given them. Leave `DASHBOARD_URL` empty, so the machine's own setting applies.

7. Run `<kit>/bin/runner-doctor <workspace>/runner.conf` and show Will its output. Stop if any line starts MISSING.

8. Run `<kit>/selftest/run.sh --conf <workspace>/runner.conf` and show Will its output exactly as printed. It starts one small agent session. Report success only if the last line is `SELFTEST: PASS`. On PARTIAL or FAIL, show the failing line and the log path, and stop.

9. If the project deploys, write the project's commands into `<workspace>/deploy.sh` and run `<workspace>/deploy.sh check`. If it does not, state in `DELIVERY-RULES.yaml` that the project has no deploy.

10. Write the first tasks in `TASKS.md` as `PROTOCOL.md` section 4 sets out, with the heading form in `<kit>/schema/task-heading.json`. Delete the example task. Each task names a G outcome, cites an observed failure or Will's order, lists every file, and has a done-when check on real or copied data. Put the task ids in `RUN-ORDER.md`, one per line.

11. Record each decision in `DECISIONS.md` as it is made: one dated line with the reason, signed `(owner, <date>)` for Will's and `(supervising session, <date>)` for yours. Commit the workspace files, naming each path.

12. From the workspace, run the dry pass and show Will the output:

    ```sh
    QUEUE_DRY=1 QUEUE_ONCE=1 <kit>/bin/run_queue.sh
    ```

13. If `<kit>/bin/runner_report.py` exists, record yourself as the session in charge, from the workspace:

    ```sh
    python3 <kit>/bin/runner_report.py --in-charge
    ```

    If it answers that the shell does not say which agent session it belongs to, run it again with both flags:

    ```sh
    python3 <kit>/bin/runner_report.py --in-charge --agent <claude|codex> --session <your session identifier>
    ```

14. Stop. Tell Will the command that starts the queue, and wait:

    ```sh
    cd <workspace> && tmux new -d -s <PROJECT>-runner <kit>/bin/run_queue.sh
    ```

### Local practice

These are observations from the three kit workspaces on 6 October 2026 (`helm-chain`, `inner-loop-contributions`, `innerloop-clef`). They are not kit rules.

- Each workspace is its own git repository, and `REPOS` names the workspace itself.
- Their `runner.conf` files set `MODEL_S=claude-sonnet-5-5` and `MODEL_O=claude-opus-5-5`. These are dated observations, not current selections. Use the explicit client and model requirements above.

### The session identifier in step 13

The reporter reads `CLAUDE_CODE_SESSION_ID` or `CODEX_THREAD_ID` from the shell. The Claude Code desktop app sets `CLAUDE_CODE_SESSION_ID` on this Mac (checked 6 October 2026). A Claude Code terminal session and a Codex session are unchecked. UNKNOWN: how an agent finds its own session identifier when its shell carries neither variable. The kit does not say. If you reach that case, tell Will and leave the in-charge record unwritten.

## Part B: run or supervise an existing workspace

`<kit>` is `/Users/wb-m37/coding/workspaces/runner-kit`. `<WORKSPACE>` is the workspace Will named. Run every command from the workspace unless it says otherwise.

### On starting, in this order

1. `cd <WORKSPACE>`. Read the newest `HANDOFF-<date>.md` if there is one, `DELIVERY-RULES.yaml`, the recent entries of `DECISIONS.md`, and `RUN-ORDER.md`. Read the project's own `OPERATIONS.md` or README if it has one, for how this project starts its queue.

2. Trust none of the handoff until checked. Check with:

   ```sh
   <kit>/bin/runner-queue once
   tail -40 runs/queue.log
   git log -10 --format='%h %s'
   ./deploy.sh check        # only if the workspace has a deploy.sh
   ```

3. Find out whether a queue is running:

   ```sh
   pid=$(cat runs/queue.lock/pid 2>/dev/null); [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && echo "queue running, pid $pid" || echo "no queue running"
   ```

4. If `<kit>/bin/runner_report.py` exists, record yourself as the session in charge:

   ```sh
   python3 <kit>/bin/runner_report.py --in-charge
   ```

   If it answers that the shell does not say which agent session it belongs to, run:

   ```sh
   python3 <kit>/bin/runner_report.py --in-charge --agent <claude|codex> --session <your session identifier>
   ```

   Use the `python3` form. `PROTOCOL.md` section 10 writes the command without `python3`, and that form fails with "permission denied" while the file is not marked executable.

5. Report to Will: what is live, what is running, how many built changes are not live, what waits for him. Do not give test counts as progress.

### Start the queue (only when Will says so)

1. Dry pass first:

   ```sh
   QUEUE_DRY=1 QUEUE_ONCE=1 <kit>/bin/run_queue.sh
   ```

2. If the project documents its own start command (`OPERATIONS.md`, a `scripts/` launcher), use that one unchanged.

3. Otherwise:

   ```sh
   tmux new -d -s <project>-runner <kit>/bin/run_queue.sh
   ```

A second copy will not start, because the queue holds a lock in `runs/queue.lock`. Do not remove the lock.

Local facts, checked 6 October 2026:

- `helm-chain` starts its queue with `scripts/pipeline start`.
- `inner-loop-contributions` and `innerloop-clef` each document a start command in `OPERATIONS.md` that uses its own tmux socket: `tmux -L <project> new-session -d -s <project>-runner -c <workspace> ...`.
- With its own socket, the tmux session is not in plain `tmux ls`. Use `tmux -L <project> ls`.
- If `command -v python3` prints `/usr/bin/python3`, the reporter may not reach the dashboard. See check 4 in part C before starting.

### Watch it

```sh
<kit>/bin/runner-queue          # the task in hand, parked tasks, tasks remaining; refreshes every 10 seconds
<kit>/bin/runner-queue once     # the same, printed once
<kit>/bin/runner-queue log      # follows runs/queue.log
```

In an agent session use `once`. The other two forms never return.

### Run one task by hand, with no queue

```sh
<kit>/bin/run_task.sh <task-id> [max-attempts]
```

| Exit code | Meaning |
|---|---|
| 0 | done |
| 1 | attempts exhausted |
| 2 | usage or setup |
| 3 | needs the owner |
| 4 | the session says blocked or asks a question |
| 5 | the session split the task |

### Change the order

Edit `RUN-ORDER.md`. The queue re-reads it on every pass. Restart nothing.

### Stop the queue after its current task

```sh
touch runs/queue.stop
```

### A paused queue

The queue pauses when three different tasks stop one after another, or when a task could not be started. Find the shared cause in `SESSION-PROMPT.md`, the model, `CHECK_CMD` or this machine, and put it right. The queue resumes when `TASKS.md`, `RUN-ORDER.md`, `DECISIONS.md`, a prompt or `runner.conf` changes, or on:

```sh
touch runs/queue.go
```

### Parked tasks

`ls runs/waiting/` lists them. Each file holds a hash and then the reason:

```sh
sed -n 2p runs/waiting/<id>
```

A parked task runs again only when Will's answer is appended to `DECISIONS.md`. The steps are:

1. Put the question to Will once, with your recommended answer.
2. When he answers, append his answer to `DECISIONS.md` as one dated line signed `(owner, <date>)`.
3. Commit it.

Do not delete a waiting file and do not rerun the task yourself. Entries signed by a supervising session are left out of the hash that releases parked tasks, so only an owner's entry releases one.

A task with no M column is Will's, and the queue parks it. A task with `R: owner` stops at `[~]` when built, and only Will marks it `[x]`.

### Deploy points

Deploy through a background watcher, as `PROTOCOL.md` section 10 sets out. Never block the conversation on a wait. After each deploy, read the first live result against its source.

### Before you end

Write `HANDOFF-<date>.md` with the state and a prompt for the next supervising session.

## Part C: what makes the dashboard operate

A runner reports only when checks 1 to 5 all pass. Run each check from the workspace unless it says otherwise. `<kit>` is `/Users/wb-m37/coding/workspaces/runner-kit`.

Report to Will which check fails first and what it printed. Do not fix the kit or write the machine file yourself. Moving the kit to a new version and the go-live script are Will's steps.

Check 6 contacts the dashboard host. Run it only when Will has asked for a live check.

### 1. The kit is at 0.3 or later

Both runner scripts must hold the line that starts the reporter.

```sh
grep -m1 'version:' <kit>/manifest.yaml
grep -n 'runner_report.py" --watch' <kit>/bin/run_queue.sh <kit>/bin/run_task.sh
```

Pass: the version is 0.3.0 or later, and grep prints one line from each script. On 6 October 2026 it printed 0.2.0 and no lines.

### 2. The machine file is present and names the dashboard

```sh
ls -l ~/.config/runner-kit/dashboard.conf
grep -c '^DASHBOARD_URL=' ~/.config/runner-kit/dashboard.conf
grep -c '^DASHBOARD_TOKEN=.' ~/.config/runner-kit/dashboard.conf
```

Pass: the file exists, is readable by its owner only (`-rw-------`), and each count is 1. The counts show that the lines exist without printing the token. Never print the file. The go-live script writes it.

### 3. Nothing switches reporting off or sends it elsewhere

The reporter takes the first address that is set, in this order: `RUNNER_DASHBOARD_URL` in the environment, `DASHBOARD_URL` in the project's `runner.conf`, `DASHBOARD_URL` in the machine file. The values `off`, `none` and `no` mean report to nobody.

```sh
echo "${RUNNER_DASHBOARD_URL:-unset}"
grep -n '^DASHBOARD_URL=' runner.conf
```

Pass: the first prints `unset`, and the second prints nothing or `DASHBOARD_URL=` with no value.

### 4. The python3 the queue will use can reach the dashboard

This check fails silently if skipped.

```sh
command -v python3
python3 <kit>/bin/runner_report.py --check; echo "exit $?"
```

| Exit | Meaning |
|---|---|
| 0 | Pass. The line printed is the dashboard's address followed by where it was set. |
| 3 | No dashboard is set. |
| 1 | A dashboard is set and cannot be used. The line says why and names the python3 that was tried. |

On this Mac `/usr/bin/python3` cannot reach the dashboard's address and `/opt/homebrew/bin/python3` can. The address is on the tailnet, the private Tailscale network this Mac shares with the dashboard's host. The guide's author did not re-test this on 6 October 2026; `manifest.yaml` records the same refusal for the python3 shipped with Xcode.

The queue runs whichever `python3` comes first on the PATH of the shell or tmux server that started it. If `command -v python3` prints `/usr/bin/python3`, start the queue with Homebrew first:

```sh
env PATH=/opt/homebrew/bin:$PATH tmux new -d -s <project>-runner <kit>/bin/run_queue.sh
```

`<kit>/bin/runner-doctor` with no arguments runs this check too and prints one `dashboard` line.

### 5. The reporter started and says so

```sh
tail -5 runs/report.log
grep 'dashboard:' runs/queue.log | tail -3
cat runs/report.lock/pid
```

Pass: `runs/report.log` exists and both logs hold a line `dashboard: reporting to <address>`. `runs/report.lock/pid` holds the reporter's process id while it runs. A later line `dashboard: ... still trying` means the dashboard was lost. The runner carries on, and the queue log records the loss at most once an hour.

### 6. The pane appears

Open `https://<dashboard-host>:18860/runners/` on a device on the tailnet. A runner that starts gets its own pane without a reload. From a terminal, reading needs no token:

```sh
curl -fsS -m 10 https://<dashboard-host>:18860/runners/api/poll | /opt/homebrew/bin/python3 -c 'import json,sys; [print((r.get("info") or {}).get("project"), r.get("state"), r.get("age")) for r in json.load(sys.stdin)["runners"]]'
```

Pass: one line per runner, with the project's name and the seconds since its last report. This address was planned and not live on 6 October 2026.

### 7. Attach a reporter to a queue that is already running

A queue started before the kit reached 0.3 has no reporter until its next task starts. To attach one now, from the workspace:

```sh
python3 <kit>/bin/runner_report.py
```

With no arguments it finds the queue through `runs/queue.lock/pid`, detaches, and reports until that queue ends. It exits at once, silently, if no dashboard is set or if this workspace is already reporting. Then repeat check 5.

- If the queue was started with `RUNNER_CONF` and from another directory, set `RUNNER_CONF=<workspace>/runner.conf` in front.
- If it was started with `QUEUE_ORDER` or `QUEUE_RUNS` pointing somewhere unusual, add `--order <file>` and `--runs <directory>`.

This step was read in the script and not run on 6 October 2026, because no dashboard was set.

### See a report without sending it

```sh
python3 <kit>/bin/runner_report.py --once --print | head -40
```

### Three limits

- The dashboard is a view of the files and never the record. `TASKS.md` and the logs stay the truth.
- A dry pass (`QUEUE_DRY=1`) starts no reporter.
- A runner on one machine reporting to a dashboard on another had not been run before 6 October 2026. The first real queue after go-live is that test.
