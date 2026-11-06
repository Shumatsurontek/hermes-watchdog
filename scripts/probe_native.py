"""Real Hermes native delegation, scripted loopback model; no provider or Desktop claims."""

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
p.add_argument("--plugin-path", help="Runtime stage to load instead of the source checkout")
a = p.parse_args()
home = Path(os.environ["HERMES_HOME"]).resolve()
assert str(home).startswith("/private/tmp/"), "Disposable /tmp profile required"
fixture = home / "plugins" / "watchdog-contract"
fixture.mkdir(parents=True, exist_ok=True)
(home / "contract.jsonl").unlink(missing_ok=True)
(fixture / "plugin.yaml").write_text('name: watchdog-contract\nversion: "0.1.0"\n')
(fixture / "__init__.py").write_text("""
import json
import threading
from pathlib import Path
from gateway.session_context import get_session_env
lock = threading.Lock()
def register(ctx):
    def hook(name):
        def callback(**kw):
            fields = ("parent_session_id", "child_session_id", "session_id", "parent_turn_id",
                      "turn_id", "tool_call_id", "tool_name", "status", "request_id", "outcome")
            item = {k: kw[k] for k in fields if k in kw}
            item.update(hook=name, bound_id=get_session_env("HERMES_SESSION_ID"),
                        bound_key=get_session_env("HERMES_SESSION_KEY"), surface=ctx.session_surface())
            with lock:
                with (Path(__file__).parents[2] / "contract.jsonl").open("a") as f:
                    f.write(json.dumps(item) + "\\n")
        return callback
    for name in ("subagent_start", "subagent_stop", "pre_tool_call", "post_tool_call",
                 "on_human_input_request", "on_human_input_resolved"):
        ctx.register_hook(name, hook(name))
    def failure(args, **kw):
        from tools.human_input_hooks import human_input_request
        with human_input_request("approval", prompt="fixture only") as request:
            request.outcome = "denied"
        return json.dumps({"error": "fixture upstream unavailable"})
    ctx.register_tool(name="contract_failure", toolset="contract",
        schema={"name": "contract_failure", "description": "Fixture failure",
                "parameters": {"type": "object", "properties": {}}}, handler=failure)
""")
plugin = home / "plugins" / "hermes-watchdog"
if not plugin.exists():
    plugin.symlink_to(
        Path(a.plugin_path).resolve() if a.plugin_path else Path(__file__).resolve().parents[1],
        target_is_directory=True,
    )
(home / "config.yaml").write_text(
    json.dumps(
        {
            "plugins": {
                "enabled": ["watchdog-contract", "hermes-watchdog"],
                "isolation": "in_process",
                "entries": {"hermes-watchdog": {"allow_gateway_injection": True}},
            },
            "delegation": {"max_spawn_depth": 3, "max_iterations": 5},
            "providers": {"custom": {"request_timeout_seconds": 10, "stale_timeout_seconds": 10}},
        }
    )
)
sys.path.insert(0, a.hermes_source)
import hermes_bootstrap  # noqa: F401
from gateway.session_context import clear_session_vars, set_session_vars
from hermes_cli.plugins import get_plugin_manager
from plugins.plugin_storage import plugin_db
from run_agent import AIAgent

faulthandler.dump_traceback_later(90, exit=True)
calls = []
calls_lock = threading.Lock()


