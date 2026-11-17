"""Regression tests for R2C-002 (shared sentinel) and R2C-007b.

R2C-002: every artifact-backed CRUD service binds the single
``application.sentinels.UNSET`` object as its local ``_UNSET``.  No shared base
class was introduced — each service keeps its own validation and ``is``
checks — so these tests pin both the identity contract and the fact that the
four representative create paths still run their own (equivalent)
tenant/workspace preamble.

R2C-007b: ``get_architecture_element(include_deleted=...)`` keeps the keyword
(MCP ``architecture.reactivate`` passes ``True``); its docstring states that
the keyword has no effect on detail reads (#1381).
"""
from __future__ import annotations

import uuid
from contextlib import nullcontext
from dataclasses import dataclass
from types import ModuleType
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# R2C-002 — shared sentinel identity
# ---------------------------------------------------------------------------

#: All thirteen artifact-backed CRUD services that use the omitted-vs-cleared
#: sentinel.  ``requirement_service`` is owned by a parallel worker; its
#: conversion is part of the same R2C-002 change set.
_SENTINEL_SERVICE_MODULES = (
    "adr_service",
    "architecture_service",
    "artifact_service",
    "change_request_service",
    "document_service",
    "glossary_service",
    "goal_service",
    "issue_service",
    "requirement_service",
    "risk_service",
    "stakeholder_need_service",
    "test_service",
    "work_item_service",
)


def test_all_thirteen_services_bind_the_shared_sentinel():
    """Every service's ``_UNSET`` is the one object from ``sentinels``."""
    from application import sentinels

    for module_name in _SENTINEL_SERVICE_MODULES:
        module: ModuleType = __import__(f"application.{module_name}", fromlist=["_UNSET"])
        assert module._UNSET is sentinels.UNSET, module_name


def test_artifact_transport_alias_points_at_the_shared_sentinel():
    """REST/MCP import ``artifact_service.UNSET`` — it must be the same token."""
    from application import artifact_service, sentinels

    assert artifact_service.UNSET is sentinels.UNSET
    assert artifact_service.UNSET is artifact_service._UNSET


def test_sentinels_module_exposes_a_single_object():
    """The canonical token is a plain unique object, not a class or enum."""
    from application import sentinels

    assert type(sentinels.UNSET) is object


# ---------------------------------------------------------------------------
# R2C-002 — characterization of the 4 create-path preambles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CreateCase:
    """Configuration for one artifact-backed create path."""

    label: str
    module_path: str
    service_name: str
    entity_name: str
    method: str
    create_kwargs: dict[str, object]
    #: Risk constructs its entity directly (``Risk(...)`` + ``.save()``)
    #: instead of going through ``<Entity>.objects.create``.
    constructs_entity: bool = False


_CREATE_CASES = (
    _CreateCase(
        label="adr",
        module_path="application.adr_service",
        service_name="AdrService",
        entity_name="Adr",
        method="create_adr",
        create_kwargs={
            "title": "Use REST over SOAP",
            "description": "Simpler",
            "uid": "ADR-1",
        },
    ),
    _CreateCase(
        label="risk",
        module_path="application.risk_service",
        service_name="RiskService",
        entity_name="Risk",
        method="create_risk",
        create_kwargs={
            "title": "Data leak",
            "probability": "low",
            "impact": "low",
            "uid": "RISK-1",
        },
        constructs_entity=True,
    ),
    _CreateCase(
        label="issue",
        module_path="application.issue_service",
        service_name="IssueService",
        entity_name="Issue",
        method="create_issue",
        create_kwargs={"title": "Broken link", "uid": "ISSUE-1"},
    ),
    _CreateCase(
        label="test",
        module_path="application.test_service",
        service_name="TestService",
        entity_name="TestCase",
        method="create_test_case",
        create_kwargs={"title": "Unit test", "uid": "TEST-1"},
    ),
)


def _make_ctx(*, tenant_id: uuid.UUID, user_id: uuid.UUID) -> MagicMock:
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = user_id
    ctx.active_roles = ("editor",)
    ctx.has_role = lambda role: role in ctx.active_roles
    return ctx


