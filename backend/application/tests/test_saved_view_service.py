"""``SavedViewService`` / ``TableViewStateService`` (Tabellenansicht S3, Task 3.2).

Pins the service contract directly (no HTTP):

* list visibility (own + workspace-wide, never another user's private view),
* owner/admin mutation rights and the 404-not-403 rule for a private view,
* DSL validation at write time (unknown field → ``ValidationError``),
* optimistic locking on ``PATCH``,
* ``apply`` returning filtered/sorted rows and the **fail-soft** stale path
  (empty rows + one warning, never an exception — plan Review Focus 4),
* the per-user state upsert, its caps, and the tenant fence.

The filter DSL itself is exercised at the edges: ``in`` with an empty list
matches nothing, ``contains`` is literal for ``%``/``_``, an unparsable date is
a 400 and an oversized ``in`` list is refused.
"""
from __future__ import annotations

import pytest

from application.base import (
    NotFoundError,
    OptimisticLockError,
    PermissionDeniedError,
    ValidationError,
)
from application.saved_view_service import (
    MAX_STATE_BYTES,
    SavedViewService,
    TableViewStateService,
)
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import (
    Artifact,
    Requirement,
    SavedView,
    Tenant,
    User,
    UserTableViewState,
    Workspace,
)
from persistence.tenancy import TenantContext
from persistence.tests.conftest import active_tenant


def _ctx(
    tenant: Tenant,
    user: User,
    *,
    roles: tuple[str, ...] = ("editor",),
) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _provision(slug: str) -> dict:
    tenant = Tenant.objects.create(name=f"t-{slug}", slug=f"t-{slug}")
    TenantContext.set_tenant(tenant.id)
    user = User.objects.create(
        tenant=tenant, username=f"user-{slug}", email=f"{slug}@example.com"
    )
    other = User.objects.create(
        tenant=tenant, username=f"other-{slug}", email=f"other-{slug}@example.com"
    )
    workspace = Workspace.objects.create(tenant=tenant, name=f"ws-{slug}")
    return {
        "tenant": tenant,
        "user": user,
        "other": other,
        "workspace": workspace,
        "ctx": _ctx(tenant, user),
        "other_ctx": _ctx(tenant, other),
        "admin_ctx": _ctx(tenant, other, roles=("admin",)),
    }


@pytest.fixture
def env(db):
    data = _provision("savedview")
    try:
        yield data
    finally:
        TenantContext.clear_tenant()


def _requirement(tenant, workspace, title: str, *, uid: str | None = None) -> Requirement:
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    return Requirement.objects.create(
        tenant=tenant,
        artifact=artifact,
        title=title,
        uid=uid or f"REQ-{title}",
        description=f"desc {title}",
    )


def _create(env, **overrides):
    payload = {
        "workspace_id": env["workspace"].id,
        "item_type": "Requirement",
        "name": "Offene Anforderungen",
    }
    payload.update(overrides)
    return SavedViewService().create(env["ctx"], **payload)


# ---------------------------------------------------------------------------
# List / visibility
# ---------------------------------------------------------------------------


def test_create_and_list_private_visible_only_to_owner(env):
    view = _create(env)

    assert view.visibility == "private"
    assert view.owner_id == env["user"].id
    own = SavedViewService().list(env["ctx"], env["workspace"].id)
    assert [v.id for v in own] == [view.id]

    # Another user of the same tenant/workspace does not see it at all.
    assert SavedViewService().list(env["other_ctx"], env["workspace"].id) == []
    with pytest.raises(NotFoundError):
        SavedViewService().get(env["other_ctx"], view.id)


def test_workspace_view_visible_to_members_readonly_for_non_owner(env):
    view = _create(env, visibility="workspace")

    listed = SavedViewService().list(env["other_ctx"], env["workspace"].id)
    assert [v.id for v in listed] == [view.id]
    assert SavedViewService().get(env["other_ctx"], view.id).id == view.id

    with pytest.raises(PermissionDeniedError):
        SavedViewService().update(env["other_ctx"], view.id, name="hijack")
    with pytest.raises(PermissionDeniedError):
        SavedViewService().delete(env["other_ctx"], view.id)


