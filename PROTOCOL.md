# The runner protocol

One set of instructions for any coding agent working on any project. The person the work is for is called **the owner**. Where this file and a project's own rules differ, a decision signed by the owner in that project's `DECISIONS.md` wins, then this file.

`<kit>` below means the directory this file is in. What has been run and what has not is recorded in `<kit>/manifest.yaml`, not here.

## 1. The idea

Work is cut into small tasks written down in one file. A plain script, not a model, takes the next task, starts a fresh agent session on that task alone, and checks afterwards that a commit landed. Rules that matter are enforced by code at commit time, so a session cannot argue with them. The owner is asked only what only the owner can answer, once, in writing. Nothing counts as progress until the owner can open it.

Each rule here exists because of an observed failure: sessions that drifted, findings that bred tasks, the same question asked many times, code with no caller, deploys reported live that were not, and tests that stayed broken for days because each session only noted it and moved on.

## 2. Who does what

- **The owner** sets outcomes, answers product questions, and takes actions only the owner can take (passwords, sign-ins).
- **The supervising session** is the agent the owner is talking to. It writes no product code and runs no experiments. It designs, writes tasks, orders the queue, records decisions, deploys, reads the live result back and reports.
- **The runner** is two scripts with no model in them. `run_queue.sh` walks the queue. `run_task.sh` runs one task to its commit.
- **A task session** is a fresh, unattended agent session started by the runner for one task. It knows only what the task and the named files tell it.
- **The reviewer** is one reviewer the task session starts on its staged diff before committing.
- **The stop session** is a fresh, unattended supervising session the runner starts when a task stops. It makes one decision and ends.
- **A watcher** is a background subagent the supervising session starts to wait for a commit, deploy it and report (section 10).

## 3. The files of a project

All in one workspace directory, under git.

| File | What it holds |
|---|---|
| `DESIGN.md` | What is being built and why. Tasks cite it. |
| `TASKS.md` | Every task, with its status in its heading. The only record of what is done. |
| `RUN-ORDER.md` | The queue: one task id per line, in order. Lines starting `#` are comments saying who ordered the block and when. |
| `DECISIONS.md` | One dated line per decision, signed. Append only. |
| `DELIVERY-RULES.yaml` | The project's numbered outcomes (G1, G2 and so on) and its rules, each with the failure that caused it. |
| `SESSION-PROMPT.md` | The first message of every task session. |
| `REVIEW-<ADAPTER>.md` | The reviewer step for each agent, placed into the session prompt. |
| `SUPERVISOR-PROMPT.md` | The first message of every stop session. |
| `runner.conf` | The project's settings (`<kit>/schema/runner.conf.schema.json`). |
| `runs/` | Logs, the queue log, the notice log, parked tasks (`waiting/<id>`), the live commit (`live-sha`). Not hand-edited, not in git. |
| `deploy.sh` | The only way anything goes live (section 9). Absent in a project that does not deploy. |
| `HANDOFF-<date>.md` | State and a prompt for the next supervising session. |

## 4. A task

A task is the smallest change that delivers one outcome the owner can read or use. Its entry is at most 15 lines. An example from a to-do application:

```
### 2.3 A ticked item stays ticked after the page is reloaded [ ]  M: O medium, R: O high
G1, G3: the list shows only what is left to do.
Ordered by the owner, <date>. Observed: <the failure, with the row, log line or time>.
Files: <every file it may touch, and every new file by name>.
Build: <what to build, at the nearest existing boundary. About N lines.>
Done when: <a check on real or copied data that shows the outcome, not "tests pass">.
Owner sees: <what changes for the owner once it is live>.
```

Rules for writing one:

- The heading is a sentence stating the outcome, not an activity. Its exact form is in `<kit>/schema/task-heading.json`.
- It names at least one project outcome (a G id). A task that serves none is not written.
- It cites an observed failure (a run file, log line, live row or failing test) or an order from the owner. A hunch is one line in a commit message, never a task.
- `Files:` lists every file. A session may touch another file only to call, register or import what the task builds.
- A prerequisite is written `Needs <id>`. Only missing code counts as a prerequisite.
- A new model question (a new prompt or classifier question) is measured on stored cases first, as its own task with no product code. It is built only if it beats the current rule on the same cases.
- An id has at most one suffix (`3.2a`, never `3.2a1`).
- Status in the heading: `[ ]` not started, `[~]` built but held, `[x]` done with the commit hash. A done task keeps at most three lines of notes. Check output and review findings go in the commit message.

