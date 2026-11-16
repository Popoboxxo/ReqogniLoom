"""``TableQueryService`` — the server-side table read (Tabellenansicht S1, Task 1.4).

Pins the service contract directly (no HTTP):

* all eight table types resolve, in the caller's workspace/tenant only,
* filters/sort/outdated behave as the DSL says,
* RBAC read gate plus item-level rules: an explicit ``none`` rule hides the row
  **and** its count, an artifact-scoped rule overrides the workspace-wide one,
  another user's rules are irrelevant,
* the row shape (``id`` vs ``artifact_id`` vs ``version``) and JSON primitives,
* the query count does not grow with the page size (status projection and the
  freeze lookup are batched).
"""
from __future__ import annotations

import json
from uuid import UUID

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from application.base import PermissionDeniedError, ValidationError
from application.table_query_service import TableQueryService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    ITEM_PERMISSION_NONE,
    ITEM_PERMISSION_READ,
    ITEM_PERMISSION_WRITE,
    ItemPermission,
)
from persistence.models import (
    Adr,
    ArchitectureElement,
    Artifact,
    GlossaryTerm,
    Issue,
    Requirement,
    Risk,
    StakeholderNeed,
    Tenant,
    TestCase,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def env(db):
    tenant = Tenant.objects.create(name="table", slug="table")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="table-ws")
    other_workspace = Workspace.objects.create(tenant=tenant, name="other-ws")
    user = User.objects.create(tenant=tenant, username="tbl", email="tbl@example.com")
    other_user = User.objects.create(
        tenant=tenant, username="tbl-other", email="tbl-other@example.com"
    )
    foreign = Tenant.objects.create(name="foreign", slug="foreign")
    TenantContext.set_tenant(foreign.id)
    foreign_workspace = Workspace.objects.create(tenant=foreign, name="foreign-ws")
    TenantContext.set_tenant(tenant.id)

    def ctx(roles=("editor",), user_id=None):
        return AuthContext(
            user_id=user_id or user.id,
            tenant_id=tenant.id,
            active_roles=roles,
            auth_method=AuthMethod.BEARER_TOKEN,
        )

    data = {
        "tenant": tenant,
        "foreign": foreign,
        "workspace": workspace,
        "other_workspace": other_workspace,
        "foreign_workspace": foreign_workspace,
        "user": user,
        "other_user": other_user,
        "ctx": ctx(),
        "reader": ctx(roles=("viewer",)),
        "no_roles": ctx(roles=()),
        "ctx_factory": ctx,
    }
    try:
        yield data
    finally:
        TenantContext.clear_tenant()


def _artifact(env, *, workspace=None, tenant=None, lifecycle_status=None):
    return Artifact.objects.create(
        tenant=tenant or env["tenant"],
        workspace=workspace or env["workspace"],
        artifact_type="Requirement",
        lifecycle_status=lifecycle_status or "active",
    )


def _requirement(env, title, **kwargs):
    artifact = _artifact(
        env,
        workspace=kwargs.pop("workspace", None),
        tenant=kwargs.pop("tenant", None),
        lifecycle_status=kwargs.pop("lifecycle_status", None),
    )
    return Requirement.objects.create(
        tenant=artifact.tenant,
        artifact=artifact,
        title=title,
        uid=kwargs.pop("uid", f"R-{title}"),
        description=kwargs.pop("description", f"d {title}"),
        **kwargs,
    )


def _ids(queryset):
    return [row.id for row in queryset]


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------


def test_columns_lists_visible_attributes_only(env, monkeypatch):
    from application import table_query_service

    attributes = [
        {"name": "title", "kind": "core", "type": "text", "visible": True,
         "editable": True},
        {"name": "secret", "kind": "core", "type": "text", "visible": False,
         "editable": True},
    ]

    def _resolve(self, ctx, item_type, workspace_id):
        return {"attributes": attributes, "sections": [], "version": 1}

    monkeypatch.setattr(
        table_query_service.AttributeDefinitionService, "resolve", _resolve
    )
    columns = TableQueryService().columns(env["ctx"], env["workspace"].id, "Requirement")
    assert [column["name"] for column in columns] == ["title"]


def test_missing_definition_falls_back_to_builtin_attributes(env):
    attributes = TableQueryService().attributes(
        env["ctx"], env["workspace"].id, "Requirement"
    )
    assert {"title", "status", "owner"} <= {a["name"] for a in attributes}


# ---------------------------------------------------------------------------
# Scoping / filtering / sorting
# ---------------------------------------------------------------------------


