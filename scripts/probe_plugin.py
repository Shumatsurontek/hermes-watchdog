"""Load the real plugin and run its tool in a real parent conversation.
The model is a scripted local HTTP fixture; this is not a live-provider benchmark.
"""

import argparse
import faulthandler
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--hermes-source", required=True)
p.add_argument("--output", required=True)
p.add_argument("--plugin-path")
a = p.parse_args()
root = Path(a.plugin_path).resolve() if a.plugin_path else Path(__file__).resolve().parents[1]
home = Path(os.environ["HERMES_HOME"]).resolve()
assert str(home).startswith("/private/tmp/") or str(home).startswith("/tmp/"), "Disposable /tmp profile required"
(home / "plugins").mkdir(parents=True, exist_ok=True)
link = home / "plugins" / "hermes-watchdog"
if not link.exists():
    link.symlink_to(root, target_is_directory=True)
(home / "config.yaml").write_text(
    json.dumps(
        {
            "plugins": {
                "enabled": ["hermes-watchdog"],
                "isolation": "in_process",
                "entries": {"hermes-watchdog": {"allow_gateway_injection": True}},
            }
        }
    )
)
sys.path.insert(0, a.hermes_source)
import hermes_bootstrap  # noqa: F401 -- activate host dependencies

faulthandler.dump_traceback_later(90, exit=True)
from gateway.session_context import clear_session_vars, set_session_vars
from hermes_cli.plugins import get_plugin_manager
from plugins.plugin_storage import plugin_db
from run_agent import AIAgent

calls = []


class Model(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        n = int(self.headers["content-length"])
        assert n < 2_000_000
        b = json.loads(self.rfile.read(n))
        names = [t.get("function", {}).get("name") for t in b.get("tools", [])]
        calls.append(names)
        assert len(calls) <= 20
        last = b.get("messages", [])[-1] if b.get("messages") else {}
        parent_request = "tool_call" in names or "watchdog_start" in names
        start = parent_request and last.get("role") == "user" and "LAUNCH_WATCHDOG_PROBE" in str(last.get("content"))
        content = "Parent is available." if parent_request else "Worker completed the fixture."
        tool_calls = (
            [
                {
                    "index": 0,
                    "id": "call_probe",
                    "type": "function",
                    "function": {
                        "name": "tool_call",
                        "arguments": json.dumps(
                            {
                                "calls": [
                                    {
                                        "name": "watchdog_start",
                                        "arguments": {
                                            "goal": "Return Worker completed the fixture.",
                                            "deadline_seconds": 30,
                                        },
                                    }
                                ]
                            }
                        ),
                    },
                }
            ]
            if start
            else None
        )
        if not parent_request and names:
            time.sleep(2)
        message = {"role": "assistant", "content": None if start else content}
        if tool_calls:
            message["tool_calls"] = tool_calls
        result = {
            "id": "fixture",
            "object": "chat.completion",
            "model": "watchdog-probe",
            "created": int(time.time()),
            "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if start else "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        if b.get("stream"):
            chunk = dict(
                result,
                object="chat.completion.chunk",
                choices=[{"index": 0, "delta": message, "finish_reason": "tool_calls" if start else "stop"}],
            )
            payload = ("data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n").encode()
        else:
            payload = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream" if b.get("stream") else "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


server = ThreadingHTTPServer(("127.0.0.1", 0), Model)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
manager = get_plugin_manager()
manager.discover_and_load()
parent_id = "ses_watchdog_" + str(int(time.time()))
tokens = set_session_vars(platform="desktop", source="desktop", session_key=parent_id, session_id=parent_id)
try:
    parent = AIAgent(
        base_url=f"http://127.0.0.1:{server.server_port}/v1",
        api_key="loopback-fixture",
        provider="custom",
        model="watchdog-probe",
        max_iterations=3,
        max_tokens=256,
        request_overrides={"temperature": 0},
        run_budget_seconds=20,
        enabled_toolsets=["search", "watchdog"],
        session_id=parent_id,
        gateway_session_key=parent_id,
        platform="desktop",
        quiet_mode=True,
        skip_context_files=True,
        skip_memory=True,
        skip_background_review=True,
        load_soul_identity=False,
    )
    t0 = time.monotonic()
    response = parent.run_conversation(
        "LAUNCH_WATCHDOG_PROBE: launch the fixture with watchdog_start, then reply immediately."
    )
    returned = time.monotonic() - t0
    print(
        "model calls",
        calls,
        "reply",
        response.get("final_response"),
        "tool results",
        [m for m in response.get("messages", []) if m.get("role") == "tool"],
        flush=True,
    )
    db = plugin_db("hermes-watchdog")
    row = db.execute("SELECT id FROM tasks WHERE parent_id=?", (parent_id,)).fetchone()
    assert row, "Parent did not invoke watchdog_start"
    task_id = row[0]
    at_return = json.loads(db.execute("SELECT data FROM attempts WHERE task_id=?", (task_id,)).fetchone()[0])
    for _ in range(30):
        data = json.loads(db.execute("SELECT data FROM attempts WHERE task_id=?", (task_id,)).fetchone()[0])
        if data["execution"] in ("succeeded", "failed", "unknown"):
            break
        time.sleep(0.5)
    assert data["execution"] == "succeeded", data
    assert data["child_session"], "subagent_start hook did not correlate the child"
    assert data["observation_count"] > 0, "No real lifecycle observations recorded"
    report = {
        "transport": "scripted loopback OpenAI-compatible fixture",
        "parent_return_seconds": round(returned, 3),
        "state_when_parent_returned": at_return["execution"],
        "worker_state": data["execution"],
        "observations": data["observation_count"],
        "child_identity_correlated": bool(data["child_session"]),
        "parent_reply": response.get("final_response"),
        "effective_request_tools": calls,
        "notification": data["notification"],
        "native_desktop_window": "not tested",
    }
    Path(a.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    db.close()
finally:
    clear_session_vars(tokens)
    manager.unload()
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
    faulthandler.cancel_dump_traceback_later()
