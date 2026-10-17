"""GlossaryReferenceService tests (#1266).

Covers the token grammar, version-pinned / head-following resolution, drift
reporting, the auto-created usage trace link and the bulk upgrade-to-head
rewrite — all against real rows (no mocked ORM).
"""
from __future__ import annotations

import uuid

import pytest

from application.glossary_reference_service import (
    GlossaryReferenceService,
    build_reference_token,
    parse_references,
)
from application.glossary_service import GlossaryService
from auth_tenancy.context import AuthContext, AuthMethod
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Tenant, TraceLink, User, Workspace

pytestmark = pytest.mark.django_db


def _ctx(tenant_id, workspace_id, user_id) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace_id,
    )


def _setup(name: str):
    """Tenant + provisioned workspace + a real editor user + ctx."""
    tenant = Tenant.objects.create(name=name, slug=f"{name}-{uuid.uuid4().hex[:8]}")
    set_request_tenant(tenant.id)
    try:
        ws = Workspace.objects.create(tenant=tenant, name="ws", preset={"name": "standard"})
        user = User.objects.create(
            tenant=tenant,
            username=f"glosref-{uuid.uuid4().hex[:8]}",
            email="glosref@t.test",
        )
    finally:
        clear_request_tenant()
    provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)
    return tenant, ws, _ctx(tenant.id, ws.id, user.id)


def _make_term(ctx, workspace, term="Autopilot", definition="v1 definition"):
    set_request_tenant(ctx.tenant_id)
    try:
        return GlossaryService().create(ctx, workspace.id, term, definition)
    finally:
        clear_request_tenant()


def _bump_definition(ctx, term_id, definition):
    set_request_tenant(ctx.tenant_id)
    try:
        return GlossaryService().update(ctx, term_id, definition=definition)
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# Grammar
# ---------------------------------------------------------------------------


class TestParseReferences:
    def test_bare_and_pinned_tokens(self):
        text = (
            "see [[glossary:11111111-1111-1111-1111-111111111111]] and "
            "[[glossary:22222222-2222-2222-2222-222222222222@3]]"
        )
        parsed = parse_references(text)
        assert len(parsed) == 2
        assert parsed[0].revision is None
        assert parsed[1].revision == 3

    def test_ignores_other_syntax(self):
        assert parse_references("[[glossary:not-a-uuid]] {{glossary:x}}") == []

    def test_build_token_round_trip(self):
        uid = uuid.uuid4()
        assert parse_references(build_reference_token(uid))[0].global_uuid == uid
        assert parse_references(build_reference_token(uid, 4))[0].revision == 4


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


class TestResolveReferences:
    def test_pinned_revision_resolves_against_snapshot_and_reports_drift(self):
        tenant, ws, ctx = _setup("ref-pinned")
        dto = _make_term(ctx, ws, definition="v1 definition")
        _bump_definition(ctx, dto.id, "v2 definition")

        text = f"uses {build_reference_token(dto.artifact_id, 1)} now"
        mode, resolutions = GlossaryReferenceService().resolve_references(ctx, ws.id, text)

        assert mode == "pinned"
        assert len(resolutions) == 1
        ref = resolutions[0]
        assert ref.resolved is True
        assert ref.resolved_revision == 1
        assert ref.head_revision == 2
        assert ref.definition == "v1 definition"
        assert ref.drift is True

    def test_bare_token_resolves_to_head_without_drift(self):
        tenant, ws, ctx = _setup("ref-head")
        dto = _make_term(ctx, ws, definition="v1 definition")
        _bump_definition(ctx, dto.id, "v2 definition")

        text = f"uses {build_reference_token(dto.artifact_id)} now"
        _, resolutions = GlossaryReferenceService().resolve_references(ctx, ws.id, text)

        assert resolutions[0].resolved_revision == 2
        assert resolutions[0].definition == "v2 definition"
        assert resolutions[0].drift is False

    def test_always_head_mode_ignores_the_pin(self):
        tenant, ws, ctx = _setup("ref-always")
        dto = _make_term(ctx, ws, definition="v1 definition")
        _bump_definition(ctx, dto.id, "v2 definition")
        set_request_tenant(ctx.tenant_id)
        try:
            ws.glossary_reference_mode = "always_head"
            ws.save(update_fields=["glossary_reference_mode"])
        finally:
            clear_request_tenant()

        text = f"uses {build_reference_token(dto.artifact_id, 1)} now"
        mode, resolutions = GlossaryReferenceService().resolve_references(ctx, ws.id, text)

        assert mode == "always_head"
        assert resolutions[0].resolved_revision == 2
        assert resolutions[0].drift is False

    def test_unknown_uuid_is_reported_unresolved(self):
        tenant, ws, ctx = _setup("ref-unknown")
        text = f"ghost {build_reference_token(uuid.uuid4())}"
        _, resolutions = GlossaryReferenceService().resolve_references(ctx, ws.id, text)
        assert resolutions[0].resolved is False

    def test_duplicate_tokens_resolve_once(self):
        tenant, ws, ctx = _setup("ref-dup")
        dto = _make_term(ctx, ws)
        token = build_reference_token(dto.artifact_id, 1)
        _, resolutions = GlossaryReferenceService().resolve_references(
            ctx, ws.id, f"{token} and {token}"
        )
        assert len(resolutions) == 1

    def test_resolve_text_reports_drift_summary(self):
        tenant, ws, ctx = _setup("ref-summary")
        dto = _make_term(ctx, ws, definition="v1")
        _bump_definition(ctx, dto.id, "v2")
        payload = GlossaryReferenceService().resolve_text(
            ctx, ws.id, build_reference_token(dto.artifact_id, 1)
        )
        assert payload["has_drift"] is True
        assert payload["mode"] == "pinned"
        assert payload["references"][0]["requested_revision"] == 1


