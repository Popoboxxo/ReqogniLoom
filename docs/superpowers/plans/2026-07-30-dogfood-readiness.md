# Dogfood-Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the gap between "System läuft" and "ich kann ReqogniLoom für meine eigene Anforderungsarbeit benutzen" — fix the one confirmed real blocker to real AI-Ableitung, and clean the GitHub issue tracker of stale "critical" reports that are already fixed in code, so the backlog reflects reality before more work is planned on top of it.

**Architecture:** Two independent, small changesets in the `backend/` Django app. Task 1 is a pure verification pass (no production code changes, only regression tests + `gh issue close`). Task 2 is a mechanical fix inside `llm_adapter/providers.py`: a configured `model_name` (from env `LLM_MODEL_NAME` or the DB `LlmSettings` row) is silently ignored by every real provider — each one always calls the hardcoded class constant `MODEL_NAME` instead.

**Tech Stack:** Python 3.x, Django 4.2+, pytest/pytest-django, `gh` CLI.

## Global Constraints

- Backend pytest cannot currently be run in this local sandbox (DB role lacks `CREATEDB` — pre-existing, unrelated to this plan). Verify locally with `python -m pytest <path> --collect-only` (no DB) plus a full read-through, and let CI (`backend-test` job) run the real suite after push.
- Branch-Guard: implement on a feature branch (`fix/...`), never commit to `main` directly.
- Commits: Conventional Commits, English, imperative, ≤72 chars first line.
- No production code changes in Task 1 — it is a verification/reconciliation pass only.

---

## Why these two tasks and not the other open issues

A priority scan of all open GitHub issues plus a code read-through found:

- **#69 / #78 / #79 / #80** ("critical" mass-assignment, DEBUG=True, WorkflowDefinition-not-initialized) are **already fixed** in code — commit `0149ac2` ("many fixes!") restricted `UserProfileSerializer` to only `first_name`/`last_name` as writable (`roles`/`tenant_id` are not serializer fields at all), plus DEBUG/security-header hardening; `application/self_init.py` (REQ-188, `post_migrate` hook) now auto-provisions the base workspace's `WorkflowEngineDefinition` rows on first start, and `workflow/management/commands/provision_workflow_definitions.py` covers every other workspace idempotently. These just need **verification + closing**, not more engineering — that is Task 1.
- **#81** (3 MCP crash reports) looks likewise superseded by later `workspace.get_context` hardening (try/except around every depth branch) and the generic `_handle_delete` returning a proper `ToolResult.ok(...)` — folded into Task 1's verification pass.
- **#117** (no import path for `docs/REQUIREMENTS.md`) is moot: line 1 of that file already states its content was migrated into `docs/se/`, which `migrate_se_docs` already imports. No task needed.
- **#118** (Anthropic model hardcoded) is confirmed **still broken, and worse than reported** — it affects `AnthropicProvider` and `OpenAiProvider`, not just Anthropic: neither ever reads the configured `model_name` at all. This is the one real blocker to actually using ReqogniLoom's AI-Ableitung with your own model choice — **Task 2**.
- **#103** (tenant-global roles) and **#175/#176** (UI tree/scroll duplication) are real but not blockers for solo dogfooding (no cross-workspace attacker present, UI is merely inconsistent, not broken) — deliberately deferred, not part of this plan.

---

### Task 1: Verify and close stale critical issues (#69, #78, #79, #80, #81)

**Files:**
- Test: `backend/rest_api/tests/test_mass_assignment_regression.py` (new — only if no equivalent already exists, see Step 1)
- No production code files touched.

**Interfaces:**
- Consumes: `rest_api.serializers.UserProfileSerializer`, `rest_api.auth_views.MeView`, `application.self_init.run_self_init`, `mcp_server.tools.cross_cutting` (the `workspace.get_context` handler), `mcp_server.tools.generic.GenericCrudToolGroup._handle_delete`.
- Produces: nothing new for later tasks — this task only produces evidence (test output + `gh` comments) for issue closure.

- [ ] **Step 1: Check whether a mass-assignment regression test already exists**

Run: `grep -rn "mass.assign\|mass_assign" backend/rest_api/tests/ backend/auth_tenancy/tests/ -i`

