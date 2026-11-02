"""Plan F F3-T7 (#1374) — inline anchor register, I-1…I-5 and DOC-P7.

The suite runs against real rows: a provisioned workspace, a real glossary term
(its token is the supported inline grammar, ENT-F3 = a), documents created
through :class:`DocumentService` and trace links created by the anchor sync.

Covered contracts (spec §7 and concept §6.7):
  * I-1 — a stored token creates its anchor *and* its trace edge.
  * I-2 — removing the last token of an edge removes the edge; another anchor
    of the same edge keeps it alive.
  * I-3 — deleting a link with anchors answers ``409 ANCHORS_PRESENT`` with the
    affected count; the confirmed retry removes anchors + link.
  * I-4 — an edge without anchors stays valid and is untouched by a sync.
  * I-5 — a soft-deleted target keeps its anchor and ``DOC-P7`` reports it.
  * grammar — ``[[Begriff]]`` is rejected fail-closed; only the stored
    glossary token is accepted.
  * RLS — ``pl_inline_anchor`` carries ENABLE + FORCE RLS.
  * migration — ``0127``/``0128`` are reversible.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import override_settings
from rest_framework.test import APIClient

from application.base import AnchorsPresentError, ValidationError
from application.document_service import DocumentService
from application.glossary_reference_service import (
    PREFERRED_REFERENCE_LINK_TYPE,
    REFERENCE_LINK_TYPE,
    build_reference_token,
)
from application.glossary_service import GlossaryService
from application.inline_anchor_service import (
    ANCHOR_FIELD_BODY,
    ANCHOR_FIELD_DESCRIPTION,
    InlineAnchorService,
)
from application.trace_link_service import TraceLinkService
from auth_tenancy.context import AuthContext, AuthMethod
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    Document,
    InlineAnchor,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from traceability.audit.registry import DOC_P7
from traceability.audit.rule_engine import RuleEngine
from traceability.audit.types import Severity

pytestmark = pytest.mark.django_db

PRE_MIGRATION = ("persistence", "0126_work_item_rls_policy")
ANCHOR_MIGRATION = ("persistence", "0128_inline_anchor_rls_policy")


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _ctx(tenant_id, workspace_id, user_id) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace_id,
    )


@pytest.fixture
def env():
    tenant = Tenant.objects.create(name="Anchor Tenant", slug=f"anchor-{uuid.uuid4().hex[:8]}")
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="anchor-ws", preset={"name": "standard"}
        )
        user = User.objects.create(
            tenant=tenant,
            username=f"anchor-{uuid.uuid4().hex[:8]}",
            email="anchor@t.test",
        )
    finally:
        clear_request_tenant()
    provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
    set_request_tenant(tenant.id)
    try:
        from workflow.services import create_default_workflow

        create_default_workflow(
            workspace_id=workspace.id,
            preset="glossary_term_default",
            item_type="GlossaryTerm",
            tenant_id=tenant.id,
        )
    finally:
        clear_request_tenant()
    ctx = _ctx(tenant.id, workspace.id, user.id)
    return tenant, workspace, ctx


@pytest.fixture
def term(env):
    _, workspace, ctx = env
    set_request_tenant(ctx.tenant_id)
    try:
        return GlossaryService().create(ctx, workspace.id, "Hydraulikpumpe", "v1")
    finally:
        clear_request_tenant()


def _token(term) -> str:
    return build_reference_token(term.artifact_id, 1)


def _create_document(ctx, workspace, *, body="", description="") -> Document:
    set_request_tenant(ctx.tenant_id)
    try:
        return DocumentService().create_document(
            workspace.id,
            ctx,
            title="Doc",
            kind="Spec",
            description=description,
            body=body,
        )
    finally:
        clear_request_tenant()


def _update_document(ctx, document, **fields) -> Document:
    set_request_tenant(ctx.tenant_id)
    try:
        return DocumentService().update_document(document.id, ctx, **fields)
    finally:
        clear_request_tenant()


def _anchors(document) -> list[InlineAnchor]:
    return list(
        InlineAnchor.unscoped.filter(source_artifact_id=document.artifact_id)
    )


def _link(source_artifact_id, target_artifact_id) -> TraceLink | None:
    return TraceLink.unscoped.filter(
        source_id=source_artifact_id, target_id=target_artifact_id
    ).first()


# ---------------------------------------------------------------------------
# I-1: anchor set => edge exists
# ---------------------------------------------------------------------------


class TestI1AnchorCreatesEdge:
    def test_stored_token_creates_anchor_and_edge(self, env, term):
        _, workspace, ctx = env
        document = _create_document(ctx, workspace, body=f"see {_token(term)}")

        anchors = _anchors(document)
        assert len(anchors) == 1
        anchor = anchors[0]
        assert anchor.field == ANCHOR_FIELD_BODY
        assert anchor.token == _token(term)
        assert str(anchor.target_artifact_id) == str(term.artifact_id)
        assert str(anchor.tenant_id) == str(ctx.tenant_id)

        link = _link(document.artifact_id, term.artifact_id)
        assert link is not None
        assert str(link.id) == str(anchor.link_id)
        assert link.link_type in {
            PREFERRED_REFERENCE_LINK_TYPE,
            REFERENCE_LINK_TYPE,
        }

    def test_sync_is_idempotent(self, env, term):
        _, workspace, ctx = env
        document = _create_document(ctx, workspace, body=f"see {_token(term)}")
        _update_document(ctx, document, body=f"see {_token(term)} again")

        assert len(_anchors(document)) == 1
        assert (
            TraceLink.unscoped.filter(
                source_id=document.artifact_id, target_id=term.artifact_id
            ).count()
            == 1
        )


# ---------------------------------------------------------------------------
# I-2: anchor removed => edge removed when no anchor remains
# ---------------------------------------------------------------------------


class TestI2AnchorRemovalSyncsEdge:
    def test_removing_last_token_removes_edge(self, env, term):
        _, workspace, ctx = env
        document = _create_document(ctx, workspace, body=f"see {_token(term)}")
        assert _link(document.artifact_id, term.artifact_id) is not None

        _update_document(ctx, document, body="plain text")

        assert _anchors(document) == []
        assert _link(document.artifact_id, term.artifact_id) is None

    def test_other_anchor_of_the_same_edge_keeps_it_alive(self, env, term):
        _, workspace, ctx = env
        token = _token(term)
        document = _create_document(
            ctx, workspace, body=f"body {token}", description=f"desc {token}"
        )
        assert len(_anchors(document)) == 2
        link = _link(document.artifact_id, term.artifact_id)
        assert link is not None

        _update_document(ctx, document, body="plain")
        assert [a.field for a in _anchors(document)] == [ANCHOR_FIELD_DESCRIPTION]
        assert _link(document.artifact_id, term.artifact_id) is not None

        _update_document(ctx, document, description="plain")
        assert _anchors(document) == []
        assert _link(document.artifact_id, term.artifact_id) is None


# ---------------------------------------------------------------------------
# I-3: delete link with anchors -> 409 with count, confirmed retry deletes
# ---------------------------------------------------------------------------


class TestI3AnchorConfirmation:
    def test_delete_with_anchors_requires_confirmation(self, env, term):
        _, workspace, ctx = env
        document = _create_document(ctx, workspace, body=f"see {_token(term)}")
        link = _link(document.artifact_id, term.artifact_id)
        assert link is not None

        set_request_tenant(ctx.tenant_id)
        try:
            with pytest.raises(AnchorsPresentError) as excinfo:
                TraceLinkService().delete_trace_link(link.id, ctx)
            assert excinfo.value.error_code == "ANCHORS_PRESENT"
            assert excinfo.value.details == {"count": 1}

            TraceLinkService().delete_trace_link(
                link.id, ctx, confirm_anchor_count=1
            )
        finally:
            clear_request_tenant()

        assert InlineAnchor.unscoped.filter(link_id=link.id).count() == 0
        assert TraceLink.unscoped.filter(id=link.id).count() == 0

    def test_stale_confirmation_count_is_refused(self, env, term):
        _, workspace, ctx = env
        token = _token(term)
        document = _create_document(
            ctx, workspace, body=f"body {token}", description=f"desc {token}"
        )
        link = _link(document.artifact_id, term.artifact_id)
        assert link is not None

        set_request_tenant(ctx.tenant_id)
        try:
            with pytest.raises(AnchorsPresentError) as excinfo:
                TraceLinkService().delete_trace_link(
                    link.id, ctx, confirm_anchor_count=1
                )
            assert excinfo.value.details == {"count": 2}
        finally:
            clear_request_tenant()

        assert TraceLink.unscoped.filter(id=link.id).count() == 1


# ---------------------------------------------------------------------------
# I-4: an edge without anchors is valid and untouched
# ---------------------------------------------------------------------------


class TestI4UnanchoredEdge:
    def test_manual_edge_survives_a_text_sync(self, env, term):
        _, workspace, ctx = env
        document = _create_document(ctx, workspace, body="plain")
        set_request_tenant(ctx.tenant_id)
        try:
            manual = TraceLinkService().create_trace_link(
                source_id=document.artifact_id,
                target_id=term.artifact_id,
                link_type="references",
                ctx=ctx,
                rationale="manual, no text place",
            )
        finally:
            clear_request_tenant()

        _update_document(ctx, document, body="still plain")

        assert _anchors(document) == []
        assert TraceLink.unscoped.filter(id=manual.id).count() == 1


# ---------------------------------------------------------------------------
# I-5: deleted target -> anchor stays, DOC-P7 reports it
# ---------------------------------------------------------------------------


class TestI5DeadReference:
    def test_soft_deleted_target_keeps_anchor_and_rule_fires(self, env, term):
        tenant, workspace, ctx = env
        document = _create_document(ctx, workspace, body=f"see {_token(term)}")

        set_request_tenant(ctx.tenant_id)
        try:
            GlossaryService().delete(ctx, term.id)
        finally:
            clear_request_tenant()

        # I-5: the token stays in the text and the anchor stays in the register.
        anchors = _anchors(document)
        assert len(anchors) == 1

        standard = RuleEngine().run(
            tier="standard",
            workspace_id=str(workspace.id),
            tenant_id=str(tenant.id),
        )
        standard_findings = [
            f for f in standard.findings if f.rule_id == DOC_P7
        ]
        assert len(standard_findings) == 1
        assert standard_findings[0].severity is Severity.WARNING
        assert str(document.artifact_id) in standard_findings[0].artifact_ids

        extended = RuleEngine().run(
            tier="extended",
            workspace_id=str(workspace.id),
            tenant_id=str(tenant.id),
        )
        extended_findings = [
            f for f in extended.findings if f.rule_id == DOC_P7
        ]
        assert len(extended_findings) == 1
        assert extended_findings[0].severity is Severity.BLOCKER

    def test_minimal_tier_never_runs_doc_p7(self, env, term):
        tenant, workspace, ctx = env
        _create_document(ctx, workspace, body=f"see {_token(term)}")
        set_request_tenant(ctx.tenant_id)
        try:
            GlossaryService().delete(ctx, term.id)
        finally:
            clear_request_tenant()

        result = RuleEngine().run(
            tier="minimal",
            workspace_id=str(workspace.id),
            tenant_id=str(tenant.id),
        )
        assert result.findings == []

    def test_resolver_flags_the_dead_reference(self, env, term):
        _, workspace, ctx = env
        text = f"see {_token(term)}"
        document = _create_document(ctx, workspace, body=text)

        set_request_tenant(ctx.tenant_id)
        try:
            before = InlineAnchorService().resolve_text(ctx, workspace.id, text)
            assert before["has_dead_reference"] is False

            GlossaryService().delete(ctx, term.id)

            after = InlineAnchorService().resolve_text(ctx, workspace.id, text)
        finally:
            clear_request_tenant()

        assert after["has_dead_reference"] is True
        assert after["anchors"][0]["dead"] is True
        # The anchor row itself is still there (I-5).
        assert len(_anchors(document)) == 1


# ---------------------------------------------------------------------------
# Grammar: fail-closed, no second syntax
# ---------------------------------------------------------------------------


class TestGrammar:
    def test_display_form_is_rejected(self, env):
        _, workspace, ctx = env
        before = Artifact.unscoped.count()
        set_request_tenant(ctx.tenant_id)
        try:
            with pytest.raises(ValidationError):
                DocumentService().create_document(
                    workspace.id,
                    ctx,
                    title="Doc",
                    kind="Spec",
                    body="see [[Hydraulikpumpe]]",
                )
        finally:
            clear_request_tenant()
        # The rejected write must leave no half-created artifact/document.
        assert Artifact.unscoped.count() == before

    def test_invalid_glossary_token_is_rejected(self, env):
        _, workspace, ctx = env
        set_request_tenant(ctx.tenant_id)
        try:
            with pytest.raises(ValidationError):
                DocumentService().create_document(
                    workspace.id,
                    ctx,
                    title="Doc",
                    kind="Spec",
                    body="see [[glossary:not-a-uuid]]",
                )
        finally:
            clear_request_tenant()

    def test_plain_brackets_are_not_a_reference(self, env, term):
        _, workspace, ctx = env
        document = _create_document(
            ctx, workspace, body="array [a,b] stays text; see " + _token(term)
        )
        assert len(_anchors(document)) == 1


# ---------------------------------------------------------------------------
# RLS + migration reversibility
# ---------------------------------------------------------------------------


def test_doc_p7_is_registered_and_tiered():
    from traceability.audit.registry import (
        active_rule_ids_for_tier,
        get_registered_rules,
    )

    assert DOC_P7 in {rule.rule_id for rule in get_registered_rules()}
    assert DOC_P7 in active_rule_ids_for_tier("standard")
    assert DOC_P7 in active_rule_ids_for_tier("extended")
    assert DOC_P7 not in active_rule_ids_for_tier("minimal")


@pytest.mark.skipif(
    connection.vendor != "postgresql", reason="PostgreSQL-only assertion"
)
def test_anchor_table_has_force_rls():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = 'pl_inline_anchor'"
        )
        row = cursor.fetchone()
    assert row is not None, "pl_inline_anchor does not exist"
    assert row == (True, True)


@pytest.mark.django_db(transaction=True)
def test_anchor_migrations_are_reversible():
    executor = MigrationExecutor(connection)
    latest_target = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([PRE_MIGRATION])
        executor.loader.build_graph()
        assert "pl_inline_anchor" not in connection.introspection.table_names()

        executor.migrate([ANCHOR_MIGRATION])
        executor.loader.build_graph()
        assert "pl_inline_anchor" in connection.introspection.table_names()

        # Reverse: both the table and its policy must roll back cleanly.
        executor.migrate([PRE_MIGRATION])
        executor.loader.build_graph()
        assert "pl_inline_anchor" not in connection.introspection.table_names()
    finally:
        MigrationExecutor(connection).migrate(latest_target)


# ---------------------------------------------------------------------------
# REST wiring: 409 + ?confirm_anchor_count
# ---------------------------------------------------------------------------

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET="anchor-test-secret-not-real",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


def _rest_client(env) -> APIClient:
    from auth_tenancy.models import ROLE_ADMIN, UserRole

    tenant, workspace, ctx = env
    user = User.objects.get(id=ctx.user_id)
    user.set_password("anchor-pass-123")
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    response = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": "anchor-pass-123"},
        format="json",
    )
    assert response.status_code == 200, response.content
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {response.json()['token']}"
    )
    return client


@override_settings(**_JWT_OVERRIDES)
def test_rest_delete_names_the_anchor_count_and_confirm_removes_it(env, term):
    _, workspace, ctx = env
    document = _create_document(ctx, workspace, body=f"see {_token(term)}")
    link = _link(document.artifact_id, term.artifact_id)
    assert link is not None

    client = _rest_client(env)
    path = f"/api/v1/trace-links/{link.id}/"

    refused = client.delete(path)
    assert refused.status_code == 409, refused.content
    body = refused.json()["error"]
    assert body["code"] == "ANCHORS_PRESENT"
    assert body["details"] == {"count": 1}

    confirmed = client.delete(f"{path}?confirm_anchor_count=1")
    assert confirmed.status_code == 204, confirmed.content
    assert InlineAnchor.unscoped.filter(link_id=link.id).count() == 0
    assert TraceLink.unscoped.filter(id=link.id).count() == 0


@override_settings(**_JWT_OVERRIDES)
def test_rest_rejects_a_malformed_anchor_count(env, term):
    _, workspace, ctx = env
    document = _create_document(ctx, workspace, body=f"see {_token(term)}")
    link = _link(document.artifact_id, term.artifact_id)
    assert link is not None

    client = _rest_client(env)
    response = client.delete(
        f"/api/v1/trace-links/{link.id}/?confirm_anchor_count=abc"
    )
    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
