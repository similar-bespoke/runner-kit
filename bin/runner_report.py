#!/usr/bin/env python3
"""Tell a dashboard what one runner is doing.

    runner_report.py --watch <pid> [--task <id>]   started by run_queue.sh and run_task.sh
    runner_report.py                               attach to the queue already running here
    runner_report.py --once [--print]              send, or only print, one report
    runner_report.py --check                       can the dashboard be reached? exit 0 if so
    runner_report.py --in-charge                   run by a supervising session: record it as the
                                                   session in charge of this runner

A runner keeps everything it knows in its workspace: TASKS.md, RUN-ORDER.md
and runs/. This program reads those files every two seconds and sends the
dashboard (dashboard/serve.py) what changed: the task in hand, what has been
delivered, what waits for the owner, what the sessions used, the task file,
and the new lines of the session's output and of the queue log. It runs
beside the runner, detached, and nothing the runner does waits for it. It
writes its lock (runs/report.lock) and its log (runs/report.log), one line in
the queue log when it starts, and one there when the dashboard is lost or
found again (at most once an hour). It ends when the process it watches ends,
after one last report. It follows no redirect: a report and its token go to
the address that was set and to no other.

A report carries the runner's state and, with it, what is new in three files:
the task file, the session's output and the queue log. Where a report with
files in it does not arrive and one without them does (something on the way
takes small requests only, say), the files are tried again one kind at a
time and the logs in smaller pieces, so that what can arrive does; what still
cannot is named on the dashboard, in the runner's pane, and in this program's
log.

The dashboard's address is the first of these that is set:
    RUNNER_DASHBOARD_URL   in the environment
    DASHBOARD_URL          in the project's runner.conf
    DASHBOARD_URL          in ~/.config/runner-kit/dashboard.conf, which every
                           runner on the machine reads
With none set, or with the first one set to "off", this program does nothing
and exits 0. A dashboard started with a token file takes reports only with
that token: RUNNER_DASHBOARD_TOKEN in the environment, or DASHBOARD_TOKEN in
the machine's file beside the same address. A token never goes in runner.conf,
which is in git.

Each report names the agent session doing the work by the identifier its own
agent knows it by (a Claude Code session id, a Codex thread id), read from the
runner's logs, so the session can be opened again. A supervising session can
add itself with --in-charge, which writes runs/in-charge from the identifier
its own shell carries (CLAUDE_CODE_SESSION_ID or CODEX_THREAD_ID), or from
--agent and --session where the shell carries none. Nothing is taken from what
a queue inherited when it was started, because that may be another session's.

Settings are read from the file named by RUNNER_CONF, or runner.conf in the
current directory. A workspace with no runner.conf can be named in full with
--project and --workspace and, where they are not in the usual place, --tasks,
--order and --runs.
"""
import argparse
import atexit
import glob
import gzip
import hashlib
import http.client
import json
import os
import re
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVERY = 2                 # seconds between reports
TAIL = 48 * 1024          # how far back into a log a first report reaches
CHUNK = 256 * 1024        # the most text of one log a report carries
SMALLEST = 4 * 1024       # the least it comes down to, however often reports that carried more did not arrive
MOST_TASKS = 1536 * 1024  # bytes of a task file a report carries; a longer file is cut at a line, and says so
MARK = 64                 # bytes just before the place a file was read to, as a fingerprint: is it still the same file?
HEAD_MAX = 1000           # characters of a task heading that are read; a longer line is cut before any pattern is run on it
LAST_WORDS = 60           # seconds a finished runner keeps trying to send its last report
KINDS = {"tasks_md": "the task file", "out": "the session's output", "ev": "the queue log"}
STAMP = "%Y-%m-%d %H:%M:%S"
OFF = ("off", "none", "no")
AGENTS = {"claude": "Claude Code", "codex": "Codex"}
# An agent's identifier for a session. The dashboard offers it inside a command to paste into a terminal, so
# nothing that is not plainly an identifier is ever passed on as one.
SESSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
HEADING = re.compile(r"^#{3,4} (\d+\.\d+[a-z0-9]*)\s+(.*)$")
# The clock bin/render_stream.py puts before each event it writes ("%6.0fs", then two spaces), and the two lines
# that name the agent after it. selftest/dashboard.py reads these from that program's own output, so the two stay
# in step.
CLOCK = r"(?m)^(?=[ \d]{6}s|\d{7,}s) *\d+s  "
SAID = re.compile(CLOCK + "(" + "|".join(AGENTS) + "): ")
STARTED = re.compile(CLOCK + r"session started  codex thread=")
TASK_LOG = re.compile(r"^(.+)-(\d{8}-\d{6})\.log$")
QUEUE_LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (.*)$")
USAGE_LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) task (\S+) attempt (\d+) (\S+) (\S+): (\d+) min(.*)$")


# ---- settings

def load_keys(path):
    """KEY=value lines of a settings file; one pair of quotes round a value is dropped."""
    keys = {}
    try:
        lines = open(path, encoding="utf-8").read().split("\n")
    except OSError:
        return keys
    for line in lines:
        m = re.match(r"([A-Z_]+)=(.*)$", line)
        if m:
            value = m.group(2).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            keys[m.group(1)] = value
    return keys


def kit_version():
    try:
        return re.search(r"(?m)^\s*version:\s*(\S+)", open(os.path.join(KIT, "manifest.yaml"), encoding="utf-8").read()).group(1)
    except (OSError, AttributeError):
        return "unknown"


def machine_file():
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "runner-kit", "dashboard.conf")


