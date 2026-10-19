# Invoking the internal runner kit from any coding agent

Private network addresses are redacted in this distributable reference. Use the project's configured dashboard host.

Written 6 October 2026. Every rule below cites the kit file it comes from. "Verified" means I read the script or ran the command on this Mac that day. UNKNOWN means the kit's files do not say. Line numbers refer to the version 0.3 development checkout at `/Users/wb-m37/dev/runner-kit` as it stood that day, with uncommitted changes; they may move by a few lines when it is pushed.

## The short answer

Paste prompt 1 to start a project. Paste prompt 2 to run or supervise one. Both work in Claude Code, Codex or any agent that can run shell commands, because the kit is plain files and scripts.

The dashboard needs three things: the kit at version 0.3 or later, the machine file, and a python3 that can reach the dashboard. On 6 October 2026 none of the three is in place. The internal kit is at version 0.2 (commit d4dec28). The machine file does not exist. The dashboard is not live. Section 3 gives the command that checks each one.

## Terms used here

- **The kit**: the checkout at `/Users/wb-m37/coding/workspaces/runner-kit`. The prompts call it `<kit>`. It is a clone of `github.com/similar-bespoke/runner-kit`.
- **Workspace**: one project's directory. It holds `TASKS.md` (every task and its status), `RUN-ORDER.md` (the queue: one task id per line), `DECISIONS.md`, `runner.conf` (the project's settings) and `runs/` (logs and state). Source: `PROTOCOL.md` section 3.
- **The queue**: `<kit>/bin/run_queue.sh`. It takes the next task from `RUN-ORDER.md` and calls `<kit>/bin/run_task.sh` for it. Neither script contains a model. Source: `PROTOCOL.md` sections 2 and 6.
- **Task session**: a fresh agent session the runner starts for one task.
- **Supervising session**: the agent session the owner is talking to. It designs, writes tasks, orders the queue and reports. It writes no product code. Source: `PROTOCOL.md` section 2.
- **Stop session**: a fresh supervising session the queue starts by itself when a task stops. It makes one decision and ends. Source: `PROTOCOL.md` section 8.
- **Parked task**: a task waiting for the owner. Its marker is the file `runs/waiting/<id>`. Source: `PROTOCOL.md` section 6, item 3.
- **The reporter**: `<kit>/bin/runner_report.py`. It reads the workspace's files every two seconds and sends what changed to the dashboard. It exists only from version 0.3. Source: `PROTOCOL.md` section 11.
- **The machine file**: `~/.config/runner-kit/dashboard.conf`. It names the dashboard for every runner on this Mac. Source: `README.md`, "Watching the runners".
- **tmux**: a program that keeps a command running after its terminal closes. The kit uses it to run the queue unattended. Source: `README.md`, "Requirements".
- **The tailnet**: the private Tailscale network that this Mac and the Etta host share. The planned dashboard address is on it.

## 1. Prompt to start a new project

Replace the three values in angle brackets on the first lines. Paste the rest unchanged.

