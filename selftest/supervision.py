#!/usr/bin/env python3
"""Exercise supervision at command, process, queue and notification boundaries.

All recipients and agent sessions here are local stand-ins. No real messages
or provider requests are sent.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

KIT = Path(__file__).resolve().parents[1]
WATCH = KIT / "bin/runner_watch.py"


class Supervision(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="runner-oversight-")
        self.addCleanup(self.temp.cleanup)
        self.ws = Path(self.temp.name)
        self.conf = self.ws / "runner.conf"
        self.env = dict(os.environ, RUNNER_CONF=str(self.conf), RUNNER_DASHBOARD_URL="off")
        self.helper = self.ws / "coordinator"
        self.helper.write_text("#!/usr/bin/env python3\n" + """
import json, pathlib, sys, time
p=pathlib.Path(__file__).parent
with (p/'received').open('a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')
time.sleep(.05)
if (p/'fail-send').exists(): sys.exit(1)
print('sent (202)')
""")
        self.helper.chmod(0o755)
        self.bridge = self.ws / "bridge.py"
        self.bridge.write_text("""import json, pathlib, sys
e=json.load(sys.stdin)
p=pathlib.Path(__file__).parent
action=(p/'action').read_text() if (p/'action').exists() else 'continue'
if (p/'yield-first').exists() and e['task']=='1.1': action='yield'
print(json.dumps(dict(e['origin'], action=action, reason='Checked the retained user result and current work.')))
""")
        self.settings = {
            "PROJECT": "Saved shopping list", "WORKSPACE": str(self.ws), "REPOS": str(self.ws),
            "GOAL": "A user can save a shopping list and reopen it.", "SUPERVISION_REQUIRED": "yes",
            "ORIGIN_AGENT": "codex", "ORIGIN_SESSION": "test-origin",
            "SUPERVISION_INTERVAL": ".05", "SUPERVISION_TIMEOUT": ".4",
            "COORDINATOR_CMD": str(self.helper), "SUPERVISOR_CMD": "",
            "ADAPTER_T": "stub", "MODEL_T": "none", "SUPERVISOR": "T",
            "PRODUCT_DIRS": "", "FREE_DIRS": "", "NOTIFY": "none", "CHECK_CMD": "",
            "DEPLOYS": "no", "STOP_STREAK": "0"}
        self.write_conf()
        for name in ("SESSION-PROMPT.md", "REVIEW-STUB.md", "SUPERVISOR-PROMPT.md"):
            (self.ws / name).write_text("# Prompt\n---\nDo the task.\n")
        (self.ws / "DELIVERY-RULES.yaml").write_text('goal_outcomes:\n  - id: G1\n    outcome: Save and reopen a list.\n')
        (self.ws / "DECISIONS.md").write_text("# Decisions\n")
        (self.ws / "TASKS.md").write_text("### 1.1 A list is saved [ ]  M: T medium, R: T medium\nG1: Save a list.\nFiles: delivered.txt.\n")
        (self.ws / "RUN-ORDER.md").write_text("1.1\n")
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "selftest@example.invalid")
        self.git("config", "user.name", "Selftest")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.hooksPath", str(self.ws / ".git/hooks"))
        (self.ws / ".gitignore").write_text("runs/\nreceived\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Initial user tool")

    def write_conf(self):
        import shlex
        self.conf.write_text("".join(k + "=" + shlex.quote(v) + "\n" for k, v in self.settings.items()))

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.ws), *args], text=True).strip()

    def cli(self, *args, ok=True):
        r = subprocess.run([sys.executable, str(WATCH), *args], env=self.env, cwd=self.ws,
                           capture_output=True, text=True, timeout=15)
        if ok:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def event(self, kind="review", task="1.1"):
        return json.loads(self.cli("event", kind, "--task", task, "--summary", "The list now reopens with saved items.").stdout)

    def acknowledge(self, event, action="continue", session="test-origin", ok=True):
        return self.cli("review", event["id"], "--agent", "codex", "--session", session,
                        "--action", action, "--reason", "Compared the reopened list with the original items.", ok=ok)

    def enable_bridge(self):
        self.settings["SUPERVISOR_CMD"] = sys.executable + " " + str(self.bridge)
        self.write_conf()

    def client(self, version="0.162.0-alpha.test"):
        directory = self.ws / "client with spaces"
        directory.mkdir()
        client = directory / "codex"
        client.write_text("#!/usr/bin/env python3\n" + """
