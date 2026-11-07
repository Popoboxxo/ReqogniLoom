"""Ordering-plan preference keys (Q1 registry, plan item 3).

The frontend already writes two ordering-related preferences that the backend
registry used to reject as unknown:

* ``ui.connection_view.saved_views`` — user-scoped JSON-encoded view documents.
* ``ui.allocation_graph.card_fields`` — global/workspace/user card configuration.

These tests pin the registry contract and the level gate: a key is only
writable on a level its ``PreferenceKey.levels`` declares, and a ``str_list``
key rejects anything that is not a list of strings. The resolver must also hand
out independent copies of the list default, so one caller mutating a resolved
value cannot corrupt the process-wide catalogue.
"""
from __future__ import annotations

import pytest

from application.preference_registry import (
    get_preference_key,
    validate_preference_value,
)
from application.preference_service import PreferenceService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.errors import ValidationError

SAVED_VIEWS_KEY = "ui.connection_view.saved_views"
CARD_FIELDS_KEY = "ui.allocation_graph.card_fields"

pytestmark = pytest.mark.django_db


def _make_ctx(tenant, user, *roles: str) -> AuthContext:
    """Build a minimal ``AuthContext`` for the Q1 preference service."""
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=tuple(roles),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def service() -> PreferenceService:
    return PreferenceService()


@pytest.fixture
def admin_ctx(tenant_a, user_a) -> AuthContext:
    """Admin context: workspace and global preference writes require it."""
    return _make_ctx(tenant_a, user_a, "admin")


class TestRegistration:
    def test_both_keys_are_registered(self) -> None:
        saved_views = get_preference_key(SAVED_VIEWS_KEY)
        assert (
            saved_views.value_type,
            saved_views.default,
            saved_views.mode,
            saved_views.ui_editor,
            saved_views.owner,
        ) == ("str_list", [], "override", None, "P3")
        assert saved_views.levels == {"user"}
        assert saved_views.choices is None

        card_fields = get_preference_key(CARD_FIELDS_KEY)
        assert (
            card_fields.value_type,
            card_fields.default,
            card_fields.mode,
            card_fields.ui_editor,
            card_fields.owner,
        ) == ("str_list", [], "override", None, "P5")
        assert card_fields.levels == {"global", "workspace", "user"}
        assert card_fields.choices is None

    def test_defaults_are_empty_lists_and_not_shared(self) -> None:
        saved_views = get_preference_key(SAVED_VIEWS_KEY)
        card_fields = get_preference_key(CARD_FIELDS_KEY)

        assert saved_views.default == []
        assert card_fields.default == []
        assert saved_views.default is not card_fields.default

    def test_resolved_defaults_are_independent_copies(
        self, service, admin_ctx
    ) -> None:
        """A resolved default must not alias the mutable registry default."""
        result = service.effective(
            admin_ctx, keys=[SAVED_VIEWS_KEY, CARD_FIELDS_KEY]
        )
        saved_value = result["values"][SAVED_VIEWS_KEY]["value"]
        card_value = result["values"][CARD_FIELDS_KEY]["value"]

        assert saved_value == [] and card_value == []
        assert saved_value is not card_value
        assert saved_value is not get_preference_key(SAVED_VIEWS_KEY).default
        assert card_value is not get_preference_key(CARD_FIELDS_KEY).default

        saved_value.append("mutated")
        assert get_preference_key(SAVED_VIEWS_KEY).default == []

    @pytest.mark.parametrize("key", [SAVED_VIEWS_KEY, CARD_FIELDS_KEY])
    def test_non_list_value_is_rejected(self, key: str) -> None:
        spec = get_preference_key(key)
        with pytest.raises(ValidationError, match="must be a list of strings"):
            validate_preference_value(spec, "x")


class TestSavedViewsLevels:
    def test_user_level_accepts_a_list_of_strings(
        self, service, admin_ctx
    ) -> None:
        documents = ['{"name": "default"}', '{"name": "compact"}']

        payload = service.set_level(
            admin_ctx, scope="user", values={SAVED_VIEWS_KEY: documents}
        )
        assert payload["values"] == {SAVED_VIEWS_KEY: documents}

        effective = service.effective(
            admin_ctx, keys=[SAVED_VIEWS_KEY]
        )["values"][SAVED_VIEWS_KEY]
        assert effective == {"value": documents, "source": "user"}

    def test_workspace_level_write_is_rejected(
        self, service, admin_ctx, workspace_a
    ) -> None:
        with pytest.raises(
            ValidationError, match="cannot be set at level 'workspace'"
        ):
            service.set_level(
                admin_ctx,
                scope="workspace",
                values={SAVED_VIEWS_KEY: ["x"]},
                workspace_id=workspace_a.id,
            )


class TestCardFieldsLevels:
    def test_global_level_accepts_a_list_of_strings(
        self, service, admin_ctx
    ) -> None:
        config = ['{"field": "title", "visible": true}']

        payload = service.set_level(
            admin_ctx, scope="global", values={CARD_FIELDS_KEY: config}
        )
        assert payload["values"] == {CARD_FIELDS_KEY: config}

    def test_workspace_level_accepts_a_list_of_strings(
        self, service, admin_ctx, workspace_a
    ) -> None:
        config = ['{"field": "owner", "visible": false}']

        payload = service.set_level(
            admin_ctx,
            scope="workspace",
            values={CARD_FIELDS_KEY: config},
            workspace_id=workspace_a.id,
        )
        assert payload["values"] == {CARD_FIELDS_KEY: config}

    def test_user_level_accepts_a_list_of_strings(
        self, service, admin_ctx
    ) -> None:
        config = ['{"field": "status", "visible": true}']

        payload = service.set_level(
            admin_ctx, scope="user", values={CARD_FIELDS_KEY: config}
        )
        assert payload["values"] == {CARD_FIELDS_KEY: config}

    def test_override_rank_is_user_over_workspace_over_global(
        self, service, admin_ctx, workspace_a
    ) -> None:
        """The spec rank System < Workspace < User (global = System default)."""
        service.set_level(
            admin_ctx, scope="global", values={CARD_FIELDS_KEY: ["global"]}
        )
        service.set_level(
            admin_ctx,
            scope="workspace",
            values={CARD_FIELDS_KEY: ["workspace"]},
            workspace_id=workspace_a.id,
        )
        service.set_level(
            admin_ctx, scope="user", values={CARD_FIELDS_KEY: ["user"]}
        )

        def _effective() -> dict:
            return service.effective(
                admin_ctx, workspace_id=workspace_a.id, keys=[CARD_FIELDS_KEY]
            )["values"][CARD_FIELDS_KEY]

        assert _effective() == {"value": ["user"], "source": "user"}

        service.set_level(admin_ctx, scope="user", values={CARD_FIELDS_KEY: None})
        assert _effective() == {"value": ["workspace"], "source": "workspace"}

        service.set_level(
            admin_ctx,
            scope="workspace",
            values={CARD_FIELDS_KEY: None},
            workspace_id=workspace_a.id,
        )
        assert _effective() == {"value": ["global"], "source": "global"}