## 5. Choosing the model

The heading's `M:` column names who builds and at what effort; `R:` names the reviewer. Each is a letter and an effort word. `runner.conf` maps every letter to an agent (`ADAPTER_<letter>`, a file in `<kit>/adapters/`) and to a model id (`MODEL_<letter>`). The starting letters:

| Letter | Builder | Use for |
|---|---|---|
| `S` | The faster, cheaper model | Most tasks: any task whose Build line names the functions, the cases and the check. Also inventory and search. |
| `O` | The strongest model | Complex work: logic across several files, a rule that decides what the user sees, a measurement, a design. And every review. |
| `C` | A second agent | Work the owner orders for that agent. Try it on real tasks before a queue relies on it; `<kit>/manifest.yaml` gives each adapter's status. |

Builders run at `medium` effort. The reviewer is `O high` unless the owner says otherwise: the one reviewer is what catches a weaker first draft, so that is where the strongest model at its highest effort is spent. A task with no `M:` column is the owner's own and the runner parks it. A task with `R: owner` stops at `[~]` when built, and only the owner marks it `[x]`.

Pin the exact model id in `runner.conf`. An alias can resolve to an older model for days without anyone noticing.

The letter and the effort are the largest cost choices anyone makes for a task. In the project this kit came from, a task built on the strongest model at high effort cost about twice one built on it at medium effort and about four times one built on the cheaper model, and all three finished as often. Counted per line changed, the reviewer found about as many defects in the cheaper model's diffs as in the strongest model's. The tasks were not alike, so this is a record and not a comparison; `runs/usage.log` gives the same figures for your own project, one line per session. A task whose Build line names the functions, the cases and the check is one the cheaper model can build.

## 6. How the queue runs

`run_queue.sh` runs unattended in a tmux session, one task at a time:

