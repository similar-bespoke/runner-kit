#!/usr/bin/env python3
"""The runner's refusals: rules from DELIVERY-RULES.yaml that a session cannot argue with.

    runner_checks.py start <id>                  before a task's first session
    runner_checks.py staged <id> <repo>          git pre-commit hook, on the staged diff
    runner_checks.py commits <id> <repo> <base>  after a session, on each of its commits

Exit 0 when every check passes. Otherwise exit 1 with one line per failure,
each starting "RUNNER CHECK:". The checks:

  prerequisite  a task named after "Needs" or "Depends on" is not done
  new task      a commit adds more than one task heading to TASKS.md, or an id
                with a second suffix such as 2.10c1; waived, with growth
                and gate, when the commit records a decision signed "(owner, "
  growth        TASKS.md grows by more than 20 lines in one commit
  gate          a line added to TASKS.md or RUN-ORDER.md says a task may not
                start before or until something, without citing "(owner,"
  caller        a function added under a product directory (PRODUCT_DIRS) of a
                code repository (REPOS) has no reference outside tests, no
                entry in the registry file (REGISTRY_FILE, if set), and no
                task still in RUN-ORDER.md names this task as its input
  new file      a file is added that the task's own text does not name
  live switch   a live write flag (LIVE_FLAG_PATTERN in LIVE_FLAG_FILE, if set)
                is switched on while an open task says the user would
                see something false or a claim is lost

The project's settings are read from the file named by RUNNER_CONF, or
runner.conf in the current directory. The hooks and run_task.sh set
RUNNER_TASK_ID; nothing here runs for a commit made outside a runner session.
"""
import io
import os
import re
import subprocess
import sys
import tokenize


def load_conf():
    """KEY=value lines of runner.conf; one pair of quotes round a value is dropped."""
    path = os.environ.get("RUNNER_CONF") or os.path.join(os.getcwd(), "runner.conf")
    conf = {}
    try:
        lines = open(path, encoding="utf-8").read().split("\n")
    except OSError:
        sys.exit(f"RUNNER CHECK: no settings file at {path}; set RUNNER_CONF")
    for line in lines:
        m = re.match(r"([A-Z_]+)=(.*)$", line)
        if m:
            value = m.group(2).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            conf[m.group(1)] = value
    return conf


CONF = load_conf()
WORKSPACE = os.path.realpath(CONF["WORKSPACE"])
TASKS = os.path.join(WORKSPACE, "TASKS.md")
WSREPO = os.path.realpath(subprocess.run(["git", "-C", WORKSPACE, "rev-parse", "--show-toplevel"],
                                         capture_output=True, text=True).stdout.strip() or WORKSPACE)
WS_REL = os.path.relpath(WORKSPACE, WSREPO)
WS_REL = "" if WS_REL == "." else WS_REL + "/"
TASKS_REL = WS_REL + "TASKS.md"            # paths inside the repository that holds the workspace
ORDER_REL = WS_REL + "RUN-ORDER.md"
DECISIONS_REL = WS_REL + "DECISIONS.md"
CODE_REPOS = [os.path.realpath(r) for r in CONF.get("REPOS", "").split()]
PRODUCT_DIRS = tuple(CONF.get("PRODUCT_DIRS", "").split())
FREE_DIRS = tuple(CONF.get("FREE_DIRS", "").split())
REGISTRY_FILE = CONF.get("REGISTRY_FILE", "")
LIVE_FLAGS = CONF.get("LIVE_FLAG_PATTERN", "")
LIVE_FLAG_FILE = CONF.get("LIVE_FLAG_FILE", "")
MAX_GROWTH = 20
DEF = re.compile(r"\s*(?:async\s+)?def\s+(\w+)\s*\(")
HEADING = re.compile(r"^#{3,4} (\d+\.\d+[a-z0-9]*)\b")
TASK_ID = re.compile(r"\b(\d+\.\d+[a-z]?\d*[a-z]?)(?![\w.])")
SECOND_SUFFIX = re.compile(r"^\d+\.\d+[a-z]+\d")
GATE = re.compile(r"(?i)\b(?:(?:does|do|must|may|can|is|are|will) not|cannot|never) (?:be )?"
                  r"(?:start|begin|run|taken|started|begun)\w*\b[^.]*\b(?:before|until)\b"
                  r"|\bnot (?:be )?started (?:before|until)\b")


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True).stdout


