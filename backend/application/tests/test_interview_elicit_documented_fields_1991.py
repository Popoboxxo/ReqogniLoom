"""Issue #1991 — protocol derivation and end-to-end coverage.

* ADR's ``context``/``decision``/``consequences`` are attributes in their own
  right (the ``decision_record`` widget only renders them), so a definition-
  derived protocol now asks them and the answers reach ``create_adr()``.
* Unsupported/empty widget elicitation is rejected explicitly instead of
  being silently dropped from the protocol.
"""
from __future__ import annotations

import uuid

import pytest

from application.interview_protocol import (
    ProtocolValidationError,
    protocol_from_definition,
)

_ADR_FIELDS = {"context", "decision", "consequences"}


def _attr(name: str, **over):
    base = {
        "name": name,
        "kind": "core",
        "type": "text",
        "section": "general",
        "order": 0,
        "ai_elicit": True,
        "visible": True,
        "options": [],
        "label": {"de": name, "en": name},
        "widget_key": None,
        "fields": [],
    }
    base.update(over)
    return base


class TestProtocolDerivation:
    def test_adr_decision_record_fields_are_elicited(self) -> None:
        attributes = [
            _attr("title"),
            _attr("description"),
            _attr(
                "decision_record",
                type="widget",
                widget_key="markdown_tab_group",
                fields=["description", "context", "consequences"],
                ai_elicit=False,
            ),
            _attr("context", type="textarea"),
            _attr("decision", type="textarea"),
            _attr("consequences", type="textarea"),
        ]
        protocol = protocol_from_definition(attributes, "Adr")
        names = {f.name for phase in protocol.phases for f in phase.required_fields}
        assert {"title", "description", "context", "decision", "consequences"} <= names
        assert "decision_record" not in names

    def test_widget_with_no_elicitable_bound_field_is_rejected(self) -> None:
        attributes = [
            _attr("title"),
            _attr(
                "orphan_widget",
                type="widget",
                widget_key="markdown_tab_group",
                fields=["context"],
            ),
            _attr("context", ai_elicit=False),
        ]
        with pytest.raises(ProtocolValidationError) as excinfo:
            protocol_from_definition(attributes, "Adr")
        assert "orphan_widget" in str(excinfo.value)

    def test_unsupported_attribute_type_is_rejected(self) -> None:
        with pytest.raises(ProtocolValidationError) as excinfo:
            protocol_from_definition([_attr("title", type="mystery")], "Adr")
        assert "mystery" in str(excinfo.value)


@pytest.mark.django_db
def test_bootstrapped_adr_interview_carries_decision_record_fields() -> None:
    from django.core.management import call_command

    from application.adr_service import AdrService
    from application.interview_protocol import get_protocol
    from application.interview_service import InterviewService
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="Adr Elicit 1991", is_active=True)
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="ws-adr-1991", preset={"name": "standard"}
        )
        user = User.objects.create(
            username="adr-elicit-1991", email="adr-elicit-1991@t.test", tenant=tenant
        )
    finally:
        clear_request_tenant()

    call_command("bootstrap_attribute_definitions", tenant=str(tenant.id))

    set_request_tenant(tenant.id)
    try:
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("editor",),
            auth_method=AuthMethod.API_KEY,
            api_key_id=None,
        )
        protocol = get_protocol(ctx, "Adr", workspace.id)
        elicited = {f.name for phase in protocol.phases for f in phase.required_fields}
        assert _ADR_FIELDS <= elicited, elicited

        svc = InterviewService()
        session = svc.start(ctx, "Adr", workspace.id)
        answers = {
            "title": "Adopt OAuth2",
            "description": "Short summary",
            "context": "Password fatigue in support",
            "decision": "Use the identity provider",
            "consequences": "One fewer credential to manage",
        }
        for name in elicited:
            svc.answer(ctx, session.id, name, answers.get(name, f"Answer for {name}"))
        result = svc.formalize(ctx, session.id)
        adr = AdrService().get_adr(uuid.UUID(result["resulting_artifact_ids"][0]), ctx)
        assert adr.context == answers["context"]
        assert adr.decision == answers["decision"]
        assert adr.consequences == answers["consequences"]
    finally:
        clear_request_tenant()