class Model(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        n = int(self.headers["content-length"])
        assert n < 2_000_000
        body = json.loads(self.rfile.read(n))
        if "messages" not in body:
            self.send_error(400, "Fixture supports chat completions only")
            return
        messages = body["messages"]
        last = messages[-1]
        goal = str(last.get("content", ""))
        name, args = None, {}
        if last["role"] == "user":
            if "ROOT_FIXTURE" in goal:
                name, args = "delegate_task", {"tasks": [{"goal": "NEST_FIXTURE"}, {"goal": "LEAF_FIXTURE"}]}
            elif "NEST_FIXTURE" in goal:
                name, args = "delegate_task", {"tasks": [{"goal": "LEAF_FIXTURE"}]}
            elif "LEAF_FIXTURE" in goal:
                name = "contract_failure"
        # A second distinct call in each leaf crosses the cross-worker threshold.
        elif last["role"] == "tool" and "fixture upstream unavailable" in goal:
            failed = sum(
                m["role"] == "tool" and "fixture upstream unavailable" in str(m.get("content")) for m in messages
            )
            if failed == 1:
                name = "contract_failure"
        with calls_lock:
            calls.append(name or "reply")
            assert len(calls) <= 24
            index = len(calls)
        names = [t.get("function", {}).get("name") for t in body.get("tools", [])]
        fn, fnargs = (
            ("tool_call", {"calls": [{"name": name, "arguments": args}]})
            if name not in names and "tool_call" in names
            else (name, args)
        )
        message = {"role": "assistant", "content": None if name else "Fixture result returned."}
        if name:
            message["tool_calls"] = [
                {
                    "index": 0,
                    "id": f"call_{index}",
                    "type": "function",
                    "function": {"name": fn, "arguments": json.dumps(fnargs)},
                }
            ]
        result = {
            "id": "fixture",
            "object": "chat.completion",
            "model": "watchdog-native-probe",
            "created": int(time.time()),
            "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if name else "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        if body.get("stream"):
            result.update(
                object="chat.completion.chunk",
                choices=[{"index": 0, "delta": message, "finish_reason": "tool_calls" if name else "stop"}],
            )
            payload = ("data: " + json.dumps(result) + "\n\ndata: [DONE]\n\n").encode()
        else:
            payload = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream" if body.get("stream") else "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


server = ThreadingHTTPServer(("127.0.0.1", 0), Model)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
manager = get_plugin_manager()
manager.discover_and_load()
parent_id = "ses_native_probe_" + str(time.time_ns())
tokens = set_session_vars(platform="desktop", source="desktop", session_key=parent_id, session_id=parent_id)
try:
    parent = AIAgent(
        base_url=f"http://127.0.0.1:{server.server_port}/v1",
        api_key="loopback-fixture",
        provider="custom",
        model="watchdog-native-probe",
        max_iterations=5,
        max_tokens=256,
        request_overrides={"temperature": 0},
        run_budget_seconds=30,
        enabled_toolsets=["delegation", "contract"],
        session_id=parent_id,
        gateway_session_key=parent_id,
        platform="desktop",
        quiet_mode=True,
        skip_context_files=True,
        skip_memory=True,
        skip_background_review=True,
        load_soul_identity=False,
    )
    response = parent.run_conversation("ROOT_FIXTURE")
    print(
        "fixture tool responses",
        [m.get("content") for m in response.get("messages", []) if m.get("role") == "tool"],
        flush=True,
    )
    for _ in range(100):
        path = home / "contract.jsonl"
        events = [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
        if sum(e["hook"] == "subagent_stop" for e in events) >= 3:
            break
        time.sleep(0.2)
    starts = [e for e in events if e["hook"] == "subagent_start"]
    assert len(starts) == 3, (starts, calls, response.get("final_response"))
    assert any(e["parent_session_id"] != parent_id for e in starts), "No nested ancestry"
    assert all(e["bound_id"] == e["parent_session_id"] for e in starts), starts
    assert all(e["bound_key"] == parent_id for e in starts), starts
    failures = [e for e in events if e["hook"] == "post_tool_call" and e.get("tool_name") == "contract_failure"]
    assert len(failures) == 4 and all(
        e["status"] == "error" and e["turn_id"] and e["tool_call_id"] for e in failures
    ), failures
    waits = [e for e in events if e["hook"].startswith("on_human_input")]
    assert len(waits) == 8 and len({e["request_id"] for e in waits}) == 4, waits
    report = {
        "transport": "scripted loopback; no live provider or native Desktop window",
        "calls": calls,
        "events": events,
        "native_runs": len(starts),
    }
    db = plugin_db("hermes-watchdog")
    try:
        states = db.execute("SELECT state FROM native_runs WHERE root_id=?", (parent_id,)).fetchall()
        incidents = db.execute("SELECT kind,status FROM incidents WHERE root_id=?", (parent_id,)).fetchall()
        assert len(states) == 3 and all(r[0] == "returned" for r in states), states
        assert sum(r[0] == "related_failures" for r in incidents) == 1, incidents
        assert sum(r[0] == "human_input" and r[1] == "resolved" for r in incidents) == 4, incidents
        assert db.execute("SELECT count(*) FROM tasks WHERE parent_id=?", (parent_id,)).fetchone()[0] == 0
        report["watchdog"] = {
            "returned_workers": 3,
            "related_incidents": 1,
            "resolved_waits": 4,
            "legacy_reservations": 0,
        }
    finally:
        db.close()
    Path(a.output).write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {"native_runs": len(starts), "failures": len(failures), "human_wait_pairs": 4, "model_calls": len(calls)}
        )
    )
finally:
    clear_session_vars(tokens)
    manager.unload()
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
    faulthandler.cancel_dump_traceback_later()