# ---------------------------------------------------------------------------
# Insertion (+ usage trace link)
# ---------------------------------------------------------------------------


class TestInsertReference:
    def _source_artifact(self, tenant, ws) -> Artifact:
        set_request_tenant(tenant.id)
        try:
            return Artifact.objects.create(
                tenant=tenant, workspace=ws, artifact_type="Requirement"
            )
        finally:
            clear_request_tenant()

    def test_insert_creates_usage_link_and_returns_pinned_token(self):
        tenant, ws, ctx = _setup("ref-insert")
        dto = _make_term(ctx, ws)
        source = self._source_artifact(tenant, ws)

        payload = GlossaryReferenceService().insert_reference(
            ctx, ws.id, source.id, dto.artifact_id
        )

        assert payload["token"] == build_reference_token(dto.artifact_id, 1)
        assert payload["link_type"] == "references"

        set_request_tenant(tenant.id)
        try:
            links = TraceLink.objects.filter(
                source_id=source.id, target_id=dto.artifact_id
            )
            assert links.count() == 1
            assert links.first().link_type == "references"
        finally:
            clear_request_tenant()

    def test_insert_is_idempotent_about_the_link(self):
        tenant, ws, ctx = _setup("ref-insert-dup")
        dto = _make_term(ctx, ws)
        source = self._source_artifact(tenant, ws)
        svc = GlossaryReferenceService()

        svc.insert_reference(ctx, ws.id, source.id, dto.artifact_id)
        svc.insert_reference(ctx, ws.id, source.id, dto.artifact_id)

        set_request_tenant(tenant.id)
        try:
            assert TraceLink.objects.filter(source_id=source.id).count() == 1
        finally:
            clear_request_tenant()

    def test_insert_in_always_head_mode_returns_bare_token(self):
        tenant, ws, ctx = _setup("ref-insert-head")
        dto = _make_term(ctx, ws)
        source = self._source_artifact(tenant, ws)
        set_request_tenant(tenant.id)
        try:
            ws.glossary_reference_mode = "always_head"
            ws.save(update_fields=["glossary_reference_mode"])
        finally:
            clear_request_tenant()

        payload = GlossaryReferenceService().insert_reference(
            ctx, ws.id, source.id, dto.artifact_id
        )
        assert payload["token"] == build_reference_token(dto.artifact_id)


# ---------------------------------------------------------------------------
# Bulk upgrade
# ---------------------------------------------------------------------------


class TestUpgradeToHead:
    def test_rewrites_only_drifted_pins(self):
        tenant, ws, ctx = _setup("ref-upgrade")
        dto = _make_term(ctx, ws, definition="v1")
        _bump_definition(ctx, dto.id, "v2")

        fresh_uid = _make_term(ctx, ws, term="Other", definition="x").artifact_id
        text = (
            f"a {build_reference_token(dto.artifact_id, 1)} "
            f"b {build_reference_token(fresh_uid, 1)} "
            f"c {build_reference_token(dto.artifact_id)}"
        )
        new_text, upgraded = GlossaryReferenceService().upgrade_text_to_head(
            ctx, ws.id, text
        )

        assert upgraded == 1
        assert build_reference_token(dto.artifact_id, 2) in new_text
        # the already-at-head pin (v1 of Other) is untouched
        assert build_reference_token(fresh_uid, 1) in new_text
        # the bare token is never rewritten
        assert new_text.count(build_reference_token(dto.artifact_id)) == 1
