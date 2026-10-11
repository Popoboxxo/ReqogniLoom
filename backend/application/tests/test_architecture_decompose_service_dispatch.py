"""
ArchitectureDecomposeService (SysEng 2.0 N1) — dispatch-gap tests.

Companion to ``test_architecture_decompose.py``, which covers the Phase-4a
acceptance path (draft staging, transactional commit, rollback, preset gate,
ARCH-003/TRACE-P4/P5). This file covers the dispatch-level gaps that file
deliberately leaves open (the service is the single entry point for both REST
and MCP, so a dispatch regression is a regression of every surface):

* Issue #1165 error taxonomy: a provider timeout surfaces as
  :class:`DecompositionLlmTimeoutError` (REST 504), any other transport
  failure as :class:`DecompositionLlmUnavailableError` (REST 503) — both
  ``LlmResponseError`` subclasses, never a bare 500.
* ADR-02 graceful degradation: ``get_provider()`` failing degrades to the
  credential-free mock and keeps the flow alive; a failing *mock* re-raises
  unwrapped (no typed translation on the degraded path).
* Response hygiene: invalid JSON, non-array JSON, fenced and mock-marked
  payloads, and empty results (#825 family) are handled deterministically.
* Tenant isolation: a draft pointing at another tenant's element, or an
  anchor requirement from a different workspace, is refused before anything
  is persisted.
* Tampered drafts: the client echoes the draft back, so hallucinated
  ``parent_temp_id`` references and stale anchor ids must be rejected rather
  than half-committed.
"""

from __future__ import annotations

import contextlib
import json
import uuid as uuid_lib
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

from application.architecture_decompose_service import (
    ArchitectureDecomposeService,
    DecompositionDraft,
    DecompositionLlmTimeoutError,
    DecompositionLlmUnavailableError,
    _is_timeout_failure,
)
from application.base import NotFoundError, ValidationError
from auth_tenancy.context import AuthContext
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from persistence.tests.factories import make_workspace
from presets.services import switch_preset
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _active(tenant: Tenant) -> Iterator[None]:
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear_tenant() -> Iterator[None]:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="N1 Dispatch Tenant", slug="n1-dispatch")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="n1-dispatch-user",
        email="n1-dispatch@example.com",
        tenant=tenant,
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return make_workspace(tenant, name="N1-Dispatch-WS")


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="N1 Dispatch Tenant",
    )


def _artifact(tenant: Tenant, workspace: Workspace, artifact_type: str) -> Artifact:
    return Artifact.objects.create(tenant=tenant, workspace=workspace, artifact_type=artifact_type)


def _requirement(tenant, workspace, title: str = "Req") -> Requirement:
    art = _artifact(tenant, workspace, "Requirement")
    return Requirement.objects.create(tenant=tenant, artifact=art, title=title)


def _arch(tenant, workspace, title: str = "AE") -> ArchitectureElement:
    art = _artifact(tenant, workspace, "ArchitectureElement")
    return ArchitectureElement.objects.create(tenant=tenant, artifact=art, title=title)


def _allocate(tenant, req: Requirement, arch: ArchitectureElement) -> TraceLink:
    return TraceLink.objects.create(
        tenant=tenant,
        source=req.artifact,
        target=arch.artifact,
        link_type=LinkType.ALLOCATED_TO.value,
    )


def _seed_anchored_element(tenant, workspace):
    root = _arch(tenant, workspace, "Payment Subsystem")
    anchor = _requirement(tenant, workspace, "Handle payments")
    _allocate(tenant, anchor, root)
    return root, anchor


def _stub_provider(monkeypatch, *, payload: str = "", error: Exception | None = None):
    """Install a fake LLM provider (no network) and return its mock."""
    provider = MagicMock()
    if error is not None:
        provider.complete.side_effect = error
    else:
        provider.complete.return_value = payload
    monkeypatch.setattr("llm_adapter.providers.get_provider", lambda *a, **k: provider)
    return provider


