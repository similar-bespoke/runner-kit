# runner-kit

A protocol for setting up a powerful coding agent runner infrastructure that reduces token usage and ensures output quality across multi-sessions. It runs off one coordinating task and can be used with any coding agent.

A small kit that lets a coding agent work through a written list of tasks, unattended, one fresh session per task, with the rules that matter enforced by code at commit time.

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
