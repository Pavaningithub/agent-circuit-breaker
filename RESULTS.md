# Measured output

Captured on a MacBook (Apple Silicon, 16 GB), Docker Desktop with 8 GB, Ollama on CPU, model `qwen2.5:1.5b`, `MAX_ITERATIONS=30`, `rules/all.json`. Roughly 40 s per model call on CPU; a hosted API would be 1-3 s, so wall time is laptop-specific but calls and tokens are not.

| | calls | tokens | wall time | stopped by |
|---|---|---|---|---|
| Run 1, rules off | 30 | 36,860 | 21.6 min | agent `max_iterations` |
| Run 2, rules on | 9 | 4,415 | 10.8 min | repeat rule, at call 9 |

## Run 1, rules off

```
[without-rules] session=without-rules-375fa2c3 model=ollama/qwen2.5:1.5b max_iterations=30
[without-rules] iteration 1: search_logs({"minutes": -10, "service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last -10 min)
[without-rules] iteration 2: search_logs({"service": "checkout-api", "minutes": -10}) -> timeout after 10s querying log backend for checkout-api (last -10 min)
[without-rules] iteration 3: search_logs({"service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last 0 min)
[without-rules] iteration 4: search_logs({"minutes": -1, "service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last -1 min)
[without-rules] iteration 5: model answered without logs, nudging it back to the tool
[without-rules] iteration 6: search_logs({"minutes": -1, "service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last -1 min)
[without-rules] iteration 7: model answered without logs, nudging it back to the tool
[without-rules] iteration 8: search_logs({"minutes": -1, "service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last -1 min)
[without-rules] iteration 9: model answered without logs, nudging it back to the tool
[without-rules] iteration 10: search_logs({"minutes": -1, "service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last -1 min)
[without-rules] iteration 11: model answered without logs, nudging it back to the tool
[without-rules] iteration 12: search_logs({"minutes": -1, "service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last -1 min)
[without-rules] iteration 13: model answered without logs, nudging it back to the tool
[without-rules] iteration 14: search_logs({"minutes": -1, "service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last -1 min)
[without-rules] iteration 15: model answered without logs, nudging it back to the tool
[without-rules] iteration 16: search_logs({"minutes": -1, "service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last -1 min)
[without-rules] iteration 17: model answered without logs, nudging it back to the tool
[without-rules] iteration 18: search_logs({"minutes": -1, "service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last -1 min)
[without-rules] iteration 19: model answered without logs, nudging it back to the tool
[without-rules] iteration 20: search_logs({"minutes": -1, "service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last -1 min)
[without-rules] iteration 21: model answered without logs, nudging it back to the tool
[without-rules] iteration 22: search_logs({"minutes": -1, "service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last -1 min)
[without-rules] iteration 23: model answered without logs, nudging it back to the tool
[without-rules] iteration 24: search_logs({"minutes": -1, "service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last -1 min)
[without-rules] iteration 25: model answered without logs, nudging it back to the tool
[without-rules] iteration 26: search_logs({"service": "checkout-api", "minutes": -1}) -> timeout after 10s querying log backend for checkout-api (last -1 min)
[without-rules] iteration 27: model answered without logs, nudging it back to the tool
[without-rules] iteration 28: search_logs({"minutes": -1, "service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last -1 min)
[without-rules] iteration 29: model answered without logs, nudging it back to the tool
[without-rules] iteration 30: search_logs({"service": "checkout-api", "minutes": -1}) -> timeout after 10s querying log backend for checkout-api (last -1 min)
[without-rules] hit max_iterations=30, the framework guard finally stopped it.
RESULT run=without-rules status=max_iterations calls=30 prompt_tokens=35692 completion_tokens=1168 total_tokens=36860 elapsed=1294.5s
```

## Run 2, rules on

```
[with-rules] session=with-rules-9dae96d6 model=ollama/qwen2.5:1.5b max_iterations=30
[with-rules] iteration 1: search_logs({"service": "checkout-api", "minutes": -10}) -> timeout after 10s querying log backend for checkout-api (last -10 min)
[with-rules] iteration 2: search_logs({"minutes": -10, "service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last -10 min)
[with-rules] iteration 3: search_logs({"service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last 0 min)
[with-rules] iteration 4: search_logs({"minutes": -1, "service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last -1 min)
[with-rules] iteration 5: model answered without logs, nudging it back to the tool
[with-rules] iteration 6: search_logs({"service": "checkout-api", "minutes": -1}) -> timeout after 10s querying log backend for checkout-api (last -1 min)
[with-rules] iteration 7: model answered without logs, nudging it back to the tool
[with-rules] iteration 8: search_logs({"minutes": -1, "service": "checkout-api"}) -> timeout after 10s querying log backend for checkout-api (last -1 min)
[with-rules] iteration 9: gateway refused the call.
[with-rules]   breaker said: The exact same tool call (search_logs {"minutes": -1, "service": "checkout-api"}) has been requested 3 times in a row and is being refused. The tool is probably failing. Try a different approach or stop and report.
[with-rules]   agent: stopping and reporting what I have.
RESULT run=with-rules status=tripped:repeat calls=9 prompt_tokens=3946 completion_tokens=469 total_tokens=4415 elapsed=648.3s
```

## Breaker log, run 2

```
{"ts": 1794305809.65, "event": "TRIP", "session": "with-rules-9dae96d6", "rule": "repeat", "calls": 8, "tokens": 4415}
{"ts": 1794305809.65, "event": "ALERT", "session": "with-rules-9dae96d6", "rule": "repeat", "message": "The exact same tool call (search_logs {\"minutes\": -1, \"service\": \"checkout-api\"}) has been requested 3 times in a row and is being refused. The tool is probably failing. Try a different approach or stop and report.", "last_tool_calls": ["search_logs {\"minutes\": -10, \"service\": \"checkout-api\"}", "search_logs {\"service\": \"checkout-api\"}", "search_logs {\"minutes\": -1, \"service\": \"checkout-api\"}", "search_logs {\"minutes\": -1, \"service\": \"checkout-api\"}", "search_logs {\"minutes\": -1, \"service\": \"checkout-api\"}"]}
```

Two things worth noticing. Even at `temperature: 0` the small model varied its arguments for the first few calls (`minutes: -10`, then missing, then `-1`), so repeat detection only caught it once it settled. That is exactly why the budget rule exists alongside it. And every other iteration the model tried to answer without logs and the framework nudged it back to the tool, which is a very ordinary agent loop pattern and the one that keeps it looping.
