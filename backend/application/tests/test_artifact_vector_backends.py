"""Registry, settings service and admin REST for the artifact vector store.

Pins the ADR-020 extension:

* the store is a registry plugin, so a third backend needs no core change;
* selection resolves ``DB override > env > pgvector`` and stays decoupled from
  ``MEMORY_BACKEND``;
* the admin service validates against the declared schema and never leaks a
  secret;
* the REST surface enforces the same System-Admin read / superuser write gate
  as the memory-settings endpoint.
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from application.artifact_vector_settings_service import (
    ArtifactVectorSettingsService,
    ArtifactVectorSettingsValidationError,
)
from application.vector_backends import (
    VECTOR_BACKEND_REGISTRY,
    VectorBackendCapabilities,
    VectorBackendPlugin,
    VectorBackendSettingField,
    register_vector_backend,
    resolve_artifact_vector_backend_name,
)
from application.vector_port import (
    PgVectorVectorPort,
    vector_backend_diagnostic,
)
from persistence.models import SystemArtifactVectorSettings

_ADMIN_URL = "/api/v1/system/artifact-vector-settings/"
_PASSWORD = "hunter2pass"


def _login_client(user) -> APIClient:
    """Log *user* in through the real endpoint and return a Bearer client."""
    client = APIClient()
    response = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert response.status_code == 200, response.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.json()['token']}")
    return client


@pytest.fixture
def admin_api_client(db) -> APIClient:
    """A tenant admin (NOT a Django superuser)."""
    from auth_tenancy.models import TenantRole, UserRole
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(
        name="Vector Tenant", slug=f"vector-{uuid4().hex[:8]}", is_active=True
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="ws", preset={"name": "standard"}
        )
        user = User.objects.create(
            username=f"vector-admin-{uuid4().hex[:8]}",
            email="vector-admin@t.test",
            tenant=tenant,
        )
        user.set_password(_PASSWORD)
        user.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role="admin"
        )
        TenantRole.objects.create(
            tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return _login_client(user)


@pytest.fixture
def superuser_api_client(db) -> APIClient:
    """A Django superuser (deployment-level identity)."""
    from persistence.models import Tenant, User

    tenant = Tenant.objects.create(
        name="Vector Root", slug=f"vector-root-{uuid4().hex[:8]}", is_active=True
    )
    user = User.objects.create(
        username=f"vector-root-{uuid4().hex[:8]}",
        email="vector-root@t.test",
        tenant=tenant,
        is_superuser=True,
        is_staff=True,
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    return _login_client(user)


@pytest.fixture
def clean_row(db):
    SystemArtifactVectorSettings.objects.all().delete()
    yield
    SystemArtifactVectorSettings.objects.all().delete()


class TestRegistry:
    def test_pgvector_is_registered(self) -> None:
        assert "pgvector" in VECTOR_BACKEND_REGISTRY

    def test_registration_is_the_extension_point(self) -> None:
        class FakePlugin(VectorBackendPlugin):
            name = "fake"
            capabilities = VectorBackendCapabilities(search=True)

            @classmethod
            def create_search_port(cls) -> Any:
                return PgVectorVectorPort()

        register_vector_backend("fake")(FakePlugin)
        try:
            assert VECTOR_BACKEND_REGISTRY["fake"] is FakePlugin
        finally:
            VECTOR_BACKEND_REGISTRY.pop("fake", None)

    def test_unknown_selector_degrades_to_pgvector(
        self, monkeypatch: pytest.MonkeyPatch, clean_row: None
    ) -> None:
        monkeypatch.setenv("ARTIFACT_VECTOR_BACKEND", "does-not-exist")
        assert resolve_artifact_vector_backend_name() == "does-not-exist"
        assert vector_backend_diagnostic() == {
            "requested": "does-not-exist",
            "active": "pgvector",
            "reason": "unknown_artifact_vector_backend",
        }


class TestService:
    def test_read_never_creates_a_row(self, clean_row: None) -> None:
        result = ArtifactVectorSettingsService().get_effective_settings()
        assert result["vector_backend"] is None
        assert SystemArtifactVectorSettings.objects.count() == 0

    def test_db_override_wins_over_env(
        self, monkeypatch: pytest.MonkeyPatch, clean_row: None
    ) -> None:
        monkeypatch.setenv("ARTIFACT_VECTOR_BACKEND", "pgvector")
        service = ArtifactVectorSettingsService()
        service.update_settings({"vector_backend": "qdrant"})

        assert resolve_artifact_vector_backend_name() == "qdrant"
        assert service.get_effective_settings()["effective_vector_backend"] == "qdrant"

    def test_backend_is_decoupled_from_memory(self, clean_row: None) -> None:
        """A vector-store write must never touch the memory settings row."""
        from memory.models import SystemMemorySettings

        SystemMemorySettings.objects.all().delete()
        ArtifactVectorSettingsService().update_settings({"vector_backend": "qdrant"})
        assert SystemMemorySettings.objects.count() == 0

    def test_options_roundtrip_and_secret_is_write_only(self, clean_row: None) -> None:
        service = ArtifactVectorSettingsService()
        service.update_settings(
            {
                "vector_backend": "qdrant",
                "backend_options": {"qdrant": {"base_url": "http://qdrant:6333"}},
                "backend_secrets": {"qdrant": {"api_key": "super-secret"}},
            }
        )
        result = service.get_effective_settings()
        block = result["backends"]["qdrant"]
        assert block["values"]["base_url"] == "http://qdrant:6333"
        assert block["secrets_set"]["api_key"] is True
        # Never returned, in any field.
        assert "super-secret" not in str(result)

    def test_an_empty_secret_keeps_the_stored_one(self, clean_row: None) -> None:
        service = ArtifactVectorSettingsService()
        service.update_settings(
            {"backend_secrets": {"qdrant": {"api_key": "keep-me"}}}
        )
        service.update_settings({"backend_secrets": {"qdrant": {"api_key": ""}}})
        row = SystemArtifactVectorSettings.objects.get()
        assert row.backend_secrets["qdrant"]["api_key"] == "keep-me"

    def test_unknown_backend_is_rejected(self, clean_row: None) -> None:
        with pytest.raises(ArtifactVectorSettingsValidationError) as exc:
            ArtifactVectorSettingsService().update_settings(
                {"vector_backend": "nope"}
            )
        assert exc.value.details[0]["field"] == "vector_backend"

    def test_schema_violations_are_rejected(self, clean_row: None) -> None:
        with pytest.raises(ArtifactVectorSettingsValidationError) as exc:
            ArtifactVectorSettingsService().update_settings(
                {
                    "backend_options": {
                        "qdrant": {
                            "distance": "not-a-distance",
                            "timeout": -1,
                            "unknown": "x",
                        }
                    }
                }
            )
        fields = {detail["field"] for detail in exc.value.details}
        assert "backend_options.qdrant.distance" in fields
        assert "backend_options.qdrant.timeout" in fields
        assert "backend_options.qdrant.unknown" in fields

    def test_reset_clears_the_override(self, clean_row: None) -> None:
        service = ArtifactVectorSettingsService()
        service.update_settings({"vector_backend": "qdrant"})
        result = service.reset_settings()
        assert result["vector_backend"] is None
        assert result["backends"]["qdrant"]["is_override"]["base_url"] is False


class TestRest:
    def test_unauthenticated_is_rejected(self, clean_row: None) -> None:
        assert APIClient().get(_ADMIN_URL).status_code in (401, 403)

    def test_system_admin_can_read(
        self, admin_api_client: APIClient, clean_row: None
    ) -> None:
        response = admin_api_client.get(_ADMIN_URL)
        assert response.status_code == 200
        body = response.json()
        assert body["effective_vector_backend"] in {"pgvector", "qdrant"}
        assert "diagnostic" in body
        assert "qdrant" in body["backends"]

    def test_tenant_admin_without_superuser_cannot_write(
        self, admin_api_client: APIClient, clean_row: None
    ) -> None:
        response = admin_api_client.put(
            _ADMIN_URL, {"vector_backend": "qdrant"}, format="json"
        )
        # The read gate is tenant-admin; the write gate is a Django superuser.
        assert response.status_code == 403

    def test_superuser_roundtrip(
        self, superuser_api_client: APIClient, clean_row: None
    ) -> None:
        response = superuser_api_client.put(
            _ADMIN_URL,
            {
                "vector_backend": "qdrant",
                "backend_options": {"qdrant": {"base_url": "http://qdrant:6333"}},
            },
            format="json",
        )
        assert response.status_code == 200, response.content
        assert response.json()["vector_backend"] == "qdrant"

        reset = superuser_api_client.post(f"{_ADMIN_URL}reset/", {}, format="json")
        assert reset.status_code == 200
        assert reset.json()["vector_backend"] is None


class TestHealthAndChecks:
    """The production API-key gate must see the DB override, not only the env."""

    def test_check_sees_the_db_selector(
        self, monkeypatch: pytest.MonkeyPatch, clean_row: None
    ) -> None:
        from memory.checks import qdrant_artifact_backend_selected

        monkeypatch.delenv("ARTIFACT_VECTOR_BACKEND", raising=False)
        ArtifactVectorSettingsService().update_settings({"vector_backend": "qdrant"})
        assert qdrant_artifact_backend_selected() is True

    def test_check_sees_the_db_secret(
        self, monkeypatch: pytest.MonkeyPatch, clean_row: None
    ) -> None:
        from memory.checks import _qdrant_api_key_configured

        monkeypatch.delenv("QDRANT_API_KEY", raising=False)
        ArtifactVectorSettingsService().update_settings(
            {"backend_secrets": {"qdrant": {"api_key": "db-only-key"}}}
        )
        assert _qdrant_api_key_configured() is True
