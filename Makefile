# ReqogniLoom — Developer Task Runner
#
# Test targets build dedicated, source-mounted `backend-test`/`frontend-test`
# services (docker-compose.test.yml) against postgres/redis from the running
# Docker Compose dev stack. Start it first with: docker-compose up -d
#
# WHY NOT `exec` INTO backend/frontend DIRECTLY: those services may be
# running a prebuilt registry image with no source mount (see
# docker-compose.test.yml header) — `docker compose exec backend pytest`
# would then collect 0 tests instead of failing loudly, or with tests missing
# entirely from the image, `.dockerignore` already strips them on purpose.
#
# IMPORTANT: `make test` runs unit + integration tests only (backend pytest +
# frontend vitest). It NEVER runs Playwright E2E tests — those are resource-
# and time-intensive and must be invoked explicitly via `make test-e2e`.

COMPOSE ?= docker-compose
TEST_COMPOSE := $(COMPOSE) -f docker-compose.yml -f docker-compose.test.yml

.PHONY: build test test-backend test-frontend test-e2e help

## build: Build images with real version/commit/build-time stamped in (scripts/build.sh)
build:
	./scripts/build.sh

## test: Run backend (pytest) + frontend (vitest) tests — NO E2E
test: test-backend test-frontend

## test-backend: Run backend unit + integration tests (pytest)
test-backend:
	$(TEST_COMPOSE) run --rm backend-test

## test-frontend: Run frontend unit tests (vitest)
test-frontend:
	$(TEST_COMPOSE) run --rm frontend-test

## test-e2e: Run Playwright E2E tests (manual only — slow, high resource use)
test-e2e:
	cd e2e && npm install && npx playwright test

## help: List available targets
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## //'