def dashboard(conf):
    """(address, token, where the address was set). The address is empty when the runner reports to nobody."""
    machine = load_keys(machine_file())
    for url, source in ((os.environ.get("RUNNER_DASHBOARD_URL"), "RUNNER_DASHBOARD_URL"),
                        (conf.get("DASHBOARD_URL"), "runner.conf"),
                        (machine.get("DASHBOARD_URL"), machine_file())):
        if url:
            break
    else:
        return "", "", "no dashboard is set"
    if url.lower() in OFF:
        return "", "", f"switched off by {source}"
    url = url.rstrip("/")
    # The machine's token is for the machine's dashboard only: it is never sent to another address.
    token = os.environ.get("RUNNER_DASHBOARD_TOKEN") or (
        machine.get("DASHBOARD_TOKEN", "") if machine.get("DASHBOARD_URL", "").rstrip("/") == url else "")
    return url, token, source


class Place:
    """Where one runner's files are."""

    def __init__(self, args):
        path = os.environ.get("RUNNER_CONF") or os.path.join(os.getcwd(), "runner.conf")
        self.conf = load_keys(path) if os.path.isfile(path) else {}
        workspace = args.workspace or self.conf.get("WORKSPACE")
        if not workspace:
            sys.exit("runner_report.py: no settings file (set RUNNER_CONF or start from the directory that holds "
                     "runner.conf), and no --workspace")
        self.workspace = os.path.realpath(workspace)
        self.project = args.project or self.conf.get("PROJECT") or os.path.basename(self.workspace)
        self.tasks = os.path.realpath(args.tasks or os.path.join(self.workspace, "TASKS.md"))
        # A queue started with QUEUE_ORDER or QUEUE_RUNS hands them on to its tasks: both hooks must find one lock.
        self.order = os.path.realpath(args.order or os.environ.get("QUEUE_ORDER") or os.path.join(self.workspace, "RUN-ORDER.md"))
        self.runs = os.path.realpath(args.runs or os.environ.get("QUEUE_RUNS") or os.path.join(self.workspace, "runs"))
        # run_task.sh keeps its logs in the workspace's own runs/, wherever the queue's log is.
        self.logs = list(dict.fromkeys([self.runs, os.path.join(self.workspace, "runs")]))
        self.repos = [os.path.realpath(r) for r in self.conf.get("REPOS", "").split()]
        self.host = socket.gethostname().split(".")[0]
        self.id = hashlib.sha1(f"{self.host}\n{self.workspace}".encode()).hexdigest()[:12]


# ---- reading the workspace

def epoch(stamp, form=STAMP):
    """A local time as the runner's scripts write it, in seconds since 1970; None if it is not one."""
    try:
        return int(time.mktime(time.strptime(stamp, form)))
    except ValueError:
        return None


def read_text(path, last=None):
    """A file's text, or its last `last` bytes from the first whole line; empty if it cannot be read."""
    try:
        with open(path, "rb") as f:
            if last is not None and os.fstat(f.fileno()).st_size > last:
                f.seek(-last, os.SEEK_END)
                f.readline()
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def parse_tasks(text):
    """Every task in a TASKS.md, in the file's order: the parts of its heading, and its text."""
    tasks, seen, current = [], set(), None
    for line in text.split("\n"):
        # The patterns below backtrack: on a very long line they take longer than the square of its length, and a
        # task file is another's text. A heading is nowhere near this long.
        m = HEADING.match(line[:HEAD_MAX])
        if m or line.startswith("## "):
            current = None
        if m and m.group(1) not in seen and "(as proposed)" not in line[:HEAD_MAX] and "as originally written" not in line[:HEAD_MAX]:
            rest = m.group(2)
            mark = re.search(r"\[([ ~x])\]", rest)
            after = rest[mark.end():] if mark else ""
            builder = re.search(r"M: ([A-Z]) ([a-z]+)", after)
            reviewer = re.search(r"R: ([A-Z] [a-z]+|owner)", after)
            commit = re.match(r"\W*([0-9a-f]{7,40})\b", after) if "[x]" in rest else None
            current = {
                "id": m.group(1),
                "title": (rest[:mark.start()] if mark else rest).strip(),
                "status": "done" if "[x]" in rest else "held" if "[~]" in rest else "open",
                "note": re.split(r"\s+M: [A-Z] ", " " + after)[0].strip(),
                "letter": builder.group(1) if builder else "",
                "effort": builder.group(2) if builder else "",
                "reviewer": reviewer.group(1) if reviewer else "",
                "commit": commit.group(1) if commit else "",
                "body": [],
            }
            seen.add(current["id"])
            tasks.append(current)
        elif current is not None and not m:
            current["body"].append(line)
    for task in tasks:
        task["body"] = "\n".join(task["body"]).strip("\n")
    return tasks


def read_order(path):
    """The queue file's task ids, in order."""
    words = (line.split() for line in read_text(path).split("\n"))
    return [w[0] for w in words if w and not w[0].startswith("#")]


def read_usage(path):
    """runs/usage.log: one entry per session."""
    rows = []
    for line in read_text(path).split("\n"):
        m = USAGE_LINE.match(line)
        if not m:
            continue
        turns = re.search(r"(\d+) turns", m.group(7))
        tokens = re.search(r"(\d+(?:\.\d+)?)M tokens", m.group(7))
        cost = re.search(r"\$(\d+(?:\.\d+)?)", m.group(7))
        rows.append({"at": epoch(m.group(1)), "id": m.group(2), "attempt": int(m.group(3)), "minutes": int(m.group(6)),
                     "turns": int(turns.group(1)) if turns else None,
                     "tokens": float(tokens.group(1)) if tokens else None,
                     "cost": float(cost.group(1)) if cost else None})
    return rows


def load_usage(path):
    rows, by = read_usage(path), {}
    for row in rows:
        by.setdefault(row["id"], []).append(row)
    return {"rows": rows, "by": by}


