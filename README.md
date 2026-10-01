# runner-kit

A protocol for setting up a powerful coding agent runner infrastructure that reduces token usage and ensures output quality across multi-sessions. It runs off one coordinating task and can be used with any coding agent to work through a written list of tasks, unattended, one fresh session per task, with the rules that matter enforced by code at commit time.

## Why this exists

The kit came out of one private project. For six months the project was built in long coding sessions, each asked to carry a plan of several phases from start to finish. The git history of that period, 1,858 commits, shows what that produced:

- About one commit in three (33%) repaired earlier work. Its subject line used a word such as fix, repair, revert or restore.
- About one in four (24%) changed no code at all: plans, coordination notes and evidence files written by sessions about their own work.
- No commit named a written task. There was no list to check a commit against.
- One commit in six (16%) changed more than 500 lines.

The runner replaced those sessions with a written queue of small tasks, one fresh session per task, and rules checked by code when a session commits. In the first four days with the rules enforced (96 commits):

- 3% of commits repaired earlier work, and 1% were paperwork only.
- 99% began with the id of the task they delivered.
- 97 tasks were run. 88% of queue runs ended in a finished task, and a task took 1.16 sessions on average. The median finished task took about 15 minutes.

![Share of commits before the runner and with it: repairs 33% then 3%, paperwork only 24% then 1%, tied to a written task 0% then 99%](docs/before-after.svg)

The rules mattered as much as the queue. The runner first ran for six days with its rules written down but not enforced. In that week 17% of queue runs ended in a finished task, and a task took 2.61 sessions on average. Once a commit hook enforced the rules, 88% of runs ended in a finished task.

How to read these numbers:

- They come from one project and one owner, and the runner period is four days. Treat them as a record of what happened, not a benchmark.
- "Repaired earlier work" is counted from words in commit subjects. It misses repairs described another way and counts some new work that mentions a fix.
- Token use before the runner was not measured, so this page makes no claim about tokens saved. With the runner, the median task used about 7.5 million tokens, most of them cached re-reads of the same context.
- The two periods differ in more than the runner: the work itself changed, and so did the models.

## What it is

- **A protocol** (`PROTOCOL.md`): who does what, how a task is written, how the queue runs, what happens when a task stops, and when something counts as live.
- **Two scripts with no model in them**: `bin/run_queue.sh` walks the queue and `bin/run_task.sh` runs one task to its commit, retrying and resuming on its own.
- **Commit checks** (`bin/runner_checks.py`): a git pre-commit hook that refuses, for example, a new file the task does not name or a function nothing calls.
- **Adapters** (`adapters/`): one file per agent. Claude Code and Codex are included; `adapters/TEMPLATE.sh` is the contract for adding another.
- **Notifiers** (`notify/`): log only, a desktop notice, or your own command.

The person the work is for is called the owner. The owner sets outcomes and answers product questions once, in writing. Everything else is delegated.

## Install: one step

Open `INSTALL-PROMPT.md`, copy everything below its line, and paste it into your coding agent, started in your project. The agent clones the kit, reads `manifest.yaml`, `interview.yaml` and `PROTOCOL.md`, asks you only what it cannot find out itself, installs, and runs the self-test. It must not report success unless the self-test prints `SELFTEST: PASS`.

To check a machine by hand: `bin/runner-doctor`. To run the self-test by hand: `selftest/run.sh --adapter claude --model <model id>`, or `selftest/run.sh --no-agent` on a machine with no signed-in agent.

## Requirements

- git
- python3, 3.9 or newer (standard library only)
- zsh, 5 or newer. The scripts are zsh and are not ported to another shell.
- tmux, to run the queue unattended
- At least one supported agent command-line tool, installed and signed in: Claude Code (`claude`) or Codex (`codex`)

## What is proven and what is not

`manifest.yaml` holds the full record, under `adapters` and `status`. In short:

- **Proven, on macOS, with the Claude Code adapter:** the self-test passes (a dry queue pass, one real task to its commit with one reviewer, the commit check refusing an unnamed file, the notifier). The queue has also run one real task from start to finish.
- **Experimental: the Codex adapter.** Its review step can be refused by Codex's own approval reviewer, and its resume and failure handling through the runner are untested. Nothing has been run through the adapter file as it stands in this kit.
- **Not proven:** Linux; stop sessions, parking and release in a real queue; resuming a session; usage-limit and network-error handling; a project with more than one code repository; the `deploy.sh` skeleton against a real host.

Task sessions run unattended and may run shell commands in the repositories you name. Read `PROTOCOL.md` before you start a queue.

## Licence

GNU General Public License, version 3. See `LICENSE`.