```
You are the supervising session for a new project on the runner kit. I am the owner.

Project name: <PROJECT>
What I want built: <ONE PARAGRAPH>
Does it deploy anywhere: <yes or no>

The kit is /Users/wb-m37/coding/workspaces/runner-kit. Below, <kit> means that path.
Before acting, read these three files in full: <kit>/PROTOCOL.md, <kit>/manifest.yaml, <kit>/interview.yaml.
Follow PROTOCOL.md. If this prompt and PROTOCOL.md differ, PROTOCOL.md wins. Tell me the difference.

Rules for you:
- You write no product code and run no experiments. You design, write tasks, order the queue, record decisions and report. (PROTOCOL.md section 2.)
- Do not edit, pull, reset or upgrade anything inside <kit>. Every project shares it. If a step cannot be followed as written, stop and tell me which step.
- Change nothing outside the workspace and the repositories I name.
- Ask me only product questions, one at a time, each with your recommended answer. Settle engineering choices yourself and record them. (PROTOCOL.md section 10, items 2 and 3.)
- Never write a token or secret into runner.conf or any file in git.
- Do not start the queue. Finish at the dry pass and wait for my yes.

Steps, in order:
1. Run <kit>/bin/runner-doctor and show me its output. Stop if any line starts MISSING.
2. The workspace is /Users/wb-m37/coding/workspaces/<PROJECT>. Create it with mkdir -p. It must be inside a git repository that tracks its files. The parent repository at /Users/wb-m37/coding ignores workspaces/*, so run git init in the workspace unless it already is a repository.
3. Run <kit>/bin/runner-init [--deploy] <workspace> <repo> [<repo> ...]. Use --deploy only if I said the project deploys. Each <repo> is a code repository the task sessions will change. If the code lives in the workspace itself, name the workspace as the repo. Show me every line it prints. If it prints a line to add to an existing hook or .gitignore, add it only on my yes.
4. Write DESIGN.md with me: what is being built and why.
5. Put my outcomes in DELIVERY-RULES.yaml as goal_outcomes (- id: G1 / outcome: "..."), and set meta.written to today's date. Add no rule unless a failure has been observed.
6. Fill runner.conf by editing the KEY=value lines in place. One KEY=value per line, no spaces round the =, no comment after a value, single quotes round a value with spaces or symbols. At least: PROJECT, PRODUCT_DIRS, FREE_DIRS, CHECK_CMD, NOTIFY, an ADAPTER_ and a MODEL_ for each letter in use, DEFAULT_BUILDER, DEFAULT_REVIEWER, SUPERVISOR, DEPLOYS and LIVE_CHECK_CMD. Pin exact model ids, never aliases. Ask me for the model ids if I have not given them. Leave DASHBOARD_URL empty, so the machine's own setting applies.
7. Run <kit>/bin/runner-doctor <workspace>/runner.conf and show me its output. Stop if any line starts MISSING.
8. Run <kit>/selftest/run.sh --conf <workspace>/runner.conf and show me its output exactly as printed. It starts one small agent session. Report success only if the last line is SELFTEST: PASS. On PARTIAL or FAIL, show the failing line and the log path, and stop.
9. If the project deploys, write the project's commands into <workspace>/deploy.sh and run <workspace>/deploy.sh check. If it does not, state in DELIVERY-RULES.yaml that the project has no deploy.
10. Write the first tasks in TASKS.md as PROTOCOL.md section 4 sets out, with the heading form in <kit>/schema/task-heading.json. Delete the example task. Each task names a G outcome, cites an observed failure or my order, lists every file, and has a done-when check on real or copied data. Put the task ids in RUN-ORDER.md, one per line.
11. Record each decision in DECISIONS.md as it is made, one dated line, signed (owner, <date>) for mine and (supervising session, <date>) for yours, with the reason. Commit the workspace files, naming each path.
12. From the workspace, run the dry pass and show me the output: QUEUE_DRY=1 QUEUE_ONCE=1 <kit>/bin/run_queue.sh
13. If <kit>/bin/runner_report.py exists, record yourself as the session in charge, from the workspace: python3 <kit>/bin/runner_report.py --in-charge
    If it answers that the shell does not say which agent session it belongs to, run it again as: python3 <kit>/bin/runner_report.py --in-charge --agent <claude|codex> --session <your session identifier>
14. Stop. Tell me the command that starts the queue and wait: cd <workspace> && tmux new -d -s <PROJECT>-runner <kit>/bin/run_queue.sh
```

Where each step comes from:

| Step | Source |
|---|---|
| Read three files first | `INSTALL-PROMPT.md` step 2; `manifest.yaml` header |
| 1, 7 | `manifest.yaml` install steps 1 and 6; `bin/runner-doctor` header ("ok", "MISSING" or "WARN", exit 0 when nothing is MISSING) |
| 2 | `manifest.yaml` install step 2; `PROTOCOL.md` section 13, item 2. The `git init` line is local: `/Users/wb-m37/coding/.gitignore` holds `workspaces/*` (verified) |
| 3 | `bin/runner-init` usage line; `manifest.yaml` install step 3 |
| 4, 5 | `PROTOCOL.md` section 13, items 1 and 4; `manifest.yaml` install step 5 |
| 6 | `manifest.yaml` install step 4; the comments in `templates/runner.conf`; `PROTOCOL.md` section 5 (pin the model id) |
| 8 | `manifest.yaml` install step 7 and `selftest`; `INSTALL-PROMPT.md` steps 6 and 7 |
| 9 | `PROTOCOL.md` section 13, item 5, and section 9 |
| 10 | `PROTOCOL.md` section 4; `manifest.yaml` `after_install` |
| 11 | `PROTOCOL.md` section 10, item 3; `manifest.yaml` install step 9 |
| 12, 14 | `PROTOCOL.md` section 13, item 6; `INSTALL-PROMPT.md` rules ("Do not start the queue") |
| 13 | `PROTOCOL.md` section 10, item 1; `bin/runner_report.py` lines 904 to 924 |

