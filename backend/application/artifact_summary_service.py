"""COMP-AS-SUMMARY ArtifactSummaryService — on-demand summary of one artifact.

Issue #1792 / S1 (spec: ``docs/superpowers/specs/2026-11-14-ai-artifact-summaries-design.md``
§5). One authenticated caller asks for a short natural-language summary of
**one** artifact *and the trace neighbours it may see*, or gets a degraded answer
with a reason. There is no database write path: the only state is the cache.

Deliberate boundaries, all of them load-bearing:

* **Permissions before payload.** The caller's read access is resolved with
  :class:`~application.effective_permission_service.EffectivePermissionService`
  (RBAC + item-level rule + API-key workspace fence) *before* any neighbour text
  is built. A neighbour without ``read`` never enters the prompt -- not
  truncated, not as an id. The count of everything left out is reported as
  ``omitted_neighbours`` (a number, never an identity), so "incomplete" stays
  distinguishable from "nothing linked" (§5.5).
* **Bound payload.** At most ``SUMMARY_MAX_NEIGHBOURS`` neighbours, each capped
  to ``SUMMARY_MAX_CHARS_PER_NEIGHBOR`` characters, and the focus artifact to
  ``SUMMARY_MAX_CHARS_PER_SECTION``. Deterministic order (hop, then link type,
  then the neighbour's readable label) keeps the cache key stable (§5.2).
* **Content is data, not instructions.** The prompt puts the artifact and the
  neighbours in explicit ``<artifact>`` / ``<neighbours>`` blocks and says so
  (§5.3).
* **The summary never fails the request.** No provider, mock provider, daily
  budget, timeout or provider exception all degrade to ``text=None`` with one
  of the four enum reasons (§5.8, §9/E11); the transport still answers 200.
* **Nothing degraded is cached.** Mock/placeholder answers, empty answers and
  every degradation stay out of the cache (§5.4).
* **One switch, off by default.** ``ARTIFACT_SUMMARY_ENABLED`` produces
  ``degraded_reason="disabled"`` -- deliberately not a 404/403, so a client can
  render "feature off" (§5.6).
* **Cache only holds what the caller saw.** The permission filter runs *before*
  the cache lookup, and the visible neighbour set is part of the cache key, so
  an entry built from another caller's view is never served (§5.5, option (a)).
* **No memory injection.** ``artifact_summary`` is on
  ``MEMORY_HARD_OFF_SLOTS`` (ADR-024 AC-1).

The persisted, periodically refreshed per-artifact-type summary (#1793) is a
second scope on the same vocabulary. It is written by
:meth:`ArtifactSummaryService.summarize_artifact_type` (S5) and read here by
:meth:`~ArtifactSummaryService.list_type_summaries`,
:meth:`~ArtifactSummaryService.get_type_summary` and
:meth:`~ArtifactSummaryService.get_artifact_scope_summary` (S6, with
:meth:`~ArtifactSummaryService.refresh_type_summary` for the manual run). Both
scopes share the gates, the caps and the E11 reason vocabulary.

req_id: REQ-L2-AI-002 (LLM provider abstraction), issue #1792.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)
from application.effective_permission_service import EffectivePermissionService
from application.summary_support import ARTIFACT_KIND, TYPE_ROSTER_KIND
from persistence.models import Artifact, ArtifactSummary, TraceLink, Workspace

if TYPE_CHECKING:
    from auth_tenancy.context import AuthContext

logger = logging.getLogger(__name__)

#: PromptTemplate name; registered in
#: ``AiDerivationService.PROMPT_TEMPLATE_DEFAULTS`` and declared in
#: ``application.prompt_slots`` (spec §5.3, §9/E7).
PROMPT_TEMPLATE_NAME = "artifact_summary"

#: Credential-free placeholder provider. Its output is not a summary, is never
#: presented as one and is never cached.
MOCK_PROVIDER_NAME = "mock"

#: Default trace depth when neither the caller nor the workspace says otherwise.
DEFAULT_TRACE_DEPTH = 1

#: Hard ceiling for the trace depth (spec §9/E3). Depth 2 adds second-hop
#: neighbours *after* every first-hop neighbour, so the cap still holds.
MAX_TRACE_DEPTH = 2

#: The closed degradation vocabulary of spec §9/E11. ``stale`` is reserved for
#: the persisted per-type scope (#1793, S6) -- the cache-only scope here can
#: never be stale. No free text ever reaches the response (CWE-209); the finer
#: cause (mock, timeout, no provider) stays in the log.
DEGRADED_BUDGET_EXHAUSTED = "budget_exhausted"
DEGRADED_PROVIDER_UNAVAILABLE = "provider_unavailable"
DEGRADED_STALE = "stale"
DEGRADED_DISABLED = "disabled"
DEGRADATION_REASONS: frozenset[str] = frozenset(
    {
        DEGRADED_BUDGET_EXHAUSTED,
        DEGRADED_PROVIDER_UNAVAILABLE,
        DEGRADED_STALE,
        DEGRADED_DISABLED,
    }
)

_CACHE_PREFIX = "artifact_summary"
_INFLIGHT_PREFIX = "artifact_summary:inflight"

#: Upper bound for one read of the stored type scopes (issue #1793 / S6). The
#: roster vocabulary is bounded (the twelve ``DEFAULT_SUMMARY_SCOPES``), so this
#: only fences a pathological tenant; a caller sees ``truncated=true`` instead
#: of an unbounded answer.
MAX_SUMMARY_ROWS = 50


@dataclass(frozen=True)
class SummaryLimits:
    """Per-call caps, read from settings so tests and ops can steer them."""

    max_neighbours: int
    max_chars_per_neighbour: int
    max_chars_per_section: int
    cache_ttl_seconds: int
    min_interval_seconds: int

    @classmethod
    def from_settings(cls) -> SummaryLimits:
        return cls(
            max_neighbours=int(getattr(settings, "SUMMARY_MAX_NEIGHBOURS", 20)),
            max_chars_per_neighbour=int(
                getattr(settings, "SUMMARY_MAX_CHARS_PER_NEIGHBOR", 300)
            ),
            max_chars_per_section=int(
                getattr(settings, "SUMMARY_MAX_CHARS_PER_SECTION", 1500)
            ),
            cache_ttl_seconds=int(getattr(settings, "SUMMARY_CACHE_TTL_SECONDS", 3600)),
            min_interval_seconds=int(
                getattr(settings, "ARTIFACT_SUMMARY_MIN_INTERVAL_SECONDS", 3600)
            ),
        )


@dataclass(frozen=True)
class ArtifactSummaryResult:
    """Outcome of one summary attempt (spec §5.7 wire contract).

    ``text is None`` with ``degraded=True`` means "no summary, and here is
    why". ``degraded=False`` always carries text: unlike a search summary there
    is no empty-input case, because the focus artifact itself is always there.
    """

    artifact_id: UUID
    artifact_type: str
    text: str | None
    degraded: bool
    degraded_reason: str | None
    cache_hit: bool
    trace_depth: int
    neighbour_count: int
    omitted_neighbours: int
    generated_at: datetime

    def as_payload(self) -> dict[str, Any]:
        """Wire form (REST body; the MCP tool in S3 reuses the same keys)."""
        return {
            "artifact_id": str(self.artifact_id),
            "artifact_type": self.artifact_type,
            "summary": self.text,
            "degraded": self.degraded,
            "degraded_reason": self.degraded_reason,
            "cache_hit": self.cache_hit,
            "trace_depth": self.trace_depth,
            "neighbour_count": self.neighbour_count,
            "omitted_neighbours": self.omitted_neighbours,
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass(frozen=True)
class _Neighbour:
    """One candidate trace link; one entry per ``(neighbour, link_type)`` pair."""

    artifact_id: UUID
    link_type: str
    direction: str
    hop: int
    rationale: str
    link_modified_at: datetime | None


def resolve_trace_depth(workspace: Any | None, requested: int | None = None) -> int:
    """Clamp a requested (or configured) trace depth into ``1..MAX_TRACE_DEPTH``.

    Spec §9/E3: the workspace setting ``summary_trace_depth`` is the default and
    the caller may ask for less/more, but both are clamped rather than rejected
    -- ``0`` behaves like 1, ``7`` like 2. Since S5 the column exists on
    :class:`~persistence.models.Workspace`; the attribute lookup stays
    defensive so a bare ``SimpleNamespace`` in tests keeps working.
    """
    configured: Any = requested
    if configured is None and workspace is not None:
        configured = getattr(workspace, "summary_trace_depth", None)
    try:
        value = int(configured) if configured is not None else DEFAULT_TRACE_DEPTH
    except (TypeError, ValueError):
        value = DEFAULT_TRACE_DEPTH
    return max(1, min(MAX_TRACE_DEPTH, value))


# ---------------------------------------------------------------------------
# Issue #1793 (S5, spec §9/E8): the summary-only daily token budget.
#
# Counted per purpose (``artifact_type_summary``) so the sweep can neither eat
# the other AI flows' budget nor be blocked by it unexpectedly. ``0``/empty
# means "off", matching ``TENANT_TOKEN_LIMIT_PER_DAY`` semantics.
# ---------------------------------------------------------------------------

#: Prompt slot *and* token-accounting purpose of the periodic type summary.
TYPE_SUMMARY_PROMPT_TEMPLATE_NAME = "artifact_type_summary"

#: Cap on the roster prompt: at most this many artifacts, each rendered to
#: ``ROSTER_MAX_CHARS_PER_ITEM``. Same reasoning as the S1 caps — the prompt
#: must stay bounded no matter how large the workspace grows.
ROSTER_MAX_ITEMS = 200
ROSTER_MAX_CHARS_PER_ITEM = 300


def summary_daily_token_limit() -> int:
    """Return the summary-only daily limit; ``0`` means unlimited."""
    try:
        value = int(getattr(settings, "SUMMARY_DAILY_TOKEN_LIMIT", 0) or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def summary_tokens_used_today() -> int:
    """Tokens spent on summary purposes in the active tenant's last 24 h."""
    from llm_adapter.token_tracking import get_daily_usage_for_capability

    return get_daily_usage_for_capability(TYPE_SUMMARY_PROMPT_TEMPLATE_NAME)


