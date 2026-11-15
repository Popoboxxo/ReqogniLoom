"""Issue #1792 (S3) — the MCP tool ``artifact.summary``.

The service behind it is covered in
``application/tests/test_artifact_summary_service.py`` and the REST twin in
``rest_api/tests/test_artifact_summary_1792.py``; this module pins the *MCP
surface*:

* the advertised contract (name, read classification, strict schema),
* dispatch behaviour (missing/malformed ``artifact_id``, unknown artifact),
* the two typed parameters -- ``refresh`` is a **strict** boolean (the string
  ``"false"`` is a caller error, never a silent LLM call) and ``depth`` is
  clamped to ``1..2`` like REST, not rejected,
* the degradation path (flag off answers ``degraded_reason="disabled"`` with no
  provider call) and the payload parity with the REST channel (one field set,
  asserted against the REST serializer itself),
* the workspace fence: an artifact of a workspace the caller holds no role in is
  denied by the dispatch gate *before* the handler runs,
* the shared spend ceiling: ``artifact_summary`` is resolved through
  ``admin_ops.rate_limits``, so REST and MCP cannot drift apart.

``artifact.summary`` is a read tool: nothing is persisted and no audit entry is
written (REQ-L2-MC-012), even though one call may cost one provider call.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from application.artifact_summary_service import ArtifactSummaryService
from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.cross_cutting import CrossCuttingToolGroup
from mcp_server.workspace_scope import resolve_target_workspace_id
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Tenant, User, Workspace
from persistence.tests.factories import (
    assign_role,
    make_requirement,
    make_user,
    make_workspace,
)

pytestmark = pytest.mark.django_db

API_KEY = "reqlo_test_key"
SUMMARY_TEXT = "Zwei Anforderungen betreffen die Anmeldung."

_CACHE_OVERRIDE = override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "artifact-summary-mcp-test",
        }
    },
    ARTIFACT_SUMMARY_ENABLED=True,
)

#: Spec §5.7 wire contract, restated on the MCP side. The parity test below
#: additionally compares this against the REST serializer's own field names, so
#: a field added on one channel only cannot pass unnoticed.
_SUMMARY_FIELDS = {
    "artifact_id",
    "artifact_type",
    "summary",
    "degraded",
    "degraded_reason",
    "cache_hit",
    "trace_depth",
    "neighbour_count",
    "omitted_neighbours",
    "generated_at",
}


class _CountingProvider:
    """Credential-free stand-in for a real provider; counts its calls."""

    PROVIDER_NAME = "counting"

    def __init__(self, text: str = SUMMARY_TEXT) -> None:
        self.text = text
        self.calls: list[Any] = []

    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        self.calls.append(prompt)
        return self.text


@pytest.fixture(autouse=True)
def _cache() -> Iterator[None]:
    """Isolate the summary cache and the rate buckets per test."""
    with _CACHE_OVERRIDE:
        cache.clear()
        try:
            yield
        finally:
            cache.clear()
            clear_request_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(
        name="Summary MCP", slug=f"summary-mcp-{uuid.uuid4().hex[:8]}"
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return make_workspace(tenant, name="summary-mcp-ws")
    finally:
        clear_request_tenant()


@pytest.fixture
def caller(tenant: Tenant, workspace: Workspace) -> User:
    """An Editor in *workspace* -- the role the summary service resolves."""
    set_request_tenant(tenant.id)
    try:
        user = make_user(tenant)
        assign_role(user, workspace, "editor")
    finally:
        clear_request_tenant()
    return user


def _context(tenant: Tenant, user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid.uuid4(),
    )


@pytest.fixture
def ctx(tenant: Tenant, caller: User) -> AuthContext:
    return _context(tenant, caller)


@pytest.fixture
def requirement(workspace: Workspace):
    set_request_tenant(workspace.tenant_id)
    try:
        return make_requirement(
            workspace,
            uid="REQ-L1-001",
            title="Anmeldung per OAuth",
            description="Das System authentifiziert Nutzer per OAuth 2.0.",
        )
    finally:
        clear_request_tenant()


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> _CountingProvider:
    fake = _CountingProvider()
    monkeypatch.setattr("llm_adapter.providers.get_provider", lambda *a, **k: fake)
    return fake


def _call(
    params: dict[str, Any],
    ctx: AuthContext,
    *,
    service: ArtifactSummaryService | None = None,
):
    group = CrossCuttingToolGroup(summary_service=service)
    return group.execute_tool(
        tool_name="artifact.summary",
        params=params,
        auth_context=ctx,
        api_key=API_KEY,
    )


# ---------------------------------------------------------------------------
# Advertised contract
# ---------------------------------------------------------------------------


def test_schema_is_the_documented_read_contract() -> None:
    schemas = {s["name"]: s for s in CrossCuttingToolGroup().get_tool_schemas()}
    assert "artifact.summary" in schemas, sorted(schemas)

    schema = schemas["artifact.summary"]
    input_schema = schema["inputSchema"]
    properties = input_schema["properties"]

    assert input_schema["required"] == ["artifact_id"]
    assert properties["artifact_id"]["type"] == "string"
    assert properties["refresh"]["type"] == "boolean"
    assert properties["depth"]["type"] == "integer"
    # The description must carry the "degraded is not an error" contract, or an
    # agent will read a degraded answer as a failure.
    assert "degraded" in schema["description"]


def test_registry_classifies_it_as_a_read_tool() -> None:
    """A read, not a write: no WRITE RBAC gate, no audit entry."""
    assert ToolRegistry()._is_write_tool("artifact.summary") is False


def test_manifest_lists_it_once_as_read_and_the_count_moved_to_294() -> None:
    from mcp_server.management.commands.export_tool_manifest import build_manifest

    manifest = build_manifest()
    entries = [t for t in manifest["tools"] if t["name"] == "artifact.summary"]

    assert len(entries) == 1, entries
    assert entries[0]["prefix"] == "artifact"
    assert entries[0]["is_write"] is False
    # Issue #1792 / S3: 293 -> 294. Documented in six places, gated by
    # test_tool_manifest_drift.py and the two doc-surface guards.
    assert manifest["tool_count"] == 294
    assert manifest["tool_count"] == len(manifest["tools"])


# ---------------------------------------------------------------------------
# Dispatch / parameter validation
# ---------------------------------------------------------------------------


def test_missing_artifact_id_is_a_validation_error(ctx: AuthContext) -> None:
    result = _call({}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "artifact_id" in result.message


def test_malformed_artifact_id_is_a_validation_error(ctx: AuthContext) -> None:
    service = MagicMock()
    result = _call({"artifact_id": "not-a-uuid"}, ctx, service=service)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    service.summarize_artifact.assert_not_called()


def test_unknown_artifact_is_not_found(ctx: AuthContext) -> None:
    result = _call({"artifact_id": str(uuid.uuid4())}, ctx)

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


@pytest.mark.parametrize("value", ["false", "true", 0, 1, [], {}])
def test_refresh_must_be_a_real_boolean(ctx: AuthContext, value: object) -> None:
    """A string ``"false"`` cannot silently switch on a paid call."""
    service = MagicMock()
    result = _call(
        {"artifact_id": str(uuid.uuid4()), "refresh": value}, ctx, service=service
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "refresh" in result.message
    service.summarize_artifact.assert_not_called()


@pytest.mark.parametrize("value", ["abc", True, False, 1.5, [], {}])
def test_depth_must_be_an_integer(ctx: AuthContext, value: object) -> None:
    """``True`` must not silently mean depth 1 (``bool`` is an ``int``)."""
    service = MagicMock()
    result = _call(
        {"artifact_id": str(uuid.uuid4()), "depth": value}, ctx, service=service
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "depth" in result.message
    service.summarize_artifact.assert_not_called()


# ---------------------------------------------------------------------------
# Happy path / payload parity
# ---------------------------------------------------------------------------


def test_payload_is_the_rest_field_set(
    ctx: AuthContext, requirement, provider: _CountingProvider
) -> None:
    # Imported here, not at module level: this is the one test that reads the
    # REST channel, and it does so only to prove the two channels share a
    # contract (a field added on one side must not pass unnoticed).
    from rest_api.summary_views import ArtifactSummarySerializer

    result = _call({"artifact_id": str(requirement.artifact_id)}, ctx)

    assert result.success is True, result.message
    payload = result.data
    assert set(payload) == _SUMMARY_FIELDS
    assert set(payload) == set(ArtifactSummarySerializer().fields)

    assert payload["artifact_id"] == str(requirement.artifact_id)
    assert payload["artifact_type"] == "Requirement"
    assert payload["summary"] == SUMMARY_TEXT
    assert payload["degraded"] is False
    assert payload["degraded_reason"] is None
    assert payload["cache_hit"] is False
    assert payload["trace_depth"] == 1
    assert len(provider.calls) == 1


def test_second_call_is_a_cache_hit_without_a_provider_call(
    ctx: AuthContext, requirement, provider: _CountingProvider
) -> None:
    _call({"artifact_id": str(requirement.artifact_id)}, ctx)
    second = _call({"artifact_id": str(requirement.artifact_id)}, ctx)

    assert second.success is True, second.message
    assert second.data["cache_hit"] is True
    assert len(provider.calls) == 1


def test_refresh_true_regenerates(
    ctx: AuthContext, requirement, provider: _CountingProvider
) -> None:
    _call({"artifact_id": str(requirement.artifact_id)}, ctx)
    refreshed = _call(
        {"artifact_id": str(requirement.artifact_id), "refresh": True}, ctx
    )

    assert refreshed.success is True, refreshed.message
    assert refreshed.data["cache_hit"] is False
    assert len(provider.calls) == 2


# ---------------------------------------------------------------------------
# Depth clamping (REST parity)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("requested", "expected"),
    [(0, 1), (1, 1), (2, 2), (7, 2), ("2", 2)],
)
def test_depth_is_clamped_not_rejected(
    ctx: AuthContext,
    requirement,
    provider: _CountingProvider,
    requested: Any,
    expected: int,
) -> None:
    result = _call({"artifact_id": str(requirement.artifact_id), "depth": requested}, ctx)

    assert result.success is True, result.message
    assert result.data["trace_depth"] == expected


# ---------------------------------------------------------------------------
# Degradation instead of failure
# ---------------------------------------------------------------------------


def test_disabled_flag_degrades_without_a_provider_call(
    ctx: AuthContext, requirement, provider: _CountingProvider
) -> None:
    with override_settings(ARTIFACT_SUMMARY_ENABLED=False):
        result = _call({"artifact_id": str(requirement.artifact_id)}, ctx)

    assert result.success is True, result.message
    assert result.data["degraded"] is True
    assert result.data["degraded_reason"] == "disabled"
    assert result.data["summary"] is None
    # The switch answers before any payload work or provider resolution.
    assert provider.calls == []


def test_a_provider_failure_degrades_instead_of_failing(
    ctx: AuthContext, requirement
) -> None:
    broken = _CountingProvider()

    def _raise(*_args, **_kwargs):
        broken.calls.append("call")
        raise RuntimeError("provider down")

    broken.complete = _raise  # type: ignore[method-assign]
    with patch("llm_adapter.providers.get_provider", lambda *a, **k: broken):
        result = _call({"artifact_id": str(requirement.artifact_id)}, ctx)

    assert result.success is True, result.message
    assert result.data["degraded"] is True
    assert result.data["degraded_reason"] == "provider_unavailable"
    assert broken.calls == ["call"]


# ---------------------------------------------------------------------------
# Workspace fence
# ---------------------------------------------------------------------------


def test_target_workspace_is_resolved_from_the_artifact_id(
    tenant: Tenant, workspace: Workspace, requirement
) -> None:
    """The dispatcher needs the owning workspace; ``artifact_id`` must supply it."""
    set_request_tenant(tenant.id)
    try:
        resolved = resolve_target_workspace_id(
            "artifact.summary", {"artifact_id": str(requirement.artifact_id)}
        )
    finally:
        clear_request_tenant()

    assert resolved == str(workspace.id)


def test_foreign_workspace_is_denied_before_the_handler(
    e2e_tenant: Tenant,
    e2e_workspace: Workspace,
    e2e_userrole_member,
    e2e_api_key_member: str,
) -> None:
    """A member of workspace A must not read a summary of workspace B.

    The denial has to come from the dispatch gate: the handler would otherwise
    answer ``PERMISSION_DENIED`` from the service too, and the difference is
    exactly whether the caller-supplied id ever reached domain code.
    """
    set_request_tenant(e2e_tenant.id)
    try:
        foreign = Workspace.objects.create(tenant=e2e_tenant, name="Foreign WS B")
        foreign_artifact = Artifact.objects.create(
            tenant=e2e_tenant, workspace=foreign, artifact_type="Requirement"
        )
    finally:
        clear_request_tenant()

    with patch.object(
        ArtifactSummaryService, "summarize_artifact"
    ) as summarize:
        result = ToolRegistry().dispatch_request(
            tool_name="artifact.summary",
            params={"artifact_id": str(foreign_artifact.id)},
            api_key=e2e_api_key_member,
        )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    summarize.assert_not_called()


def test_own_workspace_is_admitted(
    e2e_tenant: Tenant,
    e2e_workspace: Workspace,
    e2e_userrole_member,
    e2e_api_key_member: str,
) -> None:
    """The gate must not lock a member out of their own workspace."""
    set_request_tenant(e2e_tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=e2e_tenant, workspace=e2e_workspace, artifact_type="Requirement"
        )
    finally:
        clear_request_tenant()

    # Flag off keeps this a pure gate test: no provider is configured here.
    with override_settings(ARTIFACT_SUMMARY_ENABLED=False):
        result = ToolRegistry().dispatch_request(
            tool_name="artifact.summary",
            params={"artifact_id": str(artifact.id)},
            api_key=e2e_api_key_member,
        )

    assert result.success is True, result.message
    assert result.data["degraded_reason"] == "disabled"


# ---------------------------------------------------------------------------
# Rate parity with REST
# ---------------------------------------------------------------------------


def test_the_shared_artifact_summary_scope_limits_the_tool(
    ctx: AuthContext, requirement
) -> None:
    """The 61st call in an hour is RATE_LIMITED -- same config as REST."""
    params = {"artifact_id": str(requirement.artifact_id)}

    with override_settings(ARTIFACT_SUMMARY_ENABLED=False), patch(
        "admin_ops.rate_limits.resolve_rate", return_value="2/hour"
    ):
        first = _call(params, ctx)
        second = _call(params, ctx)
        third = _call(params, ctx)

    assert first.success is True, first.message
    assert second.success is True, second.message
    assert third.success is False
    assert third.error_code == "RATE_LIMITED"