def sections(text):
    """Task id -> (heading line, section text), for every ### or #### task heading."""
    lines, out, current = text.split("\n"), {}, None
    for line in lines:
        m = HEADING.match(line)
        if m or line.startswith("## "):
            current = None
        if m and "(as proposed)" not in line and "as originally written" not in line:
            current = m.group(1)
            out[current] = [line, []]
        elif current:
            out[current][1].append(line)
    return {k: (v[0], "\n".join(v[1])) for k, v in out.items()}


def done(heading):
    return "[x]" in heading


def check_start(task_id):
    tasks = sections(open(TASKS).read())
    if task_id not in tasks:
        return []
    heading, body = tasks[task_id]
    failures = []
    for clause in re.findall(r"\b(?:Needs|Depends on)\b:?\s+([^\n]*)", heading + "\n" + body):
        clause = re.split(r"\.(?:\s|$)", clause)[0]
        for need in TASK_ID.findall(clause):
            if need != task_id and need in tasks and not done(tasks[need][0]):
                failures.append(f"prerequisite: task {task_id} needs {need}, which is not done; run {need} first")
    return failures


def parse_diff(diff):
    """File path -> (added lines, removed lines) from a -U0 unified diff."""
    files, path = {}, None
    for line in diff.split("\n"):
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
            if path:
                files.setdefault(path, ([], []))
        elif line.startswith("--- "):
            old = line[6:] if line.startswith("--- a/") else None
            if old:
                files.setdefault(old, ([], []))
                path = old
        elif path and line.startswith("+"):
            files[path][0].append(line[1:])
        elif path and line.startswith("-"):
            files[path][1].append(line[1:])
    return files


def references(repo, name):
    """How many times `name` appears as a code token (not in a string or comment) outside tests."""
    hits = subprocess.run(["grep", "-rlw", "--include=*.py", name, *[d for d in PRODUCT_DIRS if os.path.isdir(os.path.join(repo, d))]],
                          cwd=repo, capture_output=True, text=True).stdout.split()
    count = 0
    for rel in hits:
        try:
            source = open(os.path.join(repo, rel), encoding="utf-8").read()
            count += sum(1 for tok in tokenize.generate_tokens(io.StringIO(source).readline)
                         if tok.type == tokenize.NAME and tok.string == name)
        except (OSError, SyntaxError, tokenize.TokenError, UnicodeDecodeError):
            count += 2   # unreadable: do not refuse on it
    return count


def registered(repo, rel, name):
    """A registry file names the function with its module: something calls it by that string."""
    if not REGISTRY_FILE:
        return False
    try:
        source = open(os.path.join(repo, REGISTRY_FILE), encoding="utf-8").read()
    except OSError:
        return False
    return bool(re.search(rf'"{re.escape(rel[:-3].replace("/", "."))}",\s*"{re.escape(name)}"', source))


def queued_consumer(task_id):
    """A task still in RUN-ORDER.md, not done, whose text names task_id: the code's caller is on its way."""
    order = os.path.join(WORKSPACE, "RUN-ORDER.md")
    try:
        queued = [line.split()[0] for line in open(order) if line.strip() and not line.startswith("#")]
    except OSError:
        return False
    tasks = sections(open(TASKS).read())
    named = re.compile(rf"(?<![\w.]){re.escape(task_id)}(?![0-9a-z])")
    return any(q != task_id and q in tasks and not done(tasks[q][0]) and named.search(tasks[q][0] + tasks[q][1])
               for q in queued)