def test_query_scopes_to_workspace_and_tenant(env):
    inside = _requirement(env, "Inside")
    _requirement(env, "OtherWorkspace", workspace=env["other_workspace"])
    _requirement(
        env,
        "ForeignTenant",
        tenant=env["foreign"],
        workspace=env["foreign_workspace"],
    )
    rows = TableQueryService().query(env["ctx"], env["workspace"].id, "Requirement")
    assert _ids(rows) == [inside.id]


def test_query_applies_filters_and_sort(env):
    alpha = _requirement(env, "Alpha")
    _requirement(env, "Beta")
    rows = TableQueryService().query(
        env["ctx"],
        env["workspace"].id,
        "Requirement",
        {"title": {"op": "contains", "value": "Alp"}},
        [{"field": "title", "dir": "desc"}],
    )
    assert _ids(rows) == [alpha.id]


def test_query_excludes_outdated_by_default_and_includes_on_request(env):
    active = _requirement(env, "Active")
    gone = _requirement(env, "Gone", lifecycle_status="outdated")
    service = TableQueryService()
    assert _ids(service.query(env["ctx"], env["workspace"].id, "Requirement")) == [
        active.id
    ]
    assert set(
        _ids(
            service.query(
                env["ctx"],
                env["workspace"].id,
                "Requirement",
                include_deleted=True,
            )
        )
    ) == {active.id, gone.id}


def test_unsupported_item_type_rejected(env):
    for item_type in ("Goal", "Document", "Nope"):
        with pytest.raises(ValidationError):
            TableQueryService().query(env["ctx"], env["workspace"].id, item_type)


def test_all_eight_types_resolve(env):
    creators = {
        "Requirement": lambda artifact: Requirement.objects.create(
            tenant=env["tenant"], artifact=artifact, title="r", uid="R-1"
        ),
        "StakeholderNeed": lambda artifact: StakeholderNeed.objects.create(
            tenant=env["tenant"], artifact=artifact, title="n", uid="N-1"
        ),
        "ArchitectureElement": lambda artifact: ArchitectureElement.objects.create(
            tenant=env["tenant"], artifact=artifact, title="a", uid="A-1"
        ),
        "TestCase": lambda artifact: TestCase.objects.create(
            tenant=env["tenant"], artifact=artifact, title="t", uid="T-1"
        ),
        "Adr": lambda artifact: Adr.objects.create(
            tenant=env["tenant"],
            workspace_id=env["workspace"].id,
            artifact=artifact,
            title="d",
            uid="D-1",
        ),
        "Risk": lambda artifact: Risk.objects.create(
            tenant=env["tenant"],
            workspace_id=env["workspace"].id,
            artifact=artifact,
            title="k",
            uid="K-1",
        ),
        "Issue": lambda artifact: Issue.objects.create(
            tenant=env["tenant"],
            workspace_id=env["workspace"].id,
            artifact=artifact,
            title="i",
            uid="I-1",
        ),
        "GlossaryTerm": lambda artifact: GlossaryTerm.objects.create(
            tenant=env["tenant"],
            workspace=env["workspace"],
            artifact=artifact,
            term="g",
            definition="dg",
        ),
    }
    service = TableQueryService()
    for item_type, create in creators.items():
        artifact = Artifact.objects.create(
            tenant=env["tenant"],
            workspace=env["workspace"],
            artifact_type=item_type,
        )
        create(artifact)
        attributes = service.attributes(env["ctx"], env["workspace"].id, item_type)
        queryset = service.query(env["ctx"], env["workspace"].id, item_type)
        rows = service.serialize_rows(env["ctx"], list(queryset), attributes)
        assert len(rows) == 1, item_type
        assert rows[0]["item_type"] == item_type
        json.dumps(rows)  # JSON primitives only


def test_stale_unknown_filter_field_raises_validation_error(env):
    with pytest.raises(ValidationError, match="removed_attribute"):
        TableQueryService().query(
            env["ctx"],
            env["workspace"].id,
            "Requirement",
            {"removed_attribute": {"op": "contains", "value": "x"}},
        )


# ---------------------------------------------------------------------------
# Rights
# ---------------------------------------------------------------------------


def test_role_without_read_is_permission_denied(env):
    with pytest.raises(PermissionDeniedError):
        TableQueryService().query(env["no_roles"], env["workspace"].id, "Requirement")


def _rule(env, *, level, artifact=None, user=None):
    return ItemPermission.objects.create(
        tenant=env["tenant"],
        user=user or env["user"],
        workspace=env["workspace"],
        artifact=artifact,
        permission_level=level,
    )