def summary_budget_exhausted() -> bool:
    """Whether the summary-only daily budget is spent (fail-open when unset)."""
    limit = summary_daily_token_limit()
    if limit <= 0:
        return False
    return summary_tokens_used_today() >= limit



class _ReadAccess:
    """Fail-closed read decisions for one caller, cached per request.

    Combines the three fences the other cross-workspace readers already use
    (``application.search_service``): the API key's workspace fence, the
    caller's roles *in the target workspace* (never ``ctx.active_roles`` for a
    foreign workspace), and the item-level rule layer. Any error means "not
    readable": hiding a neighbour is always the safe direction.
    """

    def __init__(self, ctx: AuthContext) -> None:
        self._ctx = ctx
        self._roles: dict[UUID, tuple[str, ...]] = {}
        self._decisions: dict[tuple[UUID, UUID | None], bool] = {}
        self._service = EffectivePermissionService()

    def can_read(self, workspace_id: UUID | None, artifact_id: UUID | None) -> bool:
        if workspace_id is None:
            return False
        key = (workspace_id, artifact_id)
        if key in self._decisions:
            return self._decisions[key]
        allowed = self._resolve(workspace_id, artifact_id)
        self._decisions[key] = allowed
        return allowed

    def workspace_roles(self, workspace_id: UUID | None) -> tuple[str, ...]:
        """The caller's roles *in this workspace* (never ``ctx.active_roles``).

        The API-key fence is applied first: a fenced key that does not name the
        workspace gets an empty role tuple, so every downstream decision fails
        closed instead of falling back to the tenant-wide aggregate.
        """
        from auth_tenancy.resource_scope import workspace_fence_denial
        from auth_tenancy.services.authorization import AuthorizationService

        if workspace_id is None:
            return ()
        try:
            fence = getattr(self._ctx, "api_key_workspace_ids", ())
            if workspace_fence_denial(fence, workspace_id) is not None:
                return ()
            roles = self._roles.get(workspace_id)
            if roles is None:
                roles = AuthorizationService().active_roles_for(
                    user_id=self._ctx.user_id, workspace_id=workspace_id
                )
                self._roles[workspace_id] = roles
            return roles
        except Exception:  # noqa: BLE001 - deny, never leak
            logger.debug(
                "artifact_summary: role lookup failed workspace=%s",
                workspace_id,
                exc_info=True,
            )
            return ()

    def can_write(self, workspace_id: UUID | None) -> bool:
        """Whether the caller may spend a provider call in *workspace_id*.

        Deliberately evaluated against the roles *in that workspace*: a
        ``ctx.active_roles`` check would let an editor of workspace A refresh
        workspace B's summaries (the ADR-011 scope-classifier hole).
        """
        from auth_tenancy.services.authorization import AuthorizationService, Operation

        roles = self.workspace_roles(workspace_id)
        if not roles:
            return False
        try:
            decision = AuthorizationService().decide_access(roles, Operation.WRITE)
        except Exception:  # noqa: BLE001 - deny, never leak
            logger.debug(
                "artifact_summary: write decision failed workspace=%s",
                workspace_id,
                exc_info=True,
            )
            return False
        return bool(decision.allow)

    def _resolve(self, workspace_id: UUID, artifact_id: UUID | None) -> bool:
        try:
            roles = self.workspace_roles(workspace_id)
            if not roles:
                return False
            decision = self._service.resolve_effective_permission(
                active_roles=roles,
                user_id=self._ctx.user_id,
                workspace_id=workspace_id,
                artifact_id=artifact_id,
                level="read",
            )
            return decision.is_allowed
        except Exception:  # noqa: BLE001 - hide the neighbour, never leak it
            logger.debug(
                "artifact_summary: read lookup failed workspace=%s artifact=%s",
                workspace_id,
                artifact_id,
                exc_info=True,
            )
            return False


