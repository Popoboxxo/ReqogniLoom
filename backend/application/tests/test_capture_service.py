"""``suggestion.capture`` + the create/update adapters (ADR-032, plan P2/P3).

These tests drive the real Layer-2 service against the database and pin the
contract the REST and MCP transports rely on:

* the workspace switch is the first decisive gate — off means **no model call**;
* secrets are redacted before storage and before the prompt, and the raw text
  is never persisted;
* the rule filter drops commands/short messages without spending a call;
* idempotency and the recently-rejected window suppress repeats;
* a create suggestion, once accepted by a human, produces a real artifact
  through the production ``create_X()`` path and keeps its capture provenance;
* an update suggestion, once accepted, changes the target and bumps its
  version; a stale ``base_version`` is a conflict and overwrites nothing;
* an agent key can never accept (ADR-019 Zusage 7(c)).

The model is replaced by a scripted fake provider: these tests are about the
server's contract, not about model quality.
"""
from __future__ import annotations

import pytest

from application.base import ProducerContextRequiredError
from application.capture_update import CaptureConflictError
from application.capture_errors import (
    CaptureDisabledError,
    CaptureTextTooLongError,
    WorkspaceForbiddenError,
)
from application.capture_service import (
    CAPTURE_MAX_TEXT_LENGTH,
    CaptureService,
)
from application.requirement_service import RequirementService
from application.suggestion_service import SuggestionService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    ROLE_ADMIN,
    ApiKey,
    PreferenceValue,
    UserRole,
)
from link_types.workspace_store import provision_workspace_link_types
from persistence.models import Requirement, Suggestion, Tenant, User, Workspace
from persistence.tenancy import TenantContext

_LONG_ENOUGH = (
    "Das System muss eine eingehende Anfrage innerhalb von zwei Sekunden "
    "beantworten und bei Zeitüberschreitung einen Fehler melden."
)


class _FakeProvider:
    """Scripted stand-in for a configured LLM provider."""

    PROVIDER_NAME = "fake-capture"

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, purpose: str = "", timeout=None) -> str:  # noqa: ARG002
        self.prompts.append(prompt)
        return self.answer


def _requirement_answer(title: str, description: str) -> str:
    """A well-formed capture answer with one Requirement proposal."""
    return (
        "```json\n"
        '[{"operation": "create", "type": "Requirement", '
        f'"fields": {{"title": "{title}", "description": "{description}"}}, '
        '"rationale": "stated requirement"}]\n'
        "```"
    )


@pytest.fixture
def env(db):
    """Tenant + workspace + admin owner + a relay key that holds ``capture``."""
    tenant = Tenant.objects.create(name="t-capture", slug="t-capture")
    TenantContext.set_tenant(tenant.id)
    try:
        owner = User.objects.create(
            tenant=tenant, username="cap-owner", email="cap@example.com"
        )
        workspace = Workspace.objects.create(tenant=tenant, name="ws")
        provision_workspace_link_types(
            workspace_id=workspace.id, tenant_id=tenant.id
        )
        UserRole.objects.create(
            tenant=tenant, user=owner, workspace=workspace, role=ROLE_ADMIN
        )
        key = ApiKey.objects.create(
            tenant=tenant,
            user=owner,
            name="relay",
            key_hash="sha256p1:capture",
            principal_type="agent",
            agent_label="Relay",
            workspace_ids=[str(workspace.id)],
            capture_enabled=True,
        )
        PreferenceValue.objects.create(
            tenant=tenant,
            scope="workspace",
            workspace=workspace,
            key="capture.enabled",
            value=True,
        )

        capture_ctx = AuthContext(
            user_id=owner.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method=AuthMethod.API_KEY,
            api_key_id=key.id,
            actor_type="agent",
            agent_label="Relay",
            scope="write",
        )
        # A human bearer session: decides suggestions, never captures.
        human_ctx = AuthContext(
            user_id=owner.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )

        yield {
            "tenant": tenant,
            "owner": owner,
            "workspace": workspace,
            "key": key,
            "capture_ctx": capture_ctx,
            "human_ctx": human_ctx,
        }
    finally:
        TenantContext.clear_tenant()


