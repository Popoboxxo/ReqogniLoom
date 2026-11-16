"""The type-aware table filter DSL (Tabellenansicht S1, Task 1.3).

Pins the frozen wire contract and its edges (plan Review Focus 2):

* operators follow the attribute type — text ``contains``, enum/actor/status
  ``in``, number/date ``gte|lte``, boolean ``eq``; ``criteria-list``/``widget``
  have none,
* unknown field / disallowed operator / wrong value type / oversized ``in`` →
  ``ValidationError`` naming the field (never a silent ignore),
* text matching is literal (``%``, ``_``, quotes),
* an empty ``in`` list matches nothing, not everything,
* the pseudo-fields ``allocated``/``level`` answer exactly the same rows as
  ``?allocated=``/``?level=``,
* sort terms, the ``id`` tie-breaker and the ``tree`` expansion,
* the module is transport-free: it imports and compiles with no request object,
  and raises the plain ``application.base.ValidationError``.
"""
from __future__ import annotations

from uuid import UUID

import pytest

from application.base import ValidationError
from application.requirement_service import RequirementService
from application.table_filter_dsl import (
    FILTER_OPERATORS_BY_TYPE,
    MAX_CONSTRAINTS_PER_FIELD,
    MAX_IN_VALUES,
    allowed_operators,
    compile_filters,
    compile_sort,
)
from application.table_query_service import BUILTIN_ATTRIBUTES
from application.workspace_lookup import ENTITY_SPECS
from application.workspace_lookup import import_entity_model as _model_for
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import (
    Actor,
    Artifact,
    Requirement,
    Tenant,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from persistence.tests.conftest import active_tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def env(db):
    tenant = Tenant.objects.create(name="dsl", slug="dsl")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="dsl-ws")
    user = User.objects.create(
        tenant=tenant, username="dsl-user", email="dsl@example.com"
    )
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    data = {"tenant": tenant, "workspace": workspace, "ctx": ctx, "user": user}
    try:
        yield data
    finally:
        TenantContext.clear_tenant()


def from_table_types(item_type: str) -> str:
    """``item_type`` -> ``ENTITY_SPECS`` key (same registry the DSL uses)."""
    from application.table_filter_dsl import TABLE_ITEM_TYPES

    return TABLE_ITEM_TYPES[item_type]


def _attributes(item_type: str = "Requirement"):
    return [dict(attribute) for attribute in BUILTIN_ATTRIBUTES[item_type]]


def _requirement(env, title, *, uid=None, level=None, sort_key=None, owner=None):
    artifact = Artifact.objects.create(
        tenant=env["tenant"],
        workspace=env["workspace"],
        artifact_type="Requirement",
        sort_key=sort_key,
        owner_id=owner.id if owner is not None else None,
    )
    requirement = Requirement.objects.create(
        tenant=env["tenant"],
        artifact=artifact,
        title=title,
        uid=uid or f"R-{title}",
        description=f"d {title}",
    )
    if level is not None:
        Requirement.objects.filter(id=requirement.id).update(level=level)
        requirement.refresh_from_db()
    return requirement


def _filter(env, filters, item_type="Requirement", attributes=None):
    qs = Requirement.objects.filter(workspace_id=env["workspace"].id)
    if item_type != "Requirement":
        model = _model_for(ENTITY_SPECS[from_table_types(item_type)].model_path)
        qs = model.objects.all()
    return qs.filter(
        compile_filters(
            item_type,
            attributes if attributes is not None else _attributes(item_type),
            filters,
            tenant_id=env["tenant"].id,
            workspace_id=env["workspace"].id,
        )
    )


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------


def test_operators_derived_from_type():
    assert FILTER_OPERATORS_BY_TYPE["text"] == frozenset({"contains"})
    assert FILTER_OPERATORS_BY_TYPE["enum"] == frozenset({"in"})
    assert FILTER_OPERATORS_BY_TYPE["actor"] == frozenset({"in"})
    assert FILTER_OPERATORS_BY_TYPE["number"] == frozenset({"gte", "lte"})
    assert "criteria-list" not in FILTER_OPERATORS_BY_TYPE
    assert "widget" not in FILTER_OPERATORS_BY_TYPE


def test_status_is_filterable_with_in_only(env):
    status = next(
        attribute for attribute in _attributes() if attribute["name"] == "status"
    )
    assert allowed_operators(status) == frozenset({"in"})
    with pytest.raises(ValidationError, match="status"):
        _filter(env, {"status": {"op": "contains", "value": "draft"}})


