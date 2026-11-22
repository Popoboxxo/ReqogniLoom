"""#1987 — producer context is the credential, not the principal label.

The ADR-019 gate must keep refusing a human bearer (no key id) while accepting
an authenticated API key with a write-capable scope. A user-principal plugin key
with the explicit ``author`` scope is such a producer: it resolves to
``actor_type="agent"`` at authentication time so the M2 proposal stamp and the
self-confirm block keep working.
"""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from application.base import (
    ProducerContextRequiredError,
    is_producer_context,
    require_producer_context,
)
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    API_KEY_SCOPE_AUTHOR,
    API_KEY_SCOPE_READ,
    API_KEY_SCOPE_WRITE,
    PRINCIPAL_TYPE_AGENT,
    PRINCIPAL_TYPE_USER,
    ApiKey,
)
from auth_tenancy.services.authentication import (
    AuthenticationService,
    generate_api_key_plaintext,
    hash_api_key,
    resolve_api_key_actor_type,
)
from persistence.models import Tenant, User

_KEY_ID = uuid4()
_USER_ID = uuid4()
_TENANT_ID = uuid4()


def _ctx(**overrides: object) -> AuthContext:
    base: dict[str, object] = {
        "user_id": _USER_ID,
        "tenant_id": _TENANT_ID,
        "active_roles": ("admin",),
        "auth_method": AuthMethod.API_KEY,
        "api_key_id": _KEY_ID,
        "scope": "author",
    }
    base.update(overrides)
    return AuthContext(**base)  # type: ignore[arg-type]


class TestProducerContextRule:
    def test_author_scoped_api_key_qualifies_even_with_user_actor_type(self):
        """The credential decides; a caller-built context stays accepted."""
        ctx = _ctx(actor_type=PRINCIPAL_TYPE_USER)
        assert is_producer_context(ctx) is True
        require_producer_context(ctx)

    def test_agent_scoped_api_key_qualifies(self):
        ctx = _ctx(actor_type=PRINCIPAL_TYPE_AGENT, scope="write")
        assert is_producer_context(ctx) is True
        require_producer_context(ctx)

    @pytest.mark.parametrize("scope", [API_KEY_SCOPE_WRITE, "admin"])
    def test_user_principal_legacy_scope_is_refused(self, scope):
        """Sync-path residual: write cap alone must not authorise a producer.

        Such a key resolves to ``actor_type="user"``; the M2 proposal stamp in
        TraceLinkService keys off that flag, so admitting it here would persist
        a link that looks confirmed and cannot be decided.
        """
        ctx = _ctx(actor_type=PRINCIPAL_TYPE_USER, scope=scope)
        assert is_producer_context(ctx) is False
        with pytest.raises(ProducerContextRequiredError) as exc:
            require_producer_context(ctx)
        assert "agent actor" in str(exc.value)

    def test_gate_uses_the_shared_actor_type_resolver(self):
        """The gate and the authentication path cannot drift apart."""
        from auth_tenancy.services.authentication import resolve_api_key_actor_type

        for actor_type, scope in [
            (PRINCIPAL_TYPE_AGENT, API_KEY_SCOPE_WRITE),
            (PRINCIPAL_TYPE_USER, API_KEY_SCOPE_AUTHOR),
        ]:
            ctx = _ctx(actor_type=actor_type, scope=scope)
            assert (
                resolve_api_key_actor_type(
                    principal_type=ctx.actor_type, scope=ctx.scope
                )
                == PRINCIPAL_TYPE_AGENT
            )
            assert is_producer_context(ctx) is True

    def test_human_bearer_is_still_refused_fail_closed(self):
        ctx = _ctx(
            auth_method=AuthMethod.BEARER_TOKEN,
            api_key_id=None,
            actor_type=PRINCIPAL_TYPE_USER,
        )
        assert is_producer_context(ctx) is False
        with pytest.raises(ProducerContextRequiredError) as exc:
            require_producer_context(ctx)
        assert "human bearer" in str(exc.value)
        assert "author" in str(exc.value)

    def test_read_only_api_key_is_refused(self):
        ctx = _ctx(scope=API_KEY_SCOPE_READ, actor_type=PRINCIPAL_TYPE_AGENT)
        assert is_producer_context(ctx) is False
        with pytest.raises(ProducerContextRequiredError):
            require_producer_context(ctx)

    def test_unknown_scope_fails_closed(self):
        with pytest.raises(ProducerContextRequiredError):
            require_producer_context(_ctx(scope="not-a-scope"))

    def test_api_key_without_key_id_is_refused(self):
        with pytest.raises(ProducerContextRequiredError):
            require_producer_context(_ctx(api_key_id=None))


