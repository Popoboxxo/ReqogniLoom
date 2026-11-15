"""Tests for ArtifactSummaryService (#1792, S1).

Pins the four properties that make the on-demand summary safe and affordable:

* the payload is bounded and deterministic (caps, hop order, sort order),
* a neighbour the caller may not read never reaches the prompt -- and the
  answer says how many were left out without naming them,
* every degradation (flag off, budget, mock, provider error, in-flight) is a
  reason, never an exception, and nothing degraded is cached,
* a cache hit costs zero provider calls and two different visibility sets can
  never share one entry.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from application.artifact_summary_service import (
    DEGRADATION_REASONS,
    DEGRADED_BUDGET_EXHAUSTED,
    DEGRADED_DISABLED,
    DEGRADED_PROVIDER_UNAVAILABLE,
    DEGRADED_STALE,
    ArtifactSummaryService,
    resolve_trace_depth,
)
from application.base import NotFoundError, PermissionDeniedError
from auth_tenancy.context import AuthContext
from auth_tenancy.models import ItemPermission
from persistence.models import Tenant, TraceLink, User, Workspace
from persistence.tenancy import TenantContext
from persistence.tests.factories import (
    editor_ctx,
    make_requirement,
    make_user,
    make_workspace,
)

pytestmark = pytest.mark.django_db

_CACHE_OVERRIDE = override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "artifact-summary-test",
        }
    },
)

_SUMMARY_TEXT = "Dieses Requirement regelt die Anmeldung."


@contextlib.contextmanager
def _active(tenant: Tenant) -> Iterator[None]:
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _isolated_cache() -> Iterator[None]:
    with _CACHE_OVERRIDE:
        cache.clear()
        try:
            yield
        finally:
            cache.clear()
            TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _artifact_summary_enabled() -> Iterator[None]:
    """The feature is off by default; every test here opts in explicitly.

    Kept out of ``_CACHE_OVERRIDE`` on purpose: a test that needs the flag off
    carries an ``@override_settings`` decorator, which must win over this
    fixture.
    """
    with override_settings(ARTIFACT_SUMMARY_ENABLED=True):
        yield


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Artifact Summary", slug="artifact-summary")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return make_workspace(tenant, name="Summary-WS")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return make_user(tenant, username="summary-user")


@pytest.fixture
def ctx(tenant: Tenant, workspace: Workspace, user: User) -> AuthContext:
    with _active(tenant):
        return editor_ctx(tenant, workspace, user=user)


@pytest.fixture
def focus(workspace: Workspace):
    with _active(workspace.tenant):
        return make_requirement(
            workspace,
            uid="REQ-L1-001",
            title="Anmeldung per OAuth",
            description="Das System authentifiziert Nutzer per OAuth 2.0.",
        )


class _FakeProvider:
    PROVIDER_NAME = "anthropic"

    def __init__(self, text: str = _SUMMARY_TEXT) -> None:
        self._text = text
        self.calls: list[str] = []
        self.timeouts: list[float | None] = []

    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        self.calls.append(prompt)
        self.timeouts.append(timeout)
        return self._text


class _RaisingProvider(_FakeProvider):
    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        self.calls.append(prompt)
        raise RuntimeError("provider down")


def _neighbour(workspace: Workspace, focus, *, index: int, link_type: str = "derives-from"):
    """Create a linked neighbour artifact and return it."""
    requirement = make_requirement(
        workspace,
        uid=f"REQ-L1-N{index:03d}",
        title=f"Neighbour {index}",
        description=f"Description of neighbour {index}.",
    )
    TraceLink.objects.create(
        tenant=workspace.tenant,
        source=focus.artifact,
        target=requirement.artifact,
        link_type=link_type,
        rationale=f"Rationale {index}",
    )
    return requirement


def _prompt_json(prompt: str, tag: str):
    """Parse the JSON body of ``<tag ...>…</tag>`` out of a rendered prompt."""
    start = prompt.index(f"<{tag}")
    start = prompt.index(">", start) + 1
    end = prompt.index(f"</{tag}>")
    return json.loads(prompt[start:end].strip())


def _summarize(artifact_id, ctx: AuthContext, provider, **kwargs):
    with patch("llm_adapter.providers.get_provider", return_value=provider):
        return ArtifactSummaryService().summarize_artifact(
            artifact_id, ctx, **kwargs
        )


# ---------------------------------------------------------------------------
# Payload: what reaches the prompt
# ---------------------------------------------------------------------------


def test_prompt_frames_artifact_and_neighbours_as_data(
    workspace: Workspace, focus, ctx: AuthContext
) -> None:
    with _active(workspace.tenant):
        neighbour = _neighbour(workspace, focus, index=2)
    provider = _FakeProvider()

    result = _summarize(focus.artifact_id, ctx, provider)

    assert result.text == _SUMMARY_TEXT
    assert result.degraded is False
    assert result.degraded_reason is None
    assert result.neighbour_count == 1
    assert result.omitted_neighbours == 0
    prompt = provider.calls[0]
    assert "<artifact type=\"Requirement\">" in prompt
    assert "untrusted" in prompt.lower()
    artifact_block = _prompt_json(prompt, "artifact")
    assert artifact_block["label"] == "REQ-L1-001"
    assert "OAuth 2.0" in artifact_block["text"]
    neighbours = _prompt_json(prompt, "neighbours")
    assert [entry["label"] for entry in neighbours] == [neighbour.uid]
    assert neighbours[0]["link_type"] == "derives-from"


def test_focus_text_is_capped_at_the_section_limit(
    workspace: Workspace, focus, ctx: AuthContext
) -> None:
    focus.description = "x" * 5000
    focus.save(update_fields=["description"])
    provider = _FakeProvider()

    _summarize(focus.artifact_id, ctx, provider)

    artifact_block = _prompt_json(provider.calls[0], "artifact")
    assert len(artifact_block["text"]) == 1500


def test_twenty_one_neighbours_are_capped_to_twenty(
    workspace: Workspace, focus, ctx: AuthContext
) -> None:
    with _active(workspace.tenant):
        for index in range(21):
            _neighbour(workspace, focus, index=index)
    provider = _FakeProvider()

    result = _summarize(focus.artifact_id, ctx, provider)

    entries = _prompt_json(provider.calls[0], "neighbours")
    assert len(entries) == 20
    assert result.neighbour_count == 20
    assert result.omitted_neighbours == 1


def test_each_neighbour_entry_stays_within_three_hundred_characters(
    workspace: Workspace, focus, ctx: AuthContext
) -> None:
    with _active(workspace.tenant):
        requirement = make_requirement(
            workspace, uid="REQ-L1-900", title="Long rationale"
        )
        TraceLink.objects.create(
            tenant=workspace.tenant,
            source=focus.artifact,
            target=requirement.artifact,
            link_type="derives-from",
            rationale="r" * 2000,
        )
    provider = _FakeProvider()

    _summarize(focus.artifact_id, ctx, provider)

    entries = _prompt_json(provider.calls[0], "neighbours")
    assert len(entries) == 1
    assert len(json.dumps(entries[0], ensure_ascii=False)) <= 300


def test_depth_two_lists_second_hop_after_every_first_hop(
    workspace: Workspace, focus, ctx: AuthContext
) -> None:
    with _active(workspace.tenant):
        first = _neighbour(workspace, focus, index=2, link_type="allocated-to")
        second = _neighbour(workspace, focus, index=3, link_type="derives-from")
        far = make_requirement(workspace, uid="REQ-L1-500", title="Second hop")
        TraceLink.objects.create(
            tenant=workspace.tenant,
            source=first.artifact,
            target=far.artifact,
            link_type="refines",
            rationale="Second hop rationale",
        )
    provider = _FakeProvider()

    _summarize(focus.artifact_id, ctx, provider, depth=2)

    entries = _prompt_json(provider.calls[0], "neighbours")
    assert [entry["hop"] for entry in entries] == [1, 1, 2]
    # Within hop 1 the order is (link_type, label): "allocated-to" < "derives-from".
    assert [entry["label"] for entry in entries[:2]] == [first.uid, second.uid]
    assert entries[2]["label"] == "REQ-L1-500"


def test_default_depth_is_one_hop(
    workspace: Workspace, focus, ctx: AuthContext
) -> None:
    with _active(workspace.tenant):
        first = _neighbour(workspace, focus, index=2)
        far = make_requirement(workspace, uid="REQ-L1-500", title="Second hop")
        TraceLink.objects.create(
            tenant=workspace.tenant,
            source=far.artifact,
            target=first.artifact,
            link_type="refines",
            rationale="",
        )
    provider = _FakeProvider()

    result = _summarize(focus.artifact_id, ctx, provider)

    assert result.trace_depth == 1
    assert [entry["label"] for entry in _prompt_json(provider.calls[0], "neighbours")] == [
        first.uid
    ]


# ---------------------------------------------------------------------------
# Permissions: read before payload
# ---------------------------------------------------------------------------


def test_neighbour_without_read_is_absent_from_the_prompt(
    workspace: Workspace, user: User, focus, ctx: AuthContext
) -> None:
    with _active(workspace.tenant):
        hidden = _neighbour(workspace, focus, index=2)
        visible = _neighbour(workspace, focus, index=3)
        ItemPermission.objects.create(
            tenant=workspace.tenant,
            user=user,
            workspace=workspace,
            artifact_id=hidden.artifact_id,
            permission_level="none",
        )
    provider = _FakeProvider()

    result = _summarize(focus.artifact_id, ctx, provider)

    prompt = provider.calls[0]
    assert visible.uid in prompt
    assert hidden.uid not in prompt
    assert "Rationale 2" not in prompt
    assert result.neighbour_count == 1
    assert result.omitted_neighbours == 1


def test_two_visibility_sets_never_share_a_cache_entry(
    tenant: Tenant, workspace: Workspace, user: User, focus, ctx: AuthContext
) -> None:
    other_user = make_user(tenant, username="summary-other")
    with _active(tenant):
        hidden_for_me = _neighbour(workspace, focus, index=2)
        ItemPermission.objects.create(
            tenant=tenant,
            user=user,
            workspace=workspace,
            artifact_id=hidden_for_me.artifact_id,
            permission_level="none",
        )
        other_ctx = editor_ctx(tenant, workspace, user=other_user)
    provider = _FakeProvider()

    mine = _summarize(focus.artifact_id, ctx, provider)
    theirs = _summarize(focus.artifact_id, other_ctx, provider)

    # The other caller sees the neighbour this caller may not, so the entry
    # cannot be reused: two provider calls, two entries.
    assert len(provider.calls) == 2
    assert mine.cache_hit is False
    assert theirs.cache_hit is False
    assert hidden_for_me.uid in provider.calls[1]
    assert hidden_for_me.uid not in provider.calls[0]
    # And each caller's own second call is served from their entry.
    assert _summarize(focus.artifact_id, ctx, _FakeProvider()).cache_hit is True
    assert len(provider.calls) == 2


def test_artifact_without_read_raises_permission_denied(
    tenant: Tenant, workspace: Workspace, focus
) -> None:
    with _active(tenant):
        outsider = make_user(tenant, username="summary-outsider")
        outsider_ctx = AuthContext(
            user_id=outsider.id,
            tenant_id=tenant.id,
            active_roles=(),
            auth_method="test",
            api_key_id=None,
        )
    provider = _FakeProvider()

    with pytest.raises(PermissionDeniedError):
        _summarize(focus.artifact_id, outsider_ctx, provider)
    assert provider.calls == []


def test_unknown_artifact_raises_not_found(ctx: AuthContext) -> None:
    provider = _FakeProvider()

    with pytest.raises(NotFoundError):
        _summarize(uuid.uuid4(), ctx, provider)
    assert provider.calls == []


# ---------------------------------------------------------------------------
# Cache and dedupe
# ---------------------------------------------------------------------------


def test_cache_hit_costs_no_provider_call(
    workspace: Workspace, focus, ctx: AuthContext
) -> None:
    provider = _FakeProvider()

    first = _summarize(focus.artifact_id, ctx, provider)
    second = _summarize(focus.artifact_id, ctx, provider)

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.text == first.text
    assert second.generated_at == first.generated_at
    assert len(provider.calls) == 1


def test_refresh_bypasses_the_cache(
    workspace: Workspace, focus, ctx: AuthContext
) -> None:
    provider = _FakeProvider()

    _summarize(focus.artifact_id, ctx, provider)
    refreshed = _summarize(focus.artifact_id, ctx, provider, refresh=True)

    assert refreshed.cache_hit is False
    assert len(provider.calls) == 2


def test_an_inflight_run_prevents_a_second_call(
    workspace: Workspace, focus, ctx: AuthContext
) -> None:
    provider = _FakeProvider()
    cache.set(f"artifact_summary:inflight:{focus.artifact_id}", "1", 60)

    result = _summarize(focus.artifact_id, ctx, provider)

    assert provider.calls == []
    assert result.text is None
    assert result.degraded is True
    assert result.degraded_reason == DEGRADED_PROVIDER_UNAVAILABLE


# ---------------------------------------------------------------------------
# Degradation: reasons, never exceptions, never cached
# ---------------------------------------------------------------------------


@override_settings(ARTIFACT_SUMMARY_ENABLED=False)
def test_flag_off_answers_disabled_without_a_provider_call(
    workspace: Workspace, focus, ctx: AuthContext
) -> None:
    provider = _FakeProvider()

    result = _summarize(focus.artifact_id, ctx, provider)

    assert result.degraded is True
    assert result.degraded_reason == DEGRADED_DISABLED
    assert result.text is None
    assert provider.calls == []


def test_mock_provider_degrades_and_is_never_cached(
    workspace: Workspace, focus, ctx: AuthContext
) -> None:
    from llm_adapter.providers import MockLlmProvider

    with patch("llm_adapter.providers.get_provider", return_value=MockLlmProvider()):
        first = ArtifactSummaryService().summarize_artifact(focus.artifact_id, ctx)
        second = ArtifactSummaryService().summarize_artifact(focus.artifact_id, ctx)

    assert first.text is None
    assert first.degraded_reason == DEGRADED_PROVIDER_UNAVAILABLE
    assert second.cache_hit is False


def test_provider_error_degrades_and_is_never_cached(
    workspace: Workspace, focus, ctx: AuthContext
) -> None:
    provider = _RaisingProvider()

    first = _summarize(focus.artifact_id, ctx, provider)
    second = _summarize(focus.artifact_id, ctx, provider)

    assert first.degraded is True
    assert first.degraded_reason == DEGRADED_PROVIDER_UNAVAILABLE
    assert second.cache_hit is False
    assert len(provider.calls) == 2


def test_budget_exhaustion_degrades_and_is_never_cached(
    workspace: Workspace, focus, ctx: AuthContext
) -> None:
    provider = _FakeProvider()

    with patch(
        "llm_adapter.token_tracking.is_over_daily_limit", return_value=True
    ):
        result = _summarize(focus.artifact_id, ctx, provider)

    assert result.degraded is True
    assert result.degraded_reason == DEGRADED_BUDGET_EXHAUSTED
    assert provider.calls == []


def test_degraded_reason_is_none_on_success(
    workspace: Workspace, focus, ctx: AuthContext
) -> None:
    result = _summarize(focus.artifact_id, ctx, _FakeProvider())

    assert result.degraded is False
    assert result.degraded_reason is None


def test_the_degradation_vocabulary_is_closed() -> None:
    """Spec §9/E11: exactly four reasons, no free text in the response."""
    assert DEGRADATION_REASONS == {
        DEGRADED_BUDGET_EXHAUSTED,
        DEGRADED_DISABLED,
        DEGRADED_PROVIDER_UNAVAILABLE,
        DEGRADED_STALE,
    }


def test_the_provider_call_carries_the_sync_timeout(
    workspace: Workspace, focus, ctx: AuthContext
) -> None:
    provider = _FakeProvider()

    _summarize(focus.artifact_id, ctx, provider)

    assert provider.timeouts == [20.0]


# ---------------------------------------------------------------------------
# Depth clamping (spec §9/E3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("requested", "expected"),
    [(None, 1), (0, 1), (1, 1), (2, 2), (7, 2), (-3, 1)],
)
def test_resolve_trace_depth_clamps_the_request(requested, expected: int) -> None:
    assert resolve_trace_depth(None, requested) == expected


@pytest.mark.parametrize(
    ("configured", "expected"), [(None, 1), (0, 1), (1, 1), (2, 2), (7, 2)]
)
def test_resolve_trace_depth_reads_the_workspace_setting(configured, expected: int) -> None:
    workspace = SimpleNamespace(summary_trace_depth=configured)

    assert resolve_trace_depth(workspace) == expected


def test_an_explicit_request_wins_over_the_workspace_setting() -> None:
    workspace = SimpleNamespace(summary_trace_depth=2)

    assert resolve_trace_depth(workspace, 1) == 1


def test_out_of_range_depth_is_clamped_not_rejected(
    workspace: Workspace, focus, ctx: AuthContext
) -> None:
    provider = _FakeProvider()

    result = _summarize(focus.artifact_id, ctx, provider, depth=7)

    assert result.trace_depth == 2
