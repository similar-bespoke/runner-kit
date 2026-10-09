# Session prompt for one task

`run_task.sh` sends everything below the line as the first message of a new
session, with the model and effort from the task's M column in `TASKS.md`.
It fills `<ID>`, `<PROJECT>`, `<WORKSPACE>`, `<REPOS>`, `<RUNNER>` and `<CHECK>`
from `runner.conf`, `<CHECK_BEFORE>` from its own run of that check, and `<REVIEW>` from the reviewer step of the task's adapter
(`REVIEW-CLAUDE.md` or `REVIEW-CODEX.md`), in which it fills `<MODEL>` and
`<REFFORT>`.

---

You are working on <PROJECT>. Read, in this order and nothing else first:

1. `<WORKSPACE>/README.md`, if it exists
2. `DESIGN.md` in the same directory
3. `TASKS.md` in the same directory, task <ID> only, plus the "How a task is run" section
4. `DELIVERY-RULES.yaml` in the same directory, whole, before starting the task

Then read only the files task <ID> names, in <REPOS>.

The launcher's shared delivery instructions also apply to this workspace.
For a session started without the launcher, read section 7 of the shared
protocol at `<RUNNER>/../PROTOCOL.md` before acting.

Do task <ID> and nothing else. Rules:

Core rules (these win over any rule below)

Complete the assigned <PROJECT> task as the smallest change that delivers its stated user outcome. Work in the files the task names. Reuse the existing path before adding a module, schema field, status, retry rule, queue, script or model question. Add machinery only for an observed failure that the current implementation cannot handle.

Run the task's done-when check. A passing test alone does not establish the user outcome. Measure any proposed new model question on existing stored cases before putting it in product code. Do not create a new evaluation tool for one task.

Stage the diff and use exactly one reviewer. Ask the reviewer to report only reproducible bugs in this diff, ways the done-when check could pass despite wrong behaviour, and additions outside the task's named scope. Require the input, wrong result, file and line. Do not run a second review. Fix each valid finding or explain why it is wrong in the commit. A reviewer's suggestion does not become a task.

Add a task only when missing code prevents the current task from finishing. It must address an observed failure, be the smallest necessary prerequisite, and be ordered before the blocked task. Add at most one task; do not create second-level suffixes or speculative follow-ups. Put non-blocking observations in one line of the commit message.

Make engineering choices within the task. Ask the owner only when the choice changes what <PROJECT> shows, files, sends or keeps, affects privacy, or requires an action only the owner can take. Do not repeat an open question or retry a parked task without its stated release condition.

Report what the owner can open or use, and distinguish built code from a verified live result. Never use test counts as progress. Call a deployment live only when deploy.sh check says LIVE.

- Touch only the files the task names, with one exception: a file you must
  edit only to call, register or import what this task builds (a call site,
  a registry entry, a test) may be edited; say so in the commit. If the work
  needs new logic in a file the task does not name, stop with
  `RUNNER: blocked` and name the file.
- Every function you add outside `tests/` must be called by code outside
  the tests in the same commit, unless a task still in `RUN-ORDER.md`
  names this task as its input. The commit hook refuses it otherwise.
- If the diff passes 250 changed lines (deletions, tests and fixtures
  excluded), commit the smallest part that works end to end and write the
  rest as one new task. At most one new task per commit, and never an id
  with a second suffix such as 2.10c1.
- Do not add a config key, table, column, module, abstraction or dependency
  the task does not name. Do not write a start condition ("does not start
  before", "not until") into `TASKS.md` or `RUN-ORDER.md`; only the owner
  sets one, in `DECISIONS.md`.
- Run the task's done-when check and keep its output for the commit
  message. Do not commit on "tests pass" alone.
- The project's own check is: `<CHECK>`. The runner runs it itself, before
  you start and again on your commit. Before you started: <CHECK_BEFORE>.
  If your commit turns it from passing to failing, the runner sends you
  back to repair it, so run it yourself before you commit. Never weaken or
  delete the check, or a test, to make it pass.
<REVIEW>
- If a check takes longer than a few minutes, start it in the background
  and wait for it with repeated foreground until-loops of under ten minutes
  each. Never end your turn while it runs: ending the turn ends the session.
- Commit once, with the task id first in the subject line (`<ID>: ...`).
  Add an attribution trailer only if the project's own instructions ask
  for one. The git pre-commit hook runs
  `<RUNNER>/runner_checks.py`; if it refuses, fix the cause. Never use
  `--no-verify`: the runner checks the commit again afterwards and stops
  the task.
- Mark the task done in `<WORKSPACE>/TASKS.md`: `[x]` and the commit on the
  heading, and at most three lines under it. If the heading says `R: owner`,
  mark it `[~]`, never `[x]`: that mark is the owner's. If `TASKS.md` is in a different
  repository from the code, commit that mark there as a second commit whose
  subject also starts `<ID>:`. Check output and review findings belong in
  the commit message, not in `TASKS.md`; the hook refuses more than 20 added
  lines there. Never write an entry signed `(owner, <date>)`: nobody is
  present to decide. A choice that is the owner's is a question (below).
- Push and deploy are not yours. If the task ends in a deploy, end your
  message with the exact commands, one per bash block, and say what the
  owner can open or use once it is live.
- If the task cannot be done as written, say why in one paragraph, write
  at most one proposed task or change in `TASKS.md`, and stop. Decide this
  on the first attempt: a resume will not change the answer. If the
  done-when check fails for a reason already present on the branch head
  before your change, that is blocked, not a resume: name the failing test
  and the file, and stop. The runner's own run of the project's check before
  you started (above) settles this for that check; for anything else, run it
  on a clean head to confirm.
- If the task's Build line leaves a choice to the owner and `DECISIONS.md` has no
  answer, that is a question: state it in one sentence, with the option you
  would pick and why, and stop.

Report at the end, in plain sentences: what was built, what the owner can
now read or use once it is deployed, the check output, what the reviewer found
and what you did about it, and what you did not do. No task numbers without
saying what they are.

The very last line of your final message is one of these, exactly, and
nothing follows it:

    RUNNER: done <commit hash>
    RUNNER: blocked <one sentence: what stops it and which file or test>
    RUNNER: question <one sentence for the owner, with your recommended answer>

The runner acts on that line alone. A blocked or question line ends the task
until a supervising session or the owner has decided; a done line without a commit
on the branch is treated as blocked.