@dataclass(frozen=True)
class _NeighbourMeta:
    """What the prompt and the permission filter need about one neighbour."""

    label: str
    workspace_id: UUID | None
    artifact_type: str


def _neighbour_meta(artifact_ids: Iterable[UUID]) -> dict[UUID, _NeighbourMeta]:
    """Map artifact id -> readable label, owning workspace and type.

    One query for the whole candidate set: the label is the specialised row's
    ``uid`` (the same readable id the indexer uses,
    ``application.artifact_indexer._artifact_label``), falling back to the
    artifact id. Resolving it in bulk is what allows the deterministic
    ``(hop, link_type, uid)`` order without a query per candidate.
    """
    from application.artifact_indexer import _ARTIFACT_ACCESSORS

    ids = {artifact_id for artifact_id in artifact_ids if artifact_id is not None}
    if not ids:
        return {}
    accessors = tuple(sorted(set(_ARTIFACT_ACCESSORS.values())))
    rows = Artifact.objects.filter(id__in=ids).select_related(*accessors)
    meta: dict[UUID, _NeighbourMeta] = {}
    for row in rows:
        accessor = _ARTIFACT_ACCESSORS.get(row.artifact_type)
        related = getattr(row, accessor, None) if accessor else None
        label = getattr(related, "uid", None)
        meta[row.id] = _NeighbourMeta(
            label=str(label or row.id),
            workspace_id=row.workspace_id,
            artifact_type=row.artifact_type,
        )
    return meta


def _collect_candidates(artifact_id: UUID, depth: int) -> list[_Neighbour]:
    """Every trace link up to *depth* hops around *artifact_id*, deduplicated.

    A neighbour may be connected by more than one link type; each distinct
    ``(neighbour, link_type)`` pair is one entry, because the relation -- not
    just the neighbour -- is what the summary has to describe. Hop 2 is only
    collected when asked for; both hops stay in application-level lists so the
    whole selection is deterministic.
    """
    candidates: list[_Neighbour] = []
    seen: set[tuple[UUID, str]] = set()

    frontier = {artifact_id}
    scope = {artifact_id}
    for hop in range(1, depth + 1):
        if not frontier:
            break
        links = TraceLink.objects.filter(
            Q(source_id__in=frontier) | Q(target_id__in=frontier)
        ).values(
            "source_id", "target_id", "link_type", "rationale", "modified_at"
        )
        next_frontier: set[UUID] = set()
        for link in links:
            source_id = link["source_id"]
            target_id = link["target_id"]
            neighbour_id = target_id if source_id in frontier else source_id
            if neighbour_id in scope:
                continue
            key = (neighbour_id, link["link_type"])
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                _Neighbour(
                    artifact_id=neighbour_id,
                    link_type=link["link_type"],
                    direction=(
                        "outgoing" if source_id in frontier else "incoming"
                    ),
                    hop=hop,
                    rationale=link["rationale"] or "",
                    link_modified_at=link["modified_at"],
                )
            )
            next_frontier.add(neighbour_id)
        scope.update(next_frontier)
        frontier = next_frontier
    return candidates


def _artifact_section(
    artifact: Artifact, *, char_limit: int
) -> tuple[dict[str, Any], str]:
    """Build the focus-artifact section and its uncapped text.

    The text is rendered from the same per-type field list the indexer uses
    (``artifact_indexer.SOURCES``), so "what this artifact says" has exactly one
    definition in the codebase. The uncapped text feeds the content hash -- a
    change beyond the prompt cap must still invalidate the cache.
    """
    from application.artifact_indexer import _ARTIFACT_ACCESSORS, SOURCES

    accessor = _ARTIFACT_ACCESSORS.get(artifact.artifact_type)
    related = getattr(artifact, accessor, None) if accessor else None
    spec = SOURCES.get(artifact.artifact_type)
    full_text = spec.render(related) if spec is not None and related is not None else ""
    label = getattr(related, "uid", None)
    section = {
        "id": str(artifact.id),
        "artifact_type": artifact.artifact_type,
        "label": str(label or artifact.id),
        "text": full_text[:char_limit],
    }
    return section, full_text


def _neighbour_entry(neighbour: _Neighbour, label: str, *, char_limit: int) -> dict[str, Any]:
    """One prompt entry; the JSON form never exceeds *char_limit* characters."""
    entry: dict[str, Any] = {
        "label": label,
        "artifact_type": None,
        "link_type": neighbour.link_type,
        "direction": neighbour.direction,
        "hop": neighbour.hop,
        "rationale": neighbour.rationale,
    }
    while entry["rationale"] and len(json.dumps(entry, ensure_ascii=False)) > char_limit:
        entry["rationale"] = entry["rationale"][
            : max(0, len(entry["rationale"]) - 20)
        ]
    return entry