def test_non_owner_update_and_delete_denied_admin_allowed(env):
    view = _create(env)

    # A plain editor who is not the owner cannot touch a private view: the
    # update path answers 403 (the *read* path answers 404 first, see above).
    with pytest.raises(PermissionDeniedError):
        SavedViewService().update(env["other_ctx"], view.id, name="editor rename")

    updated = SavedViewService().update(
        env["admin_ctx"], view.id, name="admin rename"
    )
    assert updated.name == "admin rename"
    assert updated.version == 2

    SavedViewService().delete(env["admin_ctx"], view.id)
    with pytest.raises(NotFoundError):
        SavedViewService().get(env["ctx"], view.id)


def test_list_filters_by_item_type(env):
    _create(env, name="Req")
    _create(env, item_type="TestCase", name="TC")

    assert len(SavedViewService().list(env["ctx"], env["workspace"].id)) == 2
    only_tc = SavedViewService().list(env["ctx"], env["workspace"].id, "TestCase")
    assert [v.name for v in only_tc] == ["TC"]


def test_cross_tenant_view_not_found(env, db):
    foreign = _provision("savedview-foreign")
    view = _create(foreign)

    with pytest.raises(NotFoundError):
        SavedViewService().get(env["ctx"], view.id)
    assert SavedViewService().list(env["ctx"], env["workspace"].id) == []


def test_unknown_workspace_not_found(env):
    import uuid

    with pytest.raises(NotFoundError):
        SavedViewService().list(env["ctx"], uuid.uuid4())


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_create_with_unknown_filter_field_rejected(env):
    with pytest.raises(ValidationError) as excinfo:
        _create(env, filters={"nope": {"op": "contains", "value": "x"}})

    assert "nope" in str(excinfo.value)


def test_create_with_unknown_item_type_rejected(env):
    with pytest.raises(ValidationError):
        _create(env, item_type="Goal")


def test_create_with_unknown_sort_field_rejected(env):
    with pytest.raises(ValidationError):
        _create(env, sort=[{"field": "nope", "dir": "asc"}])


def test_unique_name_conflict_is_validation_error(env):
    _create(env)

    with pytest.raises(ValidationError) as excinfo:
        _create(env)

    assert "already exists" in str(excinfo.value)


def test_two_owners_may_share_a_name(env):
    _create(env)

    SavedViewService().create(
        env["other_ctx"],
        workspace_id=env["workspace"].id,
        item_type="Requirement",
        name="Offene Anforderungen",
    )
    # Same name, different owner: both rows exist (the per-user list only ever
    # shows the caller's own private views, so count through the model).
    with active_tenant(env["tenant"]):
        assert SavedView.objects.filter(
            workspace_id=env["workspace"].id, name="Offene Anforderungen"
        ).count() == 2


def test_update_with_stale_expected_version_is_optimistic_lock_error(env):
    view = _create(env)

    with pytest.raises(OptimisticLockError):
        SavedViewService().update(env["ctx"], view.id, expected_version=99)

    current = SavedViewService().update(
        env["ctx"], view.id, name="neu", expected_version=1
    )
    assert current.version == 2


def test_update_validates_new_filters(env):
    view = _create(env)

    with pytest.raises(ValidationError):
        SavedViewService().update(
            env["ctx"], view.id, filters={"nope": {"op": "eq", "value": 1}}
        )


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def test_apply_returns_filtered_sorted_queryset(env):
    _requirement(env["tenant"], env["workspace"], "Alpha")
    _requirement(env["tenant"], env["workspace"], "Beta")
    _requirement(env["tenant"], env["workspace"], "Alpaka")

    view = _create(
        env,
        filters={"title": {"op": "contains", "value": "Alp"}},
        sort=[{"field": "title", "dir": "desc"}],
    )
    result = SavedViewService().apply(env["ctx"], view.id)

    assert result.warnings == []
    assert [row["values"]["title"] for row in result.rows] == ["Alpha", "Alpaka"]
    assert result.rows[0]["item_type"] == "Requirement"
    assert result.rows[0]["artifact_id"]
    assert result.rows[0]["locked"] is None


def test_apply_with_removed_attribute_is_empty_with_warning(env):
    """A stored filter that no longer compiles: 200 + empty + warning."""
    _requirement(env["tenant"], env["workspace"], "Alpha")
    view = _create(env)

    # Simulate the definition drifting away from the stored document: the row
    # now names a field the DSL does not know (an attribute removed from the
    # definition after the view was saved). Written around the service on
    # purpose — that is exactly the stale state apply has to survive.
    SavedView.objects.filter(id=view.id).update(
        filters={"removed_attribute": {"op": "contains", "value": "x"}}
    )

    result = SavedViewService().apply(env["ctx"], view.id)

    assert result.rows == []
    assert len(result.warnings) == 1
    assert "removed_attribute" in result.warnings[0]