def load_tasks(path):
    text = read_text(path)
    raw = text.encode()
    sent = text
    if len(raw) > MOST_TASKS:
        sent = raw[:MOST_TASKS].decode("utf-8", "ignore").rsplit("\n", 1)[0] + (
            "\n\n(This task file is longer than a dashboard takes. The rest of it is not shown here.)\n")
    return {"text": sent, "bytes": len(raw), "hash": hashlib.sha1(raw).hexdigest(), "tasks": parse_tasks(text)}


def total(rows, key):
    """The sum of what is known; None when nothing is."""
    known = [r[key] for r in rows if r.get(key) is not None]
    return round(sum(known), 2) if known else None


def queue_state(text):
    """What the last lines of the queue log say the queue is doing."""
    s = {"hand": None, "deciding": None, "stop_session": "", "idle": False, "paused": False, "stopped": False,
         "note": "", "last": None}
    for line in text.split("\n"):
        m = QUEUE_LINE.match(line)
        if not m:
            continue
        at, msg = m.group(1), m.group(2)
        if msg.startswith("queue started"):
            s.update(hand=None, deciding=None, idle=False, paused=False, stopped=False, note="")
        elif (t := re.match(r"task (\S+): running run_task\.sh", msg)):
            s.update(hand=t.group(1), idle=False, note="")
        elif (t := re.match(r"task (\S+): run_task\.sh exit (\d+)", msg)):
            s.update(hand=None, last={"id": t.group(1), "exit": int(t.group(2)), "at": epoch(at)})
        elif (t := re.match(r"supervising session (\S+) for task (\S+)", msg)):
            s.update(deciding=t.group(2), stop_session=t.group(1))
        elif msg.startswith("verdict:"):
            s["deciding"] = None
        elif msg.startswith("notify:") and " queue idle." in msg:
            s.update(idle=True, note=msg.split(" queue idle.", 1)[1].strip())
        elif msg.startswith("notify:") and " queue paused: " in msg:
            s.update(paused=True, note=msg.split(" queue paused: ", 1)[1].split(" The queue starts again")[0].strip())
        elif msg.startswith("queue resumed"):
            s.update(paused=False, note="")
        elif msg.startswith(("stop file found", "queue pass done")):
            s["stopped"] = True
    return s


def session_in(text):
    """The agent session a task's log names last: the id the runner chose, or the one the agent gave itself."""
    named = re.findall(r"(?m)^attempt \d+ of \d+: (?:new|resuming) session ?(\S*)", text)
    found = named[-1] if named else ""
    if not found:
        given = re.findall(r"session started\s+codex thread=(\S+)", text)
        found = given[-1] if given else ""
    return found if SESSION.match(found) else ""


def agent_of(conf, letter, builder=""):
    """The adapter behind a letter of runner.conf; without one, what the builder's name in a log suggests."""
    adapter = conf.get("ADAPTER_" + letter, "") if letter else ""
    low = builder.lower()
    return adapter or ("claude" if "claude" in low else "codex" if "codex" in low else "")


def agent_in(text):
    """The agent a session log was written by, from what bin/render_stream.py writes in it; empty when the log
    does not say. For a workspace whose settings are not known. A Codex session names itself when it starts
    ("session started  codex thread=..."), and that is taken first. Otherwise the lines written for what the agent
    said ("claude: ..." or "codex: ...") decide, when they all name one agent; where they name both, nothing is
    said. Only a line that begins with render_stream.py's clock counts: a line with no clock is something the
    agent's own program printed ("claude: command not found" in a Codex log, say), not something an agent said."""
    if STARTED.search(text):
        return "codex"
    said = set(SAID.findall(text))
    return said.pop() if len(said) == 1 else ""


def session_in_charge(place):
    """The supervising session that last said it is in charge of this runner (--in-charge), or None."""
    try:
        said = json.loads(read_text(os.path.join(place.runs, "in-charge")) or "null")
    except ValueError:
        return None
    if not isinstance(said, dict) or not isinstance(said.get("id"), str) or not SESSION.match(said["id"]):
        return None
    return {"agent": re.sub(r"[^a-z0-9_-]", "", str(said.get("agent", "")).lower())[:40], "id": said["id"],
            "at": said.get("at") if type(said.get("at")) is int else None}


def task_logs(place, task=None):
    """The readable session logs (runs/<id>-<stamp>.log), newest last; of one task, or of all."""
    found = []
    for runs in place.logs:
        for path in glob.glob(os.path.join(glob.escape(runs), "*-[0-9]*-[0-9]*.log")):
            m = TASK_LOG.match(os.path.basename(path))
            if m and (task is None or m.group(1) == task):
                found.append((m.group(2), path, m.group(1)))
    return sorted(set(found))


def alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


QUEUES = {}     # process id -> is it a queue? The system is asked once for each.


def is_queue(pid):
    """Is this process a queue? A lock left behind by a queue that was killed names a number the system may since
    have given to something else, and that must not be watched as if it were the queue."""
    if pid not in QUEUES:
        try:
            said = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=5).stdout
            QUEUES[pid] = "run_queue" in said if said.strip() else True
        except (OSError, subprocess.TimeoutExpired):
            QUEUES[pid] = True      # nothing to ask: take the lock's word for it
    return QUEUES[pid]


def queue_pid(place):
    """The process id of the queue running in this workspace, or 0."""
    try:
        pid = int(open(os.path.join(place.runs, "queue.lock", "pid")).read().strip())
    except (OSError, ValueError):
        return 0
    return pid if alive(pid) and is_queue(pid) else 0


def before(f, place):
    """The bytes just before a place in a file: enough to tell, later, whether what was read is still there."""
    f.seek(max(0, place - MARK))
    return f.read(min(MARK, place))