If a test already asserts `PATCH /auth/me/` with `roles`/`tenant_id`/`is_admin` in the body does not change those fields, skip to Step 3 (test already covers #69/#80-item-2). Otherwise continue to Step 2.

- [ ] **Step 2: Write the regression test for #69 / #80 (mass assignment on /auth/me/)**

```python
# backend/rest_api/tests/test_mass_assignment_regression.py
import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_patch_me_ignores_roles_and_tenant_id(admin_user, admin_token):
    """[Issue #69/#80] PATCH /auth/me/ must not let a caller escalate roles
    or switch tenant_id via unexpected body fields."""
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")

    original_tenant_id = admin_user.tenant_id
    original_roles = list(admin_user.roles)

    response = client.patch(
        "/api/v1/auth/me/",
        {
            "roles": ["superadmin"],
            "tenant_id": "00000000-0000-0000-0000-000000000000",
            "is_admin": True,
            "first_name": "Regression",
        },
        format="json",
    )

    assert response.status_code == 200
    admin_user.refresh_from_db()
    assert admin_user.tenant_id == original_tenant_id
    assert list(admin_user.roles) == original_roles
    assert admin_user.first_name == "Regression"
```

Adapt the `admin_user`/`admin_token` fixture names to whatever `test_auth_login.py` / `test_auth_cookie.py` already use in this repo (read one of those two files first — do not invent new fixture names).

- [ ] **Step 3: Run it, confirm it passes against current code**

Run: `docker compose exec backend python manage.py test rest_api.tests.test_mass_assignment_regression -v 2` (or the equivalent pytest invocation the repo's CI uses — check `.github/workflows/ci.yml` `backend-test` job for the exact command).

Expected: PASS. If it fails, #69/#80 are NOT actually fixed — stop this task, open a real fix task instead (do not close the issues).

- [ ] **Step 4: Manually re-verify #78/#79 (WorkflowDefinition init) against a fresh container**

```bash
docker compose down -v
docker compose up -d
# wait for the one-shot `migrate` service to finish
curl -s -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"$SYSTEM_ADMIN_PASSWORD\"}"
# grab the returned access token as $TOKEN, then:
curl -s http://localhost:8000/api/v1/workflow-defaults/ -H "Authorization: Bearer $TOKEN"
```

Expected: `workflow_defaults` is non-empty (self_init/REQ-188 provisioned it). Then confirm the original repro from #78/#79 no longer 500s:

```bash
curl -s -X DELETE http://localhost:8000/api/v1/requirements/<id>/ -H "Authorization: Bearer $TOKEN"
```

Expected: `204` (or `200`), not `500`.

- [ ] **Step 5: Manually re-verify the 3 sub-bugs of #81 against MCP**

Reproduce each of the three repro steps from the #81 issue body (`workspace.get_context` with `depth=full`+`roles`, `issue.delete`, `change_request.get`) against `/mcp/` on a running stack. For `change_request.get`: confirm the tool is actually named `change_request.read` (the generic CRUD tool group naming convention used by `adr`/`risk`/`issue`/`glossary`, see `mcp_server/tools/generic.py`) — if so, the bug report used the wrong tool name and the fix is a one-line note on the issue, not a code change.

Expected outcomes per sub-bug:
- `workspace.get_context(depth=full, roles=[...])`: returns a normal `ToolResult`, no crash, no DEBUG HTML in the response.
- `issue.delete`: returns `{"status": "deleted"}`, not an empty 200 body.
- `change_request.read` (not `.get`): returns the entity, not "No service method found".

- [ ] **Step 6: Close the confirmed-fixed issues with evidence**

For every issue where Steps 3-5 confirmed current behavior matches the fix, comment with the exact command and output that proves it, then close:

```bash
gh issue comment 69 --repo Popoboxxo/ReqogniLoom --body "Verified fixed: PATCH /auth/me/ no longer applies roles/tenant_id (UserProfileSerializer only exposes first_name/last_name). Regression test added in backend/rest_api/tests/test_mass_assignment_regression.py."
gh issue close 69 --repo Popoboxxo/ReqogniLoom
```

Repeat for 78, 79, 80, 81 with their respective evidence. Do NOT close any issue whose Step 3-5 verification actually failed — file what is still broken as a new, precisely-scoped issue instead.

- [ ] **Step 7: Commit the regression test (if Step 2 created one)**

```bash
git add backend/rest_api/tests/test_mass_assignment_regression.py
git commit -m "test: add regression coverage for /auth/me/ mass assignment"
```

---

### Task 2: Fix providers ignoring the configured model_name (#118)

**Files:**
- Modify: `backend/llm_adapter/providers.py` — `_BaseHttpProvider.__init__` (currently around line 758), and every `model=self.MODEL_NAME` occurrence inside the `AnthropicProvider` and `OpenAiProvider` class bodies. Line numbers will have shifted by the time you edit — use `grep -n "self.MODEL_NAME" backend/llm_adapter/providers.py` and only touch occurrences between each class's `class ...Provider(_BaseHttpProvider):` line and the next `class` line. Do NOT touch `AzureOpenAiProvider` (already correctly does `self._config.azure_deployment or self.MODEL_NAME`) or `OllamaProvider`/`OpencodeGoProvider` (already resolve their own `self._model` from `LLM_MODEL`/`MODEL_NAME`).
- Test: `backend/llm_adapter/tests/test_provider_contracts.py`

**Interfaces:**
- Consumes: `llm_adapter.providers.ProviderConfig.model_name` (already populated from `LLM_MODEL_NAME` env or `LlmSettings.model_name` via `_read_env_config`/`_apply_db_settings` — nothing to change there).
- Produces: `_BaseHttpProvider.model_name` (new instance attribute) — every subclass's `_chat`/capability method must read `self.model_name` instead of `self.MODEL_NAME` when talking to the real API. `self.MODEL_NAME` remains as the class-level default/fallback.

- [ ] **Step 1: Write the failing test**

```python
# add to backend/llm_adapter/tests/test_provider_contracts.py

@pytest.mark.parametrize(
    "provider_cls",
    [OpenAiProvider, AnthropicProvider],
    ids=lambda c: c.__name__,
)
def test_http_provider_honours_configured_model_name(provider_cls: type) -> None:
    """[Issue #118] A configured model_name must override the class default
    MODEL_NAME - providers must not silently ignore LLM_MODEL_NAME / the
    DB-configured LlmSettings.model_name."""
    config = ProviderConfig(
        provider_name="test-dummy",
        api_key="sk-dummy-key-for-contract-tests-only",
        model_name="a-custom-configured-model",
    )
    provider = provider_cls(config)
    assert provider.model_name == "a-custom-configured-model"


@pytest.mark.parametrize(
    "provider_cls",
    [OpenAiProvider, AnthropicProvider],
    ids=lambda c: c.__name__,
)
def test_http_provider_falls_back_to_default_model_name(provider_cls: type) -> None:
    """[Issue #118] With no configured model_name, the provider still falls
    back to its own MODEL_NAME class default (no regression on unconfigured
    deployments)."""
    config = ProviderConfig(
        provider_name="test-dummy",
        api_key="sk-dummy-key-for-contract-tests-only",
        model_name="",
    )
    provider = provider_cls(config)
    assert provider.model_name == provider_cls.MODEL_NAME
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest backend/llm_adapter/tests/test_provider_contracts.py -k model_name -v`
Expected: FAIL with `AttributeError: object has no attribute 'model_name'` (the attribute does not exist yet).

- [ ] **Step 3: Add self.model_name to _BaseHttpProvider.__init__**

In `backend/llm_adapter/providers.py`, change:

```python
    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
```

to:

```python
    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        # Issue #118: a configured model_name (LLM_MODEL_NAME env or the
        # DB-persisted LlmSettings row, see _apply_db_settings) must win over
        # the class-level MODEL_NAME default - subclasses must call the real
        # API with self.model_name, never self.MODEL_NAME directly.
        self.model_name = config.model_name or self.MODEL_NAME
```

- [ ] **Step 4: Replace every model=self.MODEL_NAME with model=self.model_name inside AnthropicProvider and OpenAiProvider**

Run `grep -n "self.MODEL_NAME" backend/llm_adapter/providers.py` to get current line numbers, then for every occurrence inside the `AnthropicProvider` or `OpenAiProvider` class bodies, replace `self.MODEL_NAME` with `self.model_name`. Leave the class-level `MODEL_NAME = "..."` attribute declarations themselves untouched — only the usages inside method bodies change.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest backend/llm_adapter/tests/test_provider_contracts.py -v`
Expected: all PASS, including the two new tests and the pre-existing contract tests (unaffected).

- [ ] **Step 6: Run the full llm_adapter test suite for regressions**

Run: `python -m pytest backend/llm_adapter/ -v`
Expected: PASS. If CI is the only place this can actually execute (per the Global Constraints DB limitation), do a full read-through of `test_llm_adapter.py`/`test_resilient_transport.py` for any test that constructs `AnthropicProvider`/`OpenAiProvider` and asserts on `.MODEL_NAME` directly — update those assertions to `.model_name` too if found.

- [ ] **Step 7: Commit**

```bash
git add backend/llm_adapter/providers.py backend/llm_adapter/tests/test_provider_contracts.py
git commit -m "fix: honor configured model_name in Anthropic/OpenAI providers"
```

- [ ] **Step 8: Close #118 with evidence**

```bash
gh issue comment 118 --repo Popoboxxo/ReqogniLoom --body "Fixed: _BaseHttpProvider now resolves self.model_name = config.model_name or self.MODEL_NAME at init, and AnthropicProvider/OpenAiProvider read self.model_name instead of the hardcoded class constant. Regression tests in test_provider_contracts.py."
gh issue close 118 --repo Popoboxxo/ReqogniLoom
```

---

## Self-Review Notes

- Spec coverage: both real, confirmed-broken/stale items found in the priority scan are covered (#118 fix; #69/#78/#79/#80/#81 verification). #117 correctly excluded (moot — already migrated). #103/#175/#176 explicitly deferred with rationale, not silently dropped.
- No placeholders: every step has runnable code or an exact command.
- Type/name consistency: `model_name` (new instance attr) vs `MODEL_NAME` (existing class attr) is used consistently across both tasks' code samples.
