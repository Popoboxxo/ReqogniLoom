"""Audit-field collisions are cleared before the base-class swap.

Datenmodell-Konsolidierung Phase 2 Task 14.

Task 15 completed the move these fields were prepared for, so three assertions
here were deliberately flipped rather than deleted — they now pin the *arrival*
shape instead of the transitional one:

* ``created_by`` was asserted absent (Task 14 freed the attribute name); it is
  now the inherited ``AuditableModel.created_by`` User FK, which was the point.
* ``modified_at`` was asserted nullable (transitional, so pre-existing rows
  could be backfilled); the base class declares it NOT NULL.

``created_by_name`` and its pinned ``db_column="created_by"`` are unchanged and
still guarded below — that is the part of Task 14 that stays load-bearing.
"""
import pytest
from django.apps import apps

MODELS = ["Adr", "Risk", "Goal", "MainGoal", "Issue", "ChangeRequest"]


@pytest.mark.parametrize("model_name", MODELS)
def test_created_by_char_field_is_renamed(model_name):
    model = apps.get_model("application", model_name)
    field = model._meta.get_field("created_by_name")

    assert field.get_attname_column()[1] == "created_by"
    assert field.max_length == 255


@pytest.mark.parametrize("model_name", MODELS)
def test_created_by_is_now_the_inherited_user_fk(model_name):
    """Task 14 freed the ``created_by`` attribute; Task 15 filled it with the FK.

    The free-text actor string lives on ``created_by_name`` (asserted above),
    so the two must not collide: distinct field names, distinct columns.
    """
    model = apps.get_model("application", model_name)
    field = model._meta.get_field("created_by")

    assert field.many_to_one is True
    assert field.remote_field.model._meta.model_name == "user"
    assert field.get_attname_column()[1] == "created_by_id"
    assert model._meta.get_field("created_by_name").column == "created_by"


@pytest.mark.parametrize("model_name", MODELS)
def test_modified_at_is_not_nullable_after_the_swap(model_name):
    """``AuditableModel.modified_at`` is NOT NULL; 0022 backfilled and tightened."""
    model = apps.get_model("application", model_name)
    field = model._meta.get_field("modified_at")

    assert field.null is False
    assert field.auto_now is True


@pytest.mark.django_db
def test_modified_at_is_populated_on_create():
    from persistence.models import Tenant
    from persistence.tenancy import TenantContext

    from application.models import Adr

    # tenant_id is a real FK since Task 15, and Adr.objects is tenant-scoped.
    tenant = Tenant.objects.create(name="audit-fields", slug="audit-fields")
    TenantContext.set_tenant(tenant.id)
    row = Adr.objects.create(
        workspace_id="00000000-0000-0000-0000-000000000001",
        tenant=tenant,
        title="A",
        description="d",
    )
    row.refresh_from_db()

    assert row.modified_at is not None