def _run_create_case(case: _CreateCase) -> dict[str, bool]:
    """Execute one create path under mocks; return its preamble signature.

    The signature records the tenant/workspace setup shared by all four
    services: context setup, write-permission check, tenant/workspace lookups
    and the backing ``Artifact`` row.  Revision, workflow init, audit and event
    emission are stubbed so only the preamble is characterized.
    """
    module: ModuleType = __import__(case.module_path, fromlist=[case.service_name])
    service_cls = getattr(module, case.service_name)

    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    ctx = _make_ctx(tenant_id=tenant_id, user_id=user_id)
    tenant = MagicMock()
    workspace = MagicMock()

    with (
        # The create methods are wrapped in @atomic_transaction; all ORM is
        # mocked here, so no real transaction (and no test DB) is needed.
        patch("django.db.transaction.atomic", return_value=nullcontext()),
        patch("application.artifact_version_service.ArtifactVersionService.record", return_value=1),
        patch(f"{case.module_path}.ServiceBase._set_tenant_context") as mock_set_ctx,
        patch(f"{case.module_path}.ServiceBase._assert_write_permission") as mock_perm,
        patch("persistence.models.Tenant.objects") as mock_tenant,
        patch("persistence.models.Workspace.objects") as mock_ws,
        patch("persistence.models.Artifact.objects") as mock_artifact,
        patch(f"{case.module_path}.ServiceBase._audit"),
        patch(f"{case.module_path}.ServiceBase._emit_event"),
        patch(f"{case.module_path}.ServiceBase._make_event", return_value=MagicMock()),
        patch("workflow.services.initialize_workflow_states"),
    ):
        mock_tenant.filter.return_value.first.return_value = tenant
        mock_ws.filter.return_value.first.return_value = workspace
        mock_artifact.create.return_value = MagicMock()

        if case.constructs_entity:
            with patch(f"{case.module_path}.{case.entity_name}") as mock_entity_cls:
                entity = mock_entity_cls.return_value
                entity.id = uuid.uuid4()
                entity.artifact_id = uuid.uuid4()
                entity.compute_score.return_value = 9
                getattr(service_cls(), case.method)(
                    workspace_id=workspace_id, ctx=ctx, **case.create_kwargs
                )
        else:
            with patch(f"{case.module_path}.{case.entity_name}.objects") as mock_entity_mgr:
                entity = MagicMock()
                entity.id = uuid.uuid4()
                entity.artifact_id = uuid.uuid4()
                mock_entity_mgr.create.return_value = entity
                getattr(service_cls(), case.method)(
                    workspace_id=workspace_id, ctx=ctx, **case.create_kwargs
                )

    assert mock_artifact.create.call_count == 1
    artifact_kwargs = mock_artifact.create.call_args.kwargs
    set_ctx_args = mock_set_ctx.call_args.args
    perm_args = mock_perm.call_args.args

    return {
        "set_tenant_context_once_with_ctx": (
            mock_set_ctx.call_count == 1 and len(set_ctx_args) == 1 and set_ctx_args[0] is ctx
        ),
        "assert_write_permission_once_with_ctx": (
            mock_perm.call_count == 1 and len(perm_args) == 1 and perm_args[0] is ctx
        ),
        "tenant_lookup_by_ctx_tenant_id": (
            mock_tenant.filter.call_count == 1
            and mock_tenant.filter.call_args.kwargs == {"id": tenant_id}
        ),
        "workspace_lookup_by_requested_id": (
            mock_ws.filter.call_count == 1
            and mock_ws.filter.call_args.kwargs == {"id": workspace_id}
        ),
        "artifact_bound_to_resolved_tenant": artifact_kwargs["tenant"] is tenant,
        "artifact_bound_to_resolved_workspace": artifact_kwargs["workspace"] is workspace,
    }


def test_create_paths_share_tenant_workspace_preamble():
    """ADR/Risk/Issue/Test create paths run the same tenant/workspace preamble.

    This is the characterization guard for the R2C-002 ANPASSEN decision: the
    sentinel is shared, but no ``ArtifactBackedEntityService`` base class was
    introduced.  Each service owns its validation and preamble; this test
    proves the four preambles remain observably equivalent.
    """
    signatures = {case.label: _run_create_case(case) for case in _CREATE_CASES}

    canonical = signatures["adr"]
    assert all(value is True for value in canonical.values())
    for label, signature in signatures.items():
        assert signature == canonical, f"{label} preamble diverged from ADR: {signature}"


# ---------------------------------------------------------------------------
# R2C-007b — include_deleted keyword on the detail read
# ---------------------------------------------------------------------------


def test_architecture_detail_read_keeps_include_deleted_keyword():
    """The keyword survives (MCP passes True) and is documented as inert."""
    import inspect

    from application.architecture_service import ArchitectureService

    signature = inspect.signature(ArchitectureService.get_architecture_element)
    param = signature.parameters.get("include_deleted")
    assert param is not None
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is False

    doc = ArchitectureService.get_architecture_element.__doc__ or ""
    assert "no effect on detail reads (#1381)" in doc
