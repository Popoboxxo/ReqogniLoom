"""``UserTableViewState`` / ``SavedView`` — models and RLS (Tabellenansicht S3, Task 3.1).

What is pinned here, and why it is load-bearing:

* **Defaults.** A new saved view is ``private``; both tables start with
  independent, non-shared JSON containers (a mutable class-level default would
  let one row's edit leak into the next).
* **Uniqueness.** One state row per ``(user, workspace, item_type)``; one named
  view per ``(workspace, item_type, owner)`` — two users may both keep a view
  called "Offene Anforderungen".
* **Tenant isolation twice.** The model guard rejects a workspace of another
  tenant, and PostgreSQL RLS is asserted as the least-privilege app role (the
  pytest session connects as superuser and would bypass every policy).
"""
from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection

from persistence.db_roles import APP_DB_ROLE
from persistence.models import SavedView, UserTableViewState, User, Workspace
from persistence.tests.conftest import active_tenant

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


def _user(tenant, slug: str) -> User:
    with active_tenant(tenant):
        return User.objects.create(
            tenant=tenant, username=f"u-{slug}", email=f"{slug}@example.com"
        )


def _view(tenant, workspace, owner, **overrides) -> SavedView:
    payload = {
        "tenant": tenant,
        "workspace": workspace,
        "owner": owner,
        "item_type": "Requirement",
        "name": "Offene Anforderungen",
    }
    payload.update(overrides)
    with active_tenant(tenant):
        return SavedView.objects.create(**payload)


def _state(tenant, workspace, user, **overrides) -> UserTableViewState:
    payload = {
        "tenant": tenant,
        "workspace": workspace,
        "user": user,
        "item_type": "Requirement",
    }
    payload.update(overrides)
    with active_tenant(tenant):
        return UserTableViewState.objects.create(**payload)


# ---------------------------------------------------------------------------
# Defaults and uniqueness
# ---------------------------------------------------------------------------


def test_saved_view_defaults_private(tenant_a, workspace_a):
    owner = _user(tenant_a, "owner")
    view = _view(tenant_a, workspace_a, owner)

    assert view.visibility == "private"
    assert view.columns == []
    assert view.filters == {}
    assert view.sort == []
    assert view.version == 1


def test_json_defaults_are_independent_instances(tenant_a, workspace_a):
    owner = _user(tenant_a, "owner")
    first = _view(tenant_a, workspace_a, owner, name="A")
    second = _view(tenant_a, workspace_a, owner, name="B")

    first.columns.append({"field": "title", "order": 0})
    first.filters["title"] = {"op": "contains", "value": "x"}
    assert second.columns == []
    assert second.filters == {}


def test_unique_name_per_owner_workspace_type(tenant_a, workspace_a):
    owner = _user(tenant_a, "owner")
    other = _user(tenant_a, "other")
    _view(tenant_a, workspace_a, owner)

    with pytest.raises(IntegrityError):
        _view(tenant_a, workspace_a, owner)

    # Same name, different owner → allowed, and so is another item type.
    _view(tenant_a, workspace_a, other)
    _view(tenant_a, workspace_a, owner, item_type="TestCase")


def test_state_unique_per_user_workspace_type(tenant_a, workspace_a):
    user = _user(tenant_a, "owner")
    _state(tenant_a, workspace_a, user)

    with pytest.raises(IntegrityError):
        _state(tenant_a, workspace_a, user)


def test_state_is_per_user(tenant_a, workspace_a):
    first = _user(tenant_a, "first")
    second = _user(tenant_a, "second")
    _state(tenant_a, workspace_a, first, columns=[{"field": "title", "order": 0}])
    second_state = _state(tenant_a, workspace_a, second)

    assert second_state.columns == []


# ---------------------------------------------------------------------------
# Tenant guard (model level)
# ---------------------------------------------------------------------------


def test_saved_view_rejects_a_workspace_of_another_tenant(
    tenant_a, tenant_b, workspace_b
):
    owner = _user(tenant_a, "owner")
    with active_tenant(tenant_a), pytest.raises(ValidationError) as excinfo:
        SavedView.objects.create(
            tenant=tenant_a,
            workspace=workspace_b,
            owner=owner,
            item_type="Requirement",
            name="cross-tenant",
        )

    assert "workspace" in excinfo.value.message_dict