class _RecordingAuditLogger:
    """Stand-in for LlmAuditLogger capturing every log_llm_call entry."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def log_llm_call(self, **kwargs) -> None:
        self.calls.append(kwargs)


def _recording_audit_logger_factory(instances: list):
    def _factory():
        logger = _RecordingAuditLogger()
        instances.append(logger)
        return logger

    return _factory


def _tree(width: int, depth: int) -> list:
    """Build a provider tree *width* nodes wide, recursed along the first child.

    Sparse on purpose: only the first child of each level recurses, so the
    payload stays small (``width * depth`` nodes) while still exceeding every
    cap the dispatch test asserts.
    """
    if depth <= 0:
        return []

    def _node(index: int, children: list) -> dict:
        return {
            "title": f"Node L{depth}-{index}",
            "description": "Generated node.",
            "requirement": {"title": f"Req L{depth}-{index}"},
            "children": children,
        }

    return [_node(0, _tree(width, depth - 1))] + [_node(index, []) for index in range(1, width)]


# ---------------------------------------------------------------------------
# Issue #1165 — the typed provider-failure taxonomy (504/503, never a 500)
# ---------------------------------------------------------------------------


class TestLlmErrorTaxonomy:
    def test_timeout_raises_decomposition_llm_timeout_error(
        self, tenant, workspace, ctx, monkeypatch
    ):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)

        provider = _stub_provider(monkeypatch, error=TimeoutError("read timed out after 180s"))
        with _active(tenant), pytest.raises(DecompositionLlmTimeoutError) as excinfo:
            ArchitectureDecomposeService().generate_draft(ctx, root.id, max_breadth=2, max_depth=1)

        assert excinfo.value.error_code == "LLM_TIMEOUT"
        provider.complete.assert_called_once()

    def test_transport_failure_raises_decomposition_llm_unavailable_error(
        self, tenant, workspace, ctx, monkeypatch
    ):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)

        provider = _stub_provider(monkeypatch, error=RuntimeError("connection reset by peer"))
        with _active(tenant), pytest.raises(DecompositionLlmUnavailableError) as excinfo:
            ArchitectureDecomposeService().generate_draft(ctx, root.id, max_breadth=2, max_depth=1)

        assert excinfo.value.error_code == "LLM_UNAVAILABLE"
        provider.complete.assert_called_once()

    def test_both_error_types_stay_llm_response_errors(self):
        """Every pre-existing catch path keeps working unchanged (#1165)."""
        from application.ai_derivation_service import LlmResponseError

        assert issubclass(DecompositionLlmTimeoutError, LlmResponseError)
        assert issubclass(DecompositionLlmUnavailableError, LlmResponseError)

    @pytest.mark.parametrize(
        "error,expected",
        [
            (TimeoutError(), True),
            (RuntimeError("provider timeout after 180s"), True),
            (RuntimeError("connection reset by peer"), False),
            (ValueError("bad request"), False),
        ],
    )
    def test_is_timeout_failure_classification(self, error, expected):
        assert _is_timeout_failure(error) is expected

    def test_provider_failure_writes_a_failed_audit_entry(
        self, tenant, workspace, ctx, monkeypatch
    ):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)

        instances: list = []
        monkeypatch.setattr(
            "llm_adapter.audit_logger.LlmAuditLogger",
            _recording_audit_logger_factory(instances),
        )
        _stub_provider(monkeypatch, error=RuntimeError("upstream exploded"))

        with _active(tenant), pytest.raises(DecompositionLlmUnavailableError):
            ArchitectureDecomposeService().generate_draft(ctx, root.id, max_breadth=2, max_depth=1)

        assert len(instances) == 1
        assert instances[0].calls == [
            {
                "provider": "mock",
                "capability": "arch_decompose_tree",
                "artifact_id": str(root.artifact_id),
                "token_usage": None,
                "success": False,
                "error": "upstream exploded",
            }
        ]


# ---------------------------------------------------------------------------
# ADR-02 graceful degradation — the provider-less path must stay alive
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    def test_unconfigured_provider_degrades_to_the_mock_draft(
        self, tenant, workspace, ctx, monkeypatch
    ):
        from llm_adapter.providers import LlmNotConfiguredError

        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)

        def _boom(*args, **kwargs):
            raise LlmNotConfiguredError("no api key configured")

        monkeypatch.setattr("llm_adapter.providers.get_provider", _boom)

        audit_instances: list = []
        monkeypatch.setattr(
            "llm_adapter.audit_logger.LlmAuditLogger",
            _recording_audit_logger_factory(audit_instances),
        )
        record_mock = MagicMock()
        monkeypatch.setattr("llm_adapter.token_tracking.record_token_usage", record_mock)

        with _active(tenant):
            draft = ArchitectureDecomposeService().generate_draft(
                ctx, root.id, max_breadth=2, max_depth=1
            )

        assert draft.degraded is True
        assert draft.provider == "mock"
        assert draft.nodes
        assert all(not logger.calls for logger in audit_instances)
        record_mock.assert_not_called()

    def test_failing_mock_reraises_the_raw_error_unwrapped(
        self, tenant, workspace, ctx, monkeypatch
    ):
        from llm_adapter.providers import LlmNotConfiguredError

        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)

        class _FailingMock:
            def complete(self, *args, **kwargs):
                raise RuntimeError("mock is offline")

        monkeypatch.setattr("llm_adapter.providers.MockLlmProvider", _FailingMock)

        def _boom(*args, **kwargs):
            raise LlmNotConfiguredError("no api key configured")

        monkeypatch.setattr("llm_adapter.providers.get_provider", _boom)

        with _active(tenant), pytest.raises(RuntimeError) as excinfo:
            ArchitectureDecomposeService().generate_draft(ctx, root.id, max_breadth=2, max_depth=1)

        assert str(excinfo.value) == "mock is offline"
        assert not isinstance(excinfo.value, DecompositionLlmUnavailableError)


