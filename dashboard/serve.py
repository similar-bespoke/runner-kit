#!/usr/bin/env python3
"""The runner dashboard: takes what runners report and serves one page that shows them.

    serve.py [--host 127.0.0.1] [--port 8787] [--state-dir DIR] [--token-file FILE]
             [--allow-host NAME] [--home URL] [--prefix /path] [--keep-hours 12] [--no-renaming]

Runners send their state with bin/runner_report.py. This program keeps the
latest report from each runner, the last lines of its output and its task
file, and serves dashboard/index.html, which asks for all of it once a second.

    GET  /                     the page
    GET  /api/poll             every runner, and the output lines a page has not
                               seen yet (?since=<id>:<number>:<life>,...)
    GET  /api/tasks?id=<id>    a runner's tasks, read from its TASKS.md
    GET  /api/tasks.md?id=<id> the same file as it is, as plain text
    GET  /api/token            does the caller hold the token reports need?
    GET  /healthz              one line for checks
    POST /api/ingest           a report from a runner
    POST /api/name             a name for a runner, given on the page: {"id", "name"}

Who can reach it. It listens on this machine only (127.0.0.1) unless --host
says otherwise: put it behind whatever already serves the network it is meant
for, a reverse proxy or a tunnel, which is also what gives it https. Give
--prefix if that passes the path on unchanged. It answers to this machine's
own names, to localhost and to any numeric address; a name a proxy or tunnel
gives it must be named with --allow-host (once for each name). That refusal is
what stops a page on another site, which can point a name of its own at this
machine's address, from asking the dashboard questions through a visitor's
browser.

Who can do what. Reading needs nothing: what runners send, their output and
task files included, is shown to everyone who can open the page. With
--token-file a report is taken only with that token; without one, anyone who
can reach the port can report, so give it a token on any network that is
shared. Anyone who can open the page can give a runner a name there, token or
no token, unless --no-renaming is given. A name is a label on the page and
nothing else: it is kept in the state directory under the runner's id, which
is the same whenever that workspace on that machine runs again, and it changes
nothing a runner does.

What it keeps. Nothing here is needed to run tasks: a runner that cannot reach
the dashboard carries on. The state directory (runs/dashboard in the kit unless
--state-dir says otherwise) keeps the latest report and task file of each
runner, so they are shown again at once after a restart; each runner sends its
output lines again by itself. A runner that has not reported for --keep-hours
leaves the page. A report is read into exactly the fields the page shows, each
of the kind the page expects, and the rest is dropped: one runner's report,
however it is made, cannot stop the page showing the others.

What it takes, and what it costs. A report is at most 2 MB as it is sent and
4 MB unpacked, and holds at most 20,000 values; the values are counted before
the report is read into them, because a few kilobytes can say a million empty
lists. Two reports are unpacked and read at a time, and none of that work
holds the lock the page's questions need. A sender that is refused (no
token, too large, a name the dashboard was not given) is answered at once,
before its body has arrived, and what it is still sending is then read and
dropped for a moment, so that it hears the refusal and not a broken
connection.

How many it serves. One thread a caller, and at most 64 callers in hand at
once. A caller the dashboard is waiting on (one that has connected and said
nothing, one sending a request a little at a time, one not reading its answer)
gives up its place when all are taken and another comes; a caller it is at
work for never does, nor one that came a moment ago. That keeps callers that say nothing from shutting the
others out. It is no defence against a flood of real requests: this is a small
program for a network its owner trusts, and a network that is not trusted
wants a proxy in front of it that is made for that. Standard library only,
Python 3.9 or newer.
"""
import argparse
import base64
import gzip
import hashlib
import hmac
import ipaddress
import json
import math
import os
import re
import secrets
import signal
import socket
import sys
import threading
import time
import zlib
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(KIT, "bin"))
from runner_report import SESSION, kit_version, parse_tasks  # noqa: E402  (shared with the reporter, so both read alike)

