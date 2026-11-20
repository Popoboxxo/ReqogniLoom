"""A memory provider is a plugin: registry + schema, no core edits.

This test pins the abstraction's acceptance criterion from
``docs/concepts/memory-provider-abstraction.md``: a backend added to
``MEMORY_BACKEND_REGISTRY`` becomes selectable in the settings API and is
configurable through its declared ``settings_schema`` — without touching
``memory_rest``, the settings service or the MCP layer.

The dummy is registered only for the duration of the test and removed in a
``finally`` so the global conformance test (``test_every_registered_backend_has_
conformance_fixture``) still sees the real registry.
"""
from __future__ import annotations

import pytest

from memory.backends import (
    MEMORY_BACKEND_REGISTRY,
    BackendSettingField,
    MemoryBackend,
    MemoryCapabilities,
)

pytestmark = pytest.mark.django_db


class _DummyPluginBackend(MemoryBackend):
    """Minimal declaration-only adapter.

    The abstract store methods are deliberately left unimplemented: nothing in
    this test instantiates the backend, only the registry/schema surfaces are
    exercised (which is exactly what a new provider needs before its store is
    written).
    """

    capabilities = MemoryCapabilities(dialectic=False, search=False)
    settings_key = "plugin_dummy"
    settings_schema = (
        BackendSettingField("base_url", "str", "PLUGIN_DUMMY_BASE_URL"),
        BackendSettingField("api_key", "secret", "PLUGIN_DUMMY_API_KEY"),
    )


@pytest.fixture()
def dummy_plugin():
    MEMORY_BACKEND_REGISTRY["plugin_dummy"] = _DummyPluginBackend
    try:
        yield _DummyPluginBackend
    finally:
        MEMORY_BACKEND_REGISTRY.pop("plugin_dummy", None)


def test_registry_provider_is_selectable_in_the_settings_serializer(dummy_plugin):
    from memory.memory_rest import SystemMemorySettingsWriteSerializer

    serializer = SystemMemorySettingsWriteSerializer(
        data={"memory_backend": "plugin_dummy"}
    )

    assert serializer.is_valid(), serializer.errors


def test_builtin_backends_stay_selectable() -> None:
    from memory.memory_rest import SystemMemorySettingsWriteSerializer

    choices = set(SystemMemorySettingsWriteSerializer().fields["memory_backend"].choices)

    assert {"pgvector", "honcho", "qdrant"} <= choices


def test_declared_schema_drives_validation_and_the_admin_payload(dummy_plugin):
    from application.memory_settings_service import MemorySettingsService

    valid = MemorySettingsService._validate_backend_maps(
        {"plugin_dummy": {"base_url": "http://memory.internal"}}, None
    )
    assert valid == []

    unknown = MemorySettingsService._validate_backend_maps(
        {"plugin_dummy": {"nope": "x"}}, None
    )
    assert unknown, "an undeclared field must be rejected"

    payload = MemorySettingsService().backends_payload()
    assert "plugin_dummy" in payload
    schema_names = [field["name"] for field in payload["plugin_dummy"]["schema"]]
    assert schema_names == ["base_url", "api_key"]
    assert payload["plugin_dummy"]["capabilities"]["dialectic"] is False


def test_optional_provider_hooks_are_declared_on_the_port() -> None:
    # Every optional extension point must exist on the base class with a
    # no-op default, so an adapter overrides only the ones it needs and an
    # existing backend stays valid.
    assert callable(MemoryBackend.webhook_route)
    assert callable(MemoryBackend.verify_webhook)
    assert callable(MemoryBackend.provision_tenant)
    assert callable(MemoryBackend.teardown_tenant)
    assert _DummyPluginBackend.webhook_route.__qualname__.endswith("MemoryBackend.webhook_route")
