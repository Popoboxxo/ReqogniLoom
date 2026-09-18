# ReqogniLoom — Developer Task Runner
#
# Deployment-example compose files live in deploy/ (docker-compose.yml =
# full stack, docker-compose.minimal.yml = slim), test overlay lives in
# testing/ (docker-compose.test.yml) — see README.md "Deployment" section.
# Neither is in the repo root, so every invocation needs `--project-directory
# .` (pins .env lookup + relative bind-mount paths, e.g. ./backend, to the
# repo root instead of deploy/'s own directory) — the *_COMPOSE variables
# below bake that in so you never have to type it.
#
# Test targets build dedicated, source-mounted `backend-test`/`frontend-test`
# services (testing/docker-compose.test.yml) against postgres/redis from the
# running dev stack. Start it first with: make up
#
# WHY NOT `exec` INTO backend/frontend DIRECTLY: those services may be
# running a prebuilt registry image with no source mount (see
# testing/docker-compose.test.yml header) — `docker compose exec backend
# pytest` would then collect 0 tests instead of failing loudly, or with
# tests missing entirely from the image, `.dockerignore` already strips
# them on purpose.
#
# IMPORTANT: `make test` runs unit + integration tests only (backend pytest +
# frontend vitest). It NEVER runs Playwright E2E tests — those are resource-
# and time-intensive and must be invoked explicitly via `make test-e2e`.

COMPOSE ?= docker-compose
DEV_COMPOSE := $(COMPOSE) -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml --project-directory .
MINIMAL_COMPOSE := $(COMPOSE) -f deploy/docker-compose.minimal.yml --project-directory .
TEST_COMPOSE := $(COMPOSE) -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory .

.PHONY: up down minimal minimal-down honcho bluepencil bluepencil-down build test test-backend test-frontend test-e2e help

## up: Start the full dev stack (hot-reload override applied)
up:
	$(DEV_COMPOSE) up -d

## down: Stop the full dev stack
down:
	$(DEV_COMPOSE) down

## minimal: Start the minimal stack (postgres, redis, backend, migrate, frontend)
minimal:
	$(MINIMAL_COMPOSE) up -d

## minimal-down: Stop the minimal stack
minimal-down:
	$(MINIMAL_COMPOSE) down

## honcho: Add the optional Honcho memory backend to the running dev stack
honcho:
	$(DEV_COMPOSE) --profile honcho up -d

## bluepencil: Add the optional bluepencil review-notes sidecar (QS/demo only — no auth, no tenant isolation). Two-part enable: starts the sidecar only; to arm the frontend review layer also set BLUEPENCIL_ENABLED=1 in .env and restart the frontend service
bluepencil:
	$(DEV_COMPOSE) --profile bluepencil up -d

## bluepencil-down: Stop just the bluepencil sidecar (leaves the rest of the stack running)
bluepencil-down:
	$(DEV_COMPOSE) --profile bluepencil stop bluepencil

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
