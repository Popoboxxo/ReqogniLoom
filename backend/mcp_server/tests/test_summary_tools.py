"""Issue #1793 (S6) — the MCP tool group ``summary``.

Two tools, deliberately split (spec §9/E9): ``summary.get`` reads the last
*stored* ``ArtifactSummary`` state and is free, ``summary.refresh`` spends at
most one provider call and is a write. This module pins the MCP surface:

* the advertised contract (names, required ``workspace_id``, read/write
  classification, manifest count 294 -> 296, new prefix ``summary``),
* the scope rule — ``artifact_type`` and ``artifact_id`` are mutually
  exclusive, and a refresh must name exactly one of them,
* the read path (list / one type / one artifact scope, empty scopes, stale
  computation, the REST-identical field set),
* the manual-run gates (on-demand switch, day budget, agent key, throttle) and
  that they *bypass the cadence* rather than the brakes,
* workspace fencing at the dispatcher (foreign workspace denied before the
  handler, viewer cannot refresh).

The REST twin lives in ``rest_api/tests/test_artifact_summary_1793.py``; both
channels share the payload builder, asserted here against the REST serializer.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from application.artifact_summary_service import (
    MAX_SUMMARY_ROWS,
    SUMMARY_PAYLOAD_KEYS,
    ArtifactSummaryService,
)
from application.summary_support import ARTIFACT_KIND, TYPE_ROSTER_KIND, upsert_summary
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ApiKey, UserRole
from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.summaries import SummaryToolGroup
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, ArtifactSummary, Tenant, User, Workspace
from persistence.tenancy import TenantContext
from persistence.tests.factories import (
    assign_role,
    make_requirement,
    make_user,
    make_workspace,
)

pytestmark = pytest.mark.django_db

API_KEY = "reqlo_test_key"
STORED_TEXT = "Zehn Anforderungen betreffen die Anmeldung."

_CACHE_OVERRIDE = override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "summary-tools-mcp-test",
        }
    },
    ARTIFACT_SUMMARY_ENABLED=True,
    ARTIFACT_SUMMARY_SWEEP_ENABLED=True,
    ARTIFACT_SUMMARY_AGENT_KEY_ID="",
    SUMMARY_DAILY_TOKEN_LIMIT=0,
    ARTIFACT_SUMMARY_INTERVAL_MINUTES=1440,
    ARTIFACT_SUMMARY_MIN_INTERVAL_MINUTES=60,
    ARTIFACT_SUMMARY_MIN_INTERVAL_SECONDS=3600,
)


@pytest.fixture(autouse=True)
def _state() -> Iterator[None]:
    """Isolate cache, rate buckets and the tenant context between tests."""
    with _CACHE_OVERRIDE:
        cache.clear()
        TenantContext.clear_tenant()
        try:
            yield
        finally:
            cache.clear()
            TenantContext.clear_tenant()
            clear_request_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(
        name="Summary Tools", slug=f"summary-tools-{uuid.uuid4().hex[:8]}"
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return make_workspace(
            tenant, name="summary-tools-ws", summary_sweep_interval_minutes=1440
        )
    finally:
        clear_request_tenant()


@pytest.fixture
def caller(tenant: Tenant, workspace: Workspace) -> User:
    set_request_tenant(tenant.id)
    try:
        user = make_user(tenant)
        assign_role(user, workspace, "editor")
    finally:
        clear_request_tenant()
    return user


@pytest.fixture
def ctx(tenant: Tenant, caller: User) -> AuthContext:
    return AuthContext(
        user_id=caller.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid.uuid4(),
    )


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


def _stored_roster(
    workspace: Workspace,
    artifact_type: str = "Requirement",
    *,
    text: str = STORED_TEXT,
    item_count: int = 10,
    generated_at: Any = None,
    status: str = ArtifactSummary.Status.OK,
    reason: str = "",
) -> ArtifactSummary:
    """Persist one type-roster row through the production helper."""
    TenantContext.set_tenant(workspace.tenant_id)
    try:
        row = upsert_summary(
            workspace=workspace,
            summary_kind=TYPE_ROSTER_KIND,
            artifact_type=artifact_type,
            values={
                "text": text,
                "content_hash": "a" * 64,
                "input_digest": {"item_count": item_count},
                "status": status,
                "reason": reason,
                "provider": "counting",
                "generated_at": generated_at or timezone.now(),
            },
        )
    finally:
        TenantContext.clear_tenant()
    return row


def _agent_key(tenant: Tenant, workspace: Workspace) -> ApiKey:
    """An agent API key the manual run may act under (S5 pattern)."""
    TenantContext.set_tenant(tenant.id)
    try:
        suffix = uuid.uuid4().hex[:8]
        user = User.objects.create(
            username=f"summary-agent-{suffix}",
            email=f"summary-agent-{suffix}@example.com",
            tenant=tenant,
        )
        UserRole.objects.create(
            tenant=tenant, workspace=workspace, user=user, role="editor"
        )
        return ApiKey.objects.create(
            tenant=tenant,
            user=user,
            name="summary-bot",
            key_hash=f"sha256p1:{uuid.uuid4().hex}",
            principal_type="agent",
            agent_label="Summary Bot",
            scope="write",
        )
    finally:
        TenantContext.clear_tenant()


def _call(
    tool_name: str,
    params: dict[str, Any],
    ctx: AuthContext,
    *,
    service: ArtifactSummaryService | None = None,
):
    group = SummaryToolGroup(service=service)
    return group.execute_tool(
        tool_name=tool_name, params=params, auth_context=ctx, api_key=API_KEY
    )


def _call_spy(outcome: str = "summarized"):
    return patch(
        "application.artifact_summary_service.ArtifactSummaryService.summarize_artifact_type",
        return_value=outcome,
    )


# ---------------------------------------------------------------------------
# Advertised contract
# ---------------------------------------------------------------------------


def test_schemas_are_the_documented_contract() -> None:
    schemas = {s["name"]: s for s in SummaryToolGroup().get_tool_schemas()}
    assert set(schemas) == {"summary.get", "summary.refresh"}

    for name, schema in schemas.items():
        input_schema = schema["inputSchema"]
        assert input_schema["required"] == ["workspace_id"], name
        assert input_schema["properties"]["workspace_id"]["type"] == "string"
        assert "artifact_type" in input_schema["properties"]
        assert "artifact_id" in input_schema["properties"]

    # The read tool must say that a degradation is not an error, and the write
    # tool must say that a refused run is an outcome, not a failure.
    assert "degradation is NOT an error" in schemas["summary.get"]["description"]
    assert "skipped:" in schemas["summary.refresh"]["description"]


def test_registry_classifies_read_and_write() -> None:
    registry = ToolRegistry()
    assert registry._is_write_tool("summary.get") is False
    assert registry._is_write_tool("summary.refresh") is True


def test_manifest_keeps_47_prefixes_and_the_current_count() -> None:
    from mcp_server.management.commands.export_tool_manifest import build_manifest

    manifest = build_manifest()
    by_name = {t["name"]: t for t in manifest["tools"]}

    assert by_name["summary.get"]["prefix"] == "summary"
    assert by_name["summary.get"]["is_write"] is False
    assert by_name["summary.refresh"]["prefix"] == "summary"
    assert by_name["summary.refresh"]["is_write"] is True
    # Issue #1793 / S6: 294 -> 296, 46 -> 47 prefixes. The catalogue then kept
    # growing within the same 47 prefixes (R3.2: ``artifact.bulk_update`` moved
    # 296 -> 297 -> 298), which is what the current-size assertion below pins.
    assert manifest["tool_count"] == 298
    assert manifest["tool_count"] == len(manifest["tools"])
    assert len({t["prefix"] for t in manifest["tools"]}) == 47


# ---------------------------------------------------------------------------
# Scope rules
# ---------------------------------------------------------------------------


def test_both_scope_parameters_are_rejected(ctx: AuthContext, workspace: Workspace):
    """``artifact_type`` and ``artifact_id`` name different scopes."""
    params = {
        "workspace_id": str(workspace.id),
        "artifact_type": "Requirement",
        "artifact_id": str(uuid.uuid4()),
    }
    for tool in ("summary.get", "summary.refresh"):
        result = _call(tool, params, ctx)
        assert result.success is False, result.data
        assert result.error_code == "VALIDATION_ERROR"
        assert "at most one" in result.message


def test_refresh_without_a_scope_is_rejected(ctx: AuthContext, workspace: Workspace):
    service = MagicMock()
    result = _call(
        "summary.refresh", {"workspace_id": str(workspace.id)}, ctx, service=service
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "artifact_type" in result.message
    service.list_type_summaries.assert_not_called()


def test_missing_workspace_id_is_a_validation_error(ctx: AuthContext):
    result = _call("summary.get", {}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "workspace_id" in result.message


def test_malformed_workspace_id_is_a_validation_error(ctx: AuthContext):
    result = _call("summary.get", {"workspace_id": "not-a-uuid"}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_artifact_type_must_be_a_string(ctx: AuthContext, workspace: Workspace):
    result = _call(
        "summary.get",
        {"workspace_id": str(workspace.id), "artifact_type": ["Requirement"]},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "artifact_type" in result.message


# ---------------------------------------------------------------------------
# Read path
# ---------------------------------------------------------------------------


def test_get_without_scope_lists_every_stored_type(
    ctx: AuthContext, workspace: Workspace
):
    _stored_roster(workspace, "Requirement", text="reqs")
    _stored_roster(workspace, "Risk", text="risks", item_count=3)

    result = _call("summary.get", {"workspace_id": str(workspace.id)}, ctx)

    assert result.success is True, result.message
    payload = result.data
    assert payload["workspace_id"] == str(workspace.id)
    assert payload["count"] == 2
    assert payload["truncated"] is False
    assert payload["limit"] == MAX_SUMMARY_ROWS
    types = [row["artifact_type"] for row in payload["summaries"]]
    assert types == ["Requirement", "Risk"]
    assert payload["summaries"][0]["text"] == "reqs"


def test_one_scope_payload_is_the_rest_field_set(
    ctx: AuthContext, workspace: Workspace
):
    from rest_api.summary_views import StoredSummarySerializer

    _stored_roster(workspace, "Requirement")

    result = _call(
        "summary.get",
        {"workspace_id": str(workspace.id), "artifact_type": "Requirement"},
        ctx,
    )

    assert result.success is True, result.message
    payload = result.data
    assert set(payload) == set(SUMMARY_PAYLOAD_KEYS)
    assert set(payload) == set(StoredSummarySerializer().fields)
    assert payload["summary_kind"] == TYPE_ROSTER_KIND
    assert payload["artifact_type"] == "Requirement"
    assert payload["text"] == STORED_TEXT
    assert payload["item_count"] == 10
    assert payload["reason"] is None
    assert payload["stale"] is False
    assert payload["status"] == "ok"


def test_a_never_summarised_type_is_empty_not_an_error(
    ctx: AuthContext, workspace: Workspace
):
    result = _call(
        "summary.get",
        {"workspace_id": str(workspace.id), "artifact_type": "Risk"},
        ctx,
    )

    assert result.success is True, result.message
    payload = result.data
    assert payload["text"] is None
    assert payload["item_count"] == 0
    assert payload["reason"] is None
    assert payload["stale"] is False


def test_artifact_scope_reads_the_stored_row(
    ctx: AuthContext, workspace: Workspace, requirement
):
    TenantContext.set_tenant(workspace.tenant_id)
    try:
        artifact = Artifact.objects.get(id=requirement.artifact_id)
        upsert_summary(
            workspace=workspace,
            summary_kind=ARTIFACT_KIND,
            artifact=artifact,
            values={
                "text": "one artifact",
                "content_hash": "b" * 64,
                "input_digest": {"item_count": 1},
                "status": ArtifactSummary.Status.OK,
                "generated_at": timezone.now(),
            },
        )
    finally:
        TenantContext.clear_tenant()

    result = _call(
        "summary.get",
        {"workspace_id": str(workspace.id), "artifact_id": str(requirement.artifact_id)},
        ctx,
    )

    assert result.success is True, result.message
    assert result.data["summary_kind"] == ARTIFACT_KIND
    assert result.data["artifact_id"] == str(requirement.artifact_id)
    assert result.data["text"] == "one artifact"


def test_artifact_of_another_workspace_is_not_found(
    ctx: AuthContext, tenant: Tenant, workspace: Workspace
):
    set_request_tenant(tenant.id)
    try:
        foreign = Workspace.objects.create(tenant=tenant, name="Foreign summary WS")
        foreign_artifact = Artifact.objects.create(
            tenant=tenant, workspace=foreign, artifact_type="Requirement"
        )
    finally:
        clear_request_tenant()

    result = _call(
        "summary.get",
        {"workspace_id": str(workspace.id), "artifact_id": str(foreign_artifact.id)},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_a_stored_state_past_twice_the_cadence_is_stale(
    ctx: AuthContext, workspace: Workspace
):
    _stored_roster(
        workspace,
        "Requirement",
        generated_at=timezone.now() - timedelta(days=3),
    )

    result = _call(
        "summary.get",
        {"workspace_id": str(workspace.id), "artifact_type": "Requirement"},
        ctx,
    )

    assert result.success is True, result.message
    assert result.data["stale"] is True
    assert result.data["reason"] == "stale"


def test_a_switched_off_sweep_makes_every_stored_state_stale(
    ctx: AuthContext, workspace: Workspace
):
    _stored_roster(workspace, "Requirement", generated_at=timezone.now())

    with override_settings(ARTIFACT_SUMMARY_SWEEP_ENABLED=False):
        result = _call(
            "summary.get",
            {"workspace_id": str(workspace.id), "artifact_type": "Requirement"},
            ctx,
        )

    assert result.success is True, result.message
    assert result.data["stale"] is True
    assert result.data["reason"] == "stale"


# ---------------------------------------------------------------------------
# Refresh gates
# ---------------------------------------------------------------------------


def _enable(settings, *, key: ApiKey | None = None) -> None:
    settings.ARTIFACT_SUMMARY_ENABLED = True
    settings.ARTIFACT_SUMMARY_SWEEP_ENABLED = False
    settings.SUMMARY_DAILY_TOKEN_LIMIT = 0
    settings.ARTIFACT_SUMMARY_AGENT_KEY_ID = str(key.id) if key is not None else ""


def test_refresh_flag_off_is_a_skip_without_a_call(
    settings, ctx: AuthContext, tenant: Tenant, workspace: Workspace
):
    _enable(settings, key=_agent_key(tenant, workspace))
    settings.ARTIFACT_SUMMARY_ENABLED = False

    with _call_spy() as summarize:
        result = _call(
            "summary.refresh",
            {"workspace_id": str(workspace.id), "artifact_type": "Requirement"},
            ctx,
        )

    assert result.success is True, result.message
    assert result.data["outcome"] == "skipped:flag_off"
    assert result.data["reason"] is None
    summarize.assert_not_called()


def test_refresh_bypasses_the_cadence_but_keeps_the_brakes(
    settings, ctx: AuthContext, tenant: Tenant, workspace: Workspace
):
    """Sweep flag off + workspace interval 0 must still allow a manual run."""
    settings.ARTIFACT_SUMMARY_SWEEP_ENABLED = False
    workspace.summary_sweep_interval_minutes = 0
    workspace.save(update_fields=["summary_sweep_interval_minutes"])
    _enable(settings, key=_agent_key(tenant, workspace))

    with _call_spy("summarized") as summarize:
        result = _call(
            "summary.refresh",
            {"workspace_id": str(workspace.id), "artifact_type": "Requirement"},
            ctx,
        )

    assert result.success is True, result.message
    assert result.data["outcome"] == "summarized"
    summarize.assert_called_once()


def test_refresh_respects_the_summary_day_budget(
    settings, ctx: AuthContext, tenant: Tenant, workspace: Workspace
):
    _enable(settings, key=_agent_key(tenant, workspace))

    with patch(
        "application.artifact_summary_sweep.summary_budget_exhausted",
        return_value=True,
    ), _call_spy() as summarize:
        result = _call(
            "summary.refresh",
            {"workspace_id": str(workspace.id), "artifact_type": "Requirement"},
            ctx,
        )

    assert result.success is True, result.message
    assert result.data["outcome"] == "skipped:budget_exhausted"
    summarize.assert_not_called()


def test_refresh_without_an_agent_key_does_not_run(
    settings, ctx: AuthContext, workspace: Workspace
):
    _enable(settings, key=None)

    with _call_spy() as summarize:
        result = _call(
            "summary.refresh",
            {"workspace_id": str(workspace.id), "artifact_type": "Requirement"},
            ctx,
        )

    assert result.success is True, result.message
    assert result.data["outcome"] == "skipped:no_agent_key"
    summarize.assert_not_called()


def test_a_second_refresh_inside_the_min_interval_is_throttled(
    settings, ctx: AuthContext, tenant: Tenant, workspace: Workspace
):
    _enable(settings, key=_agent_key(tenant, workspace))

    with _call_spy("summarized") as summarize:
        first = _call(
            "summary.refresh",
            {"workspace_id": str(workspace.id), "artifact_type": "Requirement"},
            ctx,
        )
        second = _call(
            "summary.refresh",
            {"workspace_id": str(workspace.id), "artifact_type": "Requirement"},
            ctx,
        )

    assert first.data["outcome"] == "summarized"
    assert second.data["outcome"] == "skipped:throttled"
    assert summarize.call_count == 1


def test_artifact_refresh_is_the_on_demand_summary(
    settings, ctx: AuthContext, tenant: Tenant, workspace: Workspace, requirement
):
    """``artifact_id`` delegates to the cache-only artifact summary (S1)."""
    _enable(settings, key=_agent_key(tenant, workspace))

    with patch.object(
        ArtifactSummaryService,
        "summarize_artifact",
        return_value=MagicMock(as_payload=lambda: {"summary": "text"}),
    ) as summarize:
        result = _call(
            "summary.refresh",
            {
                "workspace_id": str(workspace.id),
                "artifact_id": str(requirement.artifact_id),
            },
            ctx,
        )

    assert result.success is True, result.message
    assert result.data == {"summary": "text"}
    summarize.assert_called_once()
    assert summarize.call_args.kwargs["refresh"] is True


def test_the_shared_artifact_summary_scope_limits_the_refresh(
    ctx: AuthContext, tenant: Tenant, workspace: Workspace
):
    """The 3rd call in an hour is RATE_LIMITED -- same config as REST."""
    params = {"workspace_id": str(workspace.id), "artifact_type": "Requirement"}

    with patch("admin_ops.rate_limits.resolve_rate", return_value="2/hour"), patch(
        "application.artifact_summary_service.ArtifactSummaryService.refresh_type_summary",
        return_value={"text": "x"},
    ):
        first = _call("summary.refresh", params, ctx)
        second = _call("summary.refresh", params, ctx)
        third = _call("summary.refresh", params, ctx)

    assert first.success is True, first.message
    assert second.success is True, second.message
    assert third.success is False
    assert third.error_code == "RATE_LIMITED"


# ---------------------------------------------------------------------------
# Workspace fence (dispatcher)
# ---------------------------------------------------------------------------


def test_get_is_admitted_in_the_own_workspace(
    e2e_tenant: Tenant,
    e2e_workspace: Workspace,
    e2e_userrole_member,
    e2e_api_key_member: str,
):
    result = ToolRegistry().dispatch_request(
        tool_name="summary.get",
        params={"workspace_id": str(e2e_workspace.id)},
        api_key=e2e_api_key_member,
    )

    assert result.success is True, result.message
    assert result.data["count"] == 0


def test_get_of_a_foreign_workspace_is_denied_before_the_handler(
    e2e_tenant: Tenant,
    e2e_workspace: Workspace,
    e2e_userrole_member,
    e2e_api_key_member: str,
):
    set_request_tenant(e2e_tenant.id)
    try:
        foreign = Workspace.objects.create(tenant=e2e_tenant, name="Foreign WS")
    finally:
        clear_request_tenant()

    with patch.object(
        ArtifactSummaryService, "list_type_summaries"
    ) as list_summaries:
        result = ToolRegistry().dispatch_request(
            tool_name="summary.get",
            params={"workspace_id": str(foreign.id)},
            api_key=e2e_api_key_member,
        )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    list_summaries.assert_not_called()


def test_a_viewer_cannot_refresh(
    e2e_workspace: Workspace, e2e_userrole_viewer, e2e_api_key_viewer: str
):
    with patch.object(
        ArtifactSummaryService, "refresh_type_summary"
    ) as refresh:
        result = ToolRegistry().dispatch_request(
            tool_name="summary.refresh",
            params={
                "workspace_id": str(e2e_workspace.id),
                "artifact_type": "Requirement",
            },
            api_key=e2e_api_key_viewer,
        )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    refresh.assert_not_called()