import json,pathlib,sys
p=pathlib.Path(__file__).parent.parent
if sys.argv[1:]==['--version']:
    print('codex-cli VERSION')
elif sys.argv[1:]==['login','status']:
    print('Logged in using ChatGPT')
else:
    with (p/'client-calls').open('a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')
    if (p/'reject-request').exists(): sys.exit(1)
    print(json.dumps({'type':'turn.completed'}))
""".replace("VERSION", version))
        client.chmod(0o755)
        self.settings["CODEX_BIN"] = str(client)
        self.write_conf()
        return client

    def test_build_resume_and_review_use_the_same_selected_client_and_model(self):
        self.client()
        adapter = KIT / "adapters/codex.sh"
        for operation in ("adapter_start", "adapter_resume"):
            r = subprocess.run(["zsh", "-c", '''source "$RUNNER_CONF"; source "$1"
A_MODEL=gpt-6.1-sol; A_EFFORT=high; A_TASK_ID=1.1; A_SESSION=retained-session
A_PROMPT='Complete the user task'; A_DIRS=("$WORKSPACE"); $2''', "adapter-check", str(adapter), operation],
                               env=self.env, cwd=self.ws, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run([str(KIT / "bin/runner-codex"), "exec", "review", "-m", "gpt-6.1-sol", "--ephemeral", "Review the staged diff"],
                           env=self.env, cwd=self.ws, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = [json.loads(line) for line in (self.ws / "client-calls").read_text().splitlines()]
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(call[call.index('-m') + 1] == "gpt-6.1-sol" for call in calls))
        self.assertEqual(calls[1][:3], ["exec", "resume", "retained-session"])
        self.assertEqual(calls[2][:2], ["exec", "review"])

    def test_old_client_is_refused_without_path_fallback(self):
        self.client("0.151.0")
        r = subprocess.run([str(KIT / "bin/runner-codex"), "exec", "-m", "gpt-6.1-sol", "Do the task"],
                           env=self.env, cwd=self.ws, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.ws / "client-calls").exists())
        self.assertIn("No fallback", r.stderr)

    def test_failed_selected_model_is_not_replaced(self):
        self.client()
        (self.ws / "reject-request").touch()
        r = subprocess.run([str(KIT / "bin/runner-codex"), "exec", "review", "-m", "gpt-6.1-sol", "Review the staged diff"],
                           env=self.env, cwd=self.ws, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        calls = [json.loads(line) for line in (self.ws / "client-calls").read_text().splitlines()]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][calls[0].index('-m') + 1], "gpt-6.1-sol")

    def test_unpinned_model_is_refused(self):
        self.client()
        r = subprocess.run([str(KIT / "bin/runner-codex"), "exec", "Do the task"],
                           env=self.env, cwd=self.ws, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.ws / "client-calls").exists())

    def test_doctor_uses_project_client_before_checking_sign_in(self):
        self.client()
        kit = self.ws / "kit"
        shutil.copytree(KIT, kit, ignore=shutil.ignore_patterns(".git", "__pycache__", "skills"))
        wrapper = kit / "bin/runner-codex"
        wrapper.write_text(wrapper.read_text().replace(
            "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex",
            str(self.ws / "no-desktop-client")))
        self.settings.update(ADAPTER_S="codex", MODEL_S="gpt-6.1-sol", DEFAULT_BUILDER="S", SUPERVISOR="S")
        self.write_conf()
        subprocess.run([str(kit / "bin/runner-init"), str(self.ws), str(self.ws)],
                       capture_output=True, text=True, check=True)
        env = {k: v for k, v in self.env.items() if k != "RUNNER_CONF"}
        # tmux is not needed to run this setup check or the self-test.
        commands = self.ws / "commands"
        commands.mkdir()
        (commands / "tmux").write_text("#!/bin/sh\nprintf 'tmux test\\n'\n")
        (commands / "tmux").chmod(0o755)
        env["PATH"] = str(commands) + os.pathsep + env.get("PATH", "")
        r = subprocess.run([str(kit / "bin/runner-doctor"), str(self.conf)],
                           cwd=self.ws.parent, env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("agent codex: installed, signed in", r.stdout)
        self.assertNotIn("MISSING", r.stdout)

    def received(self):
        p = self.ws / "received"
        return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []

    def test_exact_origin_required(self):
        event = self.event()
        self.assertNotEqual(self.acknowledge(event, session="another-session", ok=False).returncode, 0)
        self.acknowledge(event)

    def test_rejected_model_needs_a_decision_instead_of_a_timed_retry(self):
        raw = self.ws / "rejected.jsonl"
        raw.write_text(json.dumps({"type": "turn.failed", "error": {"message": "invalid_request_error: The 'gpt-6.1-sol' model is not supported when using Codex with a ChatGPT account."}}) + "\n")
        r = subprocess.run(["zsh", "-c", 'source "$1"; adapter_read_result "$2"; print -r -- "$RESULT_KIND"',
                            "adapter-check", str(KIT / "adapters/codex.sh"), str(raw)],
                           env=self.env, capture_output=True, text=True, check=True)
        self.assertEqual(r.stdout.strip(), "config")
        event = json.loads(self.cli("hold", "--task", "1.1", "--reason", "The configured model is unavailable. Check the account model list before retrying.").stdout)
        self.assertTrue((self.ws / "runs/oversight/yielded/1.1.json").exists())
        self.assertFalse(any((self.ws / "runs").glob("available-*")))
        self.assertIn(event["id"], self.received()[0][-1])

    def test_only_actionable_coordinator_messages(self):
        for kind in ("started", "progress", "built", "idle", "stopped"):
            self.event(kind)
        self.assertEqual(self.received(), [])
        self.event("needs_input")
        self.event("attention")
        self.assertEqual([m[1] for m in self.received()], ["question", "blocker"])
        self.assertIn(self.settings["GOAL"], self.received()[0][-1])

    def test_uncertain_send_is_not_blindly_repeated(self):
        (self.ws / "fail-send").touch()
        event = self.event("needs_input")
        (self.ws / "fail-send").unlink()
        self.assertNotEqual(self.cli("flush", ok=False).returncode, 0)
        self.assertEqual(len(self.received()), 1)
        self.cli("flush", "--retry-uncertain")
        self.cli("flush")
        self.assertEqual(len(self.received()), 2)
        self.assertTrue(all(event["id"] in m[-1] for m in self.received()))

    def test_uncertain_message_does_not_hide_an_independent_question(self):
        (self.ws / "fail-send").touch()
        first = self.event("needs_input")
        (self.ws / "fail-send").unlink()
        second = self.event("needs_input", "2.1")
        self.assertEqual(len(self.received()), 2)
        self.assertIn(first["id"], self.received()[0][-1])
        self.assertIn(second["id"], self.received()[1][-1])

    def test_concurrent_senders_do_not_duplicate_messages(self):
        self.settings["COORDINATOR_CMD"] = str(self.ws / "not-installed")
        self.write_conf()
        self.event("needs_input")
        self.settings["COORDINATOR_CMD"] = str(self.helper)
        self.write_conf()
        processes = [subprocess.Popen([sys.executable, str(WATCH), "flush"], env=self.env,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(3)]
        for p in processes:
            p.communicate(timeout=10)
        self.assertEqual(len(self.received()), 1)

    def test_useful_quiet_work_can_exceed_supervision_timeout(self):
        self.enable_bridge()
        self.cli("run", "--task", "1.1", "--phase", "user check", "--", sys.executable,
                 "-c", "import time; time.sleep(.8); print('user result verified')")
        self.assertFalse((self.ws / "runs/oversight/yielded/1.1.json").exists())

    def test_lost_supervision_stops_descendants_and_preserves_work(self):
        self.acknowledge(self.event())
        child = "import time,pathlib; time.sleep(1.5); pathlib.Path('escaped').touch()"
        command = "import subprocess,time,pathlib; pathlib.Path('preserved').write_text('completed work'); subprocess.Popen([%r,'-c',%r]); time.sleep(30)" % (sys.executable, child)
        r = self.cli("run", "--task", "1.1", "--phase", "builder", "--", sys.executable, "-c", command, ok=False)
        self.assertEqual(r.returncode, 75, r.stderr)
        self.assertEqual((self.ws / "preserved").read_text(), "completed work")
        time.sleep(1.6)
        self.assertFalse((self.ws / "escaped").exists())
        self.assertTrue((self.ws / "runs/oversight/yielded/1.1.json").exists())

    def test_parent_can_interrupt_active_work(self):
        self.enable_bridge()
        command = "import time,pathlib; pathlib.Path('preserved').touch(); pathlib.Path('action').write_text('yield'); time.sleep(30)"
        r = self.cli("run", "--task", "1.1", "--phase", "review", "--", sys.executable, "-c", command, ok=False)
        self.assertEqual(r.returncode, 75, r.stderr)
        self.assertTrue((self.ws / "preserved").exists())

    def test_yielded_task_does_not_block_an_independent_task(self):
        self.enable_bridge()
        (self.ws / "yield-first").touch()
        with (self.ws / "TASKS.md").open("a") as f:
            f.write("### 2.1 A list can be reopened [ ]  M: T medium, R: T medium\nG1: Reopen a list.\nFiles: delivered.txt.\n")
        (self.ws / "RUN-ORDER.md").write_text("1.1\n2.1\n")
        stub = self.ws / "agent.sh"
        stub.write_text('''source "$RUNNER_CONF"
echo 'saved and reopened' > delivered.txt
git add delivered.txt
git commit -qm "$1: Save and reopen a list"
python3 -c 'from pathlib import Path; p=Path("TASKS.md"); p.write_text(p.read_text().replace("A list can be reopened [ ]", "A list can be reopened [x]"))'
echo "RUNNER: done $(git rev-parse HEAD)"
''')
        env = dict(self.env, STUB_SCRIPT=str(stub), QUEUE_ONCE="1")
        for _ in range(2):
            r = subprocess.run([str(KIT / "bin/run_queue.sh")], env=env, cwd=self.ws,
                               capture_output=True, text=True, timeout=15)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.ws / "runs/waiting/1.1").exists())
        self.assertIn("A list can be reopened [x]", (self.ws / "TASKS.md").read_text())
        self.assertIn("2.1:", self.git("log", "-1", "--format=%s"))

    def acceptance(self):
        # A real local user tool: writes and reopens the requested list.
        script = self.ws / "accept.py"
        script.write_text('''import json,pathlib,subprocess
p=pathlib.Path('list.txt'); p.write_text('milk\\nbread\\n')
actual=p.read_text()
print(json.dumps(dict(passed=actual=='milk\\nbread\\n',revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),target=str(p),journey='Save milk and bread, close the file and reopen it.',expected='Milk and bread remain.',observed='The reopened list contains milk and bread.',outcomes=['G1'])))
''')
        (self.ws / "TASKS.md").write_text((self.ws / "TASKS.md").read_text().replace("[ ]", "[x]"))
        self.settings["ACCEPTANCE_CMD"] = sys.executable + " " + str(script)
        self.write_conf()
        self.enable_bridge()

    def test_completion_needs_real_user_check_and_originating_review(self):
        self.assertNotEqual(self.cli("verify", ok=False).returncode, 0)
        self.acceptance()
        # Disable automatic evidence review after enabling active command reviews.
        event = json.loads(self.cli("verify").stdout)
        self.settings["SUPERVISOR_CMD"] = ""
        self.write_conf()
        receipt = self.ws / "runs/oversight/reviews" / (event["id"] + ".json")
        receipt.unlink()
        self.assertNotEqual(self.cli("deliver", ok=False).returncode, 0)
        self.acknowledge(event)
        self.cli("deliver")
        self.cli("deliver")
        self.assertEqual([m[1] for m in self.received()], ["done"])
        self.assertIn("milk", self.received()[0][3])

    def test_changed_candidate_cannot_reuse_old_delivery_proof(self):
        self.acceptance()
        self.cli("verify")
        self.git("commit", "--allow-empty", "-qm", "Changed candidate")
        self.assertNotEqual(self.cli("deliver", ok=False).returncode, 0)
        self.assertEqual(self.received(), [])

    def test_changed_goal_cannot_reuse_old_delivery_proof(self):
        self.acceptance()
        self.cli("verify")
        with (self.ws / "DELIVERY-RULES.yaml").open("a") as f:
            f.write("  - id: G2\n    outcome: Share a list.\n")
        self.assertNotEqual(self.cli("deliver", ok=False).returncode, 0)
        self.assertEqual(self.received(), [])

    def test_new_pending_work_cannot_reuse_old_delivery_proof(self):
        self.acceptance()
        self.cli("verify")
        with (self.ws / "TASKS.md").open("a") as f:
            f.write("### 2.1 A list can be shared [ ]  M: T medium, R: T medium\n")
        with (self.ws / "RUN-ORDER.md").open("a") as f:
            f.write("2.1\n")
        self.assertNotEqual(self.cli("deliver", ok=False).returncode, 0)
        self.assertEqual(self.received(), [])

    def test_separate_repository_keeps_originating_supervision(self):
        self.acceptance()
        repo = self.ws / "code"
        self.git("clone", "-q", str(self.ws), str(repo))
        self.settings["REPOS"] = str(repo)
        self.write_conf()
        # Invoke exactly as documented, with no RUNNER_CONF environment.
        env = {k: v for k, v in self.env.items() if k != "RUNNER_CONF"}
        r = subprocess.run([sys.executable, str(WATCH), "verify"], cwd=self.ws, env=env,
                           capture_output=True, text=True, timeout=15)
        self.assertEqual(r.returncode, 0, r.stderr)
        reviews = [json.loads(p.read_text()) for p in (self.ws / "runs/oversight/events").glob("*.json")]
        self.assertTrue(any(e["task"] == "goal" and e["origin"]["session"] == "test-origin" for e in reviews))

    def test_sign_in_question_sent_once_and_other_provider_runs(self):
        # Local adapter copy simulates an unavailable provider, not a new policy.
        kit = self.ws / "kit"
        shutil.copytree(KIT, kit, ignore=shutil.ignore_patterns(".git", "__pycache__", "skills"))
        adapter = kit / "adapters/unavailable.sh"
        adapter.write_text('AGENT_NAME="Unavailable provider"\nAGENT_BIN=zsh\nAGENT_LOGIN_CMD="provider login"\nadapter_signed_in() { return 1; }\n')
        self.enable_bridge()
        self.settings.update(ADAPTER_U="unavailable", MODEL_U="none")
        self.write_conf()
        (self.ws / "TASKS.md").write_text('''### 1.1 A list is saved [ ]  M: U medium, R: T medium
G1: Save a list.
Files: delivered.txt.
### 2.1 A list can be reopened [ ]  M: T medium, R: T medium
G1: Reopen a list.
Files: delivered.txt.
''')
        (self.ws / "RUN-ORDER.md").write_text("1.1\n2.1\n")
        stub = self.ws / "agent.sh"
        stub.write_text('''source "$RUNNER_CONF"
echo 'saved and reopened' > delivered.txt
git add delivered.txt
git commit -qm "$1: Reopen a saved list"
python3 -c 'from pathlib import Path; p=Path("TASKS.md"); p.write_text(p.read_text().replace("A list can be reopened [ ]", "A list can be reopened [x]"))'
echo "RUNNER: done $(git rev-parse HEAD)"
''')
        env = dict(self.env, STUB_SCRIPT=str(stub), QUEUE_ONCE="1")
        for _ in range(2):
            r = subprocess.run([str(kit / "bin/run_queue.sh")], cwd=self.ws, env=env,
                               capture_output=True, text=True, timeout=15)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([m[1] for m in self.received()], ["question"])
        self.assertIn("A list can be reopened [x]", (self.ws / "TASKS.md").read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
