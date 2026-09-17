"""
Tests for the (workspace, uid) DB-level UniqueConstraint on Requirement
(#133).

``uid`` used to be enforced only at the application layer
(``RequirementService._assert_uid_unique_in_workspace``, a check-then-insert
that is race-prone under concurrent creates). These tests exercise the raw
ORM/DB layer directly — bypassing the service's pre-check entirely — to prove
the constraint itself, not just the friendly application-level error, closes
the race.
"""
from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from persistence import models as m
from persistence.tests.conftest import active_tenant

pytestmark = pytest.mark.django_db


def _make_requirement(tenant, workspace, *, uid, title="Req"):
    artifact = m.Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    return m.Requirement.objects.create(
        tenant=tenant, artifact=artifact, workspace=workspace, title=title, uid=uid
    )


class TestRequirementUidWorkspaceConstraint:
    def test_duplicate_uid_same_workspace_raises_integrity_error(
        self, tenant_a, workspace_a
    ):
        """A second Requirement.objects.create() with the same (workspace, uid)
        raises IntegrityError even when the application-level pre-check is
        bypassed entirely — proving the DB constraint, not just the service's
        check-then-insert, is the race-free authority."""
        with active_tenant(tenant_a):
            _make_requirement(tenant_a, workspace_a, uid="REQ-001")

            with pytest.raises(IntegrityError):
                with transaction.atomic():
                    _make_requirement(tenant_a, workspace_a, uid="REQ-001")

    def test_duplicate_uid_different_workspace_is_allowed(self, tenant_a, workspace_a):
        """Cross-workspace duplication stays legal (ReqIF import legitimately
        copies identifiers across workspaces of the same tenant, see
        application/tests/test_reqif_import_service.py::
        TestReqifImportUpsertCollisions)."""
        with active_tenant(tenant_a):
            other_workspace = m.Workspace.objects.create(
                tenant=tenant_a, name="WS-A-2"
            )
            req1 = _make_requirement(tenant_a, workspace_a, uid="REQ-001")
            req2 = _make_requirement(tenant_a, other_workspace, uid="REQ-001")

        assert req1.uid == req2.uid == "REQ-001"
        assert req1.workspace_id != req2.workspace_id

    def test_null_and_blank_uid_never_collide(self, tenant_a, workspace_a):
        """The constraint is partial (uid IS NOT NULL AND uid != '') — most
        requirements never get an explicit uid, so many NULL/blank rows in
        the same workspace must not collide with each other."""
        with active_tenant(tenant_a):
            _make_requirement(tenant_a, workspace_a, uid=None, title="A")
            _make_requirement(tenant_a, workspace_a, uid=None, title="B")
            _make_requirement(tenant_a, workspace_a, uid="", title="C")
            _make_requirement(tenant_a, workspace_a, uid="", title="D")

        assert m.Requirement.unscoped.filter(workspace=workspace_a).count() == 4