LINES = 4000                    # output lines kept for each runner
FIRST = 400                     # lines a page is given when it first sees a runner
STEP = 800                      # the most lines one answer carries
MAX_BODY = 2 * 1024 * 1024      # a report as it is sent
MAX_REPORT = 4 * 1024 * 1024    # a report unpacked
MAX_VALUES = 20000              # the values in a report: a real one is a few long texts and a few hundred short ones
MAX_TASKS = 2 * 1024 * 1024     # characters of a task file
MAX_PIECE = 1024 * 1024         # characters of one piece of a log that are read into lines
MAX_RUNNERS = 200               # runners shown at once
MAX_NAMES = 1000                # names kept
MAX_NAME = 60                   # characters in a name given to a runner on the page
BUSY = 64                       # callers in hand at once
PATIENCE = 0.25                 # seconds a caller may keep the dashboard waiting before it can lose its place
LINGER = 8 * 1024 * 1024        # bytes of a refused request that are read and dropped, so that its sender hears why
ID = re.compile(r"^[A-Za-z0-9_.-]{4,64}$")
COUNTS = ("total", "done", "held", "open", "queue", "queue_done", "parked")
USAGE = ("sessions", "minutes", "tokens", "cost", "runs", "finished", "delivered", "sessions_delivered", "median_minutes")


class Refused(Exception):
    def __init__(self, code, why):
        super().__init__(why)
        self.code = code


# ---- a report, read into the fields the page shows and nothing else

def text(value, most=2000):
    return value[:most] if isinstance(value, str) else ""


def short(most):
    return lambda value: text(value, most)


def number(value):
    """A number a browser can read back, or None: JSON has no NaN and no infinity, and a page given one stops."""
    if type(value) is int:
        return value if abs(value) < 10 ** 15 else None
    return value if type(value) is float and math.isfinite(value) else None


def whole(value):
    value = number(value)
    return int(value) if value is not None else None


def record(value, fields):
    """An object with exactly these fields, each put through its own reading; None when it is not an object."""
    return {key: read(value.get(key)) for key, read in fields.items()} if isinstance(value, dict) else None


def rows(value, fields, most, needs):
    found = [record(v, fields) for v in value[:most] if isinstance(v, dict)] if isinstance(value, list) else []
    return [row for row in found if all(row[key] not in (None, "") for key in needs)]


def session(value):
    """An agent session by its identifier. The page offers the identifier inside a command to paste into a
    terminal, so one that is not plainly an identifier is not kept at all."""
    s = record(value, {"kind": short(20), "agent": short(40), "name": short(80), "id": short(200), "task": short(40),
                       "live": lambda v: v is True, "at": number})
    return s if s and SESSION.match(s["id"]) else None


def shape(body):
    task = record(body.get("task"), {
        "id": short(40), "title": text, "letter": short(4), "effort": short(20), "reviewer": short(20),
        "builder": short(80), "model": short(120), "attempt": whole, "attempts": whole, "started": number,
        "asleep": lambda v: record(v, {"why": short(200), "until": number})})
    last = record(body.get("last"), {"id": short(40), "exit": whole, "at": number})
    sessions = body.get("sessions") if isinstance(body.get("sessions"), dict) else {}
    hours = body.get("hours") if isinstance(body.get("hours"), list) else []
    return {
        "sent": number(body.get("sent")),
        "info": record(body.get("info"), {"project": short(200), "host": short(200), "workspace": short(500),
                                          "kit": short(40), "pid": whole, "mode": short(20), "started": number}) or {},
        "state": text(body.get("state"), 20), "note": text(body.get("note")), "fault": text(body.get("fault"), 400),
        "unsent": text(body.get("unsent"), 400),
        "task": task if task and task["id"] else None,
        "last": last if last and last["id"] and last["exit"] is not None else None,
        "sessions": {"work": session(sessions.get("work")), "charge": session(sessions.get("charge"))},
        "counts": record(body.get("counts"), {key: whole for key in COUNTS}) or {},
        "queue": rows(body.get("queue"), {"id": short(40), "title": short(300), "state": short(20)}, 400, ("id",)),
        "parked": rows(body.get("parked"), {"id": short(40), "title": short(300), "why": text}, 200, ("id",)),
        "delivered": rows(body.get("delivered"), {"id": short(40), "title": short(300), "commit": short(40), "at": number,
                                                  "sessions": whole, "minutes": number, "tokens": number, "cost": number},
                          60, ("id", "at")),
        "hours": [[whole(p[0]), whole(p[1])] for p in hours[:60]
                  if isinstance(p, list) and len(p) == 2 and whole(p[0]) is not None and whole(p[1]) is not None],
        "usage": record(body.get("usage"), {key: number for key in USAGE}) or {},
        "check": text(body.get("check"), 20),
        "deploy": record(body.get("deploy"), {"live": short(40), "not_live": whole}),
        "tasks": record(body.get("tasks"), {"hash": short(64), "bytes": whole}) or {},
    }


