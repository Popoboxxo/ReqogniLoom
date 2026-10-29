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
# services (testing/docker-compose.test.yml). That file is a STANDALONE Compose
# project with its own `name:` (`<project>-test`) and its own ephemeral
# `postgres-test`/`redis-test` services (#1387): the suite therefore does NOT
# need `make up` and can never reconcile or mutate the containers of the
# running dev/production stack (a shared project name plus a different file set
# was exactly what relabelled postgres/redis and pointed them at this
# checkout). The test containers stay up between runs for inspection — drop
# them with: make test-down
#
# The project name is PINNED with a CLI `-p` (TEST_PROJECT below), because that
# is the only level that outranks everything else. Compose precedence is
# `-p` > `COMPOSE_PROJECT_NAME` (process env or .env) > `name:` in the file >
# directory basename. Without the `-p`, an exported
# `COMPOSE_PROJECT_NAME=reqogniloom` would resolve `make test-down` to the
# PRODUCTION project and run `down --volumes --remove-orphans` against it —
# exactly the blast radius #1387 exists to close.
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
# Standalone: the test stack must NOT load deploy/docker-compose.yml (#1387).
# Loading it made Compose resolve the same project name with a different file
# set, which reconciled (relabelled/recreated) the running stack's
# postgres/redis. `--project-directory .` keeps paths/env lookup at the repo
# root.
#
# `-p` is mandatory, not cosmetic: it is the only precedence level above
# COMPOSE_PROJECT_NAME (see header), so it guarantees the test stack can never
# be redirected onto the dev/production project. Keep it in sync with the
# file's `name:` fallback (`<project>-test`).
TEST_PROJECT := $(if $(COMPOSE_PROJECT_NAME),$(COMPOSE_PROJECT_NAME)-test,reqogniloom-test)
TEST_COMPOSE := $(COMPOSE) -p $(TEST_PROJECT) -f testing/docker-compose.test.yml --project-directory .

.PHONY: up down minimal minimal-down honcho qdrant qdrant-down bluepencil bluepencil-layer bluepencil-down build release-bump test test-backend test-frontend test-down test-e2e test-e2e-reseed help

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

## qdrant: Add the optional Qdrant vector backend to the running dev stack (ADR-020; opt-in only, pgvector stays the default — also set MEMORY_BACKEND=qdrant + QDRANT_BASE_URL=http://qdrant:6333 in .env)
qdrant:
	$(DEV_COMPOSE) --profile qdrant up -d

## qdrant-down: Stop just the qdrant service (leaves the rest of the stack running)
qdrant-down:
	$(DEV_COMPOSE) --profile qdrant stop qdrant

## bluepencil-layer: Fetch the pinned bluepencil browser layer into frontend/public/bluepencil/latest (verified against deploy/bluepencil/layer.lock.json; needs network). Vite serves that directory in dev
bluepencil-layer:
	bash deploy/bluepencil/fetch-layer.sh --dest frontend/public/bluepencil/latest

## bluepencil: Add the optional bluepencil review-notes hub image (QS/demo only — no per-user auth, no tenant isolation; nginx gates it behind a Django session). Requires BLUEPENCIL_AUTH_SECRET in .env. Fetches the pinned browser layer first. Two-part enable: starts the hub only; to arm the frontend review layer also set BLUEPENCIL_ENABLED=1 in .env and restart the frontend service
bluepencil: bluepencil-layer
	$(DEV_COMPOSE) --profile bluepencil up -d

## bluepencil-down: Stop just the bluepencil hub image (leaves the rest of the stack running)
bluepencil-down:
	$(DEV_COMPOSE) --profile bluepencil stop bluepencil

## build: Build images with real version/commit/build-time stamped in (scripts/build.sh)
build:
	./scripts/build.sh

## release-bump: Bump every version carrier (incl. Hermes plugins), re-render docs and run the release gates. Usage: make release-bump NEW_VERSION=1.8.0-beta.22 (release branch only)
release-bump:
	python scripts/bump_version.py --version "$(NEW_VERSION)"

## test: Run backend (pytest) + frontend (vitest) tests — NO E2E
test: test-backend test-frontend

## test-backend: Run backend unit + integration tests (pytest)
test-backend:
	$(TEST_COMPOSE) run --rm backend-test

## test-frontend: Run frontend unit tests (vitest)
test-frontend:
	$(TEST_COMPOSE) run --rm frontend-test

## test-down: Remove the isolated test stack (postgres-test/redis-test + test containers)
test-down:
	$(TEST_COMPOSE) down --volumes --remove-orphans

# ---------------------------------------------------------------------------
# E2E (Playwright) — see README.md "End-to-End Tests (Playwright)"
#
# MODEL: seed ONCE, then run as often as you like. The suite is built to be
# idempotent against a persistently seeded stack (#947) — specs create their own
# fixtures and clean them up, so repeated runs do not need a re-seed and must not
# get one implicitly: a `reseed` folded into `test-e2e` would paper over exactly
# the state-dependency this suite was hardened against, and make a red run
# unreproducible.
#
# So seeding stays an explicit target. Run it once after `make up`, or whenever
# the checks below say the stack drifted.
# ---------------------------------------------------------------------------

# Commands inside the backend container (not host shell), so they work the same
# on Windows and Linux.
E2E_SEED_CMD := $(DEV_COMPOSE) exec -T backend python manage.py

## test-e2e: Run Playwright E2E tests (manual only — slow, high resource use). Assumes a seeded stack; see test-e2e-reseed
test-e2e:
	cd e2e && npm install && npx playwright test

## test-e2e-reseed: Re-seed the E2E prerequisites (seed_demo + seed_toothbrush + global attribute definitions) and smoke-test the stack. Idempotent.
test-e2e-reseed:
	@echo "==> seeding E2E prerequisites (all three commands are idempotent)"
	$(E2E_SEED_CMD) seed_demo
	$(E2E_SEED_CMD) seed_toothbrush
	$(E2E_SEED_CMD) bootstrap_attribute_definitions
	@echo "==> smoke-testing the stack with the same precondition guard Playwright uses"
	cd e2e && npm install && npx playwright test tests/needs-cross-boundary.spec.ts

## help: List available targets
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## //'