Local practice, seen in all three kit workspaces (`helm-chain`, `inner-loop-contributions`, `innerloop-clef`): the workspace is its own git repository, and `REPOS` names the workspace itself. Their `runner.conf` files set `MODEL_S=claude-sonnet-5-5` and `MODEL_O=claude-opus-5-5`. These are observations, not kit rules.

## 2. Prompt to run or supervise an existing workspace

Replace `<WORKSPACE>` on the first line. Paste the rest unchanged.

```
You are the supervising session for the runner workspace <WORKSPACE>. I am the owner.

The kit is /Users/wb-m37/coding/workspaces/runner-kit. Below, <kit> means that path.
Read <kit>/PROTOCOL.md in full before acting, and follow it. If this prompt and PROTOCOL.md differ, PROTOCOL.md wins. Tell me the difference.

Rules for you:
- You write no product code and run no experiments.
- Do not edit, pull, reset or upgrade anything inside <kit>.
- Do not edit files in runs/ by hand. The only writes you make there are the commands this prompt names.
- Do not rerun a parked task and do not ask me again a question that is already open.
- Never bypass a commit hook. Never say "live" unless deploy.sh printed LIVE.
- Sign your own DECISIONS.md entries (supervising session, <date>). Sign an entry (owner, <date>) only when it records an answer I gave you.

On starting, in this order:
1. cd <WORKSPACE>. Read the newest HANDOFF-<date>.md if there is one, DELIVERY-RULES.yaml, the recent entries of DECISIONS.md, and RUN-ORDER.md. Read the project's own OPERATIONS.md or README if it has one, for how this project starts its queue.
2. Trust none of the handoff until checked. Check with:
   <kit>/bin/runner-queue once
   tail -40 runs/queue.log
   git log -10 --format='%h %s'
   ./deploy.sh check        (only if the workspace has a deploy.sh)
3. Is a queue running? Run: pid=$(cat runs/queue.lock/pid 2>/dev/null); [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && echo "queue running, pid $pid" || echo "no queue running"
4. If <kit>/bin/runner_report.py exists, record yourself as the session in charge, from the workspace: python3 <kit>/bin/runner_report.py --in-charge
   If it answers that the shell does not say which agent session it belongs to, run: python3 <kit>/bin/runner_report.py --in-charge --agent <claude|codex> --session <your session identifier>
5. Report to me: what is live, what is running, how many built changes are not live, what waits for me. Do not give test counts as progress.

To start the queue (only when I say so):
- Dry pass first, from the workspace: QUEUE_DRY=1 QUEUE_ONCE=1 <kit>/bin/run_queue.sh
- If the project documents its own start command (OPERATIONS.md, a scripts/ launcher), use that one unchanged.
- Otherwise, from the workspace: tmux new -d -s <project>-runner <kit>/bin/run_queue.sh
- A second copy will not start: the queue holds a lock in runs/queue.lock. Do not remove the lock.

To watch it:
- <kit>/bin/runner-queue          the task in hand, parked tasks, tasks remaining; refreshes every 10 seconds
- <kit>/bin/runner-queue once     the same, printed once
- <kit>/bin/runner-queue log      follows runs/queue.log

To run one task by hand, with no queue, from the workspace: <kit>/bin/run_task.sh <task-id> [max-attempts]
Exit codes: 0 done, 1 attempts exhausted, 2 usage or setup, 3 needs the owner, 4 the session says blocked or asks a question, 5 the session split the task.

To change the order: edit RUN-ORDER.md. The queue re-reads it on every pass. Restart nothing.

To stop the queue after its current task: touch runs/queue.stop

If the queue has paused (three different tasks stopped one after another, or a task could not be started): find the shared cause in SESSION-PROMPT.md, the model, CHECK_CMD or this machine, and put it right. The queue resumes when TASKS.md, RUN-ORDER.md, DECISIONS.md, a prompt or runner.conf changes, or on: touch runs/queue.go

Parked tasks: ls runs/waiting/ lists them. Each file holds a hash and then the reason: sed -n 2p runs/waiting/<id>
A parked task runs again only when my answer is appended to DECISIONS.md. Put the question to me once, with your recommended answer. When I answer, append my answer as one dated line signed (owner, <date>) and commit it. Do not delete a waiting file and do not rerun the task yourself.
A task with no M column is mine, and the queue parks it. A task with R: owner stops at [~] when built, and only I mark it [x].

When a deploy point comes: deploy through a background watcher, as PROTOCOL.md section 10 sets out. Never block our conversation on a wait. After each deploy, read the first live result against its source.

Before you end: write HANDOFF-<date>.md with the state and a prompt for the next supervising session.
```

