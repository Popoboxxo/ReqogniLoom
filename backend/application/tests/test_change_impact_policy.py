"""S4.10 — change-impact policy keys, typed resolution and the ceiling helper.

Covers the contract of ``application/change_impact_policy.py`` (ADR-033
``## Policy-Keys und Ebenen (S0.4)``, spec §4.2.6 / AC-15):

* the seven keys are registered on exactly the ``global`` + ``workspace`` levels,
  with the documented defaults, editors and no ``user`` level;
* resolution is ``workspace > global > default`` with a per-key source, and the
  stored enum strings are typed to ``int`` / ``float``;
* an unreadable stored value falls back to the registry default (source
  ``"default"``) instead of breaking the run;
* ``policy_hash`` is canonical over the typed policy (order- and
  storage-type-independent);
* :func:`clamp_parameters` treats the policy as a ceiling: a request can only be
  more restrictive, and every narrowed parameter is reported.

Deliberately database-backed: the contract *is* the interaction between the
registry, the tenant-scoped rows and the resolver.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from application.change_impact_policy import (
    LLM_ANNOTATION_KEY,
    MAX_DEPTH_DEFAULT,
    MAX_DEPTH_HARD_CAP,
    MAX_DEPTH_KEY,
    MAX_NODES_DEFAULT,
    MAX_NODES_HARD_CAP,
    MAX_NODES_KEY,
    MAX_PATHS_PER_FINDING,
    MIN_WEIGHT_KEY,
    POLICY_KEY_SPECS,
    SCHEDULE_INTERVAL_KEY,
    SEMANTIC_EDGES_KEY,
    TRIGGER_CHOICES,
    TRIGGER_DEFAULT,
    TRIGGER_KEY,
    clamp_parameters,
    policy_hash,
    register_change_impact_policy_keys,
    resolved_policy,
)
from application.preference_registry import all_preference_keys, get_preference_key
from application.preference_service import PreferenceService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    PREFERENCE_SCOPE_GLOBAL,
    PREFERENCE_SCOPE_USER,
    PREFERENCE_SCOPE_WORKSPACE,
    PreferenceValue,
)
from persistence.errors import ValidationError
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

#: The fully typed default policy, in the spec's key order.
DEFAULT_POLICY: dict[str, Any] = {
    TRIGGER_KEY: TRIGGER_DEFAULT,
    SCHEDULE_INTERVAL_KEY: 24,
    SEMANTIC_EDGES_KEY: False,
    LLM_ANNOTATION_KEY: False,
    MAX_DEPTH_KEY: 4,
    MAX_NODES_KEY: 200,
    MIN_WEIGHT_KEY: 0.05,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="ci-policy", slug=f"ci-policy-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    """A workspace created with the tenant context armed (tenant-scoped manager)."""
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant_id=tenant.id, name="ws-policy")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username=f"policy-{uuid.uuid4().hex[:6]}",
        email=f"policy-{uuid.uuid4().hex[:6]}@example.com",
        tenant=tenant,
    )


@pytest.fixture
def ctx(tenant: Tenant, workspace: Workspace, user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )


@pytest.fixture
def registered() -> None:
    """Guarantee the keys exist even if a test ever isolates the registry."""
    register_change_impact_policy_keys()


def _set_row(
    *,
    tenant: Tenant,
    key: str,
    value: Any,
    scope: str,
    workspace: Workspace | None = None,
) -> PreferenceValue:
    """Seed one preference row directly (bypasses the service's validation)."""
    TenantContext.set_tenant(tenant.id)
    try:
        return PreferenceValue.objects.create(
            tenant_id=tenant.id,
            scope=scope,
            key=key,
            value=value,
            workspace=workspace,
        )
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_ready_registers_all_seven_keys(self) -> None:
        """The ``application.ready()`` hook is the registration site (S4.10)."""
        registered_keys = {spec.key for spec in all_preference_keys()}
        assert len(POLICY_KEY_SPECS) == 7
        for spec in POLICY_KEY_SPECS:
            assert spec.key in registered_keys
            assert get_preference_key(spec.key) == spec

    def test_levels_are_global_and_workspace_only(self) -> None:
        expected = {PREFERENCE_SCOPE_GLOBAL, PREFERENCE_SCOPE_WORKSPACE}
        for spec in POLICY_KEY_SPECS:
            assert set(spec.levels) == expected, spec.key
            assert PREFERENCE_SCOPE_USER not in spec.levels, spec.key

    def test_defaults_editors_and_owner(self) -> None:
        expected_editors = {
            TRIGGER_KEY: "select",
            SCHEDULE_INTERVAL_KEY: "select",
            SEMANTIC_EDGES_KEY: "checkbox",
            LLM_ANNOTATION_KEY: "checkbox",
            MAX_DEPTH_KEY: "select",
            MAX_NODES_KEY: "select",
            MIN_WEIGHT_KEY: "select",
        }
        defaults = {
            TRIGGER_KEY: TRIGGER_DEFAULT,
            SCHEDULE_INTERVAL_KEY: "24",
            SEMANTIC_EDGES_KEY: False,
            LLM_ANNOTATION_KEY: False,
            MAX_DEPTH_KEY: MAX_DEPTH_DEFAULT,
            MAX_NODES_KEY: MAX_NODES_DEFAULT,
            MIN_WEIGHT_KEY: "0.05",
        }
        for spec in POLICY_KEY_SPECS:
            assert spec.default == defaults[spec.key], spec.key
            assert spec.ui_editor == expected_editors[spec.key], spec.key
            assert spec.owner == "S4", spec.key

    def test_registration_is_idempotent(self) -> None:
        register_change_impact_policy_keys()
        register_change_impact_policy_keys()
        assert get_preference_key(TRIGGER_KEY).default == TRIGGER_DEFAULT

    def test_trigger_choices_match_the_spec(self) -> None:
        assert TRIGGER_CHOICES == ("manual", "on_submit", "on_write", "scheduled")


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


class TestResolution:
    def test_no_rows_resolves_to_typed_defaults(self, tenant, workspace, registered):
        resolved = resolved_policy(tenant_id=tenant.id, workspace_id=workspace.id)
        assert resolved["effective"] == DEFAULT_POLICY
        assert resolved["source"] == {
            key: "default" for key in DEFAULT_POLICY
        }

    def test_workspace_override_wins_and_reports_its_source(
        self, tenant, workspace, registered
    ):
        _set_row(
            tenant=tenant,
            key=TRIGGER_KEY,
            value="on_submit",
            scope=PREFERENCE_SCOPE_WORKSPACE,
            workspace=workspace,
        )
        _set_row(
            tenant=tenant,
            key=MAX_NODES_KEY,
            value="500",
            scope=PREFERENCE_SCOPE_WORKSPACE,
            workspace=workspace,
        )

        resolved = resolved_policy(tenant_id=tenant.id, workspace_id=workspace.id)
        assert resolved["effective"][TRIGGER_KEY] == "on_submit"
        assert resolved["effective"][MAX_NODES_KEY] == 500
        assert resolved["source"][TRIGGER_KEY] == PREFERENCE_SCOPE_WORKSPACE
        assert resolved["source"][MAX_NODES_KEY] == PREFERENCE_SCOPE_WORKSPACE
        # Untouched keys keep their registry default and say so.
        assert resolved["effective"][MAX_DEPTH_KEY] == DEFAULT_POLICY[MAX_DEPTH_KEY]
        assert resolved["source"][MAX_DEPTH_KEY] == "default"

    def test_global_row_reports_global_and_is_overridden_per_workspace(
        self, tenant, workspace, registered
    ):
        _set_row(
            tenant=tenant,
            key=MAX_DEPTH_KEY,
            value="5",
            scope=PREFERENCE_SCOPE_GLOBAL,
        )

        global_only = resolved_policy(tenant_id=tenant.id, workspace_id=workspace.id)
        assert global_only["effective"][MAX_DEPTH_KEY] == 5
        assert global_only["source"][MAX_DEPTH_KEY] == PREFERENCE_SCOPE_GLOBAL

        _set_row(
            tenant=tenant,
            key=MAX_DEPTH_KEY,
            value="2",
            scope=PREFERENCE_SCOPE_WORKSPACE,
            workspace=workspace,
        )
        overridden = resolved_policy(tenant_id=tenant.id, workspace_id=workspace.id)
        assert overridden["effective"][MAX_DEPTH_KEY] == 2
        assert overridden["source"][MAX_DEPTH_KEY] == PREFERENCE_SCOPE_WORKSPACE

    def test_workspace_without_override_inherits_global(
        self, tenant, workspace, registered
    ):
        _set_row(
            tenant=tenant,
            key=SEMANTIC_EDGES_KEY,
            value=True,
            scope=PREFERENCE_SCOPE_GLOBAL,
        )
        resolved = resolved_policy(tenant_id=tenant.id, workspace_id=workspace.id)
        assert resolved["effective"][SEMANTIC_EDGES_KEY] is True
        assert resolved["source"][SEMANTIC_EDGES_KEY] == PREFERENCE_SCOPE_GLOBAL


# ---------------------------------------------------------------------------
# Typing
# ---------------------------------------------------------------------------


class TestTyping:
    def test_string_enum_values_are_typed(self, tenant, workspace, registered):
        _set_row(
            tenant=tenant,
            key=MAX_NODES_KEY,
            value="100",
            scope=PREFERENCE_SCOPE_GLOBAL,
        )
        _set_row(
            tenant=tenant,
            key=MIN_WEIGHT_KEY,
            value="0.2",
            scope=PREFERENCE_SCOPE_GLOBAL,
        )
        _set_row(
            tenant=tenant,
            key=SCHEDULE_INTERVAL_KEY,
            value="168",
            scope=PREFERENCE_SCOPE_GLOBAL,
        )

        effective = resolved_policy(
            tenant_id=tenant.id, workspace_id=workspace.id
        )["effective"]
        assert effective[MAX_NODES_KEY] == 100
        assert isinstance(effective[MAX_NODES_KEY], int)
        assert not isinstance(effective[MAX_NODES_KEY], bool)
        assert effective[MIN_WEIGHT_KEY] == 0.2
        assert isinstance(effective[MIN_WEIGHT_KEY], float)
        assert effective[SCHEDULE_INTERVAL_KEY] == 168
        assert isinstance(effective[SCHEDULE_INTERVAL_KEY], int)

    def test_unreadable_value_falls_back_to_default_without_raising(
        self, tenant, workspace, registered
    ):
        # A hand-edited/legacy row: the registry would have rejected the write.
        _set_row(
            tenant=tenant,
            key=TRIGGER_KEY,
            value="explode",
            scope=PREFERENCE_SCOPE_GLOBAL,
        )
        _set_row(
            tenant=tenant,
            key=MAX_DEPTH_KEY,
            value="not-a-number",
            scope=PREFERENCE_SCOPE_GLOBAL,
        )

        resolved = resolved_policy(tenant_id=tenant.id, workspace_id=workspace.id)
        assert resolved["effective"][TRIGGER_KEY] == TRIGGER_DEFAULT
        assert resolved["source"][TRIGGER_KEY] == "default"
        assert resolved["effective"][MAX_DEPTH_KEY] == DEFAULT_POLICY[MAX_DEPTH_KEY]
        assert resolved["source"][MAX_DEPTH_KEY] == "default"
        # The rest of the policy is unaffected.
        assert resolved["source"][MAX_NODES_KEY] == "default"

    def test_policy_hash_is_insertion_order_independent(self):
        first = {TRIGGER_KEY: "manual", MAX_NODES_KEY: 200}
        second = {MAX_NODES_KEY: 200, TRIGGER_KEY: "manual"}
        assert policy_hash(first) == policy_hash(second)

    def test_numeric_vs_string_storage_does_not_change_the_hash(
        self, tenant, workspace, registered
    ):
        _set_row(
            tenant=tenant,
            key=MAX_NODES_KEY,
            value="200",
            scope=PREFERENCE_SCOPE_GLOBAL,
        )
        string_storage = resolved_policy(
            tenant_id=tenant.id, workspace_id=workspace.id
        )["effective"]

        TenantContext.set_tenant(tenant.id)
        try:
            PreferenceValue.objects.filter(
                key=MAX_NODES_KEY, scope=PREFERENCE_SCOPE_GLOBAL
            ).update(value=200)
        finally:
            TenantContext.clear_tenant()

        numeric_storage = resolved_policy(
            tenant_id=tenant.id, workspace_id=workspace.id
        )["effective"]
        assert policy_hash(string_storage) == policy_hash(numeric_storage)


# ---------------------------------------------------------------------------
# Clamping (policy as ceiling)
# ---------------------------------------------------------------------------


class TestClamping:
    def test_hard_cap_wins_over_a_larger_policy_and_request(self):
        effective = {**DEFAULT_POLICY, MAX_DEPTH_KEY: 6}
        parameters, clamped = clamp_parameters(effective=effective, max_depth=9)
        assert parameters[MAX_DEPTH_KEY] == MAX_DEPTH_HARD_CAP
        assert clamped == [MAX_DEPTH_KEY]

    def test_request_above_policy_is_clamped_to_the_policy(self):
        effective = {**DEFAULT_POLICY, MAX_NODES_KEY: 200}
        parameters, clamped = clamp_parameters(effective=effective, max_nodes=500)
        assert parameters[MAX_NODES_KEY] == 200
        assert clamped == [MAX_NODES_KEY]

    def test_hard_cap_bounds_the_policy_itself(self):
        # A policy value above the hard cap can only exist via a legacy row.
        effective = {**DEFAULT_POLICY, MAX_NODES_KEY: 900}
        parameters, clamped = clamp_parameters(effective=effective)
        assert parameters[MAX_NODES_KEY] == MAX_NODES_HARD_CAP
        assert clamped == []

    def test_more_restrictive_request_is_allowed_and_not_clamped(self):
        effective = {**DEFAULT_POLICY, MAX_DEPTH_KEY: 4}
        parameters, clamped = clamp_parameters(effective=effective, max_depth=2)
        assert parameters[MAX_DEPTH_KEY] == 2
        assert clamped == []

    def test_request_cannot_enable_a_forbidden_flag(self):
        effective = {**DEFAULT_POLICY, SEMANTIC_EDGES_KEY: False}
        parameters, clamped = clamp_parameters(
            effective=effective, include_semantic=True
        )
        assert parameters[SEMANTIC_EDGES_KEY] is False
        assert clamped == [SEMANTIC_EDGES_KEY]

    def test_request_can_disable_an_allowed_flag_without_a_clamp(self):
        effective = {**DEFAULT_POLICY, LLM_ANNOTATION_KEY: True}
        parameters, clamped = clamp_parameters(effective=effective, include_llm=False)
        assert parameters[LLM_ANNOTATION_KEY] is False
        assert clamped == []

    def test_policy_flag_is_taken_when_no_request_is_given(self):
        effective = {**DEFAULT_POLICY, SEMANTIC_EDGES_KEY: True}
        parameters, clamped = clamp_parameters(effective=effective)
        assert parameters[SEMANTIC_EDGES_KEY] is True
        assert clamped == []

    def test_clamped_is_sorted_and_complete(self):
        effective = {**DEFAULT_POLICY, MAX_DEPTH_KEY: 2, MAX_NODES_KEY: 100}
        _, clamped = clamp_parameters(
            effective=effective,
            max_depth=6,
            max_nodes=500,
            include_semantic=True,
        )
        assert clamped == sorted(clamped) == [
            MAX_DEPTH_KEY,
            MAX_NODES_KEY,
            SEMANTIC_EDGES_KEY,
        ]

    @pytest.mark.parametrize("bad", ["4", 4.0, True])
    def test_non_int_request_raises(self, bad):
        with pytest.raises(ValidationError):
            clamp_parameters(effective=DEFAULT_POLICY, max_depth=bad)

    def test_non_int_nodes_request_raises(self):
        with pytest.raises(ValidationError):
            clamp_parameters(effective=DEFAULT_POLICY, max_nodes="200")

    def test_non_bool_flag_request_raises(self):
        with pytest.raises(ValidationError):
            clamp_parameters(effective=DEFAULT_POLICY, include_semantic="yes")


# ---------------------------------------------------------------------------
# No user level / code constant
# ---------------------------------------------------------------------------


class TestNoUserLevel:
    def test_user_level_write_is_rejected(self, ctx):
        with pytest.raises(ValidationError):
            PreferenceService().set_level(
                ctx, scope=PREFERENCE_SCOPE_USER, values={TRIGGER_KEY: "manual"}
            )

    def test_every_policy_key_declares_no_user_level(self):
        for spec in POLICY_KEY_SPECS:
            assert PREFERENCE_SCOPE_USER not in spec.levels


def test_max_paths_per_finding_is_a_code_constant() -> None:
    assert MAX_PATHS_PER_FINDING == 3
    assert "max_paths_per_finding" not in {spec.key for spec in POLICY_KEY_SPECS}