def next_piece(path, have, first, whole=False, known=None, most=CHUNK):
    """The next whole lines of a growing file: what follows the lines the dashboard holds, or, when it holds none
    of this file (a new file, a dashboard that restarted, a file cut short, put in another's place or written
    again where it lies), a fresh start from the file's last `first` bytes. A last line with no line feed waits
    until it has one, unless `whole` says the file is finished. A line too long for one report is sent once, as
    its first characters. `most` is how much of the file one report carries. A piece carries a fingerprint of the
    bytes just before its end, which the dashboard holds and hands back in `have["mark"]`: the next piece goes on
    only if those bytes are still where they were, so a file written again where it lies is found out even after a
    report was lost or this program was started again. `known` remembers which file it was (its inode) and how far
    a long line has been followed."""
    known = {} if known is None else known
    try:
        with open(path, "rb") as f:
            st = os.fstat(f.fileno())
            size, name = st.st_size, os.path.basename(path)
            start = have.get("to", -1) if have.get("name") == name else -1
            fresh = known.get(path, st.st_ino) != st.st_ino or not 0 <= start <= size
            known[path] = st.st_ino
            if not fresh and 0 < start:
                # A file written again where it lies keeps its name and its number, and may be longer than it was.
                # The dashboard says what stood just before the place it holds. A dashboard that says nothing (an
                # older one) leaves only this: the place must follow a line feed, unless nothing was added since.
                stood = before(f, start)
                held = have.get("mark")
                fresh = hashlib.sha1(stood).hexdigest() != held if isinstance(held, str) and held else start < size and not stood.endswith(b"\n")
            if fresh:
                start = max(0, size - first)
                if start:
                    f.seek(start)
                    start += len(f.readline())
            f.seek(start)
            data = f.read(most)
            cut, end, body = data.rfind(b"\n") + 1, start, b""
            if whole and data and len(data) < most and not data.endswith(b"\n"):
                end, body = start + len(data), data + b"\n"       # a finished file whose last line has no line feed
            elif cut:
                end, body = start + cut, data[:cut]
            elif len(data) == most:
                # One line longer than a report carries. Its end is looked for, from where the last look stopped,
                # and when it is found the line's first characters are sent in its place.
                at = max(known.get((path, start), 0), start + most)
                f.seek(at)
                while True:
                    more = f.read(CHUNK)
                    if b"\n" in more or not more:
                        break
                    at += len(more)
                known[(path, start)] = at
                if more or whole:
                    end = at + more.find(b"\n") + 1 if more else at
                    body = data[:4000] + " \u2026\n".encode()
            mark = hashlib.sha1(before(f, end)).hexdigest()
    except OSError:
        return None
    return {"name": name, "fresh": fresh, "from": start, "to": end, "size": size, "mark": mark, "text": body.decode("utf-8", "replace")}