Where each line comes from:

| Line | Source |
|---|---|
| Start-up reading and checks | `PROTOCOL.md` section 10, item 1 |
| `--in-charge`, and `--agent` with `--session` | `PROTOCOL.md` section 10, item 1; `bin/runner_report.py` docstring and lines 904 to 924 (verified: it reads `CLAUDE_CODE_SESSION_ID` or `CODEX_THREAD_ID`, else needs both flags, and writes `runs/in-charge`) |
| Report contents | `PROTOCOL.md` section 10, item 7 |
| Dry pass and tmux start | `PROTOCOL.md` section 13, item 6; `bin/run_queue.sh` header lines 8 to 12 and 41 to 45 |
| The lock | `bin/run_queue.sh` `main`, lines 291 to 299 (verified) |
| Watching | `bin/runner-queue` header; `PROTOCOL.md` section 11 |
| One task by hand, exit codes | `bin/run_task.sh` header lines 6 and 18 to 21 |
| Changing the order | `PROTOCOL.md` section 6, item 1 |
| Stop file | `PROTOCOL.md` section 6, item 6; `bin/run_queue.sh` header line 11. A stop file left from an earlier run is removed when a queue starts (line 301) |
| Pause and `queue.go` | `PROTOCOL.md` section 6, item 5; `bin/run_queue.sh` `pause`, lines 282 to 288 |
| Parked tasks | `PROTOCOL.md` section 6, item 3, and section 8; `bin/run_queue.sh` header lines 15 to 29 |
| Signing | `PROTOCOL.md` section 10, item 3. Entries signed by a supervising session are left out of the hash that releases parked tasks (`bin/run_queue.sh` `decisions_hash`, lines 76 to 91), so only an owner's entry releases one |
| Watcher, handoff | `PROTOCOL.md` section 10, items 5, 6 and 9 |

Three local facts to know when you paste prompt 2:

- `helm-chain` starts its queue with `scripts/pipeline start`. `inner-loop-contributions` and `innerloop-clef` each document a start command in `OPERATIONS.md` that uses its own tmux socket (`tmux -L <project> new-session -d -s <project>-runner -c <workspace> ...`). All three end in the kit's `bin/run_queue.sh` (verified). The prompt tells the agent to use the project's own command where one exists.
- With its own socket, the tmux session is not in plain `tmux ls`. Use `tmux -L <project> ls`.
- `PROTOCOL.md` section 10 writes the in-charge command as `<kit>/bin/runner_report.py --in-charge`, with no `python3` in front. In the unpushed 0.3 checkout on 6 October the file is not marked executable (git mode 100644, verified), so that form fails with "permission denied". The `python3` form in the prompts works either way.

UNKNOWN: how an agent finds its own session identifier when its shell carries neither variable. The kit does not say. `manifest.yaml` (under `status`, `untested`) records that `CODEX_THREAD_ID` is a name found in the Codex binary and was not seen in a Codex shell, and that `CLAUDE_CODE_SESSION_ID` was seen in the Claude Code desktop app only. I confirmed that the Claude Code desktop shell carries `CLAUDE_CODE_SESSION_ID` on this Mac. A Claude Code terminal session and a Codex session are unchecked.

## 3. What makes the dashboard operate

A runner reports only when all of these hold. Run each check from the workspace unless it says otherwise. `<kit>` is `/Users/wb-m37/coding/workspaces/runner-kit`.

