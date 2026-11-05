"""Real Hermes lifecycle against a deterministic loopback model; no account credentials.
Run with HERMES_HOME pointing at a disposable profile and --hermes-source PATH.
"""

import faulthandler

faulthandler.dump_traceback_later(30, exit=True)
import argparse
import contextvars
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--hermes-source", required=True)
p.add_argument("--output", required=True)
args = p.parse_args()
sys.path.insert(0, args.hermes_source)
import hermes_bootstrap  # noqa: F401 -- activates the host-owned dependency environment
from agent.subagent_lifecycle import (
    SubagentLaunchRequest,
    SubagentLifecycleService,
    bind_subagent_parent,
    get_active_subagent_parent,
)
from run_agent import AIAgent

requests = []
control_ready = threading.Event()


class Model(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        size = int(self.headers["content-length"])
        assert size < 2_000_000
        body = json.loads(self.rfile.read(size))
        requests.append(sorted(t.get("function", {}).get("name", "") for t in body.get("tools", [])))
        assert len(requests) <= 10
        if body.get("tools") and "CONTROL_PROBE" in json.dumps(body.get("messages", [])):
            control_ready.set()
        time.sleep(0.5)
        result = {
            "id": "probe",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "watchdog-probe",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "Probe completed."}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        data = json.dumps(result).encode()
        if body.get("stream"):
            chunk = dict(
                result,
                object="chat.completion.chunk",
                choices=[
                    {"index": 0, "delta": {"role": "assistant", "content": "Probe completed."}, "finish_reason": "stop"}
                ],
            )
            data = ("data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream" if body.get("stream") else "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


server = ThreadingHTTPServer(("127.0.0.1", 0), Model)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    print("Constructing real parent", flush=True)
    parent = AIAgent(
        base_url=f"http://127.0.0.1:{server.server_port}/v1",
        api_key="loopback-fixture",
        provider="custom",
        model="watchdog-probe",
        max_iterations=3,
        max_tokens=128,
        request_overrides={"temperature": 0},
        run_budget_seconds=15,
        enabled_toolsets=["search"],
        session_id="watchdog-probe-parent",
        quiet_mode=True,
        skip_context_files=True,
        skip_memory=True,
        skip_background_review=True,
        load_soul_identity=False,
    )
    print("Parent constructed", flush=True)
    svc = SubagentLifecycleService(get_active_subagent_parent)
    start = time.monotonic()
    with bind_subagent_parent(parent):
        print("Launching real child", flush=True)
        handle = svc.launch(
            SubagentLaunchRequest(
                goal="Reply with Probe completed.",
                model=None,
                provider=None,
                allowed_toolsets=("search",),
                role="leaf",
                correlation_id="probe-1",
            )
        )
        owned = contextvars.copy_context()
    print("Child launched", flush=True)
    launch_ms = round((time.monotonic() - start) * 1000, 2)
    unbound = svc.status(handle).state.value
    terminal = owned.run(svc.wait, handle, timeout_seconds=20)
    result = owned.run(svc.result, handle)
    print("terminal", terminal.state, terminal.diagnostic, "ready", result.ready, "requests", requests, flush=True)
    assert terminal.completed and result.ready
    assert unbound == "UNKNOWN"
    with bind_subagent_parent(parent):
        second = svc.launch(
            SubagentLaunchRequest(
                goal="CONTROL_PROBE: Reply with the fixture result.",
                model=None,
                provider=None,
                allowed_toolsets=("search",),
                role="leaf",
                correlation_id="probe-cancel",
            )
        )
        control = contextvars.copy_context()
    assert control_ready.wait(timeout=5), "Control fixture never reached model request"
    steer_accepted = control.run(svc.steer, second, "Return the fixture result concisely.")
    cancel = control.run(svc.cancel, second, reason="explicit integration test cancellation")
    cancelled = control.run(svc.wait, second, timeout_seconds=10)
    assert cancel.accepted or cancel.already_terminal
    assert cancelled.completed, "Cooperative cancellation not confirmed within test budget"
    report = {
        "runtime": args.hermes_source,
        "model_transport": "deterministic loopback HTTP, no live provider",
        "launch_ms": launch_ms,
        "unbound_status": unbound,
        "captured_context_status": terminal.state.value,
        "result": result.summary,
        "effective_request_tools": requests,
        "steer_accepted": steer_accepted,
        "cancel_accepted": cancel.accepted,
        "cancel_terminal": cancelled.state.value,
        "native_desktop_delivery": "not exercised",
        "retry_safe_surface": False,
    }
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