def piece_of(raw):
    """A piece of a growing file as a runner sends it, checked and cut into the lines that are kept; None if it is
    not one. A line ends at a line feed and nowhere else, as it does in the file."""
    if not isinstance(raw, dict):
        return None
    name, start, end, body = raw.get("name"), raw.get("from"), raw.get("to"), raw.get("text")
    if not (isinstance(name, str) and isinstance(body, str) and type(start) is int and type(end) is int and 0 <= start <= end):
        return None
    lines = body[-MAX_PIECE:].split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return {"name": name[:200], "fresh": raw.get("fresh") is True, "from": start, "to": end,
            "lines": [line.rstrip("\r")[:4000] for line in lines[-LINES:]]}


class Runner:
    def __init__(self, rid):
        self.id, self.report, self.seen, self.first, self.skew = rid, {}, 0.0, time.time(), 0.0
        self.life = secrets.token_hex(4)    # a page's place among the lines holds for this life of the runner only
        self.lines, self.seq = deque(maxlen=LINES), 0
        self.streams = {"out": {"name": "", "to": 0}, "ev": {"name": "", "to": 0}}
        self.tasks_hash, self.tasks_md, self.parsed = "", "", None

    def push(self, kind, line):
        self.seq += 1
        self.lines.append((self.seq, kind, line))

    def add(self, key, piece):
        """Whole lines of a growing file. A piece either follows exactly what is held, or says it starts afresh;
        anything else is left out, and the answer tells the runner where to go on from."""
        if not piece:
            return
        held, name = self.streams[key], piece["name"]
        if piece["fresh"]:
            if key == "out" and held["name"] and held["name"] != name:
                self.push("m", name)                # another session log begins: a rule across the output
            elif held["name"] == name and piece["from"] > held["to"]:
                self.push("m", "")                  # lines between were not sent
            elif held["name"] == name:
                self.push("m", "again")             # the same file, cut short or written again
            held.update(name=name, to=piece["from"])
        elif name != held["name"] or piece["from"] != held["to"]:
            return
        for line in piece["lines"]:
            self.push("o" if key == "out" else "q", line)
        held["to"] = piece["to"]


