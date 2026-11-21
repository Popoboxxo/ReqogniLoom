"""R3/P7 — real pgvector round-trip through the checked target-instance restore.

Plan ``docs/plans/2026-11-21-artifact-transfer-plan.md`` §6 P7 / D17 requires a
*real* dumpdata -> gzip -> SHA-256 -> ``loaddata`` round-trip against the test
database that proves a non-null pgvector embedding (and its model provenance)
survives the checked restore byte-identically. Finding EXT-004 is the driver.

These tests deliberately exercise the real :class:`AdminRestoreService` and the
real ``loaddata`` management command -- there is no ``fake_loaddata`` stub. A
checksum corruption is therefore asserted by the *absence* of the row after the
refused restore, not by inspecting a mock call list.

Run inside the ``backend-test`` container (PostgreSQL carrying the pgvector
extension, e.g. ``pgvector/pgvector:pg16``). When a real sized pgvector column
is not available the tests skip with an explicit reason; they never silently
pass.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime

import pytest
from django.core import serializers
from django.db import connection

from admin_ops.models import BackupMetadata, BackupStatus, BackupType
from admin_ops.services import AdminRestoreService
from admin_ops.services.admin_restore_service import (
    DEFAULT_BACKUP_FORMAT_VERSION,
    RESTORE_CAPTCHA,
    BackupChecksumMismatch,
)
from admin_ops.services.paths import backup_root
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.models import Artifact, Requirement, Tenant, TraceLink, Workspace
from persistence.tenancy import TenantContext

from .conftest import active_tenant

pytestmark = pytest.mark.django_db

_EMBEDDING_MODEL_ID = f"mock:p7-roundtrip-model:{EMBEDDING_VECTOR_DIMENSIONS}"


def _require_real_pgvector() -> None:
    """Skip with a clear reason unless a real sized pgvector column exists."""
    if connection.vendor != "postgresql":
        pytest.skip("pgvector round-trip needs PostgreSQL (pgvector/pgvector:pg16)")
    declared = getattr(Requirement._meta.get_field("embedding"), "dimensions", None)
    if not isinstance(declared, int) or declared <= 0:
        pytest.skip("Requirement.embedding is not a sized pgvector VectorField")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT format_type(a.atttypid, a.atttypmod) "
            "FROM pg_attribute a "
            "WHERE a.attrelid = %s::regclass AND a.attname = 'embedding'",
            [Requirement._meta.db_table],
        )
        row = cursor.fetchone()
    column_type = row[0] if row else ""
    if not column_type or not column_type.startswith("vector"):
        pytest.skip(
            f"Requirement.embedding is not a pgvector column ({column_type!r})"
        )


def _deterministic_vector(dim: int, salt: int) -> list[float]:
    """Reproducible float vector of exactly *dim* components (synthetic data)."""
    return [round(((i * 37 + salt) % 101) / 101.0, 6) for i in range(dim)]


def _as_float_list(value: object) -> list[float]:
    """Normalise a pgvector value (numpy array, list or pgvector text) to floats.

    ``dumpdata`` serialises a VectorField through its ``value_to_string`` as a
    bracketed pgvector literal (``"[0.1,0.2]"``), while the live ORM value is a
    numpy array. Both must compare equal for a real round-trip assertion.
    """
    if isinstance(value, str):
        parsed = json.loads(value) if value.strip().startswith("[") else value
        return [float(component) for component in parsed]
    to_list = getattr(value, "tolist", None)
    raw: object = to_list() if callable(to_list) else value
    return [float(component) for component in raw]  # type: ignore[union-attr]


def _write_backup(raw: bytes) -> BackupMetadata:
    """Persist *raw* on disk with a matching checksum and a completed row."""
    digest = hashlib.sha256(raw).hexdigest()
    rel_path = f"p7-pgvec-{uuid.uuid4().hex}.json.gz"
    abs_path = os.path.join(backup_root(), rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as fh:
        fh.write(raw)
    return BackupMetadata.objects.create(
        status=BackupStatus.COMPLETED,
        backup_type=BackupType.FULL,
        file_path=rel_path,
        file_size_bytes=len(raw),
        checksum_sha256=digest,
        metadata={"format_version": DEFAULT_BACKUP_FORMAT_VERSION},
        completed_at=datetime.now(UTC),
    )


def _workspace(tenant: Tenant, name: str) -> Workspace:
    return Workspace.objects.create(
        tenant=tenant, name=name, preset={"name": "standard"}
    )


def test_pgvector_embeddings_survive_checked_restore_roundtrip(admin_ctx, tenant_a):
    """dumpdata -> gzip -> SHA-256 -> real loaddata keeps both vector columns verbatim."""
    _require_real_pgvector()
    dim = EMBEDDING_VECTOR_DIMENSIONS

    with active_tenant(tenant_a):
        workspace = _workspace(tenant_a, "P7 pgvector RT WS")
        req_artifact = Artifact.objects.create(
            tenant=tenant_a, workspace=workspace, artifact_type="Requirement"
        )
        link_artifact = Artifact.objects.create(
            tenant=tenant_a, workspace=workspace, artifact_type="Requirement"
        )
        requirement = Requirement.objects.create(
            tenant=tenant_a,
            artifact=req_artifact,
            title="P7 pgvector Roundtrip Requirement",
            description="embedding and provenance must survive the restore",
            category="functional",
            type="SyReq",
            level=1,
            uid="REQ-P7-PGVEC-1",
            embedding=_deterministic_vector(dim, salt=1),
            embedding_model=_EMBEDDING_MODEL_ID,
        )
        trace_link = TraceLink.objects.create(
            tenant=tenant_a,
            source=req_artifact,
            target=link_artifact,
            link_type="derives-from",
            embedding=_deterministic_vector(dim, salt=2),
            embedding_model=_EMBEDDING_MODEL_ID,
        )
        # Read back through pgvector's ``from_db_value`` so the "source of
        # truth" is the DB (float32) representation that dumpdata serializes.
        requirement.refresh_from_db()
        trace_link.refresh_from_db()
        source_req_vector = _as_float_list(requirement.embedding)
        source_link_vector = _as_float_list(trace_link.embedding)

        raw_json = serializers.serialize(
            "json", [req_artifact, link_artifact, requirement, trace_link]
        )
        req_id, link_id = requirement.id, trace_link.id
        req_artifact_id, link_artifact_id = req_artifact.id, link_artifact.id

    payload_objects = json.loads(raw_json)
    serialized_req = next(
        obj for obj in payload_objects if obj["model"] == "persistence.requirement"
    )
    serialized_link = next(
        obj for obj in payload_objects if obj["model"] == "persistence.tracelink"
    )
    assert _as_float_list(serialized_req["fields"]["embedding"]) == source_req_vector
    assert _as_float_list(serialized_link["fields"]["embedding"]) == source_link_vector
    assert len(_as_float_list(serialized_req["fields"]["embedding"])) == dim
    assert len(_as_float_list(serialized_link["fields"]["embedding"])) == dim
    assert serialized_req["fields"]["embedding_model"] == _EMBEDDING_MODEL_ID
    assert serialized_link["fields"]["embedding_model"] == _EMBEDDING_MODEL_ID

    payload = gzip.compress(raw_json.encode("utf-8"), mtime=0)
    backup = _write_backup(payload)

    with active_tenant(tenant_a):
        Requirement.objects.filter(pk=req_id).delete()
        TraceLink.objects.filter(pk=link_id).delete()
        Artifact.objects.filter(pk__in=[req_artifact_id, link_artifact_id]).delete()
        assert not Requirement.objects.filter(uid="REQ-P7-PGVEC-1").exists()

    result = AdminRestoreService().restore(
        admin_ctx, backup_id=backup.id, confirmation_text=RESTORE_CAPTCHA
    )

    assert result.checksum_verified is True
    assert "persistence.requirement" in result.restored_tables
    assert "persistence.tracelink" in result.restored_tables

    with active_tenant(tenant_a):
        restored_req = Requirement.objects.get(uid="REQ-P7-PGVEC-1")
        restored_link = TraceLink.objects.get(pk=link_id)
        # Vector values, dimension and provenance all survive byte-identically.
        assert _as_float_list(restored_req.embedding) == source_req_vector
        assert _as_float_list(restored_link.embedding) == source_link_vector
        assert len(_as_float_list(restored_req.embedding)) == dim
        assert len(_as_float_list(restored_link.embedding)) == dim
        assert restored_req.embedding_model == _EMBEDDING_MODEL_ID
        assert restored_link.embedding_model == _EMBEDDING_MODEL_ID
        # Re-serializing the restored rows reproduces the exact same JSON field
        # representation as the source backup -- not merely an equal numpy value.
        restored_objects = json.loads(
            serializers.serialize("json", [restored_req, restored_link])
        )
        assert (
            restored_objects[0]["fields"]["embedding"]
            == serialized_req["fields"]["embedding"]
        )
        assert (
            restored_objects[1]["fields"]["embedding"]
            == serialized_link["fields"]["embedding"]
        )
        assert (
            restored_objects[0]["fields"]["embedding_model"] == _EMBEDDING_MODEL_ID
        )
        assert (
            restored_objects[1]["fields"]["embedding_model"] == _EMBEDDING_MODEL_ID
        )


def test_pgvector_checksum_corruption_blocks_roundtrip_load(admin_ctx, tenant_a):
    """A checksum-corrupt backup is refused before loaddata can write any vector row."""
    _require_real_pgvector()
    dim = EMBEDDING_VECTOR_DIMENSIONS

    with active_tenant(tenant_a):
        workspace = _workspace(tenant_a, "P7 pgvector corrupt WS")
        artifact = Artifact.objects.create(
            tenant=tenant_a, workspace=workspace, artifact_type="Requirement"
        )
        requirement = Requirement.objects.create(
            tenant=tenant_a,
            artifact=artifact,
            title="P7 Corrupt Backup Requirement",
            description="must not be loaded from a corrupt file",
            category="functional",
            type="SyReq",
            level=1,
            uid="REQ-P7-PGVEC-CORRUPT",
            embedding=_deterministic_vector(dim, salt=3),
            embedding_model=_EMBEDDING_MODEL_ID,
        )
        raw_json = serializers.serialize("json", [artifact, requirement])
        req_id, artifact_id = requirement.id, artifact.id

    payload = gzip.compress(raw_json.encode("utf-8"), mtime=0)
    backup = _write_backup(payload)
    # Corrupt the on-disk bytes *after* the checksum was recorded.
    abs_path = os.path.join(backup_root(), backup.file_path)
    with open(abs_path, "ab") as fh:
        fh.write(b"\x00CORRUPTED")

    with active_tenant(tenant_a):
        Requirement.objects.filter(pk=req_id).delete()
        Artifact.objects.filter(pk=artifact_id).delete()
        assert not Requirement.objects.filter(uid="REQ-P7-PGVEC-CORRUPT").exists()

    with pytest.raises(BackupChecksumMismatch, match="checksum mismatch"):
        AdminRestoreService().restore(
            admin_ctx, backup_id=backup.id, confirmation_text=RESTORE_CAPTCHA
        )

    with active_tenant(tenant_a):
        assert not Requirement.objects.filter(uid="REQ-P7-PGVEC-CORRUPT").exists(), (
            "a checksum-corrupt backup must never be loaded"
        )


def test_cross_tenant_checked_restore_restores_caller_rls_context(admin_ctx, tenant_a):
    """The checked restore returns the RLS target context to the caller's tenant."""
    _require_real_pgvector()
    from auth_tenancy.models import ROLE_ADMIN, UserRole

    target = Tenant.objects.create(
        name="P7 pgvector target",
        slug=f"p7-pgvec-target-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    with active_tenant(target):
        target_ws = Workspace.objects.create(
            tenant=target, name="P7 pgvector target WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=target,
            user_id=admin_ctx.user_id,
            workspace=target_ws,
            role=ROLE_ADMIN,
        )

    # Empty fixture: no rows are loaded, so the assertion is purely about the
    # restore's finally block restoring the caller's RLS tenant context.
    backup = _write_backup(gzip.compress(b"[]", mtime=0))

    with active_tenant(tenant_a):
        assert TenantContext.get_tenant() == tenant_a.id
        # D16b: a cross-tenant restore needs an audited dry-run preview first.
        AdminRestoreService().restore(
            admin_ctx,
            backup_id=backup.id,
            confirmation_text=RESTORE_CAPTCHA,
            dry_run=True,
            target_tenant=target.id,
        )
        result = AdminRestoreService().restore(
            admin_ctx,
            backup_id=backup.id,
            confirmation_text=RESTORE_CAPTCHA,
            target_tenant=target.id,
        )
        assert TenantContext.get_tenant() == tenant_a.id, (
            "RLS context must be restored to the caller's tenant, "
            "not left armed on the target"
        )

    assert result.target_tenant == target.id