1. **The kit is at 0.3 or later.** Both runner scripts must hold the line that starts the reporter.

   ```
   grep -m1 'version:' <kit>/manifest.yaml
   grep -n 'runner_report.py" --watch' <kit>/bin/run_queue.sh <kit>/bin/run_task.sh
   ```

   Pass: the version is 0.3.0 or later, and grep prints one line from each script. On 6 October it prints 0.2.0 and no lines. Source: `bin/run_queue.sh` line 303 and `bin/run_task.sh` line 108 in 0.3.

2. **The machine file is present and names the dashboard.**

   ```
   ls -l ~/.config/runner-kit/dashboard.conf
   grep -c '^DASHBOARD_URL=' ~/.config/runner-kit/dashboard.conf
   grep -c '^DASHBOARD_TOKEN=.' ~/.config/runner-kit/dashboard.conf
   ```

   Pass: the file exists, is readable by its owner only (`-rw-------`), and each count is 1. The counts show that the lines exist without printing the token. The go-live script writes this file. Source: `README.md`, "Watching the runners"; `bin/runner_report.py` docstring.

3. **Nothing switches reporting off or sends it elsewhere.** The reporter takes the first address that is set, in this order: `RUNNER_DASHBOARD_URL` in the environment, `DASHBOARD_URL` in the project's `runner.conf`, `DASHBOARD_URL` in the machine file. The values `off`, `none` and `no` mean report to nobody.

   ```
   echo "${RUNNER_DASHBOARD_URL:-unset}"
   grep -n '^DASHBOARD_URL=' runner.conf
   ```

   Pass: the first prints `unset`, and the second prints nothing or `DASHBOARD_URL=` with no value. Source: `bin/runner_report.py`, function `dashboard`, lines 125 to 141 (verified). On 6 October no kit workspace sets `DASHBOARD_URL`.

4. **The python3 the queue will use can reach the dashboard.** This is the check that fails silently if skipped.

   ```
   command -v python3
   python3 <kit>/bin/runner_report.py --check; echo "exit $?"
   ```

   Pass: exit 0, and the line printed is the dashboard's address followed by where it was set. Exit 3 means no dashboard is set. Exit 1 means it is set and cannot be used; the line says why and names the python3 that was tried. Source: `bin/runner_report.py` `main`, lines 883 to 901 (verified).

   On this Mac `/usr/bin/python3` cannot reach the tailnet address and `/opt/homebrew/bin/python3` can. I did not re-test this, because I was told to contact no host; `manifest.yaml` records the same refusal for the python3 shipped with Xcode. The queue runs whichever `python3` comes first on the PATH of the shell or tmux server that started it. On 6 October both live tmux servers have `/opt/homebrew/bin` ahead of `/usr/bin` (verified with `tmux show-environment -g`). If `command -v python3` prints `/usr/bin/python3`, start the queue with Homebrew first: `env PATH=/opt/homebrew/bin:$PATH tmux new -d -s <project>-runner <kit>/bin/run_queue.sh`. `bin/runner-doctor` prints the same advice on a failure.

   `<kit>/bin/runner-doctor` (no arguments) runs this check too and prints one `dashboard` line.

5. **The reporter started and says so.**

   ```
   tail -5 runs/report.log
   grep 'dashboard:' runs/queue.log | tail -3
   cat runs/report.lock/pid
   ```

   Pass: `runs/report.log` exists and both logs hold a line `dashboard: reporting to <address>`. `runs/report.lock/pid` holds the reporter's process id while it runs. A later line `dashboard: ... still trying` means the dashboard was lost; the runner carries on, and the queue log hears of it at most once an hour. Source: `bin/runner_report.py` docstring and `report_until_done`, lines 798 to 868.

6. **The pane appears.** Open `https://<dashboard-host>:18860/runners/` on a device on the tailnet. A runner that starts gets its own pane without a reload (`README.md`, "Watching the runners"). From a terminal, reading needs no token:

   ```
   curl -fsS -m 10 https://<dashboard-host>:18860/runners/api/poll | /opt/homebrew/bin/python3 -c 'import json,sys; [print((r.get("info") or {}).get("project"), r.get("state"), r.get("age")) for r in json.load(sys.stdin)["runners"]]'
   ```

   Pass: one line per runner, with the project's name and the seconds since its last report. Source: `dashboard/serve.py` (`/api/poll`); the same command is in the go-live script. This address is planned and not live on 6 October.