class Reporter:
    def __init__(self, place, watch, task):
        self.place, self.given, self.task = place, watch, task
        self.have = {}            # what the dashboard said it holds, from its last answer
        self.more = False         # is there more to send than the last report carried?
        self.last = None          # the last report that could be built, without its file pieces
        self.known = {}           # what next_piece remembers of each file it follows
        self.cache = {}           # parsed files, kept while the file is unchanged
        self.exits = {"offset": 0, "mark": b"", "runs": 0, "finished": 0}
        self.fault = ""
        # Files that do not arrive although the runner's state does.
        self.most = CHUNK         # how much of a log one report carries; less after reports that carried logs were lost
        self.eased = 0.0          # when that was last made less
        self.tried = ()           # the kinds of file the report just built carries
        self.doubt = None         # (kinds, why) of a report with files in it that did not arrive: was it the files?
        self.twice = 0            # how often running such a report was lost and the next one, with no file, arrived
        self.stuck = {}           # kind -> (why, how often, when to try again): what the next reports leave out

    def cached(self, path, parse):
        try:
            st = os.stat(path)
            key = (st.st_mtime_ns, st.st_size)
        except OSError:
            key = None
        if self.cache.get(path, (0,))[0] != key or key is None:
            self.cache[path] = (key, parse(path))
        return self.cache[path][1]

    def count_exits(self):
        """How many task runs the queue log records, and how many ended with the task finished."""
        path, c = os.path.join(self.place.runs, "queue.log"), self.exits
        try:
            with open(path, "rb") as f:
                if os.fstat(f.fileno()).st_size < c["offset"] or before(f, c["offset"]) != c["mark"]:
                    c.update(offset=0, mark=b"", runs=0, finished=0)    # not the file that was counted: count again
                f.seek(c["offset"])
                data = f.read()
        except OSError:
            return c
        data = data[:data.rfind(b"\n") + 1]
        codes = re.findall(rb"(?m)^\S+ \S+ task \S+: run_task\.sh exit (\d+)", data)
        c.update(offset=c["offset"] + len(data), mark=(c["mark"] + data)[-MARK:],
                 runs=c["runs"] + len(codes), finished=c["finished"] + codes.count(b"0"))
        return c

    # ---- files that do not arrive although the runner's state does
    def unsent(self):
        """What of this runner does not reach the dashboard although its state does, in words; empty when all does."""
        if not self.stuck:
            return ""
        names = [KINDS[kind] for kind in KINDS if kind in self.stuck]
        why = next(self.stuck[kind][0] for kind in KINDS if kind in self.stuck)
        return "%s, because the dashboard %s" % (" and ".join([", ".join(names[:-1]), names[-1]] if len(names) > 1 else names), why)

    def lost(self, asked, why):
        """A report did not arrive. Was it what it carried? The next report carries no file, and says."""
        self.doubt = (self.tried, why) if asked and self.tried else None
        return self.doubt is None       # with nothing in doubt, the dashboard itself is what is lost

    def arrived(self, asked):
        """A report arrived. One with no file in it, straight after one with files that was lost, shows that the
        files are what could not be taken. Once is chance, and they are simply sent again. Twice running, each
        kind is left out for a while and then tried again by itself, and the logs go in smaller pieces. A report
        that carried files and arrived clears them."""
        now = time.time()
        if not asked and self.doubt:
            kinds, why = self.doubt
            self.twice += 1
            if self.twice >= 2 or any(kind in self.stuck for kind in kinds):
                for kind in kinds:
                    often = self.stuck.get(kind, ("", 0, 0))[1] + 1
                    self.stuck[kind] = (why, often, now + min(300, EVERY * 2 ** often))
                if set(kinds) - {"tasks_md"} and self.most > SMALLEST:
                    self.most, self.eased = max(SMALLEST, self.most // 4), now
        elif asked and self.tried:
            self.twice = 0
            for kind in self.tried:
                self.stuck.pop(kind, None)
            if self.most < CHUNK and now - self.eased > 600:
                self.most, self.eased = min(CHUNK, self.most * 2), now
        self.doubt = None

    def not_live(self, live):
        """How many built changes are not live, as run_task.sh counts them; asked of git once a minute."""
        key, now = ("not_live", live), time.time()
        if self.cache.get(key, (0,))[0] < now - 60:
            count = None
            if live and self.place.repos:
                try:
                    out = subprocess.run(["git", "-C", self.place.repos[0], "rev-list", "--count", f"{live}..HEAD", "--",
                                          *(self.place.conf.get("PRODUCT_DIRS", "").split() or ["."])],
                                         capture_output=True, text=True, timeout=10)
                    count = int(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip().isdigit() else None
                except (OSError, subprocess.TimeoutExpired):
                    pass
            self.cache[key] = (now, count)
        return self.cache[key][1]

    def build(self):
        place, now = self.place, time.time()
        queue = queue_pid(place)
        watch, mode = (queue, "queue") if queue else (self.given, "task" if self.task else "queue")
        running = alive(watch)

        file = self.cached(place.tasks, load_tasks)
        tasks, by = file["tasks"], {t["id"]: t for t in file["tasks"]}
        order = list(dict.fromkeys(read_order(place.order)))
        used = self.cached(os.path.join(place.runs, "usage.log"), load_usage)
        usage = used["rows"]
        qlog = read_text(os.path.join(place.runs, "queue.log"), last=200 * 1024)
        q = queue_state(qlog)
        waiting = {}
        for path in sorted(glob.glob(os.path.join(glob.escape(place.runs), "waiting", "*"))):
            why = (read_text(path).split("\n") + ["", ""])[1]
            waiting[os.path.basename(path)] = re.sub(r"^SUPERVISOR: \w+ \S+ ", "", why).strip()

        if not running:
            state, hand = "stopped", None
        elif mode == "task":
            state, hand = "running", self.task
        elif q["deciding"]:
            state, hand = "deciding", q["deciding"]
        elif q["hand"]:
            state, hand = "running", q["hand"]
        else:
            state, hand = ("paused" if q["paused"] else "idle" if q["idle"] else "between"), None

        # The session log to show: the task in hand's, else the one started last. The time is the one in the
        # log's name, which no copy or restore of the files can change.
        logs = (task_logs(place, hand) if hand else []) or task_logs(place)
        log = logs[-1] if logs else None

        text = read_text(log[1], last=1024 * 1024) if log else ""
        first = re.search(r"(?m)^task \S+\s+builder=(.*?) model=(\S+) effort=(\S+)\s+max attempts=(\d+)", text)

        # The agent session doing the work, by the identifier its agent knows it by: the stop session while one
        # decides, else the session of the task in hand, else the last session that ran.
        work = None
        if state == "deciding" and q["stop_session"]:
            # A stop session's output is in the queue log, after the line that names the session.
            said = qlog.rpartition("supervising session %s for task " % q["stop_session"])[2]
            work = {"kind": "stop", "agent": agent_of(place.conf, place.conf.get("SUPERVISOR", "")) or agent_in(said), "name": "",
                    "id": q["stop_session"], "task": hand, "live": True}
        elif log and session_in(text):
            builder = first.group(1) if first else ""
            work = {"kind": "task", "agent": agent_of(place.conf, by.get(log[2], {}).get("letter", ""), builder) or agent_in(text),
                    "name": builder, "id": session_in(text), "task": log[2], "live": state == "running" and log[2] == hand}

        task = None
        if hand:
            head = by.get(hand, {})
            task = {"id": hand, "title": head.get("title", ""), "letter": head.get("letter", ""),
                    "effort": head.get("effort", ""), "reviewer": head.get("reviewer", "")}
            if log and log[2] == hand and state == "running":
                tries = re.findall(r"(?m)^attempt (\d+) of (\d+):", text)
                task.update(started=epoch(log[0], "%Y%m%d-%H%M%S"),
                            builder=first.group(1) if first else "", model=first.group(2) if first else "",
                            attempt=int(tries[-1][0]) if tries else 1,
                            attempts=int(tries[-1][1]) if tries else int(first.group(4)) if first else None)
                # A session that sleeps looks like one that works: say which it is.
                last = [line for line in text.split("\n") if line.strip()][-1:] or [""]
                if (nap := re.match(r"usage limit reached; sleeping (\d+)s", last[0])):
                    task["asleep"] = {"why": "the agent's usage limit", "until": int(os.path.getmtime(log[1])) + int(nap.group(1))}
                elif (nap := re.match(r"transient failure \((.*)\)\. Waiting (\d+)s", last[0])):
                    task["asleep"] = {"why": nap.group(1)[:120], "until": int(os.path.getmtime(log[1])) + int(nap.group(2))}

        done = [t for t in tasks if t["status"] == "done"]
        delivered = []
        for t in done:
            rows = [r for r in used["by"].get(t["id"], ()) if r["at"]]
            if rows:
                delivered.append({"id": t["id"], "title": t["title"], "commit": t["commit"][:10],
                                  "at": max(r["at"] for r in rows), "sessions": len(rows),
                                  "minutes": sum(r["minutes"] for r in rows),
                                  "tokens": total(rows, "tokens"), "cost": total(rows, "cost")})
        delivered.sort(key=lambda d: d["at"], reverse=True)
        hours = {}
        for d in delivered:
            if d["at"] > now - 48 * 3600:
                hours[d["at"] // 3600 * 3600] = hours.get(d["at"] // 3600 * 3600, 0) + 1

        lined = [{"id": i, "title": by[i]["title"] if i in by else "",
                  "state": "missing" if i not in by else "hand" if i == hand else "done" if by[i]["status"] == "done"
                  else "parked" if i in waiting else "held" if by[i]["status"] == "held"
                  else "owner" if not by[i]["letter"] else "open"} for i in order]
        if len(lined) > 160:    # a long queue: the part round the task in hand
            at = next((n for n, entry in enumerate(lined) if entry["state"] != "done"), len(lined))
            lined = lined[max(0, at - 60):max(0, at - 60) + 160]

        exits = self.count_exits()
        conf, live = place.conf, read_text(os.path.join(place.runs, "live-sha")).strip()
        deploys = conf.get("DEPLOYS") == "yes" or os.path.isfile(os.path.join(place.workspace, "deploy.sh"))
        check = "unset" if place.conf and not conf.get("CHECK_CMD") else "unknown"
        if os.path.isfile(os.path.join(place.runs, "check.red")):
            check = "fail"
        elif conf.get("CHECK_CMD") and (rc := read_text(os.path.join(place.runs, "check.last")).split()[-1:]):
            check = "pass" if rc[0] == "0" else "fail"
        try:
            started = int(os.path.getmtime(os.path.join(place.runs, "queue.lock", "pid"))) if queue else None
        except OSError:
            started = None
        text, digest = file["text"], file["hash"]

        report = {
            "v": 1, "id": place.id, "sent": now,
            "info": {"project": place.project, "host": place.host, "workspace": place.workspace, "kit": kit_version(),
                     "pid": watch or None, "mode": mode, "started": started},
            "state": state, "note": q["note"] if state in ("idle", "paused") else "", "fault": self.fault,
            "unsent": self.unsent(), "task": task, "last": q["last"],
            "sessions": {"work": work, "charge": session_in_charge(place)},
            "counts": {"total": len(tasks), "done": len(done),
                       "held": sum(t["status"] == "held" for t in tasks),
                       "open": sum(t["status"] == "open" for t in tasks),
                       "queue": len(order), "queue_done": sum(i in by and by[i]["status"] == "done" for i in order),
                       "parked": len(waiting)},
            "queue": lined,
            "parked": [{"id": i, "title": by[i]["title"] if i in by else "", "why": why} for i, why in waiting.items()][:200],
            "delivered": delivered[:40], "hours": sorted(hours.items()),
            "usage": {"sessions": len(usage), "minutes": sum(r["minutes"] for r in usage),
                      "tokens": total(usage, "tokens"), "cost": total(usage, "cost"),
                      "runs": exits["runs"], "finished": exits["finished"], "delivered": len(delivered),
                      "sessions_delivered": sum(d["sessions"] for d in delivered),
                      "median_minutes": statistics.median(d["minutes"] for d in delivered) if delivered else None},
            "check": check,
            "deploy": {"live": live[:10], "not_live": self.not_live(live)} if deploys else None,
            "tasks": {"hash": digest, "bytes": file["bytes"]},
        }
        self.tried = ()
        if not self.have:
            self.more = True      # files are sent once the dashboard has said what it holds, so none is sent twice
            return report, running
        # A kind of file that did not arrive is left out, and when its time comes is tried again by itself.
        again = [kind for kind in KINDS if kind in self.stuck and self.stuck[kind][2] <= now][:1]
        kinds = again or [kind for kind in KINDS if kind not in self.stuck]
        if "tasks_md" in kinds and self.have.get("tasks") != digest:
            report["tasks_md"] = text
        held, self.more = self.have.get("out") or {}, False
        # A session log's last lines are written as the next task starts: send them before the new log.
        last_log = held.get("name") and log and held["name"] != os.path.basename(log[1]) and next(
            (path for _, path, _ in task_logs(place) if os.path.basename(path) == held["name"]), None)
        if "out" not in kinds:
            pass
        elif last_log and (rest := next_piece(last_log, held, TAIL, True, self.known, self.most)) and rest["text"] and not rest["fresh"]:
            report["out"], self.more = rest, True
        elif log and (piece := next_piece(log[1], held, TAIL, not running, self.known, self.most)):
            report["out"] = piece
        if "ev" in kinds and (piece := next_piece(os.path.join(place.runs, "queue.log"), self.have.get("ev") or {},
                                                  TAIL // 4, not running, self.known, self.most)):
            report["ev"] = piece
        self.more = self.more or any(report.get(k) and report[k]["text"] and report[k]["to"] < report[k]["size"]
                                     for k in ("out", "ev"))
        self.tried = tuple(k for k in KINDS if k in report and (k == "tasks_md" or report[k]["text"]))
        for kind in again:
            if kind not in self.tried:      # nothing of it is left to send: it is no longer held up
                del self.stuck[kind]
        return report, running


# ---- sending

class Unsent(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A report goes to the address that was set and nowhere else: to follow a redirect would hand the token to
    whatever address the redirect names."""

    def redirect_request(self, *args, **kwargs):
        return None


OPEN = urllib.request.build_opener(NoRedirect)


def ask(url, token, body=None):
    request = urllib.request.Request(url, data=body, method="POST" if body is not None else "GET",
                                     headers={"User-Agent": "runner-kit/" + kit_version()})
    if body is not None:
        request.add_header("Content-Type", "application/json")
        request.add_header("Content-Encoding", "gzip")
    if token:
        request.add_header("Authorization", "Bearer " + token)
    try:
        with OPEN.open(request, timeout=15) as answer:
            return json.loads(answer.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if 300 <= error.code < 400:
            raise Unsent(f"answered with a redirect ({error.code}), which is not followed; set the dashboard's own address")
        if error.code == 401:
            raise Unsent("refused this machine's token (set DASHBOARD_TOKEN beside its address)")
        try:        # a dashboard says why it refuses, and what to do about it
            said = json.loads(error.read(4096).decode("utf-8", "replace"))
            said = plain(said.get("error", "")) if isinstance(said, dict) else ""
        except (ValueError, OSError, http.client.HTTPException):
            said = ""
        if error.code == 403 and not said:      # a gate in front of the dashboard that says only no: most likely the token
            raise Unsent("refused this machine's token (set DASHBOARD_TOKEN beside its address)")
        raise Unsent(f"answered {error.code}" + (f": {said}" if said else ""))
    except (urllib.error.URLError, OSError) as error:
        raise Unsent(f"cannot be reached ({plain(getattr(error, 'reason', error))})")
    except http.client.HTTPException as error:       # an answer cut short, or not an answer
        raise Unsent(f"gave an answer that was cut short or not HTTP ({plain(type(error).__name__)})")
    except ValueError:
        raise Unsent("gave an answer that could not be read; is the address a runner dashboard?")


def plain(words, most=240):
    """Words from somewhere else, fit to write in a log: one line of printable characters."""
    return "".join(ch if ch.isprintable() else " " for ch in str(words))[:most].strip()


def send(url, token, report):
    body = json.dumps(report, separators=(",", ":"), ensure_ascii=False).encode("utf-8", "replace")
    answer = ask(url + "/api/ingest", token, gzip.compress(body, 5))
    if not isinstance(answer, dict) or not isinstance(answer.get("have"), dict):
        raise Unsent("gave an answer that could not be read; is the address a runner dashboard?")
    return answer["have"]


def note(place, text, queue_log=False):
    """One line in the reporter's own log and, for what the owner should see, in the queue log."""
    line = f"{time.strftime(STAMP)} {text}"
    print(line, flush=True)
    if queue_log and os.path.isfile(os.path.join(place.runs, "queue.log")):
        with open(os.path.join(place.runs, "queue.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")


def take_lock(place):
    """One reporter per workspace. Returns the lock's path, or None when another is already reporting."""
    lock = os.path.join(place.runs, "report.lock")
    os.makedirs(place.runs, exist_ok=True)
    for _ in range(2):
        try:
            os.mkdir(lock)
        except FileExistsError:
            try:
                holder = int(open(os.path.join(lock, "pid")).read().strip())
                age = time.time() - os.path.getmtime(os.path.join(lock, "pid"))
            except (OSError, ValueError):
                holder, age = 0, time.time() - os.path.getmtime(lock) if os.path.isdir(lock) else 99
            if alive(holder) or age < 10:    # a reporter detaching has a new process id within moments
                return None
            shutil.rmtree(lock, ignore_errors=True)
            continue
        open(os.path.join(lock, "pid"), "w").write(str(os.getpid()))
        return lock
    return None


def detach(place, lock):
    """Leave the runner's process group, so that the runner ending is seen and reported, not shared."""
    if os.fork():
        os._exit(0)
    os.setsid()
    if os.fork():
        os._exit(0)
    open(os.path.join(lock, "pid"), "w").write(str(os.getpid()))
    log = os.path.join(place.runs, "report.log")
    if os.path.isfile(log) and os.path.getsize(log) > 1024 * 1024:
        os.replace(log, log + ".1")
    out = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
    os.dup2(out, 1)
    os.dup2(out, 2)


def report_until_done(place, reporter, url, token):
    failing, pause, ended, unsent = "", EVERY, None, ""
    told, owed = 0.0, set()       # the queue log hears bad news at most once an hour, and then the news that ends it

    def tell(words, about, good=False):
        """Say it in this program's log. Bad news goes in the queue log too, at most once an hour; good news goes
        there when the bad news it ends did."""
        nonlocal told
        loud = about in owed if good else time.time() - told > 3600
        if good:
            owed.discard(about)
        elif loud:
            told = time.time()
            owed.add(about)
        note(place, words, queue_log=loud)

    note(place, f"dashboard: reporting to {url}", queue_log=True)
    while True:
        behind = False
        try:
            report, running = reporter.build()
            reporter.fault = report["fault"] = ""
            reporter.last = {k: v for k, v in report.items() if k not in ("out", "ev", "tasks_md")}
        except Exception:
            # One file this program cannot read must not end the reporting, and must not look like silence: the
            # dashboard is sent what was last known, with the fault, and the fault is logged once.
            fault = traceback.format_exc().strip().split("\n")[-1][:300]
            if fault != reporter.fault:
                note(place, "could not read the workspace:\n" + traceback.format_exc())
            reporter.fault, reporter.more, reporter.tried = fault, False, ()
            running = alive(queue_pid(place) or reporter.given)
            report = {**(reporter.last or {"v": 1, "id": place.id, "state": "fault",
                                           "info": {"project": place.project, "host": place.host, "kit": kit_version()}}),
                      "sent": time.time(), "fault": fault}
        if running:
            ended = None          # a queue started again in this workspace is this reporter's to report
        elif ended is None:
            ended = time.time()
        asked = bool(reporter.have)       # was this report made knowing what the dashboard holds?
        try:
            reporter.have = send(url, token, report)
            reporter.arrived(asked)
            behind = reporter.more
            if failing:
                tell("dashboard: reached again", "lost", good=True)
            failing, pause = "", EVERY
            if reporter.unsent() != unsent:
                unsent = reporter.unsent()
                if unsent:
                    tell(f"dashboard: not reaching it: {unsent}. The runner's state does arrive, the rest is "
                         "tried again, and the runner is not held up", "unsent")
                else:
                    tell("dashboard: all of this runner reaches it again", "unsent", good=True)
            if not running and not behind:
                if unsent:
                    note(place, f"the runner has ended; never sent: {unsent}")
                return 0
        except Unsent as why:
            # Whether the dashboard took that report is not known. What it holds is asked again before any more
            # of a file is sent, so a report that did arrive is never sent twice.
            reporter.have = {}
            # A report with files in it that is lost says nothing yet about the dashboard: the next report, which
            # carries none, shows whether the dashboard is lost or only the files could not be taken.
            if reporter.lost(asked, str(why)) and str(why) != failing:
                failing = str(why)
                tell(f"dashboard: {failing}; still trying, and the runner is not held up", "lost")
            pause = min(10, pause * 2)
        if ended is not None and time.time() - ended > LAST_WORDS:
            note(place, "the runner has ended and its last report could not be sent")
            return 1
        time.sleep(0.2 if behind else min(pause, 3) if ended is not None else pause)


def main(argv):
    parser = argparse.ArgumentParser(description="Tell a dashboard what one runner is doing.", add_help=True)
    parser.add_argument("--watch", type=int, default=0, help="report until this process ends")
    parser.add_argument("--task", default="", help="the task a lone run_task.sh is running")
    parser.add_argument("--once", action="store_true", help="send one report and exit")
    parser.add_argument("--print", action="store_true", dest="show", help="with --once: print the report, send nothing")
    parser.add_argument("--check", action="store_true", help="say whether the dashboard can be reached")
    parser.add_argument("--foreground", action="store_true", help="do not detach")
    parser.add_argument("--in-charge", action="store_true", help="record the agent session this shell belongs to as the one in charge")
    for name in ("project", "workspace", "tasks", "order", "runs", "agent", "session"):
        parser.add_argument("--" + name, default="")
    args = parser.parse_args(argv[1:])
    if args.check:       # asked of a machine as well as of a project, so it needs no workspace
        path = os.environ.get("RUNNER_CONF") or os.path.join(os.getcwd(), "runner.conf")
        url, token, source = dashboard(load_keys(path))
        if not url:
            print(f"none: {source}")
            return 3
        try:
            answer = ask(url + "/healthz", "")
            if not isinstance(answer, dict) or answer.get("service") != "runner-dashboard":
                raise Unsent("answers, but not as a runner dashboard")
            if answer.get("token"):       # it answers; would it take this machine's reports?
                if not token:
                    raise Unsent("takes reports only with a token, and this machine has none for it "
                                 "(DASHBOARD_TOKEN beside the address, or RUNNER_DASHBOARD_TOKEN)")
                ask(url + "/api/token", token)
        except Unsent as why:
            print(f"{url} (set by {source}): {why}, with {sys.executable}")
            return 1
        print(f"{url} (set by {source})")
        return 0
    place = Place(args)
    if args.in_charge:
        # Only the session itself can say this truthfully: what a queue inherits from the shell or the tmux server
        # that started it may belong to another session altogether.
        agent, session = args.agent, args.session
        for name, variable in (("claude", "CLAUDE_CODE_SESSION_ID"), ("codex", "CODEX_THREAD_ID")):
            if not session and os.environ.get(variable) and agent in ("", name):
                agent, session = name, os.environ[variable]
        if not session:
            sys.exit("runner_report.py: this shell does not say which agent session it belongs to; "
                     "give --agent <claude|codex> and --session <its identifier>")
        if not SESSION.match(session) or not re.match(r"^[a-z0-9_-]{0,40}$", agent):
            sys.exit("runner_report.py: an agent is a short word and a session identifier is letters, digits, "
                     "dots, colons, dashes and underscores only; nothing else is recorded, because the dashboard "
                     "offers the identifier inside a command to paste into a terminal")
        os.makedirs(place.runs, exist_ok=True)
        path = os.path.join(place.runs, "in-charge")
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"agent": agent, "id": session, "at": int(time.time())}, f)
        os.replace(path + ".tmp", path)
        print(f"{AGENTS.get(agent, agent or 'session')} {session} is recorded as the session in charge of {place.project}")
        return 0
    url, token, source = dashboard(place.conf)
    if args.once and args.show:
        reporter = Reporter(place, args.watch, args.task)
        json.dump(reporter.build()[0], sys.stdout, indent=1)
        print()
        return 0
    if not url:
        return 0
    reporter = Reporter(place, args.watch, args.task)
    if args.once:
        try:
            for _ in range(50):      # the first report learns what the dashboard holds; the next ones fill it in
                reporter.have = send(url, token, reporter.build()[0])
                if not reporter.more:
                    break
        except Unsent as why:
            print(f"runner_report.py: the dashboard {why}", file=sys.stderr)
            return 1
        return 0
    if not (lock := take_lock(place)):
        return 0    # this workspace is already reporting
    if not args.foreground:
        detach(place, lock)
    atexit.register(shutil.rmtree, lock, True)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    return report_until_done(place, reporter, url, token)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