class TestApiKeyActorTypeResolution:
    @pytest.mark.parametrize(
        ("principal_type", "scope", "expected"),
        [
            (PRINCIPAL_TYPE_AGENT, API_KEY_SCOPE_READ, PRINCIPAL_TYPE_AGENT),
            (PRINCIPAL_TYPE_AGENT, API_KEY_SCOPE_AUTHOR, PRINCIPAL_TYPE_AGENT),
            (PRINCIPAL_TYPE_USER, API_KEY_SCOPE_AUTHOR, PRINCIPAL_TYPE_AGENT),
            (PRINCIPAL_TYPE_USER, "  Author  ", PRINCIPAL_TYPE_AGENT),
            # Legacy/default scopes keep their historical actor type.
            (PRINCIPAL_TYPE_USER, API_KEY_SCOPE_WRITE, PRINCIPAL_TYPE_USER),
            (PRINCIPAL_TYPE_USER, API_KEY_SCOPE_READ, PRINCIPAL_TYPE_USER),
            (PRINCIPAL_TYPE_USER, "admin", PRINCIPAL_TYPE_USER),
            (PRINCIPAL_TYPE_USER, None, PRINCIPAL_TYPE_USER),
        ],
    )
    def test_actor_type_rule(self, principal_type, scope, expected):
        assert (
            resolve_api_key_actor_type(principal_type=principal_type, scope=scope)
            == expected
        )


@pytest.mark.django_db
def test_validate_api_key_maps_author_scoped_user_key_to_agent():
    """The live validation path carries the reclassified actor type onward."""
    tenant = Tenant.objects.create(name="t-producer-1987", is_active=True)
    owner = User.objects.create(
        tenant=tenant, email="producer-1987@example.com", is_active=True
    )
    plaintext = generate_api_key_plaintext()
    ApiKey.unscoped.create(
        tenant=tenant,
        user=owner,
        name="claude-code-plugin",
        key_hash=hash_api_key(plaintext),
        principal_type=PRINCIPAL_TYPE_USER,
        scope=API_KEY_SCOPE_AUTHOR,
    )

    claims = AuthenticationService().validate_api_key(plaintext)
    assert claims.actor_type == PRINCIPAL_TYPE_AGENT
    assert claims.scope == API_KEY_SCOPE_AUTHOR
    assert claims.api_key_id is not None


@pytest.mark.django_db
def test_validate_api_key_keeps_legacy_user_key_as_user():
    tenant = Tenant.objects.create(name="t-producer-1987-legacy", is_active=True)
    owner = User.objects.create(
        tenant=tenant, email="legacy-1987@example.com", is_active=True
    )
    plaintext = generate_api_key_plaintext()
    ApiKey.unscoped.create(
        tenant=tenant,
        user=owner,
        name="owner-key",
        key_hash=hash_api_key(plaintext),
        principal_type=PRINCIPAL_TYPE_USER,
        scope=API_KEY_SCOPE_WRITE,
        expires_at=timezone.now() + timedelta(days=1),
    )

    claims = AuthenticationService().validate_api_key(plaintext)
    assert claims.actor_type == PRINCIPAL_TYPE_USER