def test_text_contains_builds_icontains(env):
    _requirement(env, "Alpha")
    _requirement(env, "Beta")
    assert [r.title for r in _filter(env, {"title": {"op": "contains", "value": "alp"}})] == [
        "Alpha"
    ]


def test_range_as_list_of_constraints_is_anded(env):
    for title, fibonacci in (("A", 1), ("B", 2), ("C", 8)):
        row = _requirement(env, title)
        Requirement.objects.filter(id=row.id).update(complexity_fibonacci=fibonacci)
    qs = _filter(
        env,
        {
            "complexity_fibonacci": [
                {"op": "gte", "value": 2},
                {"op": "lte", "value": 5},
            ]
        },
    )
    assert [row.title for row in qs] == ["B"]


def test_single_object_is_shorthand_for_one_element_list(env):
    _requirement(env, "Alpha")
    single = _filter(env, {"title": {"op": "contains", "value": "Alp"}})
    listed = _filter(env, {"title": [{"op": "contains", "value": "Alp"}]})
    assert [row.id for row in single] == [row.id for row in listed]


def test_unknown_field_names_the_field(env):
    with pytest.raises(ValidationError, match="nope"):
        _filter(env, {"nope": {"op": "contains", "value": "x"}})


def test_disallowed_operator_names_operator_and_allowed_set(env):
    with pytest.raises(ValidationError) as excinfo:
        _filter(env, {"title": {"op": "gte", "value": "x"}})
    message = str(excinfo.value)
    assert "title" in message and "gte" in message and "contains" in message


def test_orm_traversal_name_rejected(env):
    with pytest.raises(ValidationError, match="artifact__workspace__tenant"):
        _filter(env, {"artifact__workspace__tenant": {"op": "contains", "value": "x"}})


def test_extended_and_carrier_fields_rejected(env):
    attributes = [
        {"name": "custom_x", "kind": "extended", "type": "text", "editable": True},
    ]
    with pytest.raises(ValidationError, match="custom_x"):
        _filter(env, {"custom_x": {"op": "contains", "value": "x"}}, attributes=attributes)
    with pytest.raises(ValidationError, match="deciders"):
        _filter(env, {"deciders": {"op": "in", "value": []}}, item_type="Adr")


def test_in_empty_list_matches_nothing(env):
    _requirement(env, "Alpha")
    assert list(_filter(env, {"status": {"op": "in", "value": []}})) == []


def test_contains_treats_percent_underscore_and_quote_literally(env):
    _requirement(env, '100%_"x"')
    _requirement(env, "100X-Yx")
    rows = _filter(env, {"title": {"op": "contains", "value": '%_"'}})
    assert [row.title for row in rows] == ['100%_"x"']


def test_invalid_date_and_stringly_boolean_are_400(env):
    with pytest.raises(ValidationError, match="due_date"):
        _filter(
            env,
            {"due_date": {"op": "gte", "value": "not-a-date"}},
            item_type="Issue",
        )
    boolean_attributes = [
        {"name": "flag", "kind": "core", "type": "boolean", "editable": True}
    ]
    with pytest.raises(ValidationError, match="flag"):
        _filter(env, {"flag": {"op": "eq", "value": "true"}}, attributes=boolean_attributes)


def test_oversized_in_list_is_400(env):
    with pytest.raises(ValidationError, match=str(MAX_IN_VALUES)):
        _filter(
            env,
            {"status": {"op": "in", "value": [f"s{i}" for i in range(MAX_IN_VALUES + 1)]}},
        )


def test_too_many_constraints_per_field_is_400(env):
    constraints = [
        {"op": "contains", "value": "x"} for _ in range(MAX_CONSTRAINTS_PER_FIELD + 1)
    ]
    with pytest.raises(ValidationError, match="title"):
        _filter(env, {"title": constraints})


def test_actor_in_filters_owner(env):
    one = Actor.objects.create(
        tenant=env["tenant"], kind="external", display_name="One"
    )
    other = Actor.objects.create(
        tenant=env["tenant"], kind="external", display_name="Other"
    )
    _requirement(env, "Owned", owner=one)
    _requirement(env, "NotOwned", owner=other)
    rows = _filter(env, {"owner": {"op": "in", "value": [str(one.id)]}})
    assert [row.title for row in rows] == ["Owned"]


