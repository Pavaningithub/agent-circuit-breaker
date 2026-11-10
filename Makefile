MODEL ?= qwen2.5:1.5b
MAX_ITERATIONS ?= 30
COMPOSE = docker compose

.PHONY: up pull-model demo run-without-rules run-with-rules run-rule logs state down clean

up:
	$(COMPOSE) up -d --build ollama bifrost breaker
	@until curl -sf http://localhost:8080/v1/models >/dev/null 2>&1 || curl -sf http://localhost:8080/health >/dev/null 2>&1; do sleep 1; done
	@until curl -sf http://localhost:9000/healthz >/dev/null; do sleep 1; done

pull-model: up
	$(COMPOSE) exec ollama ollama pull $(MODEL)

demo: pull-model run-without-rules run-with-rules
	@echo
	@echo "Breaker log for the second run (TRIP and ALERT lines):"
	@$(COMPOSE) logs --no-log-prefix breaker | grep -E '"event": "(TRIP|ALERT)"' | tail -2

run-without-rules:
	@echo
	@echo "=== Run 1: rules OFF (only the agent's own max_iterations=$(MAX_ITERATIONS)) ==="
	RULES=none $(COMPOSE) up -d --force-recreate --no-deps breaker
	@until curl -sf http://localhost:9000/healthz >/dev/null; do sleep 1; done
	RUN_NAME=without-rules MODEL=$(MODEL) MAX_ITERATIONS=$(MAX_ITERATIONS) $(COMPOSE) run --rm --no-deps agent

run-with-rules:
	@echo
	@echo "=== Run 2: rules ON (rules/all.json) ==="
	RULES=all $(COMPOSE) up -d --force-recreate --no-deps breaker
	@until curl -sf http://localhost:9000/healthz >/dev/null; do sleep 1; done
	RUN_NAME=with-rules MODEL=$(MODEL) MAX_ITERATIONS=$(MAX_ITERATIONS) $(COMPOSE) run --rm --no-deps agent

# make run-rule RULE=repeat   (one of: none all budget rate repeat)
run-rule:
	RULES=$(RULE) $(COMPOSE) up -d --force-recreate --no-deps breaker
	@until curl -sf http://localhost:9000/healthz >/dev/null; do sleep 1; done
	RUN_NAME=rule-$(RULE) MODEL=$(MODEL) MAX_ITERATIONS=$(MAX_ITERATIONS) $(COMPOSE) run --rm --no-deps agent

logs:
	$(COMPOSE) logs -f breaker

state:
	curl -s http://localhost:9000/breaker/state

down:
	$(COMPOSE) down

clean:
	$(COMPOSE) down -v
