# Interview-Management Web Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a collapsible chat-assistant widget to the ReqogniLoom web app that conducts structured interviews through server-generated conversational turns, plus a live artifact panel showing what the interview creates/adjusts.

**Architecture:** A thin REST facade (`/api/v1/interviews/...`) wraps `InterviewService` (the engine's core, built by a separate plan) for this cookie-authenticated, non-MCP client. A new `POST /api/v1/interviews/{id}/chat/` endpoint adds the one capability the engine doesn't have: server-side conversational turn generation, since (unlike Claude Code/Opencode/Antigravity/Hermes) the web app has no AI agent of its own to drive the dialogue. The widget itself is a `position: fixed` overlay mounted in `NavigationShell`, toggle state in `localStorage`, two panes (chat transcript, live artifact list) fed by the same REST facade.

**Tech Stack:** Django REST Framework, `llm_adapter` provider abstraction, React 18 + TypeScript, Vitest + React Testing Library.

**Spec:** `docs/superpowers/specs/2026-08-14-interview-management-web-widget-design.md` (Spec 3 of 3).

## Global Constraints

- **Hard dependency on the engine plan** (`docs/superpowers/plans/Archive/2026-08-14-interview-management-engine.md`, PR #534): `InterviewService`, `InterviewSession` (including its `transcript` field), and `interview_protocol.get_protocol` must exist before this plan's Task 1 can be written against real code. Confirmed already correct in that plan: the model has `transcript`, and its Global Constraints explicitly exclude the REST facade and `interview.chat_turn` capability as this plan's responsibility — no changes needed to the engine plan for this plan to build on it.
- The web app authenticates via httpOnly cookie (`reqflow_access`) + CSRF only — no API key, no MCP. All access goes through the new REST facade, never `interview.*` MCP tools directly (spec §2).
- `missing_fields` from `InterviewService.get_state()` is `list[{"name": str, "type": str, "choices": list[str] | None}]` (confirmed against the engine plan's corrected Task 3, commit `bb7647c`) — the frontend types in this plan match that shape exactly.
- `interview.chat_turn` generation is NOT fail-open — without a working LLM provider it cannot function (spec §5), unlike grounding. The existing mock-provider fallback still lets it run in dev, with lower extraction quality.
- No streaming (spec §5), no separate `/interviews` route — the artifact panel lives inside the widget (spec §9), no E2E coverage in this plan (spec §8, YAGNI as in Spec 2).
- Ambiguous chat answers must trigger a clarifying question, never a guess (spec §5).

---

## Task 1: REST facade — `/api/v1/interviews/` ViewSet (start/list/get/get_state/answer/grounding_context/formalize)

**Files:**
- Create: `backend/rest_api/interview_views.py`
- Modify: `backend/rest_api/urls.py` (register the ViewSet)
- Test: `backend/rest_api/tests/test_interview_views.py`

**Interfaces:**
- Consumes: `application.interview_service.InterviewService` (engine plan Task 3/5/6/7), `rest_api.views._service_error_response`, `rest_api.views.get_auth_context`, `rest_api.views.parse_workspace_id` (existing helpers — read `backend/rest_api/views.py` for their exact signatures before use, do not guess).
- Produces: REST endpoints `POST /api/v1/interviews/` (start), `GET /api/v1/interviews/` (list), `GET /api/v1/interviews/{id}/` (get), `GET /api/v1/interviews/{id}/state/` (get_state), `POST /api/v1/interviews/{id}/answer/` (answer), `GET /api/v1/interviews/{id}/grounding/` (grounding_context), `POST /api/v1/interviews/{id}/formalize/` (formalize).

- [ ] **Step 1: Write the failing test**

```python
# backend/rest_api/tests/test_interview_views.py
"""REST facade for interview.* — spec §3 point 1 (dual-protocol pattern, same as requirement_bundle)."""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="REST Interview Tenant", slug="rest-interview-tenant")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WS")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def user(tenant):
    return User.objects.create(username="rest-interview-user", email="riu@example.com", tenant=tenant)


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user=user)  # check the real auth fixture pattern used by neighboring
                                        # rest_api tests (e.g. test_requirement_bundle_export.py)
                                        # before running -- force_authenticate may not match how
                                        # this project's cookie-based AuthTenancyAuthentication
                                        # actually needs to be exercised in tests.
    return api


class TestInterviewStartAndList:
    def test_start_returns_session_id_and_missing_fields(self, client, workspace):
        response = client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        assert response.status_code == 201
        assert "id" in response.data
        assert any(f["name"] == "title" for f in response.data["missing_fields"])

    def test_list_returns_started_session(self, client, workspace):
        start = client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        response = client.get(f"/api/v1/interviews/?workspace_id={workspace.id}")
        assert response.status_code == 200
        assert start.data["id"] in [s["id"] for s in response.data["results"]]


class TestInterviewStateAndAnswer:
    def test_answer_then_state_reflects_it(self, client, workspace):
        start = client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        session_id = start.data["id"]

        answer = client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "title", "value": "SSO login"},
            format="json",
        )
        assert answer.status_code == 200

        state = client.get(f"/api/v1/interviews/{session_id}/state/")
        assert state.data["collected_fields"]["title"] == "SSO login"

    def test_unknown_session_returns_404(self, client):
        import uuid

        response = client.get(f"/api/v1/interviews/{uuid.uuid4()}/state/")
        assert response.status_code == 404


class TestInterviewFormalize:
    def test_formalize_creates_requirement(self, client, workspace):
        start = client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        session_id = start.data["id"]
        client.post(f"/api/v1/interviews/{session_id}/answer/", {"field": "title", "value": "SSO login"}, format="json")

        response = client.post(f"/api/v1/interviews/{session_id}/formalize/")

        assert response.status_code == 200
        assert response.data["status"] == "completed"
        assert len(response.data["resulting_artifact_ids"]) == 1
```

Before running, open `backend/rest_api/tests/test_requirement_bundle_export.py` (or another recent `rest_api/tests/` file) to find the real authenticated-client fixture pattern this codebase uses in tests against `AuthTenancyAuthentication` — replace `client`'s `force_authenticate` if the established pattern differs (e.g. a Bearer-token header helper or a cookie-setting login flow).

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest rest_api/tests/test_interview_views.py -v`
Expected: FAIL — 404 on `/api/v1/interviews/`, route not registered

- [ ] **Step 3: Implement the ViewSet**

```python
# backend/rest_api/interview_views.py
"""REST facade for interview.* (Interview-Management Web Widget spec §3.1).

Thin adapter over application.interview_service.InterviewService, the
same service the interview.* MCP tool group wraps -- same dual-protocol
pattern already used for requirement_bundle.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from application.base import NotFoundError, ValidationError
from application.interview_service import InterviewService
from rest_api.views import _service_error_response, detect_lang, get_auth_context, parse_workspace_id


def _session_to_dict(session: Any) -> dict:
    return {
        "id": str(session.id),
        "workspace_id": str(session.workspace_id),
        "artifact_type": session.artifact_type,
        "status": session.status,
    }


class InterviewViewSet(viewsets.ViewSet):
    """ViewSet for /api/v1/interviews/."""

    def create(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(request.data.get("workspace_id"), lang)
            if error is not None:
                return error
            artifact_type = request.data.get("artifact_type")
            session = InterviewService().start(ctx, artifact_type, workspace_id)
        except ValidationError as exc:
            return _service_error_response(exc, lang)
        state = InterviewService().get_state(ctx, session.id)
        return Response({**_session_to_dict(session), **state}, status=status.HTTP_201_CREATED)

    def list(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        workspace_id, error = parse_workspace_id(request.query_params.get("workspace_id"), lang)
        if error is not None:
            return error
        status_filter = request.query_params.get("status")
        sessions = InterviewService().list_sessions(ctx, workspace_id, status=status_filter)
        return Response({"results": [_session_to_dict(s) for s in sessions]})

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            session = InterviewService().get(ctx, UUID(pk))
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        return Response(_session_to_dict(session))

    @action(detail=True, methods=["get"], url_path="state")
    def state(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            result = InterviewService().get_state(ctx, UUID(pk))
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        return Response(result)

    @action(detail=True, methods=["post"], url_path="answer")
    def answer(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            InterviewService().answer(ctx, UUID(pk), request.data.get("field"), request.data.get("value"))
            result = InterviewService().get_state(ctx, UUID(pk))
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except ValidationError as exc:
            return _service_error_response(exc, lang)
        return Response(result)

    @action(detail=True, methods=["get"], url_path="grounding")
    def grounding(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            result = InterviewService().grounding_context(ctx, UUID(pk))
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        return Response(result)

    @action(detail=True, methods=["post"], url_path="formalize")
    def formalize(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            result = InterviewService().formalize(ctx, UUID(pk))
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except ValidationError as exc:
            return _service_error_response(exc, lang)
        return Response(result)
```

Cross-check `detect_lang`/`get_auth_context`/`parse_workspace_id`/`_service_error_response`'s exact signatures in `backend/rest_api/views.py` before running — this sketch follows their usage pattern from `ArtifactViewSet`/other viewsets in that file, but verify argument order and return shapes match (e.g. whether `parse_workspace_id` returns `(uuid, None)` or raises).

- [ ] **Step 4: Register the route**

In `backend/rest_api/urls.py`, add:

```python
from rest_api.interview_views import InterviewViewSet
# ...
router.register(r"interviews", InterviewViewSet, basename="interview")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest rest_api/tests/test_interview_views.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/rest_api/interview_views.py backend/rest_api/urls.py backend/rest_api/tests/test_interview_views.py
git commit -m "feat: add REST facade for interview.* (web widget access)"
```

---

## Task 2: `interview.chat_turn` LLM capability

**Files:**
- Modify: `backend/application/interview_service.py` (add `generate_chat_turn`)
- Modify: `backend/application/ai_derivation_service.py` (add `INTERVIEW_CHAT_TURN_PROMPT_TEMPLATE` to the canonical registry)
- Test: `backend/application/tests/test_interview_service.py`

**Interfaces:**
- Consumes: `InterviewService._resolve_provider` (engine plan Task 6 — the free-form-completion pattern, already established for grounding), `InterviewSession.transcript`.
- Produces: `InterviewService.generate_chat_turn(self, ctx, session_id: UUID, user_message: str) -> dict` (returns `{"reply": str, "state": <same shape as get_state>}`), appends `{role: "user", text, timestamp}` and `{role: "assistant", text, timestamp}` to `session.transcript`.

- [ ] **Step 1: Write the failing test**

```python
# Add to backend/application/tests/test_interview_service.py
from unittest.mock import MagicMock


class _ChatFakeProvider:
    """A provider double whose .complete() returns a fixed JSON-shaped
    extraction result, following the same non-vacuous-double principle as
    bundle_compression's _FakeProvider (issue #442 investigation): this
    must not be a hardcoded final-answer double, or a test asserting
    "field got extracted" would be meaningless. It returns exactly what a
    real provider following the chat_turn prompt's contract would."""

    PROVIDER_NAME = "anthropic"

    def __init__(self, response_json: str):
        self._response_json = response_json
        self.last_prompt = None

    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        self.last_prompt = prompt
        return self._response_json


class TestGenerateChatTurn:
    def test_extracts_field_and_records_transcript(self, ctx, workspace, monkeypatch):
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        provider = _ChatFakeProvider(
            '{"extracted_fields": {"title": "SSO login support"}, "reply": "Got it -- what is the rationale?"}'
        )
        monkeypatch.setattr(
            InterviewService, "_resolve_provider", lambda self: (provider, "anthropic", None)
        )

        result = InterviewService().generate_chat_turn(ctx, session.id, "We need SSO login support")

        assert result["reply"] == "Got it -- what is the rationale?"
        assert result["state"]["collected_fields"]["title"] == "SSO login support"

        state = InterviewService().get_state(ctx, session.id)
        transcript_texts = [t["text"] for t in InterviewService().get(ctx, session.id).transcript]
        assert "We need SSO login support" in transcript_texts
        assert "Got it -- what is the rationale?" in transcript_texts

    def test_no_provider_configured_raises_not_fail_open(self, ctx, workspace, monkeypatch):
        """spec §5: chat generation is NOT fail-open, unlike grounding."""
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        monkeypatch.setattr(
            InterviewService,
            "_resolve_provider",
            lambda self: (None, "unknown", RuntimeError("no provider configured")),
        )

        with pytest.raises(ValidationError):
            InterviewService().generate_chat_turn(ctx, session.id, "anything")

    def test_ambiguous_extraction_asks_clarifying_question_without_recording_a_field(
        self, ctx, workspace, monkeypatch
    ):
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        # No "extracted_fields" key at all -- the model chose to ask instead
        # of guess, exactly the spec §5 contract.
        provider = _ChatFakeProvider('{"extracted_fields": {}, "reply": "Could you clarify the title?"}')
        monkeypatch.setattr(
            InterviewService, "_resolve_provider", lambda self: (provider, "anthropic", None)
        )

        result = InterviewService().generate_chat_turn(ctx, session.id, "something vague")

        assert result["state"]["collected_fields"] == {}
        assert result["reply"] == "Could you clarify the title?"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest application/tests/test_interview_service.py -k ChatTurn -v`
Expected: FAIL — `AttributeError: 'InterviewService' object has no attribute 'generate_chat_turn'`

- [ ] **Step 3: Add the prompt template**

In `backend/application/ai_derivation_service.py`, alongside `BUNDLE_COMPRESSION_PROMPT_TEMPLATE`:

```python
INTERVIEW_CHAT_TURN_PROMPT_TEMPLATE = """\
You are conducting a structured interview to help create or update a \
{artifact_type} in a requirements management system. Extract any field \
values the user's latest message clearly provides, and propose the next \
thing to say.

Do NOT guess. If a message is ambiguous or you are not confident about a \
value, leave it out of extracted_fields and ask a clarifying question in \
your reply instead -- an incorrectly recorded answer is worse than asking \
again.

Conversation so far (JSON list of {{role, text, timestamp}}):
{transcript_json}

Current phase instructions:
{current_phase_fragment}

Fields still needed (JSON list of {{name, type, choices}}):
{missing_fields_json}

Possibly related existing artifacts (JSON):
{grounding_snapshot_json}

Latest user message:
{user_message}

Respond with a single JSON object (no prose, no markdown fences) with \
this exact shape: {{"extracted_fields": {{"<field_name>": "<value>", ...}}, \
"reply": "<what to say back to the user>"}}. extracted_fields may be \
empty. Only include fields from the "Fields still needed" list.
"""
```

Add it to `PROMPT_TEMPLATE_DEFAULTS` under the key `"interview.chat_turn"` (same dict `ai_derivation_service.py` already merges the 7-slot registry into — find the merge point used for `"bundle_compression"` and add this alongside it, following the exact same pattern).

- [ ] **Step 4: Implement `generate_chat_turn`**

Add to `backend/application/interview_service.py`:

```python
    def generate_chat_turn(self, ctx, session_id: UUID, user_message: str) -> "dict[str, Any]":
        import json as _json
        from datetime import datetime, timezone as _tz

        session = self._get_session(ctx, session_id)
        if session.status != InterviewSession.STATUS_IN_PROGRESS:
            raise ValidationError(f"InterviewSession {session_id} is {session.status}, cannot chat.")

        provider, provider_name, resolve_error = self._resolve_provider()
        if provider is None:
            # NOT fail-open (spec §5) -- unlike grounding, there is no
            # meaningful degraded behavior for "have a conversation" without
            # an LLM, so this must surface as an error rather than silently
            # doing nothing.
            raise ValidationError(
                f"No LLM provider available for interview chat: {resolve_error}"
            )

        phase, missing = self._current_phase_and_missing(ctx, session)
        from application.ai_derivation_service import AiDerivationService, PROMPT_TEMPLATE_DEFAULTS

        template = AiDerivationService._get_template_content(ctx, "interview.chat_turn", session.workspace_id)
        if template is None:
            template = PROMPT_TEMPLATE_DEFAULTS["interview.chat_turn"]
        prompt = AiDerivationService._render(
            template,
            artifact_type=session.artifact_type,
            transcript_json=_json.dumps(session.transcript),
            current_phase_fragment=phase.prompt_fragment,
            missing_fields_json=_json.dumps([self._serialise_field(f) for f in missing]),
            grounding_snapshot_json=_json.dumps(session.grounding_snapshot),
            user_message=user_message,
        )

        raw_response = provider.complete(prompt, purpose="interview_chat_turn")
        try:
            parsed = __import__("json").loads(raw_response)
            extracted = parsed.get("extracted_fields", {}) or {}
            reply = parsed.get("reply", "")
        except (ValueError, AttributeError):
            # Model didn't follow the JSON contract -- degrade to "no fields
            # extracted, relay the raw text" rather than crashing the chat.
            extracted = {}
            reply = raw_response

        for field_name, value in extracted.items():
            self.answer(ctx, session_id, field_name, value)

        now = datetime.now(_tz.utc).isoformat()
        session.refresh_from_db()
        session.transcript = [
            *session.transcript,
            {"role": "user", "text": user_message, "timestamp": now},
            {"role": "assistant", "text": reply, "timestamp": now},
        ]
        session.save(update_fields=["transcript", "modified_at", "version"])

        return {"reply": reply, "state": self.get_state(ctx, session_id)}
```

Note: `_current_phase_and_missing` is called with `(ctx, session)` here, matching the Task-3 fix already applied in the engine plan (it originally had a `get_protocol(ctx=None, ...)` bug that was fixed to thread a real `ctx` through) — confirm the exact current signature in the already-implemented `interview_service.py` before wiring this call, in case the engine plan's own execution changed it further.

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest application/tests/test_interview_service.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 6: Commit**

```bash
git add backend/application/interview_service.py backend/application/ai_derivation_service.py backend/application/tests/test_interview_service.py
git commit -m "feat: add interview.chat_turn LLM capability"
```

---

## Task 3: `POST /api/v1/interviews/{id}/chat/` endpoint

**Files:**
- Modify: `backend/rest_api/interview_views.py`
- Test: `backend/rest_api/tests/test_interview_views.py`

**Interfaces:**
- Consumes: `InterviewService.generate_chat_turn` (Task 2).
- Produces: `POST /api/v1/interviews/{id}/chat/` accepting `{"message": str}`, returning `{"reply": str, "state": {...}}`.

- [ ] **Step 1: Write the failing test**

```python
# Add to backend/rest_api/tests/test_interview_views.py
from unittest.mock import patch


class TestInterviewChat:
    def test_chat_returns_reply_and_updated_state(self, client, workspace):
        start = client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        session_id = start.data["id"]

        with patch(
            "application.interview_service.InterviewService._resolve_provider",
            return_value=(
                type(
                    "P", (), {"PROVIDER_NAME": "anthropic",
                              "complete": lambda self, *a, **k: '{"extracted_fields": {"title": "SSO login"}, "reply": "Noted."}'}
                )(),
                "anthropic",
                None,
            ),
        ):
            response = client.post(
                f"/api/v1/interviews/{session_id}/chat/", {"message": "We need SSO login"}, format="json"
            )

        assert response.status_code == 200
        assert response.data["reply"] == "Noted."
        assert response.data["state"]["collected_fields"]["title"] == "SSO login"

    def test_chat_without_provider_returns_error_not_500(self, client, workspace):
        start = client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        session_id = start.data["id"]

        with patch(
            "application.interview_service.InterviewService._resolve_provider",
            return_value=(None, "unknown", RuntimeError("no provider")),
        ):
            response = client.post(
                f"/api/v1/interviews/{session_id}/chat/", {"message": "anything"}, format="json"
            )

        assert response.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest rest_api/tests/test_interview_views.py -k Chat -v`
Expected: FAIL — 404, route not registered

- [ ] **Step 3: Add the endpoint**

Add to `InterviewViewSet` in `backend/rest_api/interview_views.py`:

```python
    @action(detail=True, methods=["post"], url_path="chat")
    def chat(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            result = InterviewService().generate_chat_turn(ctx, UUID(pk), request.data.get("message", ""))
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except ValidationError as exc:
            return _service_error_response(exc, lang)
        return Response(result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest rest_api/tests/test_interview_views.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add backend/rest_api/interview_views.py backend/rest_api/tests/test_interview_views.py
git commit -m "feat: add POST /api/v1/interviews/{id}/chat/ endpoint"
```

---

## Task 4: Frontend `interviews.ts` API client

**Files:**
- Create: `frontend/src/api/interviews.ts`
- Test: `frontend/src/api/interviews.test.ts`

**Interfaces:**
- Consumes: `frontend/src/api/client.ts`'s `apiClient`/`getList` helpers (same convention as `api/prompt-templates.ts`, `api/tracelinks.ts` — read one of those first to match the exact call shape and error-handling convention before writing this file).
- Produces: `interviewsApi` object with methods `start(workspaceId: UUID, artifactType: string): Promise<InterviewState>`, `list(workspaceId: UUID, status?: string): Promise<InterviewSummary[]>`, `get(id: UUID): Promise<InterviewSummary>`, `getState(id: UUID): Promise<InterviewState>`, `answer(id: UUID, field: string, value: unknown): Promise<InterviewState>`, `groundingContext(id: UUID): Promise<InterviewState["grounding_snapshot"]>`, `formalize(id: UUID): Promise<{resulting_artifact_ids: string[]; status: string}>`, `chat(id: UUID, message: string): Promise<{reply: string; state: InterviewState}>`. Also exports the `InterviewField`/`InterviewState`/`InterviewSummary` TypeScript types (same shape as the Hermes plugin's `mcpClient.ts` types from the Spec 2 plan, but this is an independent module — the two frontend/plugin codebases do not share a package, so this is a deliberate, small duplication rather than a premature shared-package abstraction).

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/api/interviews.test.ts
import { describe, expect, it, vi } from "vitest";

// Read api/prompt-templates.ts and its test file FIRST to copy the real
// apiClient/getList mocking convention used in this codebase -- the sketch
// below illustrates intent, match the actual existing pattern exactly.
import { interviewsApi } from "./interviews";
import { apiClient } from "./client";

vi.mock("./client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./client")>();
  return { ...actual, apiClient: { get: vi.fn(), post: vi.fn() } };
});

describe("interviewsApi", () => {
  it("start POSTs artifact_type and workspace_id", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      id: "s-1", status: "in_progress", phase: "elicitation",
      collected_fields: {}, missing_fields: [], grounding_snapshot: { candidates: [] },
    });

    const result = await interviewsApi.start("ws-1", "Requirement");

    expect(apiClient.post).toHaveBeenCalledWith("/interviews/", {
      artifact_type: "Requirement", workspace_id: "ws-1",
    });
    expect(result.id).toBe("s-1");
  });

  it("chat POSTs message to /interviews/{id}/chat/", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      reply: "Got it.", state: {
        id: "s-1", status: "in_progress", phase: "elicitation",
        collected_fields: {}, missing_fields: [], grounding_snapshot: { candidates: [] },
      },
    });

    const result = await interviewsApi.chat("s-1", "hello");

    expect(apiClient.post).toHaveBeenCalledWith("/interviews/s-1/chat/", { message: "hello" });
    expect(result.reply).toBe("Got it.");
  });

  it("list passes status as a query param when given", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ results: [] });

    await interviewsApi.list("ws-1", "in_progress");

    expect(apiClient.get).toHaveBeenCalledWith("/interviews/", {
      workspace_id: "ws-1", status: "in_progress",
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec reqogniloom-frontend-1 sh -c 'cd /app && npx vitest run src/api/interviews.test.ts'`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `interviews.ts`**

Read `frontend/src/api/prompt-templates.ts` first and mirror its exact `apiClient.get`/`apiClient.post` call conventions (parameter passing style, base path prefixing) rather than guessing — this codebase's `apiClient` wraps axios with a fixed `/api/v1` base and Bearer/cookie auto-injection (per `client.ts`'s own header comment), so paths here should NOT repeat `/api/v1`:

```typescript
// frontend/src/api/interviews.ts
import { apiClient, getList } from "./client";
import type { UUID } from "../types";

export interface InterviewField {
  name: string;
  type: "text" | "textarea" | "enum" | "number";
  choices: string[] | null;
}

export interface InterviewState {
  id: string;
  status: "in_progress" | "completed" | "abandoned";
  phase: string;
  collected_fields: Record<string, unknown>;
  missing_fields: InterviewField[];
  grounding_snapshot: { candidates: { artifact_id: string; title: string; score: number | null }[] };
}

export interface InterviewSummary {
  id: string;
  workspace_id: string;
  artifact_type: string;
  status: string;
}

export const interviewsApi = {
  start(workspaceId: UUID, artifactType: string): Promise<InterviewState> {
    return apiClient.post<InterviewState>("/interviews/", {
      artifact_type: artifactType,
      workspace_id: workspaceId,
    });
  },

  list(workspaceId: UUID, status?: string): Promise<InterviewSummary[]> {
    const params: Record<string, string> = { workspace_id: workspaceId };
    if (status) params.status = status;
    return getList<InterviewSummary>("/interviews/", params).then((r) => r.results);
  },

  get(id: UUID): Promise<InterviewSummary> {
    return apiClient.get<InterviewSummary>(`/interviews/${id}/`);
  },

  getState(id: UUID): Promise<InterviewState> {
    return apiClient.get<InterviewState>(`/interviews/${id}/state/`);
  },

  answer(id: UUID, field: string, value: unknown): Promise<InterviewState> {
    return apiClient.post<InterviewState>(`/interviews/${id}/answer/`, { field, value });
  },

  groundingContext(id: UUID): Promise<InterviewState["grounding_snapshot"]> {
    return apiClient.get<InterviewState["grounding_snapshot"]>(`/interviews/${id}/grounding/`);
  },

  formalize(id: UUID): Promise<{ resulting_artifact_ids: string[]; status: string }> {
    return apiClient.post<{ resulting_artifact_ids: string[]; status: string }>(
      `/interviews/${id}/formalize/`
    );
  },

  chat(id: UUID, message: string): Promise<{ reply: string; state: InterviewState }> {
    return apiClient.post<{ reply: string; state: InterviewState }>(`/interviews/${id}/chat/`, { message });
  },
};
```

Reconcile this against `prompt-templates.ts`'s actual `apiClient`/`getList` call signatures (generic type params, whether `apiClient.post` takes a body as the 2nd positional arg or an options object) before running Step 4 — fix any mismatch found.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec reqogniloom-frontend-1 sh -c 'cd /app && npx vitest run src/api/interviews.test.ts'`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/interviews.ts frontend/src/api/interviews.test.ts
git commit -m "feat: add interviews API client"
```

---

## Task 5: Widget shell — toggle state + floating overlay

**Files:**
- Create: `frontend/src/components/InterviewWidget/InterviewWidget.tsx`
- Create: `frontend/src/components/InterviewWidget/InterviewWidget.module.css`
- Modify: `frontend/src/components/NavigationShell/NavigationShell.tsx` (mount the widget)
- Test: `frontend/src/components/InterviewWidget/InterviewWidget.test.tsx`

**Interfaces:**
- Consumes: `useWorkspace()` (`context/WorkspaceContext`, for `activeWorkspace`), same `localStorage` pattern as `ThemeContext` (`STORAGE_KEY` constant + read-on-mount).
- Produces: `InterviewWidget(): JSX.Element` — a floating toggle button that expands into a panel; open/closed state persisted in `localStorage` under `"reqflow-interview-widget-open"`. When collapsed, renders only the toggle button. When expanded and no session is active, shows a "start" affordance (artifact type buttons, mirrors the Hermes plugin's `InterviewListView` pattern but simpler — a single active-session slot, not a session-list browser, since spec §9 explicitly keeps this out of a separate multi-session UI). Chat/artifact panes are Task 6/7, stubbed here as empty placeholders that those tasks fill in.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/InterviewWidget/InterviewWidget.test.tsx
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { InterviewWidget } from "./InterviewWidget";

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", name: "WS" } }),
}));

describe("InterviewWidget", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders collapsed by default", () => {
    render(<InterviewWidget />);
    expect(screen.getByTestId("interview-widget-toggle")).toBeInTheDocument();
    expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
  });

  it("expands on toggle click and persists the open state", () => {
    render(<InterviewWidget />);
    fireEvent.click(screen.getByTestId("interview-widget-toggle"));

    expect(screen.getByTestId("interview-widget-panel")).toBeInTheDocument();
    expect(localStorage.getItem("reqflow-interview-widget-open")).toBe("true");
  });

  it("renders expanded on mount when localStorage says open", () => {
    localStorage.setItem("reqflow-interview-widget-open", "true");
    render(<InterviewWidget />);
    expect(screen.getByTestId("interview-widget-panel")).toBeInTheDocument();
  });

  it("collapses on a second toggle click", () => {
    render(<InterviewWidget />);
    const toggle = screen.getByTestId("interview-widget-toggle");
    fireEvent.click(toggle);
    fireEvent.click(toggle);
    expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec reqogniloom-frontend-1 sh -c 'cd /app && npx vitest run src/components/InterviewWidget/InterviewWidget.test.tsx'`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the widget shell**

```css
/* frontend/src/components/InterviewWidget/InterviewWidget.module.css */
.toggle {
  position: fixed;
  bottom: var(--space-4);
  right: var(--space-4);
  z-index: 900;
  width: 48px;
  height: 48px;
  border-radius: var(--radius-full);
  background: var(--color-primary);
  color: white;
  border: none;
  cursor: pointer;
  box-shadow: var(--shadow-card);
}

.panel {
  position: fixed;
  bottom: calc(var(--space-4) + 56px);
  right: var(--space-4);
  z-index: 900;
  width: 360px;
  max-height: 60vh;
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}
```

```typescript
// frontend/src/components/InterviewWidget/InterviewWidget.tsx
import { useEffect, useState } from "react";
import { useWorkspace } from "../../context/WorkspaceContext";
import styles from "./InterviewWidget.module.css";

const STORAGE_KEY = "reqflow-interview-widget-open";

export function InterviewWidget(): JSX.Element {
  const { activeWorkspace } = useWorkspace();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setOpen(localStorage.getItem(STORAGE_KEY) === "true");
  }, []);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    localStorage.setItem(STORAGE_KEY, String(next));
  };

  if (!activeWorkspace) return <></>;

  return (
    <>
      <button
        type="button"
        data-testid="interview-widget-toggle"
        className={styles.toggle}
        onClick={toggle}
        aria-label="Interview assistant"
      >
        💬
      </button>
      {open && (
        <div data-testid="interview-widget-panel" className={styles.panel}>
          {/* Chat pane (Task 6) and artifact pane (Task 7) render here. */}
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec reqogniloom-frontend-1 sh -c 'cd /app && npx vitest run src/components/InterviewWidget/InterviewWidget.test.tsx'`
Expected: PASS (4 tests)

- [ ] **Step 5: Mount in `NavigationShell`**

Read `frontend/src/components/NavigationShell/NavigationShell.tsx` first to find where global, always-mounted UI (independent of the current route) belongs in its render tree, and add `<InterviewWidget />` there — do not guess the insertion point without reading the file, since this component must render on every authenticated route, not just one page.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/InterviewWidget/ frontend/src/components/NavigationShell/NavigationShell.tsx
git commit -m "feat: add InterviewWidget toggle shell"
```

---

## Task 6: Chat pane

**Files:**
- Create: `frontend/src/components/InterviewWidget/InterviewChatPane.tsx`
- Modify: `frontend/src/components/InterviewWidget/InterviewWidget.tsx` (render the pane, own the active-session state)
- Test: `frontend/src/components/InterviewWidget/InterviewChatPane.test.tsx`

**Interfaces:**
- Consumes: `interviewsApi.start`/`.chat`/`.getState` (Task 4), `InterviewState` type (Task 4).
- Produces: `InterviewChatPane({interview, onStateChange}: {interview: InterviewState; onStateChange: (s: InterviewState) => void}): JSX.Element` — renders `interview.??? ` — **note:** `InterviewState` from the REST facade (Task 1/4) does not include `transcript` in its response shape as drafted; fix this before writing this task's code (see Step 0 below), since the chat pane cannot render conversation history without it.

- [ ] **Step 0: Fix a shape gap found while planning this task**

Task 1's `state`/`answer`/`chat` REST responses return whatever `InterviewService.get_state()` returns, and Task 2/3's `generate_chat_turn` returns `{"reply": ..., "state": get_state(...)}` — but `InterviewService.get_state()` (engine plan Task 3) does NOT include `transcript` in its returned dict (only `session_id, status, phase, collected_fields, missing_fields, grounding_snapshot`). The chat pane needs the transcript to render history on mount/resume. Add `"transcript": session.transcript` to `get_state()`'s return dict — this is a one-line addition to the engine plan's `InterviewService.get_state`, additive and harmless to Spec 2's Hermes form view (which simply ignores the extra key). Make this fix now, in the already-implemented `backend/application/interview_service.py`, before writing this task's frontend code, and add one assertion to the engine plan's existing `test_reports_missing_fields_for_fresh_session` test (or a new one) confirming `state["transcript"] == []` for a fresh session. Also update `InterviewState` in both `frontend/src/api/interviews.ts` (Task 4) and, if not already executed, the Hermes plugin's `mcpClient.ts` (Spec 2 plan Task 2) to include `transcript: {role: string; text: string; timestamp: string}[]`.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/InterviewWidget/InterviewChatPane.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { InterviewChatPane } from "./InterviewChatPane";
import type { InterviewState } from "../../api/interviews";

vi.mock("../../api/interviews", () => ({
  interviewsApi: { chat: vi.fn() },
}));
import { interviewsApi } from "../../api/interviews";

function makeInterview(overrides: Partial<InterviewState> = {}): InterviewState {
  return {
    id: "s-1", status: "in_progress", phase: "elicitation",
    collected_fields: {}, missing_fields: [], grounding_snapshot: { candidates: [] },
    transcript: [],
    ...overrides,
  } as InterviewState;
}

describe("InterviewChatPane", () => {
  it("renders existing transcript messages", () => {
    const interview = makeInterview({
      transcript: [{ role: "user", text: "Hi", timestamp: "t1" }, { role: "assistant", text: "Hello", timestamp: "t2" }],
    });
    render(<InterviewChatPane interview={interview} onStateChange={vi.fn()} />);

    expect(screen.getByText("Hi")).toBeInTheDocument();
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("sends a message and calls onStateChange with the refreshed state", async () => {
    const onStateChange = vi.fn();
    vi.mocked(interviewsApi.chat).mockResolvedValue({
      reply: "Got it.",
      state: makeInterview({ collected_fields: { title: "x" } }),
    });
    render(<InterviewChatPane interview={makeInterview()} onStateChange={onStateChange} />);

    fireEvent.change(screen.getByTestId("interview-chat-input"), { target: { value: "We need SSO" } });
    fireEvent.click(screen.getByTestId("interview-chat-send"));

    await waitFor(() => expect(onStateChange).toHaveBeenCalled());
    expect(interviewsApi.chat).toHaveBeenCalledWith("s-1", "We need SSO");
  });

  it("keeps the input text and shows an error if chat fails", async () => {
    vi.mocked(interviewsApi.chat).mockRejectedValue(new Error("no provider"));
    render(<InterviewChatPane interview={makeInterview()} onStateChange={vi.fn()} />);

    const input = screen.getByTestId("interview-chat-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "hello" } });
    fireEvent.click(screen.getByTestId("interview-chat-send"));

    await screen.findByText("no provider");
    expect(input.value).toBe("hello");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec reqogniloom-frontend-1 sh -c 'cd /app && npx vitest run src/components/InterviewWidget/InterviewChatPane.test.tsx'`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the pane**

```typescript
// frontend/src/components/InterviewWidget/InterviewChatPane.tsx
import { useState } from "react";
import { interviewsApi, type InterviewState } from "../../api/interviews";

export function InterviewChatPane({
  interview,
  onStateChange,
}: {
  interview: InterviewState;
  onStateChange: (s: InterviewState) => void;
}): JSX.Element {
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = async () => {
    if (!draft.trim()) return;
    setSending(true);
    setError(null);
    try {
      const { state } = await interviewsApi.chat(interview.id, draft);
      onStateChange(state);
      setDraft("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message.");
    } finally {
      setSending(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-2)" }}>
        {interview.transcript.map((msg, i) => (
          <p key={i} style={{ textAlign: msg.role === "user" ? "right" : "left" }}>
            {msg.text}
          </p>
        ))}
      </div>
      {error && <p style={{ color: "var(--color-danger)" }}>{error}</p>}
      <div style={{ display: "flex", gap: "var(--space-2)", padding: "var(--space-2)" }}>
        <input
          data-testid="interview-chat-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={sending}
        />
        <button type="button" data-testid="interview-chat-send" onClick={() => void send()} disabled={sending}>
          Send
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec reqogniloom-frontend-1 sh -c 'cd /app && npx vitest run src/components/InterviewWidget/InterviewChatPane.test.tsx'`
Expected: PASS (3 tests)

- [ ] **Step 5: Wire into `InterviewWidget`**

In `InterviewWidget.tsx`, add active-session state (`useState<InterviewState | null>(null)`) and, when no session is active, a row of "start" buttons for the in-scope artifact types (same static list as the Hermes plugin's `InterviewListView`, spec §1 of the engine design — `Requirement, ArchitectureElement, StakeholderNeed, Risk, TestCase, Adr, Issue, Goal`) that call `interviewsApi.start(activeWorkspace.id, type)` and store the result; when a session is active, render `<InterviewChatPane interview={session} onStateChange={setSession} />` inside the panel.

- [ ] **Step 6: Commit**

```bash
git add backend/application/interview_service.py frontend/src/api/interviews.ts frontend/src/components/InterviewWidget/
git commit -m "feat: add interview chat pane, fix missing transcript in get_state"
```

---

## Task 7: Artifact panel pane

**Files:**
- Create: `frontend/src/components/InterviewWidget/InterviewArtifactPane.tsx`
- Modify: `frontend/src/components/InterviewWidget/InterviewWidget.tsx` (render alongside the chat pane)
- Test: `frontend/src/components/InterviewWidget/InterviewArtifactPane.test.tsx`

**Interfaces:**
- Consumes: `InterviewState.grounding_snapshot` (Task 4), `interviewsApi.formalize` (Task 4).
- Produces: `InterviewArtifactPane({interview, onFormalized}: {interview: InterviewState; onFormalized: (r: {resulting_artifact_ids: string[]}) => void}): JSX.Element` — shows grounding candidates as "possibly related" hints while `status === "in_progress"`; a "Formalize" button enabled once `missing_fields` is empty; after formalize succeeds, shows the resulting artifact ids with links (reuses the existing `ROUTE_BASE_BY_TYPE` mapping already defined in `frontend/src/api/artifactRefs.ts` for building a route from an artifact id + type — but note `artifactRefs.ts` needs an `artifact_type` to pick a route, and `formalize`'s response only returns bare ids; the simplest correct v1 is a plain, non-navigable id list with a link to the workspace's artifact search instead of trying to resolve each id's type client-side — do not add a new lookup call just for this link, that's speculative scope beyond what the spec asks for).

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/InterviewWidget/InterviewArtifactPane.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { InterviewArtifactPane } from "./InterviewArtifactPane";
import type { InterviewState } from "../../api/interviews";

vi.mock("../../api/interviews", () => ({
  interviewsApi: { formalize: vi.fn() },
}));
import { interviewsApi } from "../../api/interviews";

function makeInterview(overrides: Partial<InterviewState> = {}): InterviewState {
  return {
    id: "s-1", status: "in_progress", phase: "elicitation",
    collected_fields: {}, missing_fields: [], grounding_snapshot: { candidates: [] },
    transcript: [],
    ...overrides,
  } as InterviewState;
}

describe("InterviewArtifactPane", () => {
  it("shows grounding candidates as hints", () => {
    const interview = makeInterview({
      grounding_snapshot: { candidates: [{ artifact_id: "a-1", title: "Similar req", score: null }] },
    });
    render(<InterviewArtifactPane interview={interview} onFormalized={vi.fn()} />);

    expect(screen.getByText(/Similar req/i)).toBeInTheDocument();
  });

  it("disables Formalize while fields are missing", () => {
    const interview = makeInterview({
      missing_fields: [{ name: "title", type: "text", choices: null }],
    });
    render(<InterviewArtifactPane interview={interview} onFormalized={vi.fn()} />);

    expect(screen.getByTestId("interview-artifact-formalize")).toBeDisabled();
  });

  it("formalizes and reports the resulting artifact ids", async () => {
    vi.mocked(interviewsApi.formalize).mockResolvedValue({
      resulting_artifact_ids: ["art-1"], status: "completed",
    });
    const onFormalized = vi.fn();
    render(<InterviewArtifactPane interview={makeInterview()} onFormalized={onFormalized} />);

    fireEvent.click(screen.getByTestId("interview-artifact-formalize"));

    await waitFor(() => expect(onFormalized).toHaveBeenCalledWith({ resulting_artifact_ids: ["art-1"] }));
    expect(screen.getByText(/art-1/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec reqogniloom-frontend-1 sh -c 'cd /app && npx vitest run src/components/InterviewWidget/InterviewArtifactPane.test.tsx'`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the pane**

```typescript
// frontend/src/components/InterviewWidget/InterviewArtifactPane.tsx
import { useState } from "react";
import { interviewsApi, type InterviewState } from "../../api/interviews";

export function InterviewArtifactPane({
  interview,
  onFormalized,
}: {
  interview: InterviewState;
  onFormalized: (r: { resulting_artifact_ids: string[] }) => void;
}): JSX.Element {
  const [result, setResult] = useState<{ resulting_artifact_ids: string[] } | null>(null);

  const formalize = async () => {
    const r = await interviewsApi.formalize(interview.id);
    setResult(r);
    onFormalized(r);
  };

  return (
    <div style={{ padding: "var(--space-2)", borderTop: "1px solid var(--color-border)" }}>
      {interview.grounding_snapshot.candidates.length > 0 && (
        <ul style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>
          {interview.grounding_snapshot.candidates.map((c) => (
            <li key={c.artifact_id}>Possibly related: {c.title}</li>
          ))}
        </ul>
      )}
      <button
        type="button"
        data-testid="interview-artifact-formalize"
        disabled={interview.missing_fields.length > 0}
        onClick={() => void formalize()}
      >
        Formalize
      </button>
      {result && <p>Created/updated: {result.resulting_artifact_ids.join(", ")}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec reqogniloom-frontend-1 sh -c 'cd /app && npx vitest run src/components/InterviewWidget/InterviewArtifactPane.test.tsx'`
Expected: PASS (3 tests)

- [ ] **Step 5: Wire into `InterviewWidget`**, alongside `InterviewChatPane`, and run the full component's test suite

Run: `docker exec reqogniloom-frontend-1 sh -c 'cd /app && npx vitest run src/components/InterviewWidget'`
Expected: PASS (all InterviewWidget tests)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/InterviewWidget/
git commit -m "feat: add interview artifact panel with formalize"
```

---

## Task 8: `AiPromptsSection.tsx` — labels + variable hints for interview slots

**Files:**
- Modify: `frontend/src/components/WorkspaceSettings/AiPromptsSection.tsx`
- Test: `frontend/src/components/WorkspaceSettings/AiPromptsSection.test.tsx` (extend if it exists — check first; if it doesn't, this codebase may test this component elsewhere, search before creating a new file)

**Interfaces:**
- Consumes: nothing new at runtime — `AiPromptsSection` is already generic over whatever `PromptTemplate` slots the backend reports (`promptTemplatesApi.listSlots`), per spec §7.
- Produces: a label-generation function for `interview.protocol.<Type>` slot names, an explicit `SLOT_LABELS["interview.chat_turn"]` entry, and a second, dedicated variable-hint paragraph for `interview.*` slots.

- [ ] **Step 1: Write the failing test**

```typescript
// Add to (or create) frontend/src/components/WorkspaceSettings/AiPromptsSection.test.tsx
// Follow this file's existing render/mock setup if it exists; the two
// assertions below are what Task 8 adds regardless of surrounding scaffolding.
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AiPromptsSection } from "./AiPromptsSection";
import { promptTemplatesApi } from "../../api/prompt-templates";

vi.mock("../../api/prompt-templates", () => ({
  promptTemplatesApi: { listSlots: vi.fn(), saveSlot: vi.fn(), clearSlot: vi.fn() },
  KNOWN_PROMPT_SLOTS: [
    "need_to_sysreq", "sysreq_to_arch_assign", "sysreq_decompose_next_level",
    "goal_aggregate", "testcase_derive", "architecture_to_risk",
    "workspace_to_glossary", "decision_to_adr",
    "interview.protocol.Requirement", "interview.chat_turn",
  ],
}));

describe("AiPromptsSection — interview slots (Spec 3 §7)", () => {
  it("generates a label for interview.protocol.<Type> slots without a hardcoded entry", async () => {
    vi.mocked(promptTemplatesApi.listSlots).mockResolvedValue({
      slots: [
        {
          name: "interview.protocol.Requirement", effective_content: "x", effective_scope: "factory",
          global_content: null, factory_default: "x",
        },
      ],
    } as never);

    render(<AiPromptsSection workspaceId="ws-1" />);

    expect(await screen.findByText(/Interview: Requirement/i)).toBeInTheDocument();
  });

  it("shows the interview-specific placeholder hint block distinct from the derivation one", async () => {
    vi.mocked(promptTemplatesApi.listSlots).mockResolvedValue({
      slots: [
        {
          name: "interview.chat_turn", effective_content: "x", effective_scope: "factory",
          global_content: null, factory_default: "x",
        },
      ],
    } as never);

    render(<AiPromptsSection workspaceId="ws-1" />);

    expect(await screen.findByText(/transcript_json/i)).toBeInTheDocument();
  });
});
```

Before running, open the current `frontend/src/components/WorkspaceSettings/AiPromptsSection.test.tsx` if it exists (search first) and match its exact `PromptSlotState` mock shape rather than guessing field names.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec reqogniloom-frontend-1 sh -c 'cd /app && npx vitest run src/components/WorkspaceSettings/AiPromptsSection.test.tsx'`
Expected: FAIL — no "Interview: Requirement" text, no `transcript_json` text

- [ ] **Step 3: Implement the label generator and hint block**

In `AiPromptsSection.tsx`, add near `SLOT_LABELS`:

```typescript
const INTERVIEW_PROTOCOL_PREFIX = "interview.protocol.";

/** Generates a label for interview.protocol.<Type> without a per-type
 * SLOT_LABELS entry -- <Type> is already PascalCase (Artifact.artifact_type
 * convention, see the engine spec §3.1), so no transformation is needed
 * beyond string concatenation. Covers future artifact types automatically. */
function labelForSlot(name: string): string {
  if (name.startsWith(INTERVIEW_PROTOCOL_PREFIX)) {
    return `Interview: ${name.slice(INTERVIEW_PROTOCOL_PREFIX.length)}`;
  }
  return SLOT_LABELS[name] ?? name;
}
```

Add to `SLOT_LABELS`:

```typescript
  "interview.chat_turn": "Interview: Chat Turn Generation",
```

Replace the label-rendering call site (`t(\`settings.promptTemplates.slot.${slot.name}\`, SLOT_LABELS[slot.name] ?? slot.name)`) to use `labelForSlot(slot.name)` as the fallback instead of `SLOT_LABELS[slot.name] ?? slot.name` directly.

Add a second hint paragraph, rendered only when at least one visible slot name starts with `"interview."`:

```typescript
{orderedSlots.some((s) => s.name.startsWith("interview.")) && (
  <p style={hintStyle}>
    {t(
      "settings.promptTemplates.interviewDescription",
      "Interview prompt placeholders differ by slot. " +
        "interview.protocol.<Type> (phase prompt_fragment): {artifact_type}, {phase_name}, " +
        "{collected_fields_json}, {missing_fields_json}, {grounding_snapshot_json}. " +
        "interview.chat_turn: {transcript_json}, {user_message}, {current_phase_fragment}, " +
        "{missing_fields_json}, {grounding_snapshot_json}."
    )}
  </p>
)}
```

Place this directly after the existing derivation-slots hint paragraph.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec reqogniloom-frontend-1 sh -c 'cd /app && npx vitest run src/components/WorkspaceSettings/AiPromptsSection.test.tsx'`
Expected: PASS

- [ ] **Step 5: Run the full frontend suite to confirm nothing broke**

Run: `docker exec reqogniloom-frontend-1 sh -c 'cd /app && npx vitest run'`
Expected: PASS (aside from the pre-existing, unrelated red `CanvasEditor.tools.test.tsx` tracked in issue #527 — do not investigate those, they predate this plan)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/WorkspaceSettings/AiPromptsSection.tsx frontend/src/components/WorkspaceSettings/AiPromptsSection.test.tsx
git commit -m "feat: label and document interview.* prompt slots in the admin UI"
```

---

## Self-Review Notes (for whoever executes this plan)

- **Task 6 Step 0 fixes a real gap found while writing this plan:** the engine plan's `InterviewService.get_state()` doesn't return `transcript`, which this plan's chat pane needs. Apply that one-line fix to the already-implemented `interview_service.py` as part of Task 6, not as a separate follow-up — it is small enough not to warrant its own task, but it must not be silently skipped.
- **No shared TypeScript package between the Hermes plugin and the web frontend.** `InterviewState`/`InterviewField` are defined twice (once in the Spec 2 plan's `mcpClient.ts`, once here in `interviews.ts`) with the same shape. This is a deliberate, small, YAGNI-consistent duplication — the two codebases have no shared package today, and introducing one for two nearly-identical type definitions would be a larger, unrelated refactor.
- **The artifact panel's post-formalize display is a bare id list, not clickable links** (Task 7) — resolving each id's type/route would need an extra lookup call the spec doesn't ask for; flagged explicitly rather than silently scoped in or out.
- **Spec §6's "race between chat-turn and a parallel host" error handling** is satisfied structurally, not via an explicit extra `get_state` refetch before every chat send: `generate_chat_turn` (Task 2) always reads the live `InterviewSession` row via `_get_session` before acting, and raises `ValidationError` if the session is no longer `in_progress` — the same server-side freshness guarantee the engine plan already provides for every mutating call, not something this plan needs to re-implement client-side.