def test_state_rejects_a_workspace_of_another_tenant(
    tenant_a, tenant_b, workspace_b
):
    user = _user(tenant_a, "owner")
    with active_tenant(tenant_a), pytest.raises(ValidationError) as excinfo:
        UserTableViewState.objects.create(
            tenant=tenant_a,
            workspace=workspace_b,
            user=user,
            item_type="Requirement",
        )

    assert "workspace" in excinfo.value.message_dict


def test_workspace_cascade_deletes_both_rows(tenant_a, workspace_a):
    owner = _user(tenant_a, "owner")
    view = _view(tenant_a, workspace_a, owner)
    state = _state(tenant_a, workspace_a, owner)

    Workspace.unscoped.get(pk=workspace_a.pk).delete()

    assert not SavedView.unscoped.filter(pk=view.pk).exists()
    assert not UserTableViewState.unscoped.filter(pk=state.pk).exists()


# ---------------------------------------------------------------------------
# RLS
# ---------------------------------------------------------------------------


@_pg_only
@pytest.mark.parametrize(
    "table", ["pl_user_table_view_state", "pl_saved_view"]
)
def test_tables_have_rls_policy(table: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT policyname FROM pg_policies WHERE tablename = %s", [table]
        )
        policies = {row[0] for row in cursor.fetchall()}

        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = %s",
            [table],
        )
        row = cursor.fetchone()

    assert f"{table}_tenant_isolation" in policies
    assert row is not None and row[0] and row[1], (
        "ENABLE + FORCE ROW LEVEL SECURITY missing"
    )


def _visible_ids(sql: str, params=None) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return {str(row[0]) for row in cursor.fetchall()}


@_pg_only
def test_rls_isolates_tenants(tenant_a, tenant_b, workspace_a, workspace_b):
    """As the app role: each armed tenant sees exactly its own rows."""
    owner_a = _user(tenant_a, "a")
    owner_b = _user(tenant_b, "b")
    view_a = _view(tenant_a, workspace_a, owner_a)
    view_b = _view(tenant_b, workspace_b, owner_b)
    state_a = _state(tenant_a, workspace_a, owner_a)
    state_b = _state(tenant_b, workspace_b, owner_b)

    try:
        with connection.cursor() as cursor:
            cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')

            unarmed_views = _visible_ids("SELECT id FROM pl_saved_view")
            unarmed_states = _visible_ids("SELECT id FROM pl_user_table_view_state")

            cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
            seen_a_views = _visible_ids("SELECT id FROM pl_saved_view")
            seen_a_states = _visible_ids("SELECT id FROM pl_user_table_view_state")

            cursor.execute("SET app.current_tenant = %s", [str(tenant_b.id)])
            seen_b_views = _visible_ids("SELECT id FROM pl_saved_view")
            seen_b_states = _visible_ids("SELECT id FROM pl_user_table_view_state")
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET app.current_tenant")
            cursor.execute("RESET ROLE")

    assert unarmed_views == set(), "policy is not fail-closed (views)"
    assert unarmed_states == set(), "policy is not fail-closed (state)"
    assert seen_a_views == {str(view_a.id)}
    assert seen_b_views == {str(view_b.id)}
    assert seen_a_states == {str(state_a.id)}
    assert seen_b_states == {str(state_b.id)}


@_pg_only
def test_rls_rejects_a_foreign_tenant_write(tenant_a, tenant_b, workspace_b):
    """WITH CHECK half: tenant A may not write a row stamped for tenant B."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
            cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
            cursor.execute(
                "INSERT INTO pl_saved_view "
                "(id, created_at, modified_at, version, tenant_id, workspace_id, "
                " owner_id, item_type, name, columns, filters, sort, visibility) "
                "VALUES (%s, now(), now(), 1, %s, %s, %s, 'Requirement', 'leak', "
                "'[]', '{}', '[]', 'private')",
                [
                    str(uuid.uuid4()),
                    str(tenant_b.id),
                    str(workspace_b.id),
                    str(uuid.uuid4()),
                ],
            )
    except Exception as exc:  # noqa: BLE001 — the policy must raise
        raised = exc
    else:  # pragma: no cover - only on a policy regression
        raised = None
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET app.current_tenant")
            cursor.execute("RESET ROLE")

    assert raised is not None, "a cross-tenant INSERT was not rejected"
    assert "row-level security" in str(raised).lower()
