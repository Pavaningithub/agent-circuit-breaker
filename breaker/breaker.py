"""
Circuit breaker sidecar for an LLM gateway.

Sits in front of the gateway (Bifrost here) and enforces three per-session rules:
  1. budget  - max tokens and max calls per task (session), rolled up to a parent session
  2. rate    - max calls per session per window
  3. repeat  - the same tool call (name + arguments) asked for N times in a row

A tripped breaker returns HTTP 429 with a plain-language error the agent can read.
Only the standard library is used so the whole thing fits in one file.
"""
import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("UPSTREAM", "http://bifrost:8080").rstrip("/")
RULES_FILE = os.environ.get("RULES_FILE", "/rules/all.json")
PORT = int(os.environ.get("PORT", "9000"))
SESSION_HEADERS = ("x-session-id", "x-bf-session-id")
PARENT_HEADER = "x-parent-session-id"

lock = threading.Lock()
sessions: dict[str, dict] = {}


def log(kind: str, **fields):
    line = {"ts": round(time.time(), 3), "event": kind, **fields}
    print(json.dumps(line), flush=True)


def load_rules() -> dict:
    try:
        with open(RULES_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        log("rules_missing", file=RULES_FILE)
        return {}


def session_state(sid: str) -> dict:
    if sid not in sessions:
        sessions[sid] = {
            "calls": 0,
            "tokens": 0,
            "call_times": deque(),
            "tool_calls": deque(),  # (ts, hash, label)
            "state": "closed",      # closed | open | half-open
            "tripped_rule": None,
            "opened_at": None,
            "trip_hash": None,
        }
    return sessions[sid]


def check_rules(sid: str, parent: str | None, rules: dict) -> tuple[str, str] | None:
    """Return (rule, message) if the request must be refused, else None."""
    s = session_state(sid)
    now = time.time()

    if s["state"] == "open":
        wait = rules.get("half_open_after_seconds")
        if wait is not None and now - s["opened_at"] >= wait:
            s["state"] = "half-open"
            log("half_open", session=sid)
        else:
            return s["tripped_rule"], (
                f"Circuit breaker is open for session {sid} ({s['tripped_rule']}). "
                "Further model calls for this task are refused until a human looks at it."
            )

    budget = rules.get("budget")
    if budget:
        totals = [("task", s)]
        if parent:
            totals.append(("parent task", session_state(parent)))
        for scope, st in totals:
            if st["calls"] >= budget["max_calls"]:
                return "budget", (
                    f"This {scope} has made {st['calls']} model calls, the limit is {budget['max_calls']}. "
                    "The task is being stopped. Report what you have so far."
                )
            if st["tokens"] >= budget["max_tokens"]:
                return "budget", (
                    f"This {scope} has used {st['tokens']} tokens, the limit is {budget['max_tokens']}. "
                    "The task is being stopped. Report what you have so far."
                )

    rate = rules.get("rate")
    if rate:
        window = rate["window_seconds"]
        while s["call_times"] and now - s["call_times"][0] > window:
            s["call_times"].popleft()
        if len(s["call_times"]) >= rate["max_calls"]:
            return "rate", (
                f"This session made {len(s['call_times'])} model calls in the last {window}s, "
                f"the limit is {rate['max_calls']}. That rhythm looks like a loop. Stop and report."
            )

    repeat = rules.get("repeat")
    if repeat and s["tool_calls"]:
        window = repeat["window_seconds"]
        recent = [tc for tc in s["tool_calls"] if now - tc[0] <= window]
        n = repeat["max_identical"]
        if len(recent) >= n:
            last = recent[-n:]
            if len({h for _, h, _ in last}) == 1:
                label = last[-1][2]
                return "repeat", (
                    f"The exact same tool call ({label}) has been requested {n} times in a row and is being refused. "
                    "The tool is probably failing. Try a different approach or stop and report."
                )
    return None


def record_response(sid: str, parent: str | None, body: bytes):
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return
    usage = data.get("usage") or {}
    tokens = int(usage.get("total_tokens") or 0)
    now = time.time()
    s = session_state(sid)
    s["tokens"] += tokens
    if parent:
        p = session_state(parent)
        p["tokens"] += tokens
        p["calls"] += 1
    for choice in data.get("choices") or []:
        for tc in (choice.get("message") or {}).get("tool_calls") or []:
            fn = tc.get("function") or {}
            name = fn.get("name", "?")
            args = fn.get("arguments", "")
            try:  # normalise argument ordering so {"a":1,"b":2} == {"b":2,"a":1}
                args = json.dumps(json.loads(args), sort_keys=True)
            except (json.JSONDecodeError, TypeError):
                pass
            h = hashlib.sha256(f"{name}:{args}".encode()).hexdigest()[:12]
            s["tool_calls"].append((now, h, f"{name} {args}"))
            while len(s["tool_calls"]) > 50:
                s["tool_calls"].popleft()
    if s["state"] == "half-open":
        # One probe call allowed. If it repeated the thing that tripped us, open for good.
        last_hash = s["tool_calls"][-1][1] if s["tool_calls"] else None
        if last_hash and last_hash == s["trip_hash"]:
            s["state"] = "open"
            s["opened_at"] = now
            log("reopened", session=sid, reason="probe repeated the same tool call")
        else:
            s["state"] = "closed"
            s["tripped_rule"] = None
            log("closed", session=sid, reason="probe looked healthy")


def trip(sid: str, rule: str, message: str):
    s = session_state(sid)
    if s["state"] != "open":
        s["state"] = "open"
        s["tripped_rule"] = rule
        s["opened_at"] = time.time()
        s["trip_hash"] = s["tool_calls"][-1][1] if s["tool_calls"] else None
        recent = [label for _, _, label in list(s["tool_calls"])[-5:]]
        log("TRIP", session=sid, rule=rule, calls=s["calls"], tokens=s["tokens"])
        log("ALERT", session=sid, rule=rule, message=message, last_tool_calls=recent)


class Handler(BaseHTTPRequestHandler):
    server_version = "agent-circuit-breaker/0.1"

    def log_message(self, *_):  # quiet the default access log; we emit JSON lines instead
        pass

    def _send(self, status: int, body: bytes, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            return self._send(200, b'{"ok":true}')
        if self.path == "/breaker/state":
            with lock:
                snap = {
                    sid: {k: (v if not isinstance(v, deque) else len(v)) for k, v in s.items()}
                    for sid, s in sessions.items()
                }
            return self._send(200, json.dumps(snap, indent=2).encode())
        return self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        sid = next((self.headers.get(h) for h in SESSION_HEADERS if self.headers.get(h)), None)
        parent = self.headers.get(PARENT_HEADER)
        rules = load_rules()

        if sid is None:
            # No session id: nothing to count against. Pass through, but say so loudly.
            log("no_session_id", path=self.path)
        else:
            with lock:
                refused = check_rules(sid, parent, rules)
                if refused:
                    rule, message = refused
                    trip(sid, rule, message)
                    err = {"error": {"type": "circuit_breaker_tripped", "rule": rule, "message": message, "session_id": sid}}
                    return self._send(429, json.dumps(err).encode())
                s = session_state(sid)
                s["calls"] += 1
                s["call_times"].append(time.time())

        req = urllib.request.Request(UPSTREAM + self.path, data=body, method="POST")
        for k, v in self.headers.items():
            if k.lower() not in ("host", "content-length", "connection"):
                req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                status, out = resp.status, resp.read()
        except urllib.error.HTTPError as e:
            status, out = e.code, e.read()
        except urllib.error.URLError as e:
            log("upstream_error", error=str(e))
            return self._send(502, json.dumps({"error": {"type": "upstream_unreachable", "message": str(e)}}).encode())

        if sid is not None and status == 200:
            with lock:
                record_response(sid, parent, out)
                s = session_state(sid)
                log("call", session=sid, calls=s["calls"], tokens=s["tokens"], state=s["state"])
        self._send(status, out)


if __name__ == "__main__":
    log("start", upstream=UPSTREAM, rules_file=RULES_FILE, rules=load_rules())
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
