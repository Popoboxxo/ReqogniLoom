# ReqFlow — Developer Task Runner
#
# Test targets run against the running Docker Compose dev stack.
# Start it first with: docker-compose up -d
#
# IMPORTANT: `make test` runs unit + integration tests only (backend pytest +
# frontend vitest). It NEVER runs Playwright E2E tests — those are resource-
# and time-intensive and must be invoked explicitly via `make test-e2e`.

COMPOSE ?= docker-compose

.PHONY: test test-backend test-frontend test-e2e help

## test: Run backend (pytest) + frontend (vitest) tests — NO E2E
test: test-backend test-frontend

## test-backend: Run backend unit + integration tests (pytest)
test-backend:
	$(COMPOSE) exec -T backend pytest -q

## test-frontend: Run frontend unit tests (vitest)
test-frontend:
	$(COMPOSE) exec -T frontend npm test

## test-e2e: Run Playwright E2E tests (manual only — slow, high resource use)
test-e2e:
	cd e2e && npm install && npx playwright test

## help: List available targets
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## //'