def _content_hash(section: dict[str, Any], full_text: str) -> str:
    """SHA-256 over the canonical serialised focus artifact (spec §5.4).

    Deliberately not ``Artifact.version`` (an optimistic-lock counter that moves
    without a content change) and not ``ArtifactVersion.revision`` (extra
    query, and not every type has one).
    """
    material = json.dumps(
        {
            "id": section["id"],
            "artifact_type": section["artifact_type"],
            "text": full_text,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _summary_cache_key(
    *,
    artifact_id: UUID,
    content_hash: str,
    trace_depth: int,
    neighbours: Sequence[tuple[str, str, str]],
    provider_name: str,
    language: str,
    prompt: str,
) -> str:
    """Cache key over content, visible neighbours, provider, language and prompt.

    Every part is deliberate: the rendered prompt makes a template edit or a
    provider switch visible; ``trace_depth`` and the neighbour identities make
    two different visible sets two different entries (the anti-leak property of
    spec §5.5); ``language`` keeps a language switch from being masked for a
    full TTL.
    """
    material = json.dumps(
        {
            "artifact_id": str(artifact_id),
            "content_hash": content_hash,
            "trace_depth": trace_depth,
            "neighbours": [list(entry) for entry in neighbours],
            "provider": provider_name,
            "language": language,
            "prompt": prompt,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"{_CACHE_PREFIX}:{digest}"


def _cached_text(entry: Any) -> tuple[str, datetime] | None:
    """Read a cache entry defensively; anything unexpected counts as a miss."""
    if not isinstance(entry, dict):
        return None
    text = entry.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    raw_generated_at = entry.get("generated_at")
    try:
        generated_at = datetime.fromisoformat(str(raw_generated_at))
    except (TypeError, ValueError):
        generated_at = timezone.now()
    if timezone.is_naive(generated_at):
        generated_at = generated_at.replace(tzinfo=datetime.timezone.utc)
    return text, generated_at


#: Keys every stored-summary payload carries, on both transports (REST and MCP
#: share this dict builder, so a field cannot appear on one channel only).
SUMMARY_PAYLOAD_KEYS: tuple[str, ...] = (
    "workspace_id",
    "summary_kind",
    "artifact_type",
    "artifact_id",
    "text",
    "reason",
    "stale",
    "item_count",
    "status",
    "provider",
    "model",
    "token_usage",
    "trigger",
    "generated_at",
    "updated_at",
)


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def empty_summary_payload(
    workspace_id: UUID | str,
    *,
    summary_kind: str,
    artifact_type: str | None = None,
    artifact_id: UUID | str | None = None,
) -> dict[str, Any]:
    """The answer for a scope that has no stored state yet.

    Spec §6.5: an empty type is *not* a degradation — ``text``/``reason`` are
    ``null`` and ``item_count`` is 0, so the UI can say "not summarised yet"
    without inventing a reason.
    """
    return {
        "workspace_id": str(workspace_id),
        "summary_kind": summary_kind,
        "artifact_type": artifact_type,
        "artifact_id": str(artifact_id) if artifact_id is not None else None,
        "text": None,
        "reason": None,
        "stale": False,
        "item_count": 0,
        "status": None,
        "provider": None,
        "model": None,
        "token_usage": None,
        "trigger": None,
        "generated_at": None,
        "updated_at": None,
    }


def stored_summary_payload(row: ArtifactSummary, *, stale: bool) -> dict[str, Any]:
    """The wire form of one stored summary row (spec §6.6).

    ``reason`` falls back to ``"stale"`` when a previously successful row has
    aged past its freshness horizon (spec §6.5): the stored ``reason`` column
    only describes the *last run*, and a stale ``ok`` row has no reason of its
    own. The four E11 values stay the only possible strings (CWE-209).
    """
    digest = row.input_digest if isinstance(row.input_digest, dict) else {}
    try:
        item_count = int(digest.get("item_count") or 0)
    except (TypeError, ValueError):
        item_count = 0
    reason = row.reason or (DEGRADED_STALE if stale else None)
    return {
        "workspace_id": str(row.workspace_id),
        "summary_kind": row.summary_kind,
        "artifact_type": row.artifact_type or None,
        "artifact_id": str(row.artifact_id) if row.artifact_id else None,
        "text": row.text or None,
        "reason": reason,
        "stale": stale,
        "item_count": item_count,
        "status": row.status or None,
        "provider": row.provider or None,
        "model": row.model or None,
        "token_usage": row.token_usage,
        "trigger": row.trigger or None,
        "generated_at": _iso_or_none(row.generated_at),
        "updated_at": _iso_or_none(getattr(row, "modified_at", None)),
    }


def _stale_interval_minutes(workspace: Workspace) -> int:
    """The freshness horizon in minutes; ``0`` means "nothing refreshes".

    A switched-off sweep (global flag off, or the workspace cadence at 0) makes
    every stored state stale — the read path then reports ``stale=true`` and
    ``reason="stale"`` instead of silently presenting an ageing text as
    current (S5 plan §7, spec §6.5). Imported lazily: the sweep module imports
    this one.
    """
    from application.artifact_summary_sweep import interval_for_workspace, sweep_enabled

    if not sweep_enabled():
        return 0
    return interval_for_workspace(workspace)


def _summary_is_stale(row: ArtifactSummary, interval_minutes: int) -> bool:
    """``generated_at < now - 2 x interval`` (spec §6.5), for successful rows."""
    if row.status != ArtifactSummary.Status.OK or row.generated_at is None:
        return False
    cutoff = timezone.now() - timedelta(minutes=2 * interval_minutes)
    return row.generated_at < cutoff


class ArtifactSummaryService(ServiceBase):
    """AI summaries: the cache-only artifact scope and the stored type scope.

    The artifact scope (:meth:`summarize_artifact`) is on demand and writes
    nothing; the type/artifact scopes that S5 persists are read by the
    ``*_summary`` methods below and refreshed by
    :meth:`refresh_type_summary`. Every public method re-checks the caller's
    roles *in the addressed workspace* before returning a payload.
    """

    def summarize_artifact(
        self,
        artifact_id: UUID | str,
        ctx: AuthContext,
        *,
        refresh: bool = False,
        depth: int | None = None,
    ) -> ArtifactSummaryResult:
        """Summarise *artifact_id* for *ctx*; never raises for provider problems.

        Raises:
            NotFoundError: the artifact does not exist in the caller's tenant.
            PermissionDeniedError: the caller has no effective ``read`` on it.
            ValidationError: ``artifact_id`` is not a UUID.
        """
        artifact_uuid = _as_uuid(artifact_id)
        self._set_tenant_context(ctx)

        artifact = Artifact.objects.filter(id=artifact_uuid).first()
        if artifact is None:
            raise NotFoundError(f"Artifact {artifact_uuid} not found.")

        workspace = (
            Workspace.objects.filter(id=artifact.workspace_id)
            .only("id", "language")
            .first()
        )
        workspace_id = workspace.id if workspace is not None else artifact.workspace_id
        trace_depth = resolve_trace_depth(workspace, depth)

        access = _ReadAccess(ctx)
        if not access.can_read(workspace_id, artifact.id):
            raise PermissionDeniedError(
                f"Permission denied: no read access to artifact {artifact_uuid}."
            )

        if not bool(getattr(settings, "ARTIFACT_SUMMARY_ENABLED", False)):
            # Spec §5.6: a switch that is off is a *reason*, not an error, and
            # it answers before any payload work or provider resolution.
            logger.info("artifact_summary: disabled by flag")
            return self._result(
                artifact,
                trace_depth=trace_depth,
                text=None,
                degraded_reason=DEGRADED_DISABLED,
            )

        limits = SummaryLimits.from_settings()
        language = (getattr(workspace, "language", "") or "en").strip() or "en"

        section, full_text = _artifact_section(
            artifact, char_limit=limits.max_chars_per_section
        )
        content_hash = _content_hash(section, full_text)

        candidates = _collect_candidates(artifact.id, trace_depth)
        meta = _neighbour_meta(candidate.artifact_id for candidate in candidates)

        visible: list[_Neighbour] = []
        for candidate in candidates:
            info = meta.get(candidate.artifact_id)
            owning_workspace = info.workspace_id if info is not None else None
            # Permission filter BEFORE the payload: a neighbour the caller may
            # not read never enters the prompt (spec §5.5).
            if not access.can_read(owning_workspace, candidate.artifact_id):
                continue
            visible.append(candidate)

        # Deterministic: all hop-1 entries before every hop-2 entry, then link
        # type, then the readable label (the uid when the type has one).
        visible.sort(
            key=lambda item: (
                item.hop,
                item.link_type,
                meta[item.artifact_id].label
                if item.artifact_id in meta
                else str(item.artifact_id),
            )
        )
        capped = visible[: limits.max_neighbours]
        omitted = len(candidates) - len(capped)

        entries = [
            _neighbour_entry(
                neighbour,
                (
                    meta[neighbour.artifact_id].label
                    if neighbour.artifact_id in meta
                    else str(neighbour.artifact_id)
                ),
                char_limit=limits.max_chars_per_neighbour,
            )
            for neighbour in capped
        ]
        for entry, neighbour in zip(entries, capped):
            info = meta.get(neighbour.artifact_id)
            entry["artifact_type"] = info.artifact_type if info is not None else None

        provider, provider_name, resolve_error = self._resolve_provider()

        try:
            from application.ai_derivation_service import AiDerivationService

            prompt = AiDerivationService._resolve_and_render(
                ctx,
                PROMPT_TEMPLATE_NAME,
                workspace_id,
                artifact_json=json.dumps(section, ensure_ascii=False, sort_keys=True),
                neighbours_json=json.dumps(entries, ensure_ascii=False, sort_keys=True),
                artifact_type=artifact.artifact_type,
                language=language,
            )
            # Until S7 centralises the directive in ``application.ai_language``,
            # the one existing source is this helper (spec §7.6).
            prompt += AiDerivationService._language_instruction(workspace_id)
        except Exception:  # noqa: BLE001 - degrade, never fail the request
            logger.exception("artifact_summary: prompt resolution failed")
            return self._result(
                artifact,
                trace_depth=trace_depth,
                text=None,
                degraded_reason=DEGRADED_PROVIDER_UNAVAILABLE,
                neighbour_count=len(capped),
                omitted_neighbours=omitted,
            )

        cache_key = _summary_cache_key(
            artifact_id=artifact.id,
            content_hash=content_hash,
            trace_depth=trace_depth,
            neighbours=[
                (
                    str(neighbour.artifact_id),
                    neighbour.link_type,
                    _timestamp(neighbour.link_modified_at),
                )
                for neighbour in capped
            ],
            provider_name=provider_name,
            language=language,
            prompt=prompt,
        )

        if not refresh:
            cached = _cached_text(cache.get(cache_key))
            if cached is not None:
                text, generated_at = cached
                return self._result(
                    artifact,
                    trace_depth=trace_depth,
                    text=text,
                    neighbour_count=len(capped),
                    omitted_neighbours=omitted,
                    cache_hit=True,
                    generated_at=generated_at,
                )

        inflight_key = f"{_INFLIGHT_PREFIX}:{artifact.id}"
        if cache.get(inflight_key):
            # Another run for this artifact is in progress. Spending a second
            # paid call for the same input is exactly what the marker prevents;
            # the finer cause stays in the log (the response only carries the
            # enum, spec §5.7).
            logger.warning(
                "artifact_summary: a run for artifact %s is already in flight; "
                "returning degraded",
                artifact.id,
            )
            return self._result(
                artifact,
                trace_depth=trace_depth,
                text=None,
                degraded_reason=DEGRADED_PROVIDER_UNAVAILABLE,
                neighbour_count=len(capped),
                omitted_neighbours=omitted,
            )

        cache.set(
            inflight_key,
            "1",
            max(1, limits.min_interval_seconds),
        )
        try:
            text, degraded_reason = self._complete(
                prompt, provider, provider_name, resolve_error
            )
        finally:
            cache.delete(inflight_key)

        generated_at = timezone.now()
        if text is not None and degraded_reason is None:
            cache.set(
                cache_key,
                {"text": text, "generated_at": generated_at.isoformat()},
                limits.cache_ttl_seconds,
            )
        return self._result(
            artifact,
            trace_depth=trace_depth,
            text=text,
            degraded_reason=degraded_reason,
            neighbour_count=len(capped),
            omitted_neighbours=omitted,
            generated_at=generated_at,
        )

    # -- periodic per-type scope (issue #1793 / S5) ----------------------

    def summarize_artifact_type(
        self,
        ctx: AuthContext,
        workspace_id: UUID | str,
        artifact_type: str,
        *,
        trigger: str = "periodic",
    ) -> str:
        """Summarise every artifact of *artifact_type* in one workspace.

        Returns ``summarized|skipped:<reason>|failed``. The write is an upsert
        into :class:`~persistence.models.ArtifactSummary` (one row per
        ``(workspace, artifact_type)``), so a second run with an unchanged
        input is a no-op that does **not** touch ``updated_at`` (spec §6.5).

        Gates that need identity/schedule live in
        :mod:`application.artifact_summary_sweep`; this method only owns the
        content and the row. It still re-checks the summary-only budget so a
        direct/manual call (S6) cannot bypass §9/E8.
        """
        from application.ai_derivation_service import AiDerivationService
        from application.artifact_indexer import SOURCES, _artifact_label
        from application.summary_support import TYPE_ROSTER_KIND, upsert_summary

        self._set_tenant_context(ctx)
        workspace = (
            Workspace.objects.filter(id=workspace_id)
            .only("id", "tenant_id", "language")
            .first()
        )
        if workspace is None:
            return "skipped:no_workspace"

        spec = SOURCES.get(artifact_type)
        if spec is None:
            return "skipped:unknown_type"

        rows = _roster_rows(spec, workspace, artifact_type)
        if not rows:
            # Spec §6.5: an empty type is not a summary opportunity — no call,
            # no write.
            return "skipped:empty"

        items = _roster_items(rows, spec, _artifact_label)
        language = (getattr(workspace, "language", "") or "en").strip() or "en"
        provider, provider_name, resolve_error = self._resolve_provider()
        items_json = json.dumps(items, ensure_ascii=False, sort_keys=True)

        try:
            prompt = AiDerivationService._resolve_and_render(
                ctx,
                TYPE_SUMMARY_PROMPT_TEMPLATE_NAME,
                workspace.id,
                artifact_type=artifact_type,
                items_json=items_json,
                item_count=len(items),
                language=language,
            )
            prompt += AiDerivationService._language_instruction(workspace.id)
        except Exception:  # noqa: BLE001 - degrade, never fail the sweep
            logger.exception("artifact_type_summary: prompt resolution failed")
            return "failed"

        content_hash = _roster_content_hash(
            items=items,
            prompt=prompt,
            provider_name=provider_name,
            language=language,
        )
        existing = ArtifactSummary.objects.filter(
            workspace=workspace,
            summary_kind=TYPE_ROSTER_KIND,
            artifact_type=artifact_type,
        ).first()
        if (
            existing is not None
            and existing.status == ArtifactSummary.Status.OK
            and existing.content_hash == content_hash
        ):
            return "skipped:unchanged"

        latest_updated = max(
            (row.modified_at for row in rows if getattr(row, "modified_at", None)),
            default=None,
        )
        digest = {
            "item_count": len(items),
            "latest_updated_at": latest_updated.isoformat() if latest_updated else None,
        }

        if summary_budget_exhausted():
            logger.warning(
                "artifact_type_summary: summary budget exhausted for %s/%s",
                workspace.id,
                artifact_type,
            )
            upsert_summary(
                workspace=workspace,
                summary_kind=TYPE_ROSTER_KIND,
                artifact_type=artifact_type,
                values={
                    "text": existing.text if existing is not None else "",
                    "content_hash": content_hash,
                    "input_digest": digest,
                    "prompt_slot": TYPE_SUMMARY_PROMPT_TEMPLATE_NAME,
                    "provider": provider_name,
                    "trigger": trigger,
                    "status": ArtifactSummary.Status.SKIPPED,
                    "reason": ArtifactSummary.Reason.BUDGET_EXHAUSTED,
                },
            )
            return "skipped:budget_exhausted"

        if provider is None or provider_name == MOCK_PROVIDER_NAME:
            logger.warning(
                "artifact_type_summary: no usable LLM provider (%s)",
                resolve_error or provider_name,
            )
            upsert_summary(
                workspace=workspace,
                summary_kind=TYPE_ROSTER_KIND,
                artifact_type=artifact_type,
                values={
                    "text": existing.text if existing is not None else "",
                    "content_hash": content_hash,
                    "input_digest": digest,
                    "prompt_slot": TYPE_SUMMARY_PROMPT_TEMPLATE_NAME,
                    "provider": provider_name,
                    "trigger": trigger,
                    "status": ArtifactSummary.Status.FAILED,
                    "reason": ArtifactSummary.Reason.PROVIDER_UNAVAILABLE,
                },
            )
            return "skipped:no_provider"

        timeout = float(getattr(settings, "SUMMARY_SYNC_TIMEOUT_SECONDS", 20))
        try:
            text = provider.complete(
                prompt,
                purpose=TYPE_SUMMARY_PROMPT_TEMPLATE_NAME,
                timeout=timeout,
            )
        except Exception:  # noqa: BLE001 - one failed scope must not abort the sweep
            logger.exception(
                "artifact_type_summary: provider call failed for %s/%s",
                workspace.id,
                artifact_type,
            )
            upsert_summary(
                workspace=workspace,
                summary_kind=TYPE_ROSTER_KIND,
                artifact_type=artifact_type,
                values={
                    "text": existing.text if existing is not None else "",
                    "content_hash": content_hash,
                    "input_digest": digest,
                    "prompt_slot": TYPE_SUMMARY_PROMPT_TEMPLATE_NAME,
                    "provider": provider_name,
                    "trigger": trigger,
                    "status": ArtifactSummary.Status.FAILED,
                    "reason": ArtifactSummary.Reason.PROVIDER_UNAVAILABLE,
                },
            )
            return "failed"

        cleaned = (text or "").strip()
        if not cleaned:
            return "skipped:empty_answer"

        from llm_adapter.token_tracking import (
            approximate_token_count,
            record_token_usage,
        )

        input_tokens = approximate_token_count(prompt)
        output_tokens = approximate_token_count(cleaned)
        record_token_usage(
            provider=provider_name,
            capability=TYPE_SUMMARY_PROMPT_TEMPLATE_NAME,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            workspace_id=str(workspace.id),
        )

        upsert_summary(
            workspace=workspace,
            summary_kind=TYPE_ROSTER_KIND,
            artifact_type=artifact_type,
            values={
                "text": cleaned,
                "content_hash": content_hash,
                "input_digest": digest,
                "prompt_slot": TYPE_SUMMARY_PROMPT_TEMPLATE_NAME,
                "provider": provider_name,
                "model": str(
                    getattr(provider, "MODEL_NAME", "")
                    or getattr(provider, "model", "")
                    or ""
                ),
                "token_usage": input_tokens + output_tokens,
                "trigger": trigger,
                "status": ArtifactSummary.Status.OK,
                "reason": "",
                "generated_at": timezone.now(),
            },
        )
        return "summarized"

    # -- stored per-scope summaries (issue #1793 / S6) -------------------

    def list_type_summaries(
        self, ctx: AuthContext, workspace_id: UUID | str
    ) -> dict[str, Any]:
        """Return the stored type-roster states of one workspace (read-only).

        One payload per artifact type that has ever been summarised, ordered by
        type and capped at :data:`MAX_SUMMARY_ROWS`. A type without a row is
        simply absent; the MCP ``summary.get`` and the REST list are the same
        read, so both channels agree on that shape.

        Raises:
            NotFoundError: workspace unknown (including another tenant's).
            PermissionDeniedError: no read role in the workspace, or an
                API-key workspace fence excludes it.
            ValidationError: ``workspace_id`` is not a UUID.
        """
        workspace = self._summary_workspace(ctx, workspace_id)
        rows = list(
            ArtifactSummary.objects.filter(
                workspace=workspace,
                summary_kind=TYPE_ROSTER_KIND,
            ).order_by("artifact_type")[: MAX_SUMMARY_ROWS + 1]
        )
        truncated = len(rows) > MAX_SUMMARY_ROWS
        stale_interval = _stale_interval_minutes(workspace)
        summaries = [
            stored_summary_payload(
                row, stale=_summary_is_stale(row, stale_interval)
            )
            for row in rows[:MAX_SUMMARY_ROWS]
        ]
        return {
            "workspace_id": str(workspace.id),
            "summaries": summaries,
            "count": len(summaries),
            "truncated": truncated,
            "limit": MAX_SUMMARY_ROWS,
        }

    def get_type_summary(
        self,
        ctx: AuthContext,
        workspace_id: UUID | str,
        artifact_type: str,
    ) -> dict[str, Any]:
        """Return the stored state of one ``(workspace, artifact_type)`` scope.

        A type that was never summarised answers the empty payload (``text``
        ``null``, ``item_count`` 0, ``reason`` ``null``) rather than 404: the
        type itself is not an addressable resource, only the workspace is.

        Raises: same as :meth:`list_type_summaries`; additionally
        ``ValidationError`` for an empty ``artifact_type``.
        """
        type_key = str(artifact_type or "").strip()
        if not type_key:
            raise ValidationError("artifact_type must be a non-empty string.")
        workspace = self._summary_workspace(ctx, workspace_id)
        row = ArtifactSummary.objects.filter(
            workspace=workspace,
            summary_kind=TYPE_ROSTER_KIND,
            artifact_type=type_key,
        ).first()
        if row is None:
            return empty_summary_payload(
                workspace.id, summary_kind=TYPE_ROSTER_KIND, artifact_type=type_key
            )
        return stored_summary_payload(
            row, stale=_summary_is_stale(row, _stale_interval_minutes(workspace))
        )

    def get_artifact_scope_summary(
        self,
        ctx: AuthContext,
        workspace_id: UUID | str,
        artifact_id: UUID | str,
    ) -> dict[str, Any]:
        """Return the stored ``artifact``-scope state of one artifact.

        This reads the **persisted** state only; it never triggers a provider
        call (``summary.refresh``/``artifact.summary`` are the spending paths).
        A scope that was never written answers the empty payload — the
        cache-only on-demand summary of #1792 does not write rows.

        Raises:
            NotFoundError: workspace or artifact unknown (another tenant's, or
                an artifact of a different workspace).
            PermissionDeniedError: no read role, or an item-level deny on the
                artifact.
            ValidationError: ``artifact_id`` is not a UUID.
        """
        artifact_uuid = _as_uuid(artifact_id)
        workspace = self._summary_workspace(ctx, workspace_id)
        artifact = Artifact.objects.filter(
            id=artifact_uuid, workspace_id=workspace.id
        ).first()
        if artifact is None:
            raise NotFoundError(f"Artifact {artifact_uuid} not found.")
        if not _ReadAccess(ctx).can_read(workspace.id, artifact.id):
            raise PermissionDeniedError(
                f"Permission denied: no read access to artifact {artifact_uuid}."
            )
        row = ArtifactSummary.objects.filter(
            workspace=workspace,
            summary_kind=ARTIFACT_KIND,
            artifact=artifact,
        ).first()
        if row is None:
            return empty_summary_payload(
                workspace.id,
                summary_kind=ARTIFACT_KIND,
                artifact_id=artifact.id,
            )
        return stored_summary_payload(
            row, stale=_summary_is_stale(row, _stale_interval_minutes(workspace))
        )

    def refresh_type_summary(
        self,
        ctx: AuthContext,
        workspace_id: UUID | str,
        artifact_type: str,
    ) -> dict[str, Any]:
        """Run one manual type-roster scope and return the resulting state.

        The manual path deliberately bypasses the workspace *cadence* (that is
        the point of a refresh) while keeping every brake of the periodic run:
        the switch, the summary-only day budget, the agent key and the
        min-interval throttle (``ArtifactSummarySweeper.run_for_scope`` with
        ``manual=True``).

        Returns the stored state (same shape as :meth:`get_type_summary`) plus
        ``outcome`` — the sweeper's
        ``summarized|skipped:<reason>|failed`` verdict, so a caller can tell
        "unchanged" from "budget exhausted" without parsing prose.

        Raises: ``NotFoundError``/``PermissionDeniedError`` as the read path;
        ``PermissionDeniedError`` additionally when the caller has no write
        role in the workspace (a refresh can spend money).
        """
        type_key = str(artifact_type or "").strip()
        if not type_key:
            raise ValidationError("artifact_type must be a non-empty string.")
        workspace = self._summary_workspace(ctx, workspace_id)
        if not _ReadAccess(ctx).can_write(workspace.id):
            raise PermissionDeniedError(
                "Permission denied: refreshing a summary requires write access "
                f"to workspace {workspace.id}."
            )

        from application.artifact_summary_sweep import ArtifactSummarySweeper

        outcome = ArtifactSummarySweeper(service=self).run_for_scope(
            tenant_id=ctx.tenant_id,
            workspace_id=workspace.id,
            artifact_type=type_key,
            trigger=ArtifactSummary.Trigger.MANUAL.value,
            manual=True,
        )
        # Re-read through the public read path so the response cannot drift from
        # what a plain GET would answer.
        payload = self.get_type_summary(ctx, workspace.id, type_key)
        payload["outcome"] = outcome
        return payload

    # -- helpers ---------------------------------------------------------

    def _summary_workspace(
        self, ctx: AuthContext, workspace_id: UUID | str
    ) -> Workspace:
        """Resolve *workspace_id* for *ctx* and enforce a read decision.

        A workspace outside the caller's tenant is ``NOT_FOUND`` (no existence
        leak); a same-tenant workspace without a role is ``PERMISSION_DENIED``.
        """
        workspace_uuid = _as_uuid(workspace_id, "workspace_id")
        self._set_tenant_context(ctx)
        workspace = Workspace.objects.filter(id=workspace_uuid).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_uuid} not found.")
        if not _ReadAccess(ctx).can_read(workspace.id, None):
            raise PermissionDeniedError(
                f"Permission denied: no read access to workspace {workspace_uuid}."
            )
        return workspace

    @staticmethod
    def _result(
        artifact: Artifact,
        *,
        trace_depth: int,
        text: str | None,
        degraded_reason: str | None = None,
        neighbour_count: int = 0,
        omitted_neighbours: int = 0,
        cache_hit: bool = False,
        generated_at: datetime | None = None,
    ) -> ArtifactSummaryResult:
        return ArtifactSummaryResult(
            artifact_id=artifact.id,
            artifact_type=artifact.artifact_type,
            text=text,
            degraded=degraded_reason is not None,
            degraded_reason=degraded_reason,
            cache_hit=cache_hit,
            trace_depth=trace_depth,
            neighbour_count=neighbour_count,
            omitted_neighbours=omitted_neighbours,
            generated_at=generated_at or timezone.now(),
        )

    @staticmethod
    def _resolve_provider() -> tuple[Any | None, str, Exception | None]:
        """Resolve the effective provider (per-tenant overlay applied).

        Mirrors ``SearchSummaryService._resolve_provider``: resolved *before*
        the cache lookup so its name can be part of the key.
        """
        from llm_adapter.providers import (
            LlmNotConfiguredError,
            LlmProviderUnknownError,
            get_provider,
        )

        try:
            provider = get_provider()
        except (LlmNotConfiguredError, LlmProviderUnknownError) as error:
            return None, MOCK_PROVIDER_NAME, error

        return provider, str(getattr(provider, "PROVIDER_NAME", "unknown")), None

    @staticmethod
    def _complete(
        prompt: str,
        provider: Any | None,
        provider_name: str,
        resolve_error: Exception | None,
    ) -> tuple[str | None, str | None]:
        """Call the provider; return ``(text, degraded_reason)``, never raise."""
        from llm_adapter.providers import MockLlmProvider
        from llm_adapter.token_tracking import is_over_daily_limit

        if provider is None:
            logger.warning(
                "artifact_summary: no LLM provider (%s); returning degraded",
                resolve_error,
            )
            return None, DEGRADED_PROVIDER_UNAVAILABLE

        if provider_name == MOCK_PROVIDER_NAME or isinstance(provider, MockLlmProvider):
            # A placeholder is not a summary: do not cache it, and never present
            # mock text as an AI result (spec §5.8).
            logger.warning("artifact_summary: mock provider configured; degraded")
            return None, DEGRADED_PROVIDER_UNAVAILABLE

        if is_over_daily_limit():
            logger.warning("artifact_summary: daily token budget exhausted; degraded")
            return None, DEGRADED_BUDGET_EXHAUSTED

        timeout = float(getattr(settings, "SUMMARY_SYNC_TIMEOUT_SECONDS", 20))
        try:
            text = provider.complete(
                prompt, purpose=PROMPT_TEMPLATE_NAME, timeout=timeout
            )
        except Exception:  # noqa: BLE001 - degrade, never fail the request
            logger.exception("artifact_summary: provider call failed")
            return None, DEGRADED_PROVIDER_UNAVAILABLE

        if not isinstance(text, str) or not text.strip():
            return None, DEGRADED_PROVIDER_UNAVAILABLE
        return text.strip(), None


def _timestamp(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def _as_uuid(value: Any, name: str = "artifact_id") -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError):
        raise ValidationError(f"{name} must be a UUID.") from None


def _roster_rows(spec: Any, workspace: Workspace, artifact_type: str) -> list[Any]:
    """Return the tenant+workspace rows of one source type, deterministically.

    ``SOURCES`` entries are the same models the indexer renders into text, so
    the summary sees exactly what search sees. Sorting by primary key keeps the
    prompt (and therefore the content hash) stable across runs.
    """
    model = spec.model()
    manager = getattr(model, "unscoped", model.objects)
    queryset = manager.filter(tenant_id=workspace.tenant_id)
    if any(field.name == "workspace" for field in model._meta.get_fields()):
        queryset = queryset.filter(workspace_id=workspace.id)
    rows = [row for row in queryset if spec.workspace(row) == workspace.id]
    rows.sort(key=lambda row: str(row.pk))
    return rows


def _roster_items(rows: list[Any], spec: Any, label_of: Any) -> list[dict[str, Any]]:
    """Render at most ``ROSTER_MAX_ITEMS`` rows as compact, bounded entries."""
    items: list[dict[str, Any]] = []
    for row in rows[:ROSTER_MAX_ITEMS]:
        text = spec.render(row)
        items.append(
            {
                "id": str(row.pk),
                "label": label_of(row),
                "text": text[:ROSTER_MAX_CHARS_PER_ITEM],
            }
        )
    return items


def _roster_content_hash(
    *, items: list[dict[str, Any]], prompt: str, provider_name: str, language: str
) -> str:
    """Hash the input set plus everything that changes the answer (spec §6.5)."""
    payload = json.dumps(
        {
            "items": items,
            "prompt": prompt,
            "provider": provider_name,
            "language": language,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "DEFAULT_TRACE_DEPTH",
    "DEGRADATION_REASONS",
    "DEGRADED_BUDGET_EXHAUSTED",
    "DEGRADED_DISABLED",
    "DEGRADED_PROVIDER_UNAVAILABLE",
    "DEGRADED_STALE",
    "MAX_TRACE_DEPTH",
    "PROMPT_TEMPLATE_NAME",
    "ROSTER_MAX_CHARS_PER_ITEM",
    "ROSTER_MAX_ITEMS",
    "TYPE_SUMMARY_PROMPT_TEMPLATE_NAME",
    "ArtifactSummaryResult",
    "ArtifactSummaryService",
    "SummaryLimits",
    "resolve_trace_depth",
    "summary_budget_exhausted",
    "summary_daily_token_limit",
    "summary_tokens_used_today",
]
