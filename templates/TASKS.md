# Tasks

## How a task is run

The workspace prompts are `SESSION-PROMPT.md` (what a task session
does), `SUPERVISOR-PROMPT.md` (what happens when a task stops) and
`DELIVERY-RULES.yaml` (the rules). `runner_checks.py` in the runner kit
(`<KIT>/bin/`) enforces the rules it can, through the git pre-commit hook in
each repository and through `run_task.sh`. The order is `RUN-ORDER.md`. The
full instructions are `<KIT>/PROTOCOL.md`. Its shared delivery instructions
are included by the launcher on every task attempt and stop session, so an
older workspace prompt still receives the current workflow.

Model and effort per task, in the M column: a letter that `runner.conf` maps
to an agent and a model (`ADAPTER_<letter>`, `MODEL_<letter>`), then the
effort. R is the one reviewer's letter and effort. A task with no M column is
the owner's and the runner parks it. A task with `R: owner` stops at `[~]`
when built.

A task id is a number, a dot, a number and at most one letter (`1.1`,
`3.2a`). Status: [ ] not started, [~] built but held, [x] done (commit).

## Tasks

### 1.1 The example outcome, stated as a sentence [ ]  M: S medium, R: O high
G1: the outcome this serves.
Ordered by the owner, <date>. Observed: <the failure, with the row, log line or time>.
Files: <every file it may touch, and every new file by name>.
Build: <what to build, at the nearest existing boundary. About N lines.>
Done when: <the observable outcome and sufficient evidence on real or copied data; name required regression checks separately when they establish different behaviour>.
Owner sees: <what changes for the owner once it is live>.