def _use_provider(monkeypatch, answer: str) -> _FakeProvider:
    """Route ``CaptureService``'s provider resolution to a scripted fake."""
    provider = _FakeProvider(answer)
    monkeypatch.setattr(
        "application.llm_provider_resolution.resolve_provider",
        lambda: (provider, provider.PROVIDER_NAME, None),
    )
    return provider


def _capture(env, *, text: str = _LONG_ENOUGH, client: str = "claude-code", **kwargs):
    return CaptureService().capture(
        env["capture_ctx"],
        workspace_id=env["workspace"].id,
        text=text,
        client=client,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Gates: switch, credential, length
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_switch_off_returns_capture_disabled_without_a_model_call(env, monkeypatch):
    provider = _use_provider(monkeypatch, _requirement_answer("A", "B"))
    PreferenceValue.objects.filter(key="capture.enabled").delete()

    with pytest.raises(CaptureDisabledError):
        _capture(env)

    # The decisive property (spec S6/A7): no model call happened.
    assert provider.prompts == []


@pytest.mark.django_db
def test_missing_capture_right_is_producer_context_required(env, monkeypatch):
    provider = _use_provider(monkeypatch, _requirement_answer("A", "B"))
    env["key"].capture_enabled = False
    env["key"].save(update_fields=["capture_enabled"])

    with pytest.raises(ProducerContextRequiredError):
        _capture(env)

    assert provider.prompts == []


@pytest.mark.django_db
def test_workspace_without_a_role_is_forbidden(env):
    other = Workspace.objects.create(tenant=env["tenant"], name="not-mine")

    with pytest.raises(WorkspaceForbiddenError):
        CaptureService().capture(
            env["capture_ctx"],
            workspace_id=other.id,
            text=_LONG_ENOUGH,
            client="claude-code",
        )


@pytest.mark.django_db
def test_text_over_the_limit_is_rejected(env):
    with pytest.raises(CaptureTextTooLongError) as excinfo:
        _capture(env, text="x" * (CAPTURE_MAX_TEXT_LENGTH + 1))

    assert excinfo.value.details["limit"] == CAPTURE_MAX_TEXT_LENGTH


@pytest.mark.django_db
def test_overlong_session_id_is_rejected(env):
    """A column-width violation is a request defect, never a database error."""
    from application.base import ValidationError as ServiceValidationError

    with pytest.raises(ServiceValidationError):
        _capture(env, source_session="x" * 256)


# ---------------------------------------------------------------------------
# Redaction + filter
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_secret_is_redacted_before_storage_and_before_the_prompt(env, monkeypatch):
    transcript = _requirement_answer(
        "Anfragefrist", "Der Dienst antwortet innerhalb von zwei Sekunden."
    )
    provider = _use_provider(monkeypatch, transcript)

    result = _capture(
        env,
        text=(
            "Bitte nimm auf: " + _LONG_ENOUGH + " Der Key ist "
            "reqlo_abcdef123456 und darf nie gespeichert werden."
        ),
    )

    assert result["created"], "the requirement should have been proposed"
    suggestion = Suggestion.objects.get(id=result["created"][0])
    assert "reqlo_abcdef123456" not in suggestion.source_excerpt
    assert "[REDACTED_API_KEY]" in suggestion.source_excerpt
    # The prompt must not carry the credential either.
    assert provider.prompts
    assert "reqlo_abcdef123456" not in provider.prompts[0]


@pytest.mark.django_db
def test_mostly_secret_message_is_dropped(env, monkeypatch):
    provider = _use_provider(monkeypatch, _requirement_answer("A", "B"))

    # Two long credentials: the redacted share clearly exceeds half the message,
    # which is what "überwiegend geschwärzt" means operationally.
    result = _capture(
        env,
        text="reqlo_" + "a" * 60 + " reqlo_" + "b" * 60,
    )

    assert result["created"] == []
    assert result["skipped"]["redacted"] == 1
    assert provider.prompts == []


@pytest.mark.parametrize(
    "secret",
    [
        # The two shapes this project's own providers issue — the original
        # pattern missed both because of the internal hyphens.
        "sk-ant-api03-AbCdEfGh1234567890abcdefghij",
        "sk-proj-AbCdEfGh1234567890abcdefghij",
        "sk-AbCdEfGh1234567890",
        # Labelled assignments (Azure account key, plain password).
        "AccountKey=0123456789abcdef0123456789abcdef",
        "password=hunter2supersecret",
        # Already-covered shapes, pinned so a rewrite cannot drop them.
        "reqlo_abcdef123456",
        "ghp_abcdefghijklmnopqrstuvwxyz",
        "Bearer abcdefghijklmnopqrstu",
    ],
)
def test_redaction_recognises_provider_and_assignment_shapes(secret):
    """Every credential shape a user plausibly pastes is removed (D5 / S8)."""
    from application.capture_redaction import redact

    result = redact(f"Der Wert ist {secret} und darf nicht raus.")

    assert result.found, secret
    assert secret not in result.text


def test_ordinary_prose_with_a_short_key_value_pair_is_not_redacted():
    """Over-redaction is bounded: ``key: value`` in prose stays readable."""
    from application.capture_redaction import redact

    result = redact("Die wichtigste Kennzahl: key: value")

    assert not result.found


@pytest.mark.django_db
def test_command_and_short_messages_are_filtered_without_a_model_call(env, monkeypatch):
    provider = _use_provider(monkeypatch, _requirement_answer("A", "B"))

    command = _capture(env, text="/status")
    short = _capture(env, text="ok danke")

    assert command["skipped"]["filtered"] == 1
    assert short["skipped"]["filtered"] == 1
    assert provider.prompts == []


@pytest.mark.django_db
def test_code_or_log_paste_is_filtered(env, monkeypatch):
    provider = _use_provider(monkeypatch, _requirement_answer("A", "B"))
    paste = "\n".join(
        [
            "2026-11-27T10:00:01 INFO starting worker",
            "2026-11-27T10:00:02 ERROR connection refused",
            "    at handler.py:42",
            "    return self.run()",
            "2026-11-27T10:00:03 INFO retrying",
            "2026-11-27T10:00:04 ERROR gave up",
        ]
    )

    result = _capture(env, text=paste)

    assert result["skipped"]["filtered"] == 1
    assert provider.prompts == []


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_second_capture_of_the_same_message_is_a_duplicate(env, monkeypatch):
    _use_provider(monkeypatch, _requirement_answer("Antwortzeit", "Zwei Sekunden."))

    first = _capture(env)
    second = _capture(env)

    assert len(first["created"]) == 1
    assert second["created"] == []
    assert second["skipped"]["duplicate"] == 1
    assert Suggestion.objects.count() == 1


@pytest.mark.django_db
def test_idempotency_constraint_race_is_reported_as_a_duplicate(env, monkeypatch):
    """The read-then-write window: the DB constraint must answer ``duplicate``.

    Two concurrent captures of the same message both pass the pre-check; the
    partial unique constraint then fires on the loser. That is the duplicate the
    contract promises — a 500 here would make a retried capture unrecoverable.
    """
    from django.db import IntegrityError

    from application.suggestion_service import SuggestionService

    _use_provider(monkeypatch, _requirement_answer("Wettlauf", "Zwei Prozesse."))

    def _raise_constraint(*args, **kwargs):
        raise IntegrityError(
            "duplicate key value violates unique constraint "
            '"uq_suggestion_workspace_idempotency_key"'
        )

    monkeypatch.setattr(SuggestionService, "create", _raise_constraint)

    result = _capture(env)

    assert result["created"] == []
    assert result["skipped"]["duplicate"] == 1


# ---------------------------------------------------------------------------
# Create suggestion -> artifact with provenance
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_accepted_create_suggestion_creates_the_artifact_with_provenance(
    env, monkeypatch
):
    _use_provider(
        monkeypatch,
        _requirement_answer(
            "Antwortzeit der API",
            "Das System antwortet innerhalb von zwei Sekunden.",
        ),
    )

    result = _capture(env, source_session="sess-42", message_id="m-7")
    assert len(result["created"]) == 1
    suggestion_id = result["created"][0]

    accepted = SuggestionService().accept(suggestion_id, env["human_ctx"])

    assert accepted["status"] == "accepted"
    requirement = Requirement.objects.get(
        workspace_id=env["workspace"].id, title="Antwortzeit der API"
    )
    # Provenance: the receipt names the created artifact and the client session.
    stored = Suggestion.objects.get(id=suggestion_id)
    assert stored.client == "claude-code"
    assert stored.source_session == "sess-42"
    assert stored.source_hash  # a hash, not the text
    # ``target_item_id`` is the ENTITY id (one meaning for the column); the
    # backing Artifact id is recorded explicitly in the payload.
    assert str(stored.target_item_id) == str(requirement.id)
    assert stored.payload["accepted_artifact_id"] == str(requirement.artifact_id)


@pytest.mark.django_db
def test_agent_may_not_accept_a_capture_suggestion(env, monkeypatch):
    from application.trace_link_service import AgentSelfConfirmError

    _use_provider(monkeypatch, _requirement_answer("Bot title", "Bot description"))
    result = _capture(env)

    with pytest.raises(AgentSelfConfirmError):
        SuggestionService().accept(result["created"][0], env["capture_ctx"])

    assert Suggestion.objects.get(id=result["created"][0]).status == "open"


# ---------------------------------------------------------------------------
# Update suggestion -> target changed, stale version conflicts
# ---------------------------------------------------------------------------


def _existing_requirement(env) -> Requirement:
    return RequirementService().create_requirement(
        workspace_id=env["workspace"].id,
        title="Bestehende Anforderung",
        ctx=env["human_ctx"],
        description="Erste Fassung.",
    )


def _update_suggestion(env, requirement: Requirement, *, base_version: int | None):
    return SuggestionService().create(
        kind=Suggestion.Kind.ARTIFACT_UPDATE,
        ctx=env["capture_ctx"],
        workspace_id=env["workspace"].id,
        payload={
            "artifact_type": "Requirement",
            "fields": {"description": "Erweiterte Fassung mit Kriterium."},
            "target_artifact_id": str(requirement.id),
            "base_version": base_version,
            "rationale": "Die Nachricht erweitert die Anforderung.",
        },
        producer="suggestion.capture",
        capture=True,
        capture_client="claude-code",
        operation=Suggestion.Operation.UPDATE,
        target_artifact_id=requirement.id,
        base_version=base_version,
    )


@pytest.mark.django_db
def test_accepted_update_suggestion_changes_the_target_and_bumps_the_version(env):
    requirement = _existing_requirement(env)
    before = requirement.version
    suggestion = _update_suggestion(env, requirement, base_version=before)

    accepted = SuggestionService().accept(suggestion.id, env["human_ctx"])

    assert accepted["status"] == "accepted"
    requirement.refresh_from_db()
    assert requirement.description == "Erweiterte Fassung mit Kriterium."
    assert requirement.version == before + 1


@pytest.mark.django_db
def test_stale_base_version_is_a_conflict_and_overwrites_nothing(env):
    requirement = _existing_requirement(env)
    suggestion = _update_suggestion(
        env, requirement, base_version=max(0, requirement.version - 1)
    )

    with pytest.raises(CaptureConflictError):
        SuggestionService().accept(suggestion.id, env["human_ctx"])

    requirement.refresh_from_db()
    assert requirement.description == "Erste Fassung."
    # The receipt stays open: the human can inspect the current artifact.
    assert Suggestion.objects.get(id=suggestion.id).status == "open"


@pytest.mark.django_db
def test_repeated_existing_artifact_becomes_an_update_proposal(env, monkeypatch):
    requirement = _existing_requirement(env)
    _use_provider(
        monkeypatch,
        _requirement_answer(
            "Bestehende Anforderung", "Zusätzlicher Absatz zur Klarstellung."
        ),
    )

    result = _capture(env)

    assert len(result["created"]) == 1
    stored = Suggestion.objects.get(id=result["created"][0])
    assert stored.kind == Suggestion.Kind.ARTIFACT_UPDATE
    assert stored.operation == Suggestion.Operation.UPDATE
    assert str(stored.target_artifact_id) == str(requirement.id)
    assert stored.base_version == requirement.version


@pytest.mark.django_db
def test_bare_title_repeat_is_counted_as_a_duplicate(env, monkeypatch):
    """A dropped repeat must be visible in ``skipped``, not silently vanish."""
    _existing_requirement(env)
    _use_provider(
        monkeypatch,
        '[{"operation": "create", "type": "Requirement", '
        '"fields": {"title": "Bestehende Anforderung"}}]',
    )

    result = _capture(env)

    assert result["created"] == []
    assert result["skipped"]["duplicate"] == 1
    assert result["skipped"]["invalid"] == 0
