- Review, before committing, automatic, one reviewer: stage the diff, then
  spawn one review subagent with the Agent tool, model and effort from the
  task's R column (for example `model: "opus"`), with this prompt: "Review
  the staged diff in the repository or repositories task <ID> changes,
  against task <ID> in <WORKSPACE>/TASKS.md.
  Report only defects in this diff: a bug, or a way the done-when check
  passes with wrong behaviour, each with file, line and a concrete
  reproduction (the input and the wrong result it gives); and any file,
  config key, table, column, module or dependency the task does not name.
  Do not report style, comments, missing tests, failures you cannot
  reproduce, or work for other tasks. Do not propose tasks. NONE if
  nothing." Run it in the foreground if the tool offers the choice, and wait
  for it to report before editing again or ending your turn. Fix each finding,
  or say in the commit message why it is wrong. Nothing a reviewer says
  becomes a task. Paste its findings, and what you did with each, into the
  commit message under the check output.