def test_item_level_none_rule_hides_row_and_count(env):
    visible = _requirement(env, "Visible")
    hidden = _requirement(env, "Hidden")
    _rule(env, level=ITEM_PERMISSION_NONE, artifact=hidden.artifact)

    queryset = TableQueryService().query(env["ctx"], env["workspace"].id, "Requirement")
    assert _ids(queryset) == [visible.id]
    assert queryset.count() == 1


def test_workspace_none_hides_everything_without_artifact_rule(env):
    _requirement(env, "One")
    _requirement(env, "Two")
    _rule(env, level=ITEM_PERMISSION_NONE)

    assert TableQueryService().query(
        env["ctx"], env["workspace"].id, "Requirement"
    ).count() == 0


def test_workspace_none_plus_artifact_read_rule_keeps_that_artifact_visible(env):
    kept = _requirement(env, "Kept")
    _requirement(env, "Dropped")
    _rule(env, level=ITEM_PERMISSION_NONE)
    _rule(env, level=ITEM_PERMISSION_READ, artifact=kept.artifact)

    assert _ids(
        TableQueryService().query(env["ctx"], env["workspace"].id, "Requirement")
    ) == [kept.id]


def test_artifact_none_plus_workspace_write_rule_hides_it(env):
    _requirement(env, "Kept")
    denied = _requirement(env, "Denied")
    _rule(env, level=ITEM_PERMISSION_WRITE)
    _rule(env, level=ITEM_PERMISSION_NONE, artifact=denied.artifact)

    assert list(
        TableQueryService()
        .query(env["ctx"], env["workspace"].id, "Requirement")
        .values_list("title", flat=True)
    ) == ["Kept"]


def test_other_users_rules_are_ignored(env):
    _requirement(env, "Mine")
    _rule(env, level=ITEM_PERMISSION_NONE, user=env["other_user"])

    assert TableQueryService().query(
        env["ctx"], env["workspace"].id, "Requirement"
    ).count() == 1


def test_read_level_rule_does_not_hide(env):
    _requirement(env, "Readable")
    _rule(env, level=ITEM_PERMISSION_READ)

    assert TableQueryService().query(
        env["ctx"], env["workspace"].id, "Requirement"
    ).count() == 1


# ---------------------------------------------------------------------------
# Row shape / query count
# ---------------------------------------------------------------------------


def test_serialize_rows_shape_and_json_primitives(env):
    requirement = _requirement(env, "Shape")
    service = TableQueryService()
    attributes = service.attributes(env["ctx"], env["workspace"].id, "Requirement")
    rows = service.serialize_rows(
        env["ctx"],
        list(service.query(env["ctx"], env["workspace"].id, "Requirement")),
        attributes,
    )
    assert len(rows) == 1
    row = rows[0]
    assert set(row) == {"id", "artifact_id", "item_type", "version", "values", "locked"}
    assert row["id"] == str(requirement.id)
    assert row["artifact_id"] == str(requirement.artifact_id)
    assert row["item_type"] == "Requirement"
    assert row["version"] == requirement.version
    assert row["locked"] is None
    assert row["values"]["title"] == "Shape"
    assert row["values"]["status"] == "draft"
    assert row["values"]["owner"] is None
    json.dumps(row)


def test_artifact_id_differs_from_row_id_and_version_is_entity_version(env):
    requirement = _requirement(env, "Ids")
    service = TableQueryService()
    attributes = service.attributes(env["ctx"], env["workspace"].id, "Requirement")
    row = service.serialize_rows(
        env["ctx"],
        list(service.query(env["ctx"], env["workspace"].id, "Requirement")),
        attributes,
    )[0]
    assert UUID(row["id"]) != UUID(row["artifact_id"])
    assert UUID(row["artifact_id"]) == requirement.artifact_id
    assert row["version"] == Requirement.objects.get(id=requirement.id).version


def test_status_value_batched_in_one_query(env):
    """Serialising 50 rows costs the same queries as 5 (status is batched)."""
    service = TableQueryService()
    attributes = service.attributes(env["ctx"], env["workspace"].id, "Requirement")
    for index in range(5):
        _requirement(env, f"Small{index}")

    def _run():
        rows = list(service.query(env["ctx"], env["workspace"].id, "Requirement"))
        return service.serialize_rows(env["ctx"], rows, attributes)

    with CaptureQueriesContext(connection) as small:
        _assert_statuses(_run(), 5)

    for index in range(45):
        _requirement(env, f"Large{index}")

    with CaptureQueriesContext(connection) as large:
        _assert_statuses(_run(), 50)

    assert len(small.captured_queries) == len(
        large.captured_queries
    ), [q["sql"] for q in large.captured_queries]


def _assert_statuses(rows, expected):
    assert len(rows) == expected
    assert all(row["values"]["status"] == "draft" for row in rows)