def test_status_in_returns_matching_states_including_initial_fallback(env):
    _requirement(env, "FallsBack")
    # No WorkflowItemState row -> the type's initial state ("draft").
    rows = _filter(env, {"status": {"op": "in", "value": ["draft"]}})
    assert [row.title for row in rows] == ["FallsBack"]
    assert list(_filter(env, {"status": {"op": "in", "value": ["released"]}})) == []


# ---------------------------------------------------------------------------
# Pseudo fields (plan O2)
# ---------------------------------------------------------------------------


def test_pseudo_fields_allocated_and_level_only_for_requirement(env):
    with pytest.raises(ValidationError, match="level"):
        _filter(env, {"level": {"op": "eq", "value": 1}}, item_type="Adr")
    with pytest.raises(ValidationError, match="allocated"):
        _filter(env, {"allocated": {"op": "eq", "value": True}}, item_type="Adr")


def test_pseudo_field_results_equal_requirement_list_filters(env):
    _requirement(env, "L1", level=1)
    _requirement(env, "L3", level=3)

    table_ids = {
        row.id for row in _filter(env, {"level": {"op": "eq", "value": 3}})
    }
    service_ids = {
        row.id
        for row in RequirementService().list_requirements(
            env["workspace"].id, env["ctx"], level=3
        )
    }
    assert table_ids == service_ids

    allocated_ids = {
        row.id for row in _filter(env, {"allocated": {"op": "eq", "value": False}})
    }
    service_allocated = {
        row.id
        for row in RequirementService().list_requirements(
            env["workspace"].id, env["ctx"], allocated=False
        )
    }
    assert allocated_ids == service_allocated


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------


def test_compile_sort_orders_multi_term():
    terms = compile_sort(
        "Requirement",
        _attributes(),
        [{"field": "category", "dir": "desc"}, {"field": "title", "dir": "asc"}],
    )
    assert terms == ("-category", "title", "id")


def test_compile_sort_rejects_bad_direction_unknown_field_and_more_than_5_terms():
    attributes = _attributes()
    with pytest.raises(ValidationError, match="title"):
        compile_sort("Requirement", attributes, [{"field": "title", "dir": "up"}])
    with pytest.raises(ValidationError, match="nope"):
        compile_sort("Requirement", attributes, [{"field": "nope"}])
    with pytest.raises(ValidationError, match="at most"):
        compile_sort("Requirement", attributes, [{"field": "title"}] * 6)


def test_compile_sort_rejects_status_actor_pseudo_and_criteria_list():
    attributes = _attributes() + [
        {"name": "acceptance_criteria_items", "kind": "core", "type": "criteria-list",
         "editable": True}
    ]
    for field in ("status", "owner", "level", "allocated", "acceptance_criteria_items"):
        with pytest.raises(ValidationError, match=field):
            compile_sort("Requirement", attributes, [{"field": field}])


def test_sort_tree_orders_by_sort_key_then_created_at_then_id(env):
    late = _requirement(env, "NoKey")
    first = _requirement(env, "KeyA", sort_key="a")
    second = _requirement(env, "KeyB", sort_key="b")

    qs = Requirement.objects.filter(workspace_id=env["workspace"].id).order_by(
        *compile_sort("Requirement", _attributes(), [{"field": "tree", "dir": "asc"}])
    )
    assert [row.id for row in qs] == [first.id, second.id, late.id]
    terms = compile_sort("Requirement", _attributes(), [{"field": "tree"}])
    # The first term is the resolved NULLS LAST expression, not a field name.
    assert not isinstance(terms[0], str)


def test_sort_tree_rejects_desc():
    with pytest.raises(ValidationError, match="tree"):
        compile_sort("Requirement", _attributes(), [{"field": "tree", "dir": "desc"}])


def test_dsl_works_without_http():
    with pytest.raises(ValidationError) as excinfo:
        compile_filters(
            "Requirement",
            _attributes(),
            {"nope": {"op": "contains", "value": "x"}},
            tenant_id=UUID(int=1),
            workspace_id=UUID(int=2),
        )
    assert type(excinfo.value) is ValidationError


def test_active_tenant_context_is_not_required_for_compile(env):
    """The DSL never needs a ``ctx``; the caller arms the tenant context."""
    with active_tenant(env["tenant"]):
        assert compile_filters(
            "Requirement",
            _attributes(),
            {"title": {"op": "contains", "value": "x"}},
            tenant_id=env["tenant"].id,
            workspace_id=env["workspace"].id,
        ) is not None