7. **Attach a reporter to a queue that is already running.** A queue started before the kit reached 0.3 has no reporter until its next task starts. To attach one now, from the workspace:

   ```
   python3 <kit>/bin/runner_report.py
   ```

   With no arguments it finds the queue through `runs/queue.lock/pid`, detaches, and reports until that queue ends. It exits at once, silently, if no dashboard is set or if this workspace is already reporting. Then repeat check 5. If the queue was started with `RUNNER_CONF` and from another directory, set `RUNNER_CONF=<workspace>/runner.conf` in front. If it was started with `QUEUE_ORDER` or `QUEUE_RUNS` pointing somewhere unusual, add `--order <file>` and `--runs <directory>`. Source: `bin/runner_report.py` docstring, class `Place`, and `main`, lines 925 to 951 (verified by reading; not run, because no dashboard is set).

To see what a report would hold without sending anything: `python3 <kit>/bin/runner_report.py --once --print | head -40`. Source: `bin/runner_report.py` docstring.

Three limits, all from the kit's own files:

- The dashboard is a view of the files and never the record. `TASKS.md` and the logs stay the truth. (`PROTOCOL.md` section 11.)
- A dry pass (`QUEUE_DRY=1`) starts no reporter. (`bin/run_queue.sh` line 303.)
- A runner on one machine reporting to a dashboard on another has not been run before. (`manifest.yaml`, `status`, `untested`.) The first real queue after go-live is that test.

## 4. What an agent must not do

Each line is a kit rule unless marked local.

1. Write product code or run experiments as a supervising session. (`PROTOCOL.md` section 2; section 12, rule 7.)
2. Edit the kit's scripts. Every project shares them. (`PROTOCOL.md` section 8; `INSTALL-PROMPT.md` rules.)
3. Local: pull, reset or upgrade the internal kit during project work. `inner-loop-contributions/OPERATIONS.md` and `innerloop-clef/DECISIONS.md` both record the kit as pinned at d4dec28. Moving it is the owner's step.
4. Hand-edit anything in `runs/`. (`PROTOCOL.md` section 3.) The kit's own commands are the exceptions: `touch runs/queue.stop`, `touch runs/queue.go`, and `runner_report.py --in-charge`.
5. Remove `runs/queue.lock` or start a second queue in one workspace. (`PROTOCOL.md` section 6, item 6.)
6. Bypass the commit hook. When a check is wrong, correct the check with a recorded decision. (`PROTOCOL.md` section 7, item 5, and section 9.)
7. Say "live" without the word LIVE printed by `deploy.sh`. (`PROTOCOL.md` section 9.)
8. Take a session's word that the tests pass. The runner runs `CHECK_CMD` itself. (`PROTOCOL.md` section 9; section 12, rule 12.)
9. Rerun a parked task, delete its waiting file, or restate an open question. A question for the owner is asked once and waits. (`PROTOCOL.md` section 8; section 12, rule 6.)
10. Sign an entry `(owner, <date>)` that the owner did not give. An owner's entry is what releases parked tasks. (`PROTOCOL.md` section 6, item 3; section 10, item 3.)
11. Write a task from a reviewer's suggestion or a hunch, or a task that names no outcome. (`PROTOCOL.md` section 4; section 12, rules 1 and 2.)
12. Add a function nothing calls, a file the task does not name, or machinery for a failure nobody has seen. (`PROTOCOL.md` section 9; section 12, rule 4.)
13. Start more than one reviewer on a task. (`PROTOCOL.md` section 7, item 4; section 12, rule 5.)
14. Use a model alias in `runner.conf`. Pin the exact id. (`PROTOCOL.md` section 5.)
15. Put a dashboard token in `runner.conf`, which is in git. It goes in the machine file or in `RUNNER_DASHBOARD_TOKEN`. (`templates/runner.conf`; `bin/runner_report.py` docstring.)
16. Let ten built changes pile up that are not live. That is a stop. (`PROTOCOL.md` section 12, rule 8.)
17. Give test counts as progress, or block the conversation on a wait. (`PROTOCOL.md` section 10, items 5 and 7.)
18. Add approval steps or pass marks the owner did not ask for. (`PROTOCOL.md` section 12, rule 11.)
19. Start the queue as part of setting a project up, before the owner says so. (`INSTALL-PROMPT.md` rules.)
20. Change anything outside the kit directory and the named project during an install. (`INSTALL-PROMPT.md` rules.)