class Dashboard:
    def __init__(self, state_dir, token, home, prefix, keep_hours, hosts=(), renaming=True):
        self.dir, self.token, self.home, self.prefix = state_dir, token, home, prefix.rstrip("/")
        self.keep, self.started, self.renaming = keep_hours * 3600, time.time(), renaming
        self.given = {h.lower().rstrip(".") for h in hosts}     # the names the owner said it is reached by
        self.hosts = {"localhost", *self.given}
        own = socket.gethostname().lower().rstrip(".")
        if own:
            self.hosts.update({own, own.split(".")[0], own.split(".")[0] + ".local"})
        self.lock, self.runners, self.dirty = threading.Lock(), {}, False
        self.names, self.naming = {}, threading.Lock()   # names the owner gave runners on the page
        self.heavy = threading.BoundedSemaphore(2)       # reports unpacked and read at once
        self.page = (None, b"", "")
        os.makedirs(os.path.join(state_dir, "tasks"), exist_ok=True)
        self.load()

    # ---- what is kept across a restart: the latest report and the task file of each runner, and the names given
    def load(self):
        try:
            names = json.load(open(os.path.join(self.dir, "names.json"), encoding="utf-8"))
            self.names = {k: v[:MAX_NAME] for k, v in names.items() if isinstance(v, str) and ID.match(k)}
        except (OSError, ValueError, AttributeError):
            pass
        try:
            saved = json.load(open(os.path.join(self.dir, "runners.json"), encoding="utf-8"))
        except (OSError, ValueError):
            return
        for entry in saved if isinstance(saved, list) else []:
            if not (isinstance(entry, dict) and isinstance(entry.get("id"), str) and ID.match(entry["id"])):
                continue
            r = Runner(entry["id"])
            r.report = shape(entry["report"]) if isinstance(entry.get("report"), dict) else {}
            r.seen, r.first, r.skew = (number(entry.get(k)) or 0.0 for k in ("seen", "first", "skew"))
            try:
                r.tasks_md = open(self.tasks_path(r.id), encoding="utf-8").read()
                r.tasks_hash = text(entry.get("tasks_hash"), 64)
            except OSError:
                pass
            self.runners[r.id] = r

    def tasks_path(self, rid):
        return os.path.join(self.dir, "tasks", rid + ".md")

    def write(self, path, body):
        mine = "%s.tmp.%d" % (path, threading.get_ident())   # two writers never share a half-written file
        with open(mine, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(mine, path)

    def forget(self, rid):
        try:
            os.remove(self.tasks_path(rid))
        except OSError:
            pass

    def save(self):
        now = time.time()
        with self.lock:
            gone = [rid for rid, r in self.runners.items() if now - r.seen > self.keep]
            for rid in gone:
                del self.runners[rid]
                self.dirty = True
            saved = None
            if self.dirty:
                saved = [{"id": r.id, "report": r.report, "seen": r.seen, "first": r.first, "skew": r.skew,
                          "tasks_hash": r.tasks_hash} for r in self.runners.values()]
                self.dirty = False
        for rid in gone:
            self.forget(rid)
        if saved is not None:
            self.write(os.path.join(self.dir, "runners.json"), json.dumps(saved, allow_nan=False))

    # ---- a report from a runner
    def take(self, body):
        if not isinstance(body, dict):
            raise Refused(400, "a report is one JSON object")
        rid = body.get("id")
        if not isinstance(rid, str) or not ID.match(rid):
            raise Refused(400, "a report needs an id")
        # Everything that takes time is done before the lock: one report must not hold up every page.
        report, pieces = shape(body), {key: piece_of(body.get(key)) for key in ("out", "ev")}
        digest = report["tasks"].get("hash", "")
        tasks_md = body["tasks_md"][:MAX_TASKS] if isinstance(body.get("tasks_md"), str) and digest else None
        now, pushed_out = time.time(), None
        with self.lock:
            r = self.runners.get(rid)
            if r is None:
                if len(self.runners) >= MAX_RUNNERS:     # the one silent longest makes room; a live runner never is
                    pushed_out = min(self.runners.values(), key=lambda other: other.seen).id
                    del self.runners[pushed_out]
                r = self.runners[rid] = Runner(rid)
            r.seen, r.report = now, report
            r.skew = now - report["sent"] if report["sent"] is not None else 0.0
            if tasks_md is not None:
                r.tasks_md, r.tasks_hash, r.parsed = tasks_md, digest, None
            # The queue log says a task has started before that task's session log has a line in it.
            begins = bool(pieces["out"] and pieces["out"]["fresh"])
            for key in (("ev", "out") if begins else ("out", "ev")):
                r.add(key, pieces[key])
            self.dirty = True
            have = {"tasks": r.tasks_hash, "out": dict(r.streams["out"]), "ev": dict(r.streams["ev"])}
        if pushed_out:
            self.forget(pushed_out)
        if tasks_md is not None:
            try:        # kept on disk only to be shown again at once after a restart: the report itself is taken
                self.write(self.tasks_path(rid), tasks_md)
            except OSError as error:
                sys.stderr.write(f"could not save a task file: {error}\n")
        return {"ok": True, "have": have}

    # ---- a name given on the page: a label for people, held here so that every device shows the same one
    def rename(self, body):
        rid = body.get("id") if isinstance(body, dict) else None
        name = body.get("name") if isinstance(body, dict) else None
        if not isinstance(rid, str) or not isinstance(name, str):
            raise Refused(400, "a name needs the runner's id and the name")
        name = " ".join("".join(ch for ch in name if ch.isprintable() or ch.isspace()).split())[:MAX_NAME]
        with self.naming:       # one name is written at a time, so the file is always the latest set of names
            with self.lock:
                if rid not in self.runners:
                    raise Refused(404, "no such runner")
                names = {k: v for k, v in self.names.items() if k != rid}
            if name:            # an empty name goes back to the project's own
                names[rid] = name
            while len(names) > MAX_NAMES:
                del names[next(iter(names))]
            try:                # written first: a name the page shows is a name that is kept
                self.write(os.path.join(self.dir, "names.json"), json.dumps(names))
            except OSError as error:
                raise Refused(500, f"the dashboard could not keep the name ({error.strerror or error})")
            self.names = names
        return {"ok": True, "label": name}

    # ---- what a page asks for
    def poll(self, since):
        now, runners = time.time(), []
        with self.lock:
            for r in sorted(self.runners.values(), key=lambda r: r.first):
                if now - r.seen > self.keep or not r.report:
                    continue
                seen, life = since.get(r.id, (None, ""))
                oldest = r.lines[0][0] if r.lines else r.seq + 1
                reset = seen is None or life != r.life or seen > r.seq or seen < oldest - 1
                lines = list(r.lines)
                lines = lines[-FIRST:] if reset else lines[seen - oldest + 1:][:STEP]
                runners.append({**r.report, "id": r.id, "life": r.life, "label": self.names.get(r.id, ""),
                                "age": round(now - r.seen, 1), "skew": round(r.skew, 1),
                                "reset": reset, "lines": lines,
                                "seq": lines[-1][0] if lines else r.seq if reset else seen})
        return {"now": now, "up": round(now - self.started), "version": kit_version(), "home": self.home,
                "renaming": self.renaming, "runners": runners}

    def tasks(self, rid):
        with self.lock:
            r = self.runners.get(rid)
            if not r or not r.tasks_md:
                return None, None
            md, digest, parsed, report = r.tasks_md, r.tasks_hash, r.parsed, r.report
        if parsed is None:
            parsed = parse_tasks(md)        # read outside the lock: a long task file must not hold up every page
            with self.lock:
                if r.tasks_hash == digest:
                    r.parsed = parsed
        return md, {
            "id": rid, "project": report.get("info", {}).get("project", ""), "hash": digest, "tasks": parsed,
            "queue": [q["id"] for q in report.get("queue", [])],
            "parked": {p["id"]: p["why"] for p in report.get("parked", [])},
            "hand": (report.get("task") or {}).get("id"),
        }

    def html(self):
        """The page, read again when the file changes, and the hash that lets its one script run."""
        path = os.path.join(HERE, "index.html")
        stamp = os.stat(path).st_mtime_ns
        if self.page[0] != stamp:
            body = open(path, "rb").read()
            scripts = re.findall(rb"<script>(.*?)</script>", body, re.S)
            allowed = " ".join("'sha256-%s'" % base64.b64encode(hashlib.sha256(s).digest()).decode() for s in scripts)
            self.page = (stamp, body, allowed)
        return self.page[1], self.page[2]


def no_constant(name):
    raise ValueError("a report holds no " + name)


def short_number(read):
    """A number of a length a report could hold. A longer one is no number, and can take long to read as one."""
    return lambda digits: read(digits) if len(digits) <= 40 else None


def values_in(data):
    """No fewer than the values a JSON text holds, counted without making them: its texts, and the commas and
    opening brackets outside them. A few kilobytes, packed, can say a million empty lists, which take a hundred
    megabytes to hold. The count is right for any text that is JSON; one that is not is refused when it is read."""
    parts = data.replace(b"\\\\", b"").replace(b'\\"', b"").split(b'"', 4 * MAX_VALUES)
    if len(parts) > 4 * MAX_VALUES:
        return len(parts)
    return len(parts) // 2 + sum(part.count(b",") + part.count(b"[") + part.count(b"{") for part in parts[::2])


def read_json(data, what):
    try:
        return json.loads(data.decode("utf-8"), parse_constant=no_constant,
                          parse_int=short_number(int), parse_float=short_number(float))
    except (ValueError, RecursionError):
        raise Refused(400, what + " is one JSON object, with no NaN and no infinity in it")


class Handler(BaseHTTPRequestHandler):
    server_version, sys_version, timeout = "runner-dashboard", "", 30

    def log_message(self, form, *args):
        if len(args) > 1 and str(args[1])[:1] in "45":      # failures only, and nothing that could steer a terminal
            line = "".join(ch if ch.isprintable() else "?" for ch in form % args)[:400]
            sys.stderr.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), line))

    def parse_request(self):
        ok = super().parse_request()
        self.server.waits(self.connection, False)       # the request is here: from now the dashboard is at work on it
        return ok

    def reply(self, code, body, kind="application/json", headers=()):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, separators=(",", ":"), allow_nan=False).encode()
        if len(body) > 1024 and "gzip" in self.headers.get("Accept-Encoding", ""):
            body, headers = gzip.compress(body, 5), (*headers, ("Content-Encoding", "gzip"))
        self.send_response(code)
        for name, value in (("Content-Type", kind), ("Content-Length", str(len(body))), ("Cache-Control", "no-store"),
                            ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer"), *headers):
            self.send_header(name, value)
        self.server.waits(self.connection)      # from here it is the caller's turn, to read
        self.end_headers()
        self.wfile.write(body)

    def route(self):
        url, app = urlparse(self.path), self.server.app
        path = url.path
        if app.prefix and (path == app.prefix or path.startswith(app.prefix + "/")):
            path = path[len(app.prefix):]
        return path or "/", parse_qs(url.query)

    def stranger(self):
        """The name this request was sent to, if it is not one the dashboard answers to; else nothing. A numeric
        address always is one: only a name can be pointed somewhere else by someone else."""
        host = (self.headers.get("Host") or "").strip().lower()
        if not host:
            return ""                   # no browser sends a request without one
        name = host[1:host.find("]")] if host.startswith("[") else host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        name = name.rstrip(".")
        try:
            ipaddress.ip_address(name)
            return ""
        except ValueError:
            return "" if name in self.server.app.hosts else re.sub(r"[^a-z0-9._-]", "", name)[:100] or "?"

    def unknown(self, name):
        return "this dashboard was not told it goes by the name %s; start it with --allow-host %s" % (name, name)

    def authorised(self):
        token = self.server.app.token
        return not token or hmac.compare_digest(self.headers.get("Authorization", "").encode(), ("Bearer " + token).encode())

    def body(self, length, within):
        """The request's body: all of it, within so many seconds, or a refusal. Its sender is one the dashboard
        waits on, and gives way like any other when every place is taken."""
        until, parts, left = time.monotonic() + within, [], length
        self.server.waits(self.connection)
        try:
            while left:
                self.connection.settimeout(max(0.05, min(self.timeout, until - time.monotonic())))
                part = self.rfile.read1(min(left, 65536))
                if not part or time.monotonic() > until:
                    break
                parts.append(part)
                left -= len(part)
        except OSError:
            pass
        finally:
            self.connection.settimeout(self.timeout)
            self.server.waits(self.connection, False)
        self.unread = 0
        if left:
            raise Refused(408, "the request did not arrive whole within %d seconds" % within)
        return b"".join(parts)

    def linger(self):
        """After a refusal, what the sender is still sending is read and dropped for a moment. A sender that finds
        the connection shut while it is still sending never reads the answer it was given."""
        left, until = min(self.unread, LINGER), time.monotonic() + 5
        try:
            self.connection.settimeout(1)
            while left > 0 and time.monotonic() < until:
                part = self.rfile.read1(min(left, 65536))
                if not part:
                    break
                left -= len(part)
        except OSError:
            pass

    def do_GET(self):
        app = self.server.app
        if (name := self.stranger()):
            self.reply(421, {"ok": False, "error": self.unknown(name)})
            return
        path, query = self.route()
        rid = (query.get("id") or [""])[0]
        if path in ("/", "/index.html"):
            body, allowed = app.html()
            policy = ("default-src 'none'; script-src %s; style-src 'unsafe-inline' https://fonts.googleapis.com; "
                      "font-src https://fonts.gstatic.com; connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
                      "form-action 'none'; frame-ancestors 'self'" % allowed)
            self.reply(200, body, "text/html; charset=utf-8", (("Content-Security-Policy", policy),))
        elif path == "/api/poll":
            since = {}
            for entry in (query.get("since") or [""])[0].split(","):
                known, _, rest = entry.partition(":")
                number_seen, _, life = rest.partition(":")
                if ID.match(known) and number_seen.isdigit() and len(number_seen) < 16:
                    since[known] = (int(number_seen), life)
            self.reply(200, app.poll(since))
        elif path in ("/api/tasks", "/api/tasks.md"):
            md, parsed = app.tasks(rid) if ID.match(rid) else (None, None)
            if md is None:
                self.reply(404, {"ok": False, "error": "no task file is held for that runner"})
            elif path.endswith(".md"):
                self.reply(200, md.encode(), "text/plain; charset=utf-8")
            else:
                self.reply(200, parsed)
        elif path == "/api/token":      # asked by bin/runner_report.py --check, so a wrong token is found before a queue runs
            if self.authorised():
                self.reply(200, {"ok": True})
            else:
                self.reply(401, {"ok": False, "error": "this dashboard takes reports only with its token"})
        elif path == "/healthz":
            self.reply(200, {"ok": True, "service": "runner-dashboard", "version": kit_version(), "token": bool(app.token),
                             "runners": len(app.runners), "up": round(time.time() - app.started)})
        else:
            self.reply(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        app = self.server.app
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            length = -1
        self.unread = max(0, length)        # what the sender has still to send, should it be refused
        try:
            if (name := self.stranger()):
                raise Refused(421, self.unknown(name))
            path = self.route()[0]
            if path not in ("/api/ingest", "/api/name"):
                raise Refused(404, "not found")
            if length < 0:
                raise Refused(411, "a request needs a Content-Length")
            most = MAX_BODY if path == "/api/ingest" else 4096
            if not 0 < length <= most:
                raise Refused(413, "at most %d bytes are taken here" % most)
            if path == "/api/name":
                # Given from the dashboard's own page, by anyone who can open it. A page on another site cannot do
                # it through a visitor's browser: a form cannot send JSON, and a script elsewhere is cross-site.
                if not app.renaming:
                    raise Refused(403, "names are fixed on this dashboard")
                if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                    raise Refused(403, "a name is given from the dashboard's own page")
                site, origin = self.headers.get("Sec-Fetch-Site"), self.headers.get("Origin")
                if site is not None:
                    own = site in ("same-origin", "none")
                elif origin:
                    # A browser that does not say where the request comes from, only which page sent it. That page
                    # is this dashboard's own if it is where this request was sent, or if its name is one the owner
                    # gave: a proxy may hand a request on under another name than the one in the address bar.
                    page = urlparse(origin)
                    mine = {h.strip().lower() for h in (self.headers.get("Host"), self.headers.get("X-Forwarded-Host")) if h}
                    own = page.netloc.lower() in mine or (page.hostname or "").rstrip(".") in app.given
                    if not own:
                        seen = re.sub(r"[^a-z0-9._-]", "", (page.hostname or "").lower())[:100] or "?"
                        raise Refused(403, "a name is given from the dashboard's own page, and this dashboard was not "
                                           "told it goes by the name %s; start it with --allow-host %s" % (seen, seen))
                else:
                    own = True
                if not own:
                    raise Refused(403, "a name is given from the dashboard's own page")
                self.reply(200, app.rename(read_json(self.body(length, 5), "a name")))
                return
            if not self.authorised():       # said at once: nothing of a report is read from a sender with no token
                raise Refused(401, "this dashboard takes reports only with its token")
            data = self.body(length, 60)
            with app.heavy:     # unpacking and reading a report is the costly part: two at a time, the rest wait
                if self.headers.get("Content-Encoding", "").lower() == "gzip":
                    unpack = zlib.decompressobj(16 + zlib.MAX_WBITS)
                    try:
                        data = unpack.decompress(data, MAX_REPORT)
                    except zlib.error:
                        raise Refused(400, "the report could not be unpacked")
                    if unpack.unconsumed_tail:
                        raise Refused(413, "a report is at most %d bytes unpacked" % MAX_REPORT)
                if len(data) > MAX_REPORT:
                    raise Refused(413, "a report is at most %d bytes unpacked" % MAX_REPORT)
                if values_in(data) > MAX_VALUES:
                    raise Refused(413, "a report holds at most %d values" % MAX_VALUES)
                body = read_json(data, "a report")
                del data
                answer = app.take(body)
            self.reply(200, answer)
        except Refused as why:
            self.close_connection = True
            self.reply(why.code, {"ok": False, "error": str(why)})
            self.linger()


class Server(ThreadingHTTPServer):
    """One thread a caller, and no more than BUSY callers in hand at once. A caller the dashboard is waiting on (one
    that connected and has said nothing, one sending its request a little at a time, one not reading its answer)
    holds a place without work being done for it. When every place is taken, the one that has kept the dashboard
    waiting longest gives its place to the newcomer, so callers that say nothing cannot shut the others out."""
    daemon_threads, allow_reuse_address, request_queue_size = True, True, 64

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.places = threading.Lock()
        self.callers = {}       # connection in hand -> since when the dashboard waits on it; None while it works for it

    def admit(self, request):
        """Take a connection in hand, if need be in the place of the caller waited on longest. False when every
        place is taken by a caller the dashboard is at work for, or has only just begun to wait on."""
        now = time.monotonic()
        with self.places:
            if len(self.callers) >= BUSY:
                waited = [(since, id(caller), caller) for caller, since in self.callers.items()
                          if since is not None and now - since > PATIENCE]
                if not waited:
                    return False
                slowest = min(waited)[2]
                del self.callers[slowest]
                try:
                    slowest.shutdown(socket.SHUT_RDWR)      # its thread sees the end of the connection, and ends
                except OSError:
                    pass
            self.callers[request] = now
            return True

    def waits(self, request, waiting=True):
        """The dashboard is now waiting on this caller, or now at work for it."""
        with self.places:
            if request in self.callers:
                self.callers[request] = time.monotonic() if waiting else None

    def process_request(self, request, client_address):
        if not self.admit(request):
            try:        # busy with requests in earnest: say so, and when to come back
                request.settimeout(0.5)
                request.sendall(b"HTTP/1.0 503 Service Unavailable\r\nRetry-After: 1\r\nContent-Length: 0\r\n\r\n")
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:           # no thread was started to give the place back
            self.leave(request)
            raise

    def leave(self, request):
        with self.places:
            self.callers.pop(request, None)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.leave(request)

    def handle_error(self, request, client_address):
        # A caller that went away, or was made to give up its place, is no fault of the dashboard's.
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError, socket.timeout)):
            return
        super().handle_error(request, client_address)


