"""
A deliberately broken on-call agent.

It is asked to investigate an alert. Its only tool, search_logs, always times out.
A stubborn framework loop keeps nudging it to fetch logs, so without a breaker it
runs until MAX_ITERATIONS. Every call goes through the gateway with a session id.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:9000/v1/chat/completions")
MODEL = os.environ.get("MODEL", "ollama/qwen2.5:1.5b")
MAX_ITERATIONS = int(os.environ.get("MAX_ITERATIONS", "30"))
RUN_NAME = os.environ.get("RUN_NAME", "run")
SESSION_ID = os.environ.get("SESSION_ID") or f"{RUN_NAME}-{uuid.uuid4().hex[:8]}"
PARENT_SESSION_ID = os.environ.get("PARENT_SESSION_ID")

TOOLS = [{
    "type": "function",
    "function": {
        "name": "search_logs",
        "description": "Search recent application logs for a service. Returns matching log lines.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service name, e.g. checkout-api"},
                "minutes": {"type": "integer", "description": "How many minutes back to search"},
            },
            "required": ["service", "minutes"],
        },
    },
}]

SYSTEM = (
    "You are an on-call SRE agent. Investigate the alert using the search_logs tool. "
    "You must retrieve logs before concluding. If a tool call fails, retry it. "
    "Only give a final answer once you have log lines to base it on."
)
ALERT = "ALERT: checkout-api error rate 14% (threshold 2%) for the last 10 minutes. Find the cause."


def search_logs(service: str, minutes: int) -> str:
    time.sleep(0.2)  # the log backend is having a bad night
    return json.dumps({"error": f"timeout after 10s querying log backend for {service} (last {minutes} min)"})


def call_model(messages):
    payload = {"model": MODEL, "messages": messages, "tools": TOOLS, "temperature": 0}
    req = urllib.request.Request(
        GATEWAY_URL, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-session-id": SESSION_ID,
                 **({"x-parent-session-id": PARENT_SESSION_ID} if PARENT_SESSION_ID else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except json.JSONDecodeError:
            return e.code, {"error": {"message": "non-JSON error from gateway"}}


def main():
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": ALERT}]
    calls = prompt_tokens = completion_tokens = 0
    status = "max_iterations"
    started = time.time()
    print(f"[{RUN_NAME}] session={SESSION_ID} model={MODEL} max_iterations={MAX_ITERATIONS}", flush=True)

    for i in range(1, MAX_ITERATIONS + 1):
        code, data = call_model(messages)
        calls += 1
        if code != 200:
            err = (data.get("error") or {})
            if err.get("type") == "circuit_breaker_tripped":
                status = f"tripped:{err.get('rule')}"
                print(f"[{RUN_NAME}] iteration {i}: gateway refused the call.", flush=True)
                print(f"[{RUN_NAME}]   breaker said: {err.get('message')}", flush=True)
                print(f"[{RUN_NAME}]   agent: stopping and reporting what I have.", flush=True)
            else:
                status = f"error:{code}"
                print(f"[{RUN_NAME}] iteration {i}: HTTP {code} {json.dumps(err)[:200]}", flush=True)
            break

        usage = data.get("usage") or {}
        prompt_tokens += int(usage.get("prompt_tokens") or 0)
        completion_tokens += int(usage.get("completion_tokens") or 0)
        msg = data["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            # The model wants to answer without logs. A stubborn framework pushes it back to the tool.
            print(f"[{RUN_NAME}] iteration {i}: model answered without logs, nudging it back to the tool", flush=True)
            messages.append({"role": "assistant", "content": msg.get("content") or ""})
            messages.append({"role": "user", "content": "You have not retrieved any logs yet. Call search_logs."})
            continue

        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls})
        for tc in tool_calls:
            fn = tc["function"]
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = search_logs(str(args.get("service", "?")), int(args.get("minutes", 0) or 0))
            print(f"[{RUN_NAME}] iteration {i}: {fn['name']}({json.dumps(args)}) -> {json.loads(result)['error']}", flush=True)
            messages.append({"role": "tool", "tool_call_id": tc.get("id", f"call_{i}"), "content": result})
    else:
        print(f"[{RUN_NAME}] hit max_iterations={MAX_ITERATIONS}, the framework guard finally stopped it.", flush=True)

    elapsed = round(time.time() - started, 1)
    total = prompt_tokens + completion_tokens
    print(
        f"RESULT run={RUN_NAME} status={status} calls={calls} prompt_tokens={prompt_tokens} "
        f"completion_tokens={completion_tokens} total_tokens={total} elapsed={elapsed}s",
        flush=True,
    )


if __name__ == "__main__":
    main()