1. Each pass re-reads `RUN-ORDER.md` and takes the first id that is in `TASKS.md`, not `[x]` and not parked. Editing the queue file is how the order changes; nothing is restarted.
2. It calls `run_task.sh <id>`. Exit 0 means done. Any other exit starts a stop session (section 8).
3. A parked task has a file `runs/waiting/<id>` holding a hash of `DECISIONS.md` and the reason. It is tried again only when the owner appends an answer. Entries signed by a supervising session are left out of the hash, so one session's note cannot release every parked task.
4. When nothing is runnable it tells the owner once that the queue is idle and which tasks wait for the owner, then checks again every five minutes.
5. When three different tasks stop one after another (`STOP_STREAK` in `runner.conf`; 0 switches this off), the queue pauses and tells the owner once. That many stops in a row more likely share a cause (the session prompt, the model, the project's check, the machine) than have one each, and running on would spend a session and a stop session on every task left in the queue. It starts again when `TASKS.md`, `RUN-ORDER.md`, `DECISIONS.md`, a prompt or `runner.conf` changes, or on `touch runs/queue.go`.
6. `touch runs/queue.stop` stops it after the current task. A lock stops a second copy starting.

`run_task.sh` for one task:

1. Checks before spending anything: that the agent's command is installed and signed in, that the repository exists, and that every `Needs` task is done.
2. Starts a fresh session with `SESSION-PROMPT.md`, the task's model and effort, and edit permission. The session id is saved, so a later attempt resumes the same session with its context.
3. Afterwards, done means two facts: a commit whose subject starts with the task id, and `[x]` on the heading. It then re-runs the commit checks on that commit, which catches a bypassed hook.
4. It runs the project's own check itself (`CHECK_CMD` in `runner.conf`, for example the test suite): once before the task's first session and again on the task's commit. It does not take the session's word that the check passes. If the check passed before and fails on the commit, the same session is sent back, with the output, to repair it; the task is done only when the check passes again. If the check already failed before the task, the owner is told once, the task runs, and its done message says the commit was not judged against the check. A result is kept with the commits it was run on, so the check after one task serves as the check before the next.
5. If not done, it reads the session's own result and acts: a failed sign-in stops for the owner; a network or overload error waits and resumes with doubling delay; a usage limit sleeps until the stated reset; two attempts with no commit and no changed file stop the task; otherwise it resumes, up to four attempts.
6. It tells the owner when a task is done, how many built changes are not live, and the deploy command.

## 7. What a task session does

The session prompt, in order:

1. Read the project's README, design, this task only, and the delivery rules. Then only the files the task names.
2. Do the task and nothing else, as the smallest change that delivers its outcome. Reuse the existing path before adding a module, field, status, retry, queue, script or model question.
3. Run the done-when check. Tests passing is not the outcome.
4. Stage the diff and start exactly one reviewer, told to report only reproducible bugs in this diff, ways the check passes with wrong behaviour, and anything outside the task's named scope, each with input, wrong result, file and line. Fix each finding or say in the commit why it is wrong. Nothing a reviewer says becomes a task.
5. Commit once, task id first in the subject, with the check output and the reviewer's findings in the message. Never bypass the commit hook.
6. Mark the task `[x]` with the commit.
7. Report what the owner can read or use once it is live, and separate built from live.
8. End with exactly one last line, which is all the runner reads:

```
RUNNER: done <commit hash>
RUNNER: blocked <one sentence: what stops it and which file or test>
RUNNER: question <one sentence for the owner, with the recommended answer>
```

A session makes engineering choices itself. It asks the owner only when the choice changes what the product shows, files, sends or keeps, affects privacy, or needs an action only the owner can take. It decides on the first attempt whether the task can be done as written; a resume does not change that answer.

## 8. When a task stops

The runner starts a stop session with the stop line and the log. It reads the rules, the last ten decisions, the task and the log's last 80 lines, then decides. It may edit only the task file, the decisions file, the session prompt and the queue; never product code, and never the kit's scripts, which every project shares. It may add at most one task, and only code the stopped task cannot finish without. It records its decision in `DECISIONS.md` with the reason and ends with one line:

```
SUPERVISOR: retry <id>
SUPERVISOR: run <id> [<id> ...] then <id>
SUPERVISOR: waiting <id> <one sentence for the owner with the recommended answer>
SUPERVISOR: skip <id> <why>
```

When the stop line says the project's check passed before the task and fails on its commit, the commit is in and the task is marked done, so the stop session adds the one task that makes the check pass again and orders it first.

A task gets two such rounds. Its third stop parks it for the owner. A question for the owner is written once; no session restates an open question or reruns a parked task.

## 9. Rules enforced by code

A git pre-commit hook in every repository the project touches runs `runner_checks.py` whenever the runner's task variable (`RUNNER_TASK_ID`) is set. It refuses a commit that:

- adds more than one task, or an id with a second suffix;
- grows `TASKS.md` by more than 20 lines;
- writes a start condition ("does not start before", "may not run until") that the owner did not sign;
- adds a function to product code that nothing outside the tests calls, unless a queued task names this one as its input;
- adds a file the task's text does not name;
- switches on a live write while an open task says the user would see something false.

A commit recording a decision signed `(owner, <date>)` is exempt from the first three. When a check is wrong, the fix is to correct the check with a recorded decision, not to bypass it.

**The check is run by the runner.** The hook judges the shape of a commit. Whether the project still works is judged by the project's own check, and `run_task.sh` runs that itself, before the task and on its commit (section 6). A session's statement that the tests pass is not evidence.

**Each check is proven.** `<kit>/selftest/run.sh` makes one bad commit per check and confirms the refusal, makes one good commit and confirms it is accepted, and drives the runner's own logic with a stand-in session that spends nothing (`<kit>/adapters/stub.sh`). A check with no case there is listed as untested in `<kit>/manifest.yaml`.

**Live means checked.** Everything goes live through `deploy.sh <commit>` in the workspace. It stops before pushing if the host cannot be reached, deploys, restarts each service, and prints `LIVE` only when the running system reports that commit and every process started after the deploy began. Only then does it write `runs/live-sha`. `deploy.sh check` reports the state at any time. No one says "live" without that word on the screen.

## 10. The supervising session's routine

1. On starting, read the handoff, the delivery rules, recent decisions and the queue. Check live state with `deploy.sh check`, the queue log and the repository's log. Trust none of the handoff until checked.
2. Design with the owner one question at a time, each with a recommended answer. Settle engineering choices alone, visibly and reversibly, and record them.
3. Record every decision in `DECISIONS.md` as it is made, signed `(owner, <date>)` or `(supervising session, <date>)`, with the reason, and commit it before the next question.
4. Turn designs into tasks (section 4) and place them in `RUN-ORDER.md`. A specification that needs thought is written by a subagent on the strongest model; inventory, search and deploys go to subagents on the cheaper model.
5. Deploy at each deploy point a task names, as soon as its commit lands, through a watcher. Never block the conversation on a wait.
6. After each deploy, read the first live result against its source: open the page or the data and compare it with the message, row or file it came from. A subagent's report is evidence to check, not a fact to pass on.
7. Report to the owner what is live, what is running, how many built changes are not live, and what waits for the owner. Never give test counts as progress.
8. When a live fault appears, find the narrow cause, queue one task for it and say what the owner sees until it lands.
9. Before the session ends, write the handoff.

**The watcher's brief.** A background subagent on the cheaper model, told: write no code and touch no file; wait in loops of under ten minutes until a commit starting `<id>:` appears; stop without deploying if the queue log shows the task parked, or after a stated time; run `deploy.sh <full commit hash>` once; run `deploy.sh check`; return the commits deployed, the check's full output, whether it printed LIVE, and any line that looks like a failure, quoted. It must not claim live without that word.

## 11. Notices and watching

- The runner sends the owner a short message when a task is done, stops, is parked or the queue goes idle. `NOTIFY` in `runner.conf` picks the route: `none` (the log only), `desktop` (a desktop notice) or `command` (the owner's own command, which receives the message as one argument). It is best effort and never blocks the runner. Every message is also a line in `runs/notify.log`.
- `runs/queue.log` is the runner's log. Each session's full transcript is kept beside it.
- `runs/usage.log` has one line per session: the task, the attempt, the letter and effort, the minutes, and what the adapter reports the session used (turns, tokens, cost at list price). Read it before deciding what letter and effort the next tasks get.
- `<kit>/bin/runner-queue` shows the task in hand, tasks parked for the owner, and the tasks remaining, refreshed every ten seconds. `runner-queue once` prints it once; `runner-queue log` follows the log.

## 12. Rules that carry to every project

The same rules, with where each is checked and whether code enforces it, are in `<kit>/rules.yaml`.

1. Every task names an outcome the user gets. Work that serves none is parked.
2. A task comes from an observed failure or the owner's order, never from a reviewer's suggestion.
3. Measure a new model question on stored cases before any product code.
4. No function without a caller, no file the task does not name, no machinery for a failure nobody has seen.
5. One reviewer per task, on the diff only.
6. A question for the owner is asked once and waits; engineering is not the owner's to answer.
7. A supervising session writes no product code.
8. Deploy early and often; ten built changes not live is a stop.
9. Live is what the deploy check says, then what the first live result shows against its source.
10. Progress is something the owner can open.
11. No approval steps or pass marks the owner did not ask for. Delegated models decide visibly and reversibly.
12. The runner, not the session, says whether the project's check passes.
13. Three different tasks stopping in a row is a fault in the system, not in the tasks: pause and put the system right.

## 13. Starting this on a new project

1. Write `DESIGN.md` and the outcomes list with the owner.
2. Run `<kit>/bin/runner-init [--deploy] <workspace-dir> <repo-dir> [<repo-dir> ...]`. The workspace must be inside a git repository. It copies the two prompts, the reviewer steps, a starter `DELIVERY-RULES.yaml` holding the rules of section 12, a starter `TASKS.md`, an empty `DECISIONS.md` and `RUN-ORDER.md` into the workspace, and never overwrites a file. It writes `runner.conf`. With `--deploy` it copies the `deploy.sh` skeleton. It installs the pre-commit hook in each named repository and in the repository that holds the workspace, but only where there is no pre-commit hook; where one exists it prints the one line to add and changes nothing.
3. Fill `runner.conf`: the project name, the product directories for the caller check, the directories free of the new-file check, the notifier, the pre-flight command, the project's own check (`CHECK_CMD`), and an adapter and a pinned model id for each letter. The registry file and the live flag are optional. Check it with `<kit>/bin/runner-doctor <workspace-dir>/runner.conf`.
4. Put the project's outcomes in `DELIVERY-RULES.yaml`. Add a rule only when a failure is observed.
5. Write the project's own commands into `deploy.sh` so that it proves live as section 9 requires, or state in the rules that the project has no deploy. Without a `deploy.sh` the runner's done message says nothing about live.
6. Write the first tasks and the queue file. From the workspace, check with `QUEUE_DRY=1 QUEUE_ONCE=1 <kit>/bin/run_queue.sh`, then start with `tmux new -d -s <project>-runner <kit>/bin/run_queue.sh`. Watch with `<kit>/bin/runner-queue`.

The workspace is flat: `RUN-ORDER.md`, `SUPERVISOR-PROMPT.md` and `runs/` sit beside `TASKS.md`. The task variable is `RUNNER_TASK_ID`, and every script finds the project through `RUNNER_CONF` or a `runner.conf` in the directory it is started from. Keep `runs/` out of git.