# ---------------------------------------------------------------------------
# Response hygiene — parse failures, fences, and empty results (#825 family)
# ---------------------------------------------------------------------------


class TestResponseHygiene:
    def test_invalid_json_raises_validation_error(self, tenant, workspace, ctx, monkeypatch):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)

        _stub_provider(monkeypatch, payload="I cannot comply with that request.")

        with _active(tenant), pytest.raises(ValidationError, match="not valid JSON"):
            ArchitectureDecomposeService().generate_draft(ctx, root.id, max_breadth=2, max_depth=1)

    def test_non_array_json_raises_validation_error(self, tenant, workspace, ctx, monkeypatch):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)

        _stub_provider(monkeypatch, payload='{"children": []}')

        with _active(tenant), pytest.raises(ValidationError, match="not a JSON array"):
            ArchitectureDecomposeService().generate_draft(ctx, root.id, max_breadth=2, max_depth=1)

    def test_fenced_json_is_tolerated(self):
        parsed = ArchitectureDecomposeService._parse_tree(
            '```json\n[{"title": "Child A", "requirement": {"title": "Req A"}}]\n```'
        )
        assert parsed == [{"title": "Child A", "requirement": {"title": "Req A"}}]

    def test_mock_fallback_marker_is_stripped(self):
        from application.ai_derivation_service import MOCK_FALLBACK_MARKER

        parsed = ArchitectureDecomposeService._parse_tree(
            f'{MOCK_FALLBACK_MARKER}[{{"title": "Child A"}}]'
        )
        assert parsed == [{"title": "Child A"}]

    def test_empty_array_raises_validation_error(self, tenant, workspace, ctx, monkeypatch):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)

        _stub_provider(monkeypatch, payload="[]")

        with _active(tenant), pytest.raises(ValidationError, match="no decomposition nodes"):
            ArchitectureDecomposeService().generate_draft(ctx, root.id, max_breadth=2, max_depth=1)

    def test_all_blank_titles_produce_no_nodes(self, tenant, workspace, ctx, monkeypatch):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)

        _stub_provider(monkeypatch, payload='[{"title": "  "}, {"title": ""}]')

        with _active(tenant), pytest.raises(ValidationError, match="no decomposition nodes"):
            ArchitectureDecomposeService().generate_draft(ctx, root.id, max_breadth=2, max_depth=1)


# ---------------------------------------------------------------------------
# Tenant isolation — the dispatch must refuse foreign ids before persisting
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    def test_generate_refuses_an_element_from_another_tenant(self, tenant, ctx):
        with _active(tenant):
            other_tenant = Tenant.objects.create(name="Other Tenant", slug="other")
            with _active(other_tenant):
                other_workspace = make_workspace(other_tenant, name="Other-WS")
                root, _ = _seed_anchored_element(other_tenant, other_workspace)

        with _active(tenant), pytest.raises(NotFoundError):
            ArchitectureDecomposeService().generate_draft(ctx, root.id)

    def test_commit_refuses_an_anchor_from_another_workspace(self, tenant, workspace, ctx):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)
            other_workspace = make_workspace(tenant, name="Other-WS-Same-Tenant")
            foreign_anchor = _requirement(tenant, other_workspace, "Foreign workspace requirement")
            svc = ArchitectureDecomposeService()
            draft = svc.generate_draft(ctx, root.id, max_breadth=1, max_depth=1)
            draft.parent_requirement_id = str(foreign_anchor.id)

            before_elements = ArchitectureElement.objects.count()
            before_requirements = Requirement.objects.count()

            with pytest.raises(ValidationError, match="different workspaces"):
                svc.commit_draft(ctx, draft)

            assert ArchitectureElement.objects.count() == before_elements
            assert Requirement.objects.count() == before_requirements

    def test_commit_refuses_a_missing_anchor_requirement(self, tenant, workspace, ctx):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)
            svc = ArchitectureDecomposeService()
            draft = svc.generate_draft(ctx, root.id, max_breadth=1, max_depth=1)
            draft.parent_requirement_id = str(uuid_lib.uuid4())

            before_requirements = Requirement.objects.count()

            with pytest.raises(NotFoundError, match="Anchor Requirement"):
                svc.commit_draft(ctx, draft)

            assert Requirement.objects.count() == before_requirements


