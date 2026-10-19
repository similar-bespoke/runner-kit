#!/usr/bin/env python3
"""Review running work, retain notices until accepted, and verify delivery.

See docs/supervision.md for the command and webhook contracts.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
import uuid

from runner_report import load_keys


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex)
    temporary.write_text(json.dumps(value, ensure_ascii=True) + "\n")
    temporary.replace(path)


def read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


class Watch:
    def __init__(self):
        conf_path = Path(os.environ.get("RUNNER_CONF", "runner.conf")).resolve()
        os.environ["RUNNER_CONF"] = str(conf_path)
        self.conf = load_keys(conf_path)
        self.workspace = Path(self.conf.get("WORKSPACE", os.getcwd())).resolve()
        self.runs = Path(os.environ.get("QUEUE_RUNS", self.workspace / "runs"))
        self.root = self.runs / "oversight"
        self.required = self.conf.get("SUPERVISION_REQUIRED", "no") == "yes"
        self.interval = float(self.conf.get("SUPERVISION_INTERVAL", "300"))
        self.timeout = float(self.conf.get("SUPERVISION_TIMEOUT", "900"))
        if not 0 < self.interval < self.timeout:
            raise ValueError("SUPERVISION_TIMEOUT must exceed the positive SUPERVISION_INTERVAL")

    def identity(self):
        return {"agent": self.conf.get("ORIGIN_AGENT", ""),
                "session": self.conf.get("ORIGIN_SESSION", "")}

    def check(self):
        missing = []
        if self.required:
            for key in ("GOAL", "ORIGIN_AGENT", "ORIGIN_SESSION"):
                if not self.conf.get(key):
                    missing.append(key)
            if self.identity()["agent"] not in ("claude", "codex"):
                missing.append("ORIGIN_AGENT=claude or codex")
            if not self.coordinator().is_file():
                missing.append("COORDINATOR_CMD (notify-coordinator executable)")
        if missing:
            raise ValueError("supervision needs " + ", ".join(missing))

    def coordinator(self):
        return Path(self.conf.get("COORDINATOR_CMD", "~/.local/bin/notify-coordinator")).expanduser()

    def task(self, task):
        text = (self.workspace / "TASKS.md").read_text()
        match = re.search(r"(?m)^### " + re.escape(task) + r" (.+)$", text)
        return re.split(r"\s+\[[ x~]\]", match[1])[0] if match else task

    def event(self, kind, task="", summary="", next_action="", evidence=""):
        event = {"id": uuid.uuid4().hex, "time": time.time(), "kind": kind,
                 "project": self.conf.get("PROJECT", self.workspace.name),
                 "goal": self.conf.get("GOAL", "Goal not configured"),
                 "origin": self.identity(), "workspace": str(self.workspace),
                 "task": task, "task_outcome": self.task(task) if task else "",
                 "summary": summary, "next": next_action, "evidence": evidence}
        event["message"] = "\n".join(x for x in (
            event["project"] + ": " + event["goal"], summary,
            "Next: " + next_action if next_action else "",
            "Evidence: " + evidence if evidence else "" ) if x)
        save(self.root / "events" / (event["id"] + ".json"), event)
        # A bridge must address this exact originating session. Its reply means
        # that session reviewed the evidence, not merely that a message arrived.
        command = self.conf.get("SUPERVISOR_CMD", "")
        if command and kind in ("review", "attention", "needs_input", "built", "idle"):
            try:
                result = subprocess.run(shlex.split(command), input=json.dumps(event),
                                        text=True, capture_output=True, timeout=30)
                reply = json.loads(result.stdout) if result.returncode == 0 else {}
                self.review(event["id"], reply.get("action", ""), reply.get("reason", ""),
                            reply.get("agent", ""), reply.get("session", ""))
            except (OSError, ValueError, subprocess.TimeoutExpired):
                print("Originating session has not acknowledged this review.", file=sys.stderr)
        if kind in ("attention", "needs_input") and not self.flush():
            print("Coding Coordinator has not acknowledged pending messages.", file=sys.stderr)
        return event

    def review(self, event_id, action, reason, agent, session):
        event = read(self.root / "events" / (event_id + ".json"))
        if not event or event["origin"] != {"agent": agent, "session": session}:
            raise ValueError("review must name the event's exact originating session")
        if event["origin"] != self.identity() or not agent or not session:
            raise ValueError("review belongs to a previous or unconfigured supervisor")
        if action not in ("continue", "yield", "stop") or not reason.strip():
            raise ValueError("review needs continue, yield or stop, and an evidence-based reason")
        receipt = {"event": event_id, "time": time.time(), "origin": self.identity(),
                   "action": action, "reason": reason}
        save(self.root / "reviews" / (event_id + ".json"), receipt)
        if action == "stop":
            (self.runs / "queue.stop").touch()
        return receipt

    def latest_review(self, task=None):
        reviews = [read(p) for p in (self.root / "reviews").glob("*.json")]
        reviews = [r for r in reviews if r.get("origin") == self.identity()]
        if task is not None:
            reviews = [r for r in reviews if read(self.root / "events" / (r["event"] + ".json")).get("task") == task]
        return max(reviews, key=lambda r: r["time"], default={})

    def hold(self, task, reason):
        event = self.event("attention", task, "Work on " + self.task(task) + " has been preserved.", reason)
        save(self.root / "yielded" / (task + ".json"), {"event": event["id"], "reason": reason})
        (self.runs / (task + ".stop")).write_text("RUNNER: blocked " + reason + "\n")
        return event

    def flush(self, retry_uncertain=False):
        if not self.required and not self.conf.get("COORDINATOR_CMD"):
            return True  # Legacy projects have not opted into coordinator writes.
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / "messages.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            return self._flush(retry_uncertain)

    def _flush(self, retry_uncertain):
        command = self.coordinator()
        complete = True
        events = sorted((read(p) for p in (self.root / "events").glob("*.json")),
                        key=lambda e: e.get("time", 0))
        for event in events:
            # Will's standing recipient policy allows only these cases.
            kind = {"delivered": "done", "attention": "blocker", "needs_input": "question"}.get(event.get("kind"))
            if not kind:
                continue
            path = self.root / "messages" / (event["id"] + ".json")
            receipt = read(path)
            if receipt.get("state") == "accepted":
                continue
            if receipt.get("state") == "uncertain" and not retry_uncertain:
                complete = False
                continue
            if not command.is_file():
                return False
            save(path, {"state": "uncertain", "event": event["id"]})
            details = "\n".join(x for x in (
                "Goal: " + event["goal"],
                "Next: " + event["next"] if event["next"] else "",
                "Evidence: " + event["evidence"] if event["evidence"] else "",
                "Message reference: " + event["id"]) if x)
            process = subprocess.Popen([str(command), event["origin"]["agent"] or "Runner",
                                        kind, event["project"], event["summary"], details],
                                       text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       start_new_session=True)
            try:
                stdout, _ = process.communicate(timeout=30)
                if process.returncode or not re.fullmatch(r"sent \(2[0-9]{2}\)\s*", stdout):
                    complete = False
                    continue
                save(path, {"state": "accepted", "event": event["id"], "time": time.time()})
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                process.communicate()
                complete = False
        return complete

    def run(self, task, phase, command):
        if not self.required:
            return subprocess.call(command)
        self.check()
        event = self.event("review", task, "Review current work on " + self.task(task) + ".",
                           "Check the recent output, changes and unresolved review findings.")
        process = None
        def terminate():
            if process is None:
                return
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            except ProcessLookupError:
                return
            # Kill remaining descendants even if the shell exited on TERM.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        def interrupted(signum, frame):
            raise KeyboardInterrupt
        previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
        started = last_event = time.monotonic()
        try:
            while True:
                if process is not None and process.poll() is not None:
                    return process.returncode
                receipt = self.latest_review()
                task_review = self.latest_review(task)
                action = task_review.get("action", "continue")
                fresh = time.time() - receipt.get("time", 0) < self.timeout
                if action in ("yield", "stop") or (process is not None and not fresh):
                    reason = task_review.get("reason", "") if fresh else "The originating session has not reviewed the runner within the agreed interval."
                    reason = reason or "The supervising session requested an intervention."
                    terminate()
                    self.hold(task, reason)
                    return 75
                if process is None:
                    if fresh and action == "continue":
                        process = subprocess.Popen(command, start_new_session=True)
                    elif time.monotonic() - started >= self.timeout:
                        self.hold(task, "Awaiting the originating session's review before work starts.")
                        return 75
                if time.monotonic() - last_event >= self.interval:
                    event = self.event("review", task, "Review " + phase + " for " + self.task(task) + ".",
                                       "Name the new evidence of progress, or redirect the work.")
                    last_event = time.monotonic()
                time.sleep(min(1, self.interval))
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            if process is not None and process.poll() is None:
                terminate()

    def contract(self):
        queue = self.workspace / "RUN-ORDER.md"
        headings = (self.workspace / "TASKS.md").read_text().splitlines()
        task_ids = []
        for line in queue.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                task = line.split()[0]
                if not any(h.startswith("### " + task + " ") and "[x]" in h for h in headings):
                    raise ValueError("the goal still has undelivered work: " + self.task(task))
                task_ids.append(task)
        revisions = {repo: subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"], text=True).strip()
                     for repo in shlex.split(self.conf["REPOS"])}
        return {"goal": self.conf.get("GOAL"), "rules": (self.workspace / "DELIVERY-RULES.yaml").read_text(),
                "queue": task_ids, "revisions": revisions, "command": self.conf.get("ACCEPTANCE_CMD"),
                "origin": self.identity()}

    def live(self, revision):
        if self.conf.get("DEPLOYS", "no") == "yes":
            live = subprocess.run([str(self.workspace / "deploy.sh"), "check"],
                                  cwd=self.workspace, capture_output=True, text=True)
            if live.returncode or not re.search(r"(?m)^LIVE\b", live.stdout) or (self.runs / "live-sha").read_text().strip() != revision:
                raise ValueError("the delivered revision has not been proved live")

    def verify(self):
        self.check()
        command = self.conf.get("ACCEPTANCE_CMD", "")
        if not command:
            raise ValueError("ACCEPTANCE_CMD must exercise the delivered result as its intended user")
        contract = self.contract()
        repo, revision = next(iter(contract["revisions"].items()))
        self.live(revision)
        result = subprocess.run([sys.executable, __file__, "run", "--task", "goal", "--phase", "delivered user check", "--", "zsh", "-c", command],
                                cwd=repo, capture_output=True, text=True)
        output = self.root / ("acceptance-" + uuid.uuid4().hex + ".log")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.stdout + result.stderr)
        answer = json.loads(result.stdout) if result.returncode == 0 else {}
        if answer.get("passed") is not True or answer.get("revision") != revision:
            raise ValueError("delivered user check failed or names another revision; see " + str(output))
        for field in ("target", "journey", "expected", "observed", "outcomes"):
            if not answer.get(field):
                raise ValueError("delivered user check must name " + field + "; see " + str(output))
        rules = (self.workspace / "DELIVERY-RULES.yaml").read_text()
        outcomes = set(re.findall(r"\bid:\s*['\"]?(G[0-9]+)\b", rules))
        if not outcomes or not isinstance(answer["outcomes"], list) or not outcomes.issubset(answer["outcomes"]):
            raise ValueError("delivered user check must cover every agreed G outcome; see " + str(output))
        if self.contract() != contract:
            raise ValueError("the candidate or goal changed during acceptance; reconcile before claiming delivery")
        event = self.event("review", summary="Review the delivered user result: " + answer["observed"],
                           next_action="Confirm that the real user journey covers every agreed outcome.",
                           evidence=answer["target"] + "; " + str(output))
        save(self.root / "acceptance.json", {"revision": revision, "event": event["id"], "check": answer,
                                             "contract": contract, "evidence": event["evidence"]})
        return event

    def deliver(self):
        self.check()
        proof = read(self.root / "acceptance.json")
        review = read(self.root / "reviews" / (proof.get("event", "") + ".json"))
        if review.get("action") != "continue" or review.get("origin") != self.identity():
            raise ValueError("the originating session must review the retained delivered user evidence first")
        if self.contract() != proof.get("contract"):
            raise ValueError("the candidate, goal or acceptance command changed; reconcile retained evidence")
        revision = proof["revision"]
        self.live(revision)
        delivery = read(self.root / "delivery.json")
        if delivery.get("acceptance") == proof["event"]:
            event = read(self.root / "events" / (delivery["event"] + ".json"))
        else:
            event = self.event("delivered", summary=proof["check"]["observed"], evidence=proof["evidence"])
            save(self.root / "delivery.json", {"revision": revision, "event": event["id"],
                                               "acceptance": proof["event"]})
        if not self.flush():
            raise ValueError("user check passed; Coding Coordinator has not acknowledged the delivery message")
        return event


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="op", required=True)
    sub.add_parser("check")
    sub.add_parser("pending")
    flush = sub.add_parser("flush")
    flush.add_argument("--retry-uncertain", action="store_true")
    event = sub.add_parser("event")
    event.add_argument("kind", choices=("started", "progress", "needs_input", "built", "idle", "stopped", "attention", "review"))
    event.add_argument("--task", default="")
    event.add_argument("--summary", required=True)
    event.add_argument("--next", default="")
    event.add_argument("--evidence", default="")
    review = sub.add_parser("review")
    review.add_argument("id")
    review.add_argument("--action", choices=("continue", "yield", "stop"), required=True)
    review.add_argument("--reason", required=True)
    review.add_argument("--agent", required=True)
    review.add_argument("--session", required=True)
    run = sub.add_parser("run")
    run.add_argument("--task", required=True)
    run.add_argument("--phase", required=True)
    run.add_argument("command", nargs=argparse.REMAINDER)
    sub.add_parser("verify")
    sub.add_parser("deliver")
    hold = sub.add_parser("hold")
    hold.add_argument("--task", required=True)
    hold.add_argument("--reason", required=True)
    args = parser.parse_args()
    watch = Watch()
    if args.op == "check":
        watch.check()
        print("Supervision configured" if watch.required else "Legacy project: active supervision is not configured")
    elif args.op == "event":
        print(json.dumps(watch.event(args.kind, args.task, args.summary, args.next, args.evidence)))
        if not watch.flush():
            print("Coding Coordinator has not acknowledged pending messages.", file=sys.stderr)
    elif args.op == "review":
        print(json.dumps(watch.review(args.id, args.action, args.reason, args.agent, args.session)))
    elif args.op == "pending":
        for path in sorted((watch.root / "events").glob("*.json"), key=lambda p: p.stat().st_mtime):
            event = read(path)
            event["review"] = read(watch.root / "reviews" / path.name)
            event["message_receipt"] = read(watch.root / "messages" / path.name)
            print(json.dumps(event))
    elif args.op == "flush":
        return 0 if watch.flush(args.retry_uncertain) else 1
    elif args.op == "run":
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not command:
            parser.error("run requires a command after --")
        return watch.run(args.task, args.phase, command)
    elif args.op == "verify":
        print(json.dumps(watch.verify()))
    elif args.op == "deliver":
        print(json.dumps(watch.deliver()))
    elif args.op == "hold":
        print(json.dumps(watch.hold(args.task, args.reason)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
