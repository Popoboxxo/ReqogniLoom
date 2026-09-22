"""
ARCH-L1-011 AuthAndTenancy — seed_demo management command tests (REQ-L1-010).

Verifies the demo seed is idempotent and provisions a working admin login.
"""
from __future__ import annotations

import json

import pytest
from django.core.management import call_command

from attribute_definitions.models import (
    GlobalAttributeDefinition,
    WorkspaceAttributeDefinition,
)
from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition


def _seeded_counts(tenant_id) -> dict[str, int]:
    """Row counts for every entity ``seed_demo`` provisions.

    Covers persistence rows (tenant/workspace/user/role) AND the definition rows
    the command seeds (workflow + attribute definitions). Tenant-scoped models
    are counted under an active tenant context (``objects`` is tenant-filtered).
    """
    set_request_tenant(tenant_id)
    try:
        admin = User.objects.get(username="admin")
        return {
            "tenants": Tenant.objects.filter(slug="demo").count(),
            "users": User.objects.filter(username="admin").count(),
            "workspaces": Workspace.objects.filter(name="Demo Workspace").count(),
            "user_roles": UserRole.objects.filter(
                user=admin, role=ROLE_ADMIN
            ).count(),
            "workflow_engine_definitions": WorkflowEngineDefinition.objects.count(),
            "global_workflow_definitions": GlobalWorkflowDefinition.objects.count(),
            "global_attribute_definitions": GlobalAttributeDefinition.objects.count(),
            "workspace_attribute_definitions": (
                WorkspaceAttributeDefinition.objects.count()
            ),
        }
    finally:
        clear_request_tenant()


def _canonical(value) -> str:
    """Stable, key-order-insensitive serialization of a JSON-ish value."""
    return json.dumps(value, sort_keys=True, default=str)


def _seeded_content_signature(tenant_id, workspace_id) -> dict:
    """Canonical CONTENT signature of every definition ``seed_demo`` seeds.

    Row counts alone cannot prove "run twice -> identical end state": a re-run
    that rewrote a definition in place would leave the counts unchanged and slip
    through. This captures the canonical content instead:

    * ``GlobalAttributeDefinition`` — ``definition_json`` + ``version`` per
      ``(item_type, preset)``.
    * ``WorkspaceAttributeDefinition`` — ``definition_json`` + ``is_customized``
      + ``version`` per ``(workspace_id, item_type)``. Empty on a fresh tenant
      today (``GlobalAttributeDefinitionStore.initialize`` creates globals only),
      but included so the net stays complete if materialization ever changes.
    * ``WorkflowEngineDefinition`` — the ``states`` / ``transitions`` lists per
      ``item_type`` for the seeded workspace.
    """
    set_request_tenant(tenant_id)
    try:
        return {
            "global_attribute_definitions": {
                (obj.item_type, obj.preset): {
                    "definition_json": _canonical(obj.definition_json),
                    "version": obj.version,
                }
                for obj in GlobalAttributeDefinition.objects.order_by(
                    "item_type", "preset"
                )
            },
            "workspace_attribute_definitions": {
                (str(obj.workspace_id), obj.item_type): {
                    "definition_json": _canonical(obj.definition_json),
                    "is_customized": obj.is_customized,
                    "version": obj.version,
                }
                for obj in WorkspaceAttributeDefinition.objects.order_by(
                    "workspace_id", "item_type"
                )
            },
            "workflow_engine_definitions": {
                obj.item_type: {
                    "states": _canonical(obj.workflow_json.get("states")),
                    "transitions": _canonical(obj.workflow_json.get("transitions")),
                }
                for obj in WorkflowEngineDefinition.objects.filter(
                    workspace_id=workspace_id
                ).order_by("item_type")
            },
        }
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_seed_demo_creates_admin_and_is_idempotent():
    call_command("seed_demo")

    assert Tenant.objects.filter(slug="demo").count() == 1
    assert User.objects.filter(username="admin").count() == 1

    tenant = Tenant.objects.get(slug="demo")
    set_request_tenant(tenant.id)
    try:
        assert Workspace.objects.filter(name="Demo Workspace").count() == 1
        workspace = Workspace.objects.get(name="Demo Workspace")
        admin = User.objects.get(username="admin")
        assert UserRole.objects.filter(user=admin, role=ROLE_ADMIN).count() == 1
    finally:
        clear_request_tenant()

    # Snapshot the COMPLETE seeded end state after the first run: row counts
    # AND the canonical content of every seeded definition.
    first_counts = _seeded_counts(tenant.id)
    assert first_counts["workflow_engine_definitions"] >= 1
    assert first_counts["global_attribute_definitions"] >= 1

    first_signature = _seeded_content_signature(tenant.id, workspace.id)
    assert first_signature["global_attribute_definitions"]
    assert first_signature["workflow_engine_definitions"]

    call_command("seed_demo")  # second run must not duplicate anything

    # ... and assert an IDENTICAL end state: same counts AND byte-identical
    # content (a re-run that rewrote a definition in place would fail here even
    # though the row counts stayed the same).
    assert _seeded_counts(tenant.id) == first_counts
    assert _seeded_content_signature(tenant.id, workspace.id) == first_signature


