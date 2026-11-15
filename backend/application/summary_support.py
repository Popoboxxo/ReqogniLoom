"""Persistence helper for :class:`~persistence.models.ArtifactSummary`.

Issue #1793 / S4 (spec: ``docs/superpowers/specs/2026-11-14-ai-artifact-summaries-design.md``
§6.1, E4/E5). The summary table holds **one** row per scope and is overwritten
in place; this module owns that write shape so the sweep (S5) and the manual
refresh (S6) cannot drift apart.

Why not call ``update_or_create`` at every call site:

* **Scope lookup is kind-dependent.** ``artifact`` scopes key on
  ``(workspace, artifact)``, ``type_roster`` scopes on
  ``(workspace, artifact_type)``. Getting the lookup wrong silently creates a
  second row outside the partial unique constraint's reach.
* **The tenant must come from the workspace.** It is never a caller argument,
  so a caller cannot stamp a row for a different tenant.
* **A concurrent run must not surface an error.** Two workers may insert the
  same scope at once; the loser's ``IntegrityError`` is absorbed and the row is
  re-read and updated (spec §6.1). Last writer wins — the end state is the same
  either way, so the failure is noise, not data loss.

The caller must have the tenant context armed (:class:`TenantContext`), like
every other write path through a ``TenantScopedModel`` manager.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.db import IntegrityError, transaction

from persistence.models import ArtifactSummary, Workspace

#: Kinds the helper accepts. Kept in sync with :class:`ArtifactSummary.SummaryKind`
#: but as literals, because the column itself is deliberately loose.
ARTIFACT_KIND = ArtifactSummary.SummaryKind.ARTIFACT.value
TYPE_ROSTER_KIND = ArtifactSummary.SummaryKind.TYPE_ROSTER.value


def scope_lookup(
    workspace: Workspace,
    summary_kind: str,
    *,
    artifact: Any | None = None,
    artifact_type: str = "",
) -> dict[str, Any]:
    """Build the ORM lookup that identifies one summary scope.

    Raises:
        ValueError: if the kind/value combination cannot identify exactly one
            scope (e.g. ``artifact`` without an artifact, or a roster without a
            type). Failing here beats writing an unconstrained row.
    """
    if summary_kind == ARTIFACT_KIND:
        if artifact is None:
            raise ValueError("summary_kind='artifact' requires an artifact.")
        return {"workspace": workspace, "artifact": artifact}
    if summary_kind == TYPE_ROSTER_KIND:
        if not artifact_type:
            raise ValueError("summary_kind='type_roster' requires an artifact_type.")
        return {"workspace": workspace, "artifact_type": artifact_type}
    raise ValueError(f"Unknown summary_kind: {summary_kind!r}")


def upsert_summary(
    *,
    workspace: Workspace,
    summary_kind: str,
    values: Mapping[str, Any],
    artifact: Any | None = None,
    artifact_type: str = "",
    max_attempts: int = 2,
) -> ArtifactSummary:
    """Create or overwrite the single row for one summary scope.

    Args:
        workspace: Tenant-scoped workspace the summary belongs to. Its tenant is
            stamped on the row; passing a tenant explicitly would be a second
            source of truth and is therefore not supported.
        summary_kind: ``"artifact"`` or ``"type_roster"`` (depends on
            :class:`ArtifactSummary.SummaryKind`).
        values: Columns to write (``text``, ``content_hash``, ``status``, ...).
            ``tenant`` is stripped — it always follows the workspace.
        artifact: The summarized artifact for the artifact scope; ignored for
            type rosters.
        artifact_type: The summarized type for the type scope; ignored for
            artifact scopes.
        max_attempts: How often a concurrent-insert race is retried. One retry
            is enough in practice: the second attempt finds the winner's row.

    Returns:
        The persisted row (the same Python object for both insert and update).

    Raises:
        ValueError: on an incomplete/unknown scope (see :func:`scope_lookup`).
        IntegrityError: if the race persists after ``max_attempts``, so a real
            constraint problem is never swallowed.
    """
    lookup = scope_lookup(
        workspace,
        summary_kind,
        artifact=artifact,
        artifact_type=artifact_type,
    )
    defaults: dict[str, Any] = dict(values)
    defaults.pop("tenant", None)
    defaults.pop("tenant_id", None)
    defaults.update(
        {
            "workspace": workspace,
            "summary_kind": summary_kind,
            "tenant_id": workspace.tenant_id,
        }
    )
    if summary_kind == ARTIFACT_KIND:
        defaults["artifact"] = artifact
    else:
        defaults["artifact_type"] = artifact_type

    last_error: IntegrityError | None = None
    for _ in range(max(1, max_attempts)):
        try:
            # The inner atomic block isolates a lost insert race: PostgreSQL
            # aborts the transaction on IntegrityError, so the retry must run
            # outside the failed block.
            with transaction.atomic():
                row, _created = ArtifactSummary.objects.update_or_create(
                    **lookup, defaults=defaults
                )
            return row
        except IntegrityError as exc:  # pragma: no cover - race only
            last_error = exc

    raise last_error if last_error is not None else RuntimeError(
        "upsert_summary failed without an error"
    )
