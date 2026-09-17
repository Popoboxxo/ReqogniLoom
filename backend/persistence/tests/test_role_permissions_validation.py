"""
Issue #128 — schema validation for the security-relevant ``Role.permissions``
JSON field.

``Role.permissions`` drives RBAC decisions, but the column accepted arbitrary
JSON: a typo in a key silently disabled a permission and a nested/derived
structure could not be reasoned about. These tests pin the structural contract
and — importantly — that it is enforced on ``save()``, not only via the
``full_clean()`` path (which nothing in this codebase calls for Role).
"""
from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Role, Tenant
from persistence.role_permissions import validate_role_permissions


@pytest.fixture
def tenant(db):
    t = Tenant.objects.create(name="Perm T", slug="perm-t", is_active=True)
    set_request_tenant(t.id)
    try:
        yield t
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# Pure validator
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"requirement.create": True},
        {"requirement.create": True, "requirement.delete": False},
        {"artifact.read": ["own", "team"]},
        {"mixed": True, "scoped": ["own"]},
    ],
)
def test_valid_permission_maps_are_accepted(value):
    assert validate_role_permissions(value) == value


def test_none_is_normalized_to_empty_map():
    assert validate_role_permissions(None) == {}


@pytest.mark.parametrize(
    "value",
    [
        [],                                   # top level must be a map
        "admin",
        42,
        {"": True},                           # empty key
        {" spaced ": True},                   # untrimmed key
        {1: True},                            # non-string key
        {"a": {"nested": True}},              # nested object
        {"a": [{"nested": True}]},            # non-string list entry
        {"a": [1, 2]},
        {"a": None},                          # ambiguous: neither grant nor deny
        {"a": "yes"},                         # string is not a decision
        {"a": 1},                             # int is not a decision
    ],
)
def test_invalid_permission_structures_are_rejected(value):
    with pytest.raises(ValidationError):
        validate_role_permissions(value)


def test_key_length_is_bounded():
    with pytest.raises(ValidationError):
        validate_role_permissions({"x" * 200: True})


def test_permission_count_is_bounded():
    with pytest.raises(ValidationError):
        validate_role_permissions({f"perm.{i}": True for i in range(500)})


# ---------------------------------------------------------------------------
# Enforcement on the model — the part that actually protects RBAC data
# ---------------------------------------------------------------------------


def test_role_save_rejects_malformed_permissions(tenant):
    """A malicious/malformed structure must not reach the database."""
    role = Role(tenant=tenant, name="broken", permissions={"a": {"nested": True}})

    with pytest.raises(ValidationError):
        role.save()

    assert not Role.objects.filter(name="broken").exists()


def test_role_save_accepts_valid_permissions(tenant):
    role = Role.objects.create(
        tenant=tenant, name="editor", permissions={"requirement.create": True}
    )
    role.refresh_from_db()
    assert role.permissions == {"requirement.create": True}


def test_role_update_is_validated_too(tenant):
    role = Role.objects.create(tenant=tenant, name="editor2", permissions={})
    role.permissions = {"bad": [{"x": 1}]}

    with pytest.raises(ValidationError):
        role.save()

    role.refresh_from_db()
    assert role.permissions == {}


def test_default_role_permissions_remain_creatable(tenant):
    """The model default ({}) must still round-trip — no regression for callers
    that create a Role without touching permissions."""
    role = Role.objects.create(tenant=tenant, name="plain")
    assert role.permissions == {}
