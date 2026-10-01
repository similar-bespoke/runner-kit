#!/usr/bin/env python3
"""Render an agent's event stream as one readable line each.

Reads the event stream on stdin (from `claude -p --output-format stream-json
--verbose` or `codex exec --json`) and prints, with a running clock: session
start, every line the agent says, every tool call with a one-line summary, the
first line of every result (errors marked), and the final result.
"""
import json
import sys
import time


def short(value, n=160):
    text = " ".join(str(value).split())
    return text if len(text) <= n else text[:n] + " …"


def summarise_input(name, inp):
    if name == "Bash":
        return short(inp.get("description") or inp.get("command", ""), 200)
    if name in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit"):
        return inp.get("file_path", "")
    if name in ("Grep", "Glob"):
        return short(f"{inp.get('pattern', '')} {inp.get('path', '')}")
    if name in ("Agent", "Task"):
        return f"model={inp.get('model', 'default')}  {short(inp.get('prompt', ''), 120)}"
    return short(json.dumps(inp), 200)


def main():
    t0 = time.time()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            print(line, flush=True)
            continue
        ts = "%6.0fs" % (time.time() - t0)
        typ = ev.get("type")
        if typ == "system" and ev.get("subtype") == "init":
            print(f"{ts}  session started  model={ev.get('model')}  tools={len(ev.get('tools', []))}", flush=True)
        elif typ == "assistant":
            if ev.get("error"):
                print(f"{ts}  ERROR: {ev.get('error')}", flush=True)
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "text" and block["text"].strip():
                    print(f"{ts}  claude: {short(block['text'], 400)}", flush=True)
                elif block.get("type") == "tool_use":
                    print(f"{ts}  -> {block['name']}: {summarise_input(block['name'], block.get('input', {}))}", flush=True)
        elif typ == "user":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_result":
                    content = block.get("content")
                    if isinstance(content, list):
                        content = " ".join(x.get("text", "") for x in content if isinstance(x, dict))
                    flag = "ERROR " if block.get("is_error") else ""
                    print(f"{ts}     <- {flag}{short(content or '', 200)}", flush=True)
        elif typ == "result":
            cost = ev.get("total_cost_usd") or 0
            print(f"{ts}  session result: {ev.get('subtype')}  turns={ev.get('num_turns')}  cost=${cost:.2f}", flush=True)
            if ev.get("result"):
                print("      " + short(ev["result"], 600), flush=True)
        elif typ == "thread.started":                      # Codex events from here
            print(f"{ts}  session started  codex thread={ev.get('thread_id')}", flush=True)
        elif typ in ("item.started", "item.completed") and isinstance(ev.get("item"), dict):
            item, kind, ended = ev["item"], ev["item"].get("type"), typ == "item.completed"
            if kind == "agent_message" and ended:
                print(f"{ts}  codex: {short(item.get('text', ''), 400)}", flush=True)
            elif kind == "command_execution" and not ended:
                print(f"{ts}  -> shell: {short(item.get('command', ''), 200)}", flush=True)
            elif kind == "command_execution":
                flag = "ERROR " if item.get("exit_code") not in (0, None) else ""
                print(f"{ts}     <- {flag}{short(item.get('aggregated_output') or '', 200)}", flush=True)
            elif kind == "file_change" and ended:
                paths = " ".join(c.get("path", "") for c in item.get("changes", []) if isinstance(c, dict))
                print(f"{ts}  -> edit: {short(paths, 200)}", flush=True)
            elif kind == "error":
                print(f"{ts}  ERROR: {short(item.get('message', ''), 300)}", flush=True)
        elif typ == "turn.completed":
            usage = ev.get("usage") or {}
            print(f"{ts}  session result: turn completed  tokens in={usage.get('input_tokens')} out={usage.get('output_tokens')}", flush=True)
        elif typ == "error" or ev.get("error"):
            print(f"{ts}  ERROR: {short(ev.get('error') or ev, 300)}", flush=True)


if __name__ == "__main__":
    main()