# ---------------------------------------------------------------------------
# Tampered drafts — the client echo must not be able to bypass invariants
# ---------------------------------------------------------------------------


class TestTamperedDraftRejection:
    def test_hallucinated_parent_temp_id_is_rejected(self, tenant, workspace, ctx):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)
            svc = ArchitectureDecomposeService()
            draft = svc.generate_draft(ctx, root.id, max_breadth=2, max_depth=1)
            draft.nodes[0].parent_temp_id = "n99"

            before_elements = ArchitectureElement.objects.count()
            before_requirements = Requirement.objects.count()

            with pytest.raises(ValidationError, match="unknown or out-of-order parent"):
                svc.commit_draft(ctx, draft)

            assert ArchitectureElement.objects.count() == before_elements
            assert Requirement.objects.count() == before_requirements

    def test_client_echo_round_trip_commits_identically(self, tenant, workspace, ctx):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, anchor = _seed_anchored_element(tenant, workspace)
            svc = ArchitectureDecomposeService()
            draft = svc.generate_draft(ctx, root.id, max_breadth=2, max_depth=2)

            echoed = DecompositionDraft.from_dict(draft.to_dict())
            result = svc.commit_draft(ctx, echoed)

            assert echoed.provider == draft.provider
            assert echoed.parent_requirement_id == str(anchor.id)
            assert len(result.created_element_ids) == len(draft.nodes)
            assert len(result.created_requirement_ids) == len(draft.nodes)
            assert len(result.created_link_ids) == 3 * len(draft.nodes)
            assert set(result.verified_rules) == {"ARCH-003", "TRACE-P4", "TRACE-P5"}


class TestDecompositionDraftPayload:
    def test_from_dict_rejects_missing_ids(self):
        with pytest.raises(ValidationError, match="missing 'root_element_id'"):
            DecompositionDraft.from_dict({"nodes": [{"temp_id": "n1", "title": "A"}]})

    def test_from_dict_rejects_empty_nodes(self):
        with pytest.raises(ValidationError, match="non-empty 'nodes'"):
            DecompositionDraft.from_dict(
                {"root_element_id": "r", "parent_requirement_id": "p", "nodes": []}
            )


# ---------------------------------------------------------------------------
# Absolute ceiling — an oversized explicit override cannot widen the blast
# radius (dispatch-level clamp, complementing the serializer-level tests)
# ---------------------------------------------------------------------------


class TestAbsoluteCeiling:
    def test_oversized_explicit_caps_are_clamped(self, tenant, workspace, ctx, monkeypatch):
        from llm_adapter.timeouts import resolve_timeout_seconds

        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)

        provider = _stub_provider(monkeypatch, payload=json.dumps(_tree(25, 6)))

        with _active(tenant):
            draft = ArchitectureDecomposeService().generate_draft(
                ctx, root.id, max_breadth=500, max_depth=9
            )

        call_kwargs = provider.complete.call_args.kwargs
        assert call_kwargs["purpose"] == "arch_decompose_tree"
        assert call_kwargs["context"] == {
            "element_title": root.title,
            "max_breadth": 10,
            "max_depth": 4,
        }
        assert call_kwargs["timeout"] == resolve_timeout_seconds("arch_decompose_tree")
        top_level = [n for n in draft.nodes if n.parent_temp_id is None]
        assert len(top_level) == 10
        assert max(n.temp_id.count(".") for n in draft.nodes) == 3


# ---------------------------------------------------------------------------
# Deterministic anchor selection — the lowest-id allocated requirement wins
# ---------------------------------------------------------------------------


class TestAnchorSelection:
    def test_lowest_id_allocated_requirement_is_the_anchor(self, tenant, workspace, ctx):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root = _arch(tenant, workspace, "Multi-anchor Subsystem")
            first = _requirement(tenant, workspace, "Anchor A")
            second = _requirement(tenant, workspace, "Anchor B")
            _allocate(tenant, first, root)
            _allocate(tenant, second, root)

            draft = ArchitectureDecomposeService().generate_draft(
                ctx, root.id, max_breadth=1, max_depth=1
            )

        assert draft.parent_requirement_id == str(min(first.id, second.id))
