"""Phase G / #1374 S3: deterministic projection, status comparison, adoption."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

import pytest

from application.base import (
    AdoptionHashMismatchError,
    PermissionDeniedError,
    ValidationError,
)
from application.document_projection_render import (
    projection_path,
    render_document,
    with_header,
)
from application.document_projection_service import DocumentProjectionService
from application.models import DomainEventOutbox
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Document, Tenant, User, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

HEX_A = "a" * 64
HEX_B = "b" * 64


def _doc(**overrides) -> SimpleNamespace:
    values = {
        "uid": "DOC-001",
        "title": "Überblick: System",
        "kind": "Spec",
        "description": "Kurzbeschreibung",
        "body": "Der Text.",
        "version": 3,
        "doc_date": None,
        "source_path": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _anchor(token: str, lifecycle: str = "active", label: str = "Begriff"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        token=token,
        target_lifecycle=lifecycle,
        target_label=label,
    )


# ---------------------------------------------------------------------------
# Renderer (pure)
# ---------------------------------------------------------------------------


def test_render_is_byte_identical_across_runs_and_input_order() -> None:
    doc = _doc()
    anchors = [_anchor("[[glossary:1]]"), _anchor("[[glossary:2]]")]
    edges = [
        {"link_type": "documents", "target_label": "Requirement aa"},
        {"link_type": "decides", "target_label": "Adr bb"},
    ]

    first = render_document(doc, anchors=anchors, edges=edges, glossary={})
    second = render_document(
        doc,
        anchors=list(reversed(anchors)),
        edges=list(reversed(edges)),
        glossary={},
    )

    assert first.content == second.content
    assert "\r" not in first.content
    assert first.sha256 == second.sha256


def test_header_carries_uid_version_state_and_content_hash() -> None:
    doc = _doc()
    projected = render_document(doc, state="Freigegeben")

    content = with_header(projected, document=doc, state="Freigegeben")

    assert "document: DOC-001" in content
    assert "version 3" in content
    assert "state Freigegeben" in content
    assert f"hash {projected.sha256}" in content
    assert content.endswith(projected.content)


def test_a_dead_anchor_becomes_plain_text_with_a_warning() -> None:
    doc = _doc(body="Siehe [[glossary:dead]].")
    dead = _anchor("[[glossary:dead]]", lifecycle="outdated", label="Altbegriff")

    projected = render_document(doc, anchors=[dead])

    assert "[[glossary:dead]]" not in projected.content
    assert "Altbegriff *(dead reference)*" in projected.content
    assert projected.warnings == ("dead reference: [[glossary:dead]]",)


def test_glossary_and_edges_are_appendix_sections_in_stable_order() -> None:
    doc = _doc()

    projected = render_document(
        doc,
        glossary={"Zebra": "Streifen", "Anker": "Halt"},
        edges=[
            {"link_type": "documents", "target_label": "Req 2"},
            {"link_type": "documents", "target_label": "Req 1"},
        ],
    )

    lines = projected.content.splitlines()
    assert "## Glossary" in lines
    assert lines.index("- **Anker** — Halt") < lines.index("- **Zebra** — Streifen")
    references = [line for line in lines if line.startswith("- `documents`")]
    assert references == [
        "- `documents` → Req 1",
        "- `documents` → Req 2",
    ]


def test_projection_path_is_confined_and_prefers_the_source_path() -> None:
    escaped = projection_path(_doc(title="../../etc/passwd", uid="DOC-1"))

    assert not escaped.startswith("/")
    assert ".." not in escaped
    assert escaped.startswith("docs/superpowers/specs/")

    sourced = projection_path(_doc(source_path="../../etc/passwd"))
    assert sourced == "etc/passwd"

    dated = projection_path(_doc(doc_date=date(2026, 1, 2)))
    assert dated.endswith("/2026-01-02-uberblick-system.md")


# ---------------------------------------------------------------------------
# Service (database)
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Projection", slug="projection-tenant")


def _user(tenant: Tenant, roles: tuple[str, ...]) -> AuthContext:
    user = User.objects.create(
        username=f"u-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        tenant=tenant,
    )
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=roles,
        auth_method="test",
    )


@pytest.fixture
def ctx(tenant) -> AuthContext:
    return _user(tenant, ("editor",))


@pytest.fixture
def workspace(tenant) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name="Projection WS", preset={"name": "standard"}
        )
    finally:
        TenantContext.clear_tenant()


def _document(tenant: Tenant, workspace: Workspace, **overrides) -> Document:
    TenantContext.set_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Document"
        )
        values = {
            "tenant": tenant,
            "workspace": workspace,
            "artifact": artifact,
            "title": "Systemspec",
            "kind": "Spec",
            "description": "Beschreibung",
            "body": "Inhalt.",
        }
        values.update(overrides)
        return Document.objects.create(**values)
    finally:
        TenantContext.clear_tenant()


def test_project_renders_the_same_bytes_twice(tenant, workspace, ctx) -> None:
    document = _document(tenant, workspace)
    service = DocumentProjectionService()

    first = service.project(document.id, ctx)
    second = service.project(document.id, ctx)

    assert first.content == second.content
    assert first.sha256 == second.sha256
    assert first.path.startswith("docs/superpowers/specs/")


def test_project_requires_a_read_role(tenant, workspace, ctx) -> None:
    document = _document(tenant, workspace)

    with pytest.raises(PermissionDeniedError):
        DocumentProjectionService().project(document.id, _user(tenant, ()))


def test_status_classifies_all_six_states(tenant, workspace, ctx) -> None:
    service = DocumentProjectionService()
    in_sync = _document(tenant, workspace, title="In sync", projected_sha256=HEX_A)
    file_changed = _document(
        tenant, workspace, title="File changed", projected_sha256=HEX_A
    )
    loom_changed = _document(
        tenant, workspace, title="Loom changed", projected_sha256=HEX_A
    )
    conflict = _document(tenant, workspace, title="Conflict", projected_sha256=HEX_A)
    missing = _document(tenant, workspace, title="Missing", projected_sha256=HEX_A)
    untracked = _document(tenant, workspace, title="Untracked")

    TenantContext.set_tenant(tenant.id)
    try:
        for document in (in_sync, file_changed, loom_changed, conflict):
            Document.objects.filter(id=document.id).update(projected_version=1)
        Document.objects.filter(id=loom_changed.id).update(version=2)
        Document.objects.filter(id=conflict.id).update(version=2)
    finally:
        TenantContext.clear_tenant()

    files = {
        projection_path(_document_view(in_sync)): HEX_A,
        projection_path(_document_view(file_changed)): HEX_B,
        projection_path(_document_view(loom_changed)): HEX_A,
        projection_path(_document_view(conflict)): HEX_B,
        projection_path(_document_view(untracked)): HEX_A,
    }

    states = {
        row.document_id: row.state
        for row in service.status(workspace.id, files, ctx)
    }

    assert states[str(in_sync.id)] == "in_sync"
    assert states[str(file_changed.id)] == "file_changed"
    assert states[str(loom_changed.id)] == "loom_changed"
    assert states[str(conflict.id)] == "conflict"
    assert states[str(missing.id)] == "missing_in_repo"
    assert states[str(untracked.id)] == "untracked_in_loom"


def _document_view(document: Document):
    """Re-read without the tenant-clearing helper (caller owns the context)."""
    return document


def test_confirm_records_the_written_hash_and_version(tenant, workspace, ctx) -> None:
    document = _document(tenant, workspace)
    service = DocumentProjectionService()

    service.confirm(document.id, HEX_A, ctx)

    TenantContext.set_tenant(tenant.id)
    try:
        document.refresh_from_db()
    finally:
        TenantContext.clear_tenant()
    assert document.projected_sha256 == HEX_A
    assert document.projected_version == document.version


def test_confirm_rejects_a_malformed_hash(tenant, workspace, ctx) -> None:
    document = _document(tenant, workspace)

    with pytest.raises(ValidationError):
        DocumentProjectionService().confirm(document.id, "nope", ctx)


def test_adopt_requires_a_matching_repository_hash(tenant, workspace, ctx) -> None:
    document = _document(
        tenant,
        workspace,
        owner_mode="repo_external",
        source_sha256=HEX_A,
    )

    with pytest.raises(AdoptionHashMismatchError):
        DocumentProjectionService().adopt(
            document.id, file_sha256=HEX_B, ctx=ctx
        )

    TenantContext.set_tenant(tenant.id)
    try:
        document.refresh_from_db()
    finally:
        TenantContext.clear_tenant()
    assert document.owner_mode == "repo_external"


def test_adopt_of_a_loom_document_is_rejected(tenant, workspace, ctx) -> None:
    document = _document(tenant, workspace)

    with pytest.raises(ValidationError, match="repo_external"):
        DocumentProjectionService().adopt(
            document.id, file_sha256=HEX_A, ctx=ctx
        )


def test_adopt_switches_ownership_and_emits_the_event(
    tenant, workspace, ctx
) -> None:
    document = _document(
        tenant,
        workspace,
        owner_mode="repo_external",
        source_sha256=HEX_A,
        source_path="docs/external/spec.md",
    )

    adopted = DocumentProjectionService().adopt(
        document.id, file_sha256=HEX_A, ctx=ctx
    )

    assert adopted.owner_mode == "loom"
    assert adopted.projection_mode == "generated"
    assert adopted.projected_sha256 == HEX_A
    TenantContext.set_tenant(tenant.id)
    try:
        assert DomainEventOutbox.objects.filter(
            event_type=DomainEventOutbox.EventType.DOCUMENT_ADOPTED.value,
            entity_id=document.id,
        ).exists()
    finally:
        TenantContext.clear_tenant()