def main(argv):
    parser = argparse.ArgumentParser(description="The runner dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787, help="0 picks a free port and prints it")
    parser.add_argument("--state-dir", default=os.path.join(KIT, "runs", "dashboard"))
    parser.add_argument("--token-file", default="", help="a file whose first line is the token reports must carry")
    parser.add_argument("--allow-host", action="append", default=[], help="a name this dashboard is reached by, besides this machine's own")
    parser.add_argument("--home", default="", help="an address the page links back to")
    parser.add_argument("--prefix", default="", help="the path this is served under, if the proxy does not strip it")
    parser.add_argument("--keep-hours", type=float, default=12, help="how long a runner that has gone quiet stays on the page")
    parser.add_argument("--no-renaming", action="store_true", help="nobody may give a runner a name on the page")
    args = parser.parse_args(argv[1:])
    token = ""
    if args.token_file:
        token = open(args.token_file, encoding="utf-8").read().split("\n")[0].strip()
        if not token:
            sys.exit(f"serve.py: {args.token_file} holds no token")
    hosts = [name.strip() for given in args.allow_host for name in given.split(",") if name.strip()]
    app = Dashboard(os.path.realpath(args.state_dir), token, args.home, args.prefix, args.keep_hours, hosts, not args.no_renaming)
    app.html()      # fail now, not at the first request, if the page is missing
    server = Server((args.host, args.port), Handler)
    server.app = app

    def stop(*_):
        raise KeyboardInterrupt

    def keep():
        while True:
            time.sleep(5)
            try:
                app.save()
            except (OSError, ValueError) as error:
                sys.stderr.write(f"could not save the dashboard's state: {error}\n")
    threading.Thread(target=keep, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    print("runner dashboard on http://%s:%d/  (reports %s; answers to %s and any numeric address)" % (
        args.host, server.server_address[1], "need the token" if token else "are taken from anyone who can reach it",
        ", ".join(sorted(app.hosts))), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.save()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