def test_apply_private_view_of_another_user_is_not_found(env):
    view = _create(env)

    with pytest.raises(NotFoundError):
        SavedViewService().apply(env["other_ctx"], view.id)


def test_apply_workspace_view_of_another_user_is_readable(env):
    _requirement(env["tenant"], env["workspace"], "Alpha")
    view = _create(env, visibility="workspace")

    result = SavedViewService().apply(env["other_ctx"], view.id)
    assert len(result.rows) == 1


# ---------------------------------------------------------------------------
# Filter edges (plan Review Focus 2)
# ---------------------------------------------------------------------------


def test_in_with_empty_list_matches_nothing(env):
    _requirement(env["tenant"], env["workspace"], "Alpha")
    view = _create(env, filters={"title": {"op": "in", "value": []}})

    assert SavedViewService().apply(env["ctx"], view.id).rows == []


def test_contains_treats_wildcards_literally(env):
    _requirement(env["tenant"], env["workspace"], "100%_done")
    _requirement(env["tenant"], env["workspace"], "100Xdone")

    view = _create(env, filters={"title": {"op": "contains", "value": "%_"}})
    rows = SavedViewService().apply(env["ctx"], view.id).rows

    assert [row["values"]["title"] for row in rows] == ["100%_done"]


def test_gte_with_unparsable_date_is_validation_error(env):
    with pytest.raises(ValidationError):
        SavedViewService().create(
            env["ctx"],
            workspace_id=env["workspace"].id,
            item_type="Issue",
            name="Fällig",
            filters={"due_date": {"op": "gte", "value": "not-a-date"}},
        )


def test_more_than_200_in_values_is_validation_error(env):
    with pytest.raises(ValidationError):
        SavedViewService().create(
            env["ctx"],
            workspace_id=env["workspace"].id,
            item_type="Requirement",
            name="Zu breit",
            filters={"title": {"op": "in", "value": [f"t{i}" for i in range(201)]}},
        )


# ---------------------------------------------------------------------------
# Per-user table state
# ---------------------------------------------------------------------------


def test_state_upsert_one_row_per_user_workspace_type(env):
    service = TableViewStateService()

    assert service.get(env["ctx"], env["workspace"].id, "Requirement") is None

    first = service.save(
        env["ctx"],
        env["workspace"].id,
        "Requirement",
        columns=[{"field": "title", "order": 0}],
        filters={"title": {"op": "contains", "value": "a"}},
        sort=[{"field": "title", "dir": "asc"}],
    )
    assert first["columns"] == [{"field": "title", "order": 0}]

    second = service.save(
        env["ctx"],
        env["workspace"].id,
        "Requirement",
        columns=[{"field": "uid", "order": 0}],
    )
    assert second["columns"] == [{"field": "uid", "order": 0}]
    assert second["filters"] == {}

    with active_tenant(env["tenant"]):
        assert UserTableViewState.objects.count() == 1


def test_state_is_per_user(env):
    service = TableViewStateService()
    service.save(
        env["ctx"], env["workspace"].id, "Requirement", columns=[{"field": "title"}]
    )

    assert service.get(env["other_ctx"], env["workspace"].id, "Requirement") is None


def test_state_rejects_oversized_json(env):
    huge = "x" * (MAX_STATE_BYTES + 1)
    with pytest.raises(ValidationError) as excinfo:
        TableViewStateService().save(
            env["ctx"],
            env["workspace"].id,
            "Requirement",
            columns=[{"field": huge, "order": 0}],
        )

    assert "limit" in str(excinfo.value)


def test_state_rejects_too_many_columns(env):
    with pytest.raises(ValidationError):
        TableViewStateService().save(
            env["ctx"],
            env["workspace"].id,
            "Requirement",
            columns=[{"field": f"f{i}", "order": i} for i in range(201)],
        )


def test_state_does_not_validate_field_names(env):
    """A column whose attribute disappeared must still be storable/loadable."""
    state = TableViewStateService().save(
        env["ctx"],
        env["workspace"].id,
        "Requirement",
        columns=[{"field": "removed_attribute", "order": 0}],
    )

    assert state["columns"] == [{"field": "removed_attribute", "order": 0}]


def test_state_requires_write_permission(env):
    viewer_ctx = _ctx(env["tenant"], env["user"], roles=("viewer",))

    with pytest.raises(PermissionDeniedError):
        TableViewStateService().save(
            viewer_ctx, env["workspace"].id, "Requirement"
        )
