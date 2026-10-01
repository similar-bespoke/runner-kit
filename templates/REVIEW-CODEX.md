- Review, before committing, automatic, one reviewer: stage the diff, then
  run this one command, once, from the repository that holds the staged
  diff, and wait for it to finish:

      codex exec review -m <MODEL> -c model_reasoning_effort="<REFFORT>" --ephemeral "Review the staged diff (git diff --cached) in this repository against task <ID> in <WORKSPACE>/TASKS.md. Report only defects in this diff: a bug, or a way the done-when check passes with wrong behaviour, each with file, line and a concrete reproduction (the input and the wrong result it gives); and any file, config key, table, column, module or dependency the task does not name. Do not report style, comments, missing tests, failures you cannot reproduce, or work for other tasks. Do not propose tasks. NONE if nothing."

  It is this same Codex command-line tool, signed in to the same account as
  this session, and it sends the diff to the same service this session
  already uses. It cannot start inside the sandbox (it needs its own home
  directory), so request to run it outside the sandbox. Do not edit while it
  runs. Fix each finding, or say in the commit message why it is wrong.
  Nothing a reviewer says becomes a task. Paste its findings, and what you
  did with each, into the commit message under the check output. If the
  command is refused or fails, do not review by another route and do not
  commit: end with `RUNNER: blocked` and quote the refusal or error.