@pytest.mark.django_db
def test_seed_demo_bootstraps_attribute_definitions():
    """#29: seed_demo must seed the tenant's global attribute definitions.

    A database populated only via ``seed_demo`` previously had zero
    ``GlobalAttributeDefinition`` rows, so the custom-fields/attribute feature
    rendered empty. ``application.self_init`` already bootstrapped them;
    ``seed_demo`` now reuses the same shared helper.
    """
    call_command("seed_demo")

    tenant = Tenant.objects.get(slug="demo")
    set_request_tenant(tenant.id)
    try:
        assert (
            GlobalAttributeDefinition.objects.filter(
                tenant_id=tenant.id
            ).count()
            >= 1
        )
        # The gap is only truly closed if a real, populated definition exists
        # for a key the artifact forms actually resolve.
        requirement = GlobalAttributeDefinition.objects.filter(
            tenant_id=tenant.id, item_type="Requirement", preset="standard"
        ).first()
        assert requirement is not None
        assert requirement.definition_json.get("attributes")
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_seed_demo_initializes_workflow_definitions():
    """#41: seed_demo left workflow definitions empty (states=[], transitions=[],
    initialized=True) until a separate POST /workflows/definition/initialize/
    per entity type. Same fix application.self_init.run_self_init() already
    applies after its own provision_admin() call."""
    from auth_tenancy.provisioning import DEFAULT_WORKSPACE_ID
    from workflow.services import get_definition

    call_command("seed_demo")

    set_request_tenant(Tenant.objects.get(slug="demo").id)
    try:
        # Raises WorkflowDefinitionError if unconfigured -- the bug this
        # regression guards against.
        definition = get_definition(
            workspace_id=DEFAULT_WORKSPACE_ID, item_type="Requirement"
        )
        assert definition.states, "Requirement workflow has no states"
        assert definition.transitions, "Requirement workflow has no transitions"
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_seed_demo_admin_password_is_usable(monkeypatch):
    # Default password when no admin-password env var is set.
    monkeypatch.delenv("SYSTEM_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_ADMIN_PASSWORD", raising=False)
    call_command("seed_demo")
    admin = User.objects.get(username="admin")
    assert admin.check_password("admin12345") is True
    assert admin.is_active is True


@pytest.mark.django_db
def test_seed_demo_is_create_only_by_default(monkeypatch):
    """A second seed_demo run must not overwrite a changed password."""
    monkeypatch.delenv("SYSTEM_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_ADMIN_PASSWORD", raising=False)
    call_command("seed_demo")

    admin = User.objects.get(username="admin")
    admin.set_password("changed-via-ui")
    admin.save(update_fields=["password", "modified_at"])

    call_command("seed_demo")  # default is create-only

    admin.refresh_from_db()
    assert admin.check_password("changed-via-ui") is True


@pytest.mark.django_db
def test_seed_demo_reset_password_flag_reapplies(monkeypatch):
    """--reset-password re-applies the demo password on an existing user."""
    monkeypatch.delenv("SYSTEM_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_ADMIN_PASSWORD", raising=False)
    call_command("seed_demo")

    admin = User.objects.get(username="admin")
    admin.set_password("changed-via-ui")
    admin.save(update_fields=["password", "modified_at"])

    call_command("seed_demo", "--reset-password")

    admin.refresh_from_db()
    assert admin.check_password("admin12345") is True
