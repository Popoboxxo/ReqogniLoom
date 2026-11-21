"""P4 (D2/D3/D5/D6) import semantics — service-level contract tests.

Covers the additive ``ImportService`` parameters that the artifact-transfer
plan introduced in P4:

* ``dry_run`` — full pipeline executes, final commit is withheld (D5);
* ``conflict_policy`` — ``version-guard`` (default), ``update``, and the two
  optional variants ``skip`` / ``error`` (D2);
* ``reconcile_status`` — rows absent from the source are soft-marked, never
  deleted (D3/D3b), carrying ``not_in_source`` / ``not_in_source_status``.

These are real-DB tests: the natural-key dedupe, the version comparison and
the reconciliation all run real ORM queries. Run via ``backend-test``.

NOTE (hand-off): ``CONFLICT_SKIP`` / ``CONFLICT_ERROR`` are declared in
``import_service.VALID_CONFLICT_POLICIES`` but are not yet branched on in
``_import_parsed``; they currently behave like ``version-guard``. The two
tests pin their intended D2 semantics so the
suite stays green today and turns into a hard failure (XPASS) the moment the
service implements them — at which point the marker must be removed.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from application.base import ValidationError
from application.import_service import (
    CONFLICT_ERROR,
    CONFLICT_SKIP,
    CONFLICT_UPDATE,
    CONFLICT_VERSION_GUARD,
    NOT_IN_SOURCE_FIELD,
    NOT_IN_SOURCE_STATUS_FIELD,
    ImportService,
)
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, Workspace

pytestmark = pytest.mark.django_db


def _ctx(tenant_id, roles=("editor",)):
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = uuid.uuid4()
    ctx.active_roles = roles
    ctx.has_role = lambda role: role in ctx.active_roles
    return ctx


@pytest.fixture(autouse=True)
def _clear_ctx():
    clear_request_tenant()
    yield
    clear_request_tenant()


@pytest.fixture
def env():
    tenant = Tenant.objects.create(
        name="P4-T", slug=f"p4-{uuid.uuid4().hex[:8]}", is_active=True
    )
    set_request_tenant(tenant.id)
    workspace = Workspace.objects.create(
        tenant=tenant, name="P4 WS", preset={"name": "standard"}
    )
    yield {
        "tenant": tenant,
        "workspace": workspace,
        "ctx": _ctx(tenant.id, ("editor", "admin")),
    }
    clear_request_tenant()


def _seed(workspace, *, title, uid, version=1, description="seeded"):
    artifact = Artifact.objects.create(
        tenant=workspace.tenant,
        workspace=workspace,
        artifact_type="Requirement",
    )
    return Requirement.objects.create(
        tenant=workspace.tenant,
        artifact=artifact,
        title=title,
        description=description,
        category="functional",
        type="SyReq",
        level=1,
        uid=uid,
        version=version,
    )


def _csv(*rows):
    """Build a Requirement CSV; each row is a mapping of column -> value."""
    columns = list(dict.fromkeys(key for row in rows for key in row))
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join(str(row.get(column, "")) for column in columns))
    return "\n".join(lines) + "\n"


def _run(env, csv_text, **kwargs):
    return ImportService().import_csv(
        csv_text, "Requirement", env["workspace"].id, env["ctx"], **kwargs
    )


def _stored(workspace, uid):
    return Requirement.objects.get(uid=uid, artifact__workspace=workspace)


# ---------- D5: dry-run ----------


def test_dry_run_reports_import_without_persisting(env):
    result = _run(
        env,
        _csv({"uid": "REQ-P4-DRY-1", "title": "Dry Row", "description": "body"}),
        dry_run=True,
    )

    assert result.success, result.errors
    assert result.dry_run is True
    assert result.imported_count == 1
    assert not Requirement.objects.filter(
        uid="REQ-P4-DRY-1", artifact__workspace=env["workspace"]
    ).exists()


def test_dry_run_reports_conflicts_without_writing(env):
    _seed(env["workspace"], title="Seeded", uid="REQ-P4-DRY-2", version=7)

    result = _run(
        env,
        _csv(
            {
                "uid": "REQ-P4-DRY-2",
                "title": "Changed",
                "description": "body",
                "version": "3",
            }
        ),
        dry_run=True,
    )

    assert result.success is False
    assert result.dry_run is True
    assert any(c["cause"]["code"] == "VERSION_CONFLICT" for c in result.conflicts)
    stored = _stored(env["workspace"], "REQ-P4-DRY-2")
    assert stored.title == "Seeded"
    assert stored.version == 7


# ---------- D2: conflict policies ----------


def test_version_guard_rejects_divergent_version(env):
    _seed(env["workspace"], title="Seeded", uid="REQ-P4-VG-1", version=7)

    result = _run(
        env,
        _csv(
            {
                "uid": "REQ-P4-VG-1",
                "title": "Overwrite Attempt",
                "description": "body",
                "version": "3",
            }
        ),
        conflict_policy=CONFLICT_VERSION_GUARD,
    )

    assert result.success is False
    assert result.failed_count == 1
    assert any(c["cause"]["code"] == "VERSION_CONFLICT" for c in result.conflicts)
    stored = _stored(env["workspace"], "REQ-P4-VG-1")
    assert stored.title == "Seeded"
    assert stored.version == 7


def test_version_guard_accepts_matching_version_as_duplicate(env):
    _seed(env["workspace"], title="Seeded", uid="REQ-P4-VG-2", version=4)

    result = _run(
        env,
        _csv(
            {
                "uid": "REQ-P4-VG-2",
                "title": "Seeded",
                "description": "body",
                "version": "4",
            }
        ),
        conflict_policy=CONFLICT_VERSION_GUARD,
    )

    # A matching version is a neutral no-op (DUPLICATE), not a failure.
    assert result.success is True
    assert result.skipped_count == 1
    assert result.failed_count == 0


def test_update_policy_applies_exported_fields_authoritatively(env):
    _seed(env["workspace"], title="Seeded", uid="REQ-P4-UPD-1", version=1)

    result = _run(
        env,
        _csv(
            {
                "uid": "REQ-P4-UPD-1",
                "title": "Authoritative Title",
                "description": "new body",
                "version": "9",
            }
        ),
        conflict_policy=CONFLICT_UPDATE,
    )

    assert result.success, result.errors
    assert result.updated_count == 1
    stored = _stored(env["workspace"], "REQ-P4-UPD-1")
    assert stored.title == "Authoritative Title"
    assert stored.description == "new body"
    assert stored.version == 9


def test_skip_policy_skips_conflicting_row_without_failure(env):
    _seed(env["workspace"], title="Seeded", uid="REQ-P4-SKIP-1", version=7)

    result = _run(
        env,
        _csv(
            {
                "uid": "REQ-P4-SKIP-1",
                "title": "Changed",
                "description": "body",
                "version": "3",
            }
        ),
        conflict_policy=CONFLICT_SKIP,
    )

    assert result.success is True
    assert result.skipped_count == 1
    assert result.failed_count == 0
    assert _stored(env["workspace"], "REQ-P4-SKIP-1").title == "Seeded"


def test_error_policy_rejects_whole_batch_on_conflict(env):
    _seed(env["workspace"], title="Seeded", uid="REQ-P4-ERR-1", version=7)

    result = _run(
        env,
        _csv(
            {
                "uid": "REQ-P4-ERR-1",
                "title": "Changed",
                "description": "body",
                "version": "3",
            },
            {"uid": "REQ-P4-ERR-2", "title": "Fresh", "description": "body"},
        ),
        conflict_policy=CONFLICT_ERROR,
    )

    assert result.success is False
    assert result.imported_count == 0
    assert any(c["cause"]["code"] == "VERSION_CONFLICT" for c in result.conflicts)


def test_invalid_conflict_policy_raises_validation_error(env):
    with pytest.raises(ValidationError, match="Unsupported conflict_policy"):
        _run(
            env,
            _csv({"uid": "REQ-P4-INV-1", "title": "Fresh"}),
            conflict_policy="banana",
        )


# ---------- D3/D3b: reconcile_status / not_in_source ----------


def test_reconcile_status_soft_marks_absent_rows_without_deleting(env):
    _seed(env["workspace"], title="Keep", uid="REQ-P4-KEEP", version=1)
    _seed(env["workspace"], title="Gone", uid="REQ-P4-GONE", version=1)

    result = _run(
        env,
        _csv({"uid": "REQ-P4-KEEP", "title": "Keep", "description": "kept"}),
        reconcile_status=True,
    )

    assert result.success, result.errors
    assert result.reconciled_count == 1

    gone = _stored(env["workspace"], "REQ-P4-GONE")
    custom = dict(gone.artifact.custom_fields or {})
    assert custom.get(NOT_IN_SOURCE_FIELD) is True
    assert custom.get(NOT_IN_SOURCE_STATUS_FIELD) == "outdated"

    keep = _stored(env["workspace"], "REQ-P4-KEEP")
    assert dict(keep.artifact.custom_fields or {}).get(NOT_IN_SOURCE_FIELD) is not True


def test_reconcile_status_is_opt_in(env):
    _seed(env["workspace"], title="Gone", uid="REQ-P4-NOREC", version=1)

    _run(
        env,
        _csv({"uid": "REQ-P4-FRESH", "title": "Fresh", "description": "body"}),
    )

    gone = _stored(env["workspace"], "REQ-P4-NOREC")
    assert dict(gone.artifact.custom_fields or {}).get(NOT_IN_SOURCE_FIELD) is not True


def test_reconcile_status_is_idempotent(env):
    _seed(env["workspace"], title="Gone", uid="REQ-P4-IDEMP", version=1)
    csv_text = _csv({"uid": "REQ-P4-FRESH2", "title": "Fresh", "description": "body"})

    first = _run(env, csv_text, reconcile_status=True)
    second = _run(env, csv_text, reconcile_status=True)

    assert first.reconciled_count == 1
    # Already-marked rows are skipped on the second pass (idempotent: no new
    # state change, and the report says so).
    assert second.reconciled_count == 0


def test_reconcile_status_under_dry_run_rolls_back_marks(env):
    _seed(env["workspace"], title="Gone", uid="REQ-P4-DRYREC", version=1)

    result = _run(
        env,
        _csv({"uid": "REQ-P4-FRESH3", "title": "Fresh", "description": "body"}),
        dry_run=True,
        reconcile_status=True,
    )

    assert result.success, result.errors
    assert result.dry_run is True
    # The reconciliation really ran (exact report) but its write was rolled back.
    gone = _stored(env["workspace"], "REQ-P4-DRYREC")
    assert dict(gone.artifact.custom_fields or {}).get(NOT_IN_SOURCE_FIELD) is not True


# ---------- envelope ----------


def test_result_envelope_exposes_p4_fields(env):
    result = _run(
        env,
        _csv({"uid": "REQ-P4-ENV", "title": "Fresh", "description": "body"}),
        dry_run=True,
    )

    body = result.to_dict()
    assert body["dry_run"] is True
    assert body["conflicts"] == []
    assert body["updated_count"] == 0
    assert body["reconciled_count"] == 0
    assert set(("succeeded", "skipped", "failed", "total")) <= set(body["counts"])