def check_diff(task_id, repo, diff, added_files, before_tasks):
    failures = []
    files = parse_diff(diff)
    repo = os.path.realpath(repo)
    code = repo in CODE_REPOS            # the caller and live-switch checks are for code repositories
    in_ws = repo == WSREPO               # the TASKS.md checks are for the repository holding the workspace
    free = FREE_DIRS + ((WS_REL + "runs/",) if in_ws else ())
    body = sections(open(TASKS).read()).get(task_id, ("", ""))
    task_text = body[0] + "\n" + body[1]

    # A commit that records a decision signed by the owner may add tasks and
    # text: the limits below are for findings, not for the owner's decisions.
    owner_decides = in_ws and any("(owner, " in line for line in files.get(DECISIONS_REL, ([], []))[0])
    tasks_change = files.get(TASKS_REL) if in_ws else None
    if tasks_change and not owner_decides:
        added, removed = tasks_change
        known = set(sections(before_tasks)) if before_tasks else set()
        new_ids = [m.group(1) for m in (HEADING.match(line) for line in added) if m and m.group(1) not in known]
        if len(new_ids) > 1:
            failures.append(f"new task: this commit adds {len(new_ids)} task headings ({', '.join(new_ids)}); at most one. "
                            "Put other findings in one line each of the commit message")
        for i in new_ids:
            if SECOND_SUFFIX.match(i):
                failures.append(f"new task: {i} is a sub-task of a sub-task; name it from the base task or leave it out")
        growth = len(added) - len(removed)
        if growth > MAX_GROWTH:
            failures.append(f"growth: TASKS.md grows by {growth} lines; at most {MAX_GROWTH}. "
                            "A done note is three lines; check output belongs in the commit message")
    for rel in ((TASKS_REL, ORDER_REL) if in_ws else ()):
        text = " ".join(" ".join(files.get(rel, ([], []))[0]).split())
        for m in GATE.finditer(text):
            around = text[max(0, m.start() - 200):m.end() + 100]
            if "(owner," not in around and not owner_decides:
                failures.append(f"gate: '{m.group(0)[:90]}' sets a start condition; only a decision signed (owner, <date>) may")

    for rel, (added, removed) in files.items():
        if rel.endswith(".py") and rel.startswith(PRODUCT_DIRS) and code:
            before = {m.group(1) for m in (DEF.match(l) for l in removed) if m}
            for n, line in enumerate(added):
                m = DEF.match(line)
                if not m or m.group(1) in before:
                    continue
                name = m.group(1)
                decorated = n > 0 and added[n - 1].lstrip().startswith("@")
                if decorated or name == "main" or name.startswith(("__", "do_", "test_")):
                    continue
                if references(repo, name) <= 1 and not registered(repo, rel, name) and not queued_consumer(task_id):
                    failures.append(f"caller: {rel} adds {name}(), which nothing outside tests uses and no queued task "
                                    "names this task as its input; wire it in or leave it out")
        if code and LIVE_FLAGS and LIVE_FLAG_FILE and rel.endswith(LIVE_FLAG_FILE):
            if any(re.search(LIVE_FLAGS, line) for line in added):
                risky = [i for i, (h, b) in sections(open(TASKS).read()).items()
                         if "[ ]" in h and "accepted by the owner" not in h
                         and re.search(r"(?m)^Kept in the run order.*(would see something false|is lost)", b)]
                if risky:
                    failures.append("live switch: a live write is switched on while open tasks say the user would see "
                                    f"something false or a claim is lost: {', '.join(risky)}. Finish them, or the owner "
                                    "writes 'accepted by the owner' in their headings")

    for rel in added_files:
        if rel.startswith(free):
            continue
        if os.path.basename(rel) not in task_text:
            failures.append(f"new file: {rel} is not named in task {task_id}'s text; the task must name every new file")
    return failures


def check_staged(task_id, repo):
    diff = git(repo, "diff", "--cached", "-U0", "--no-color", "--no-ext-diff")
    added = git(repo, "diff", "--cached", "--name-only", "--diff-filter=A").split()
    before = git(repo, "show", f"HEAD:{TASKS_REL}") if TASKS_REL in diff else ""
    return check_diff(task_id, repo, diff, added, before)


def check_commits(task_id, repo, base):
    failures = []
    for line in git(repo, "log", "--format=%H %s", f"{base}..HEAD").splitlines():
        sha, _, subject = line.partition(" ")
        if not re.match(rf"{re.escape(task_id)}[ :]", subject):
            continue   # another session's commit in the same window
        diff = git(repo, "show", "-U0", "--no-color", "--format=", sha)
        added = git(repo, "show", "--name-only", "--diff-filter=A", "--format=", sha).split()
        before = git(repo, "show", f"{sha}^:{TASKS_REL}") if TASKS_REL in diff else ""
        failures += [f"{sha[:9]} {f}" for f in check_diff(task_id, repo, diff, added, before)]
    return failures


def main(argv):
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    mode, task_id = argv[1], argv[2]
    if mode == "start":
        failures = check_start(task_id)
    elif mode == "staged" and len(argv) == 4:
        failures = check_staged(task_id, argv[3])
    elif mode == "commits" and len(argv) == 5:
        failures = check_commits(task_id, argv[3], argv[4])
    else:
        print(__doc__, file=sys.stderr)
        return 2
    for f in failures:
        print(f"RUNNER CHECK: {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
