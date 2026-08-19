"""Workspace Context Graph models (Issue #377, v1 slice).

Two new tenant-scoped tables, additive to the existing hard-edge graph
(``pl_artifact`` + ``pl_tracelink``) — never a replacement or a cache of it:

- ``ContextEdge``: derived, machine-suggested edges between artifacts.
  Never written to ``pl_tracelink`` and never given a ``LinkType`` value —
  ``LinkType`` feeds coverage/VCRM/baseline/SE-Auditor calculations, and a
  machine-guessed edge silently entering any of those is a correctness
  failure, not a style choice (see the implementation plan's Global
  Constraints).
- ``WorkspaceContextSettings``: per-workspace on/off + operational
  watermark state. Follows the "missing row = feature off, defaults apply"
  rule (the opposite of ``LlmSettings``' "row existence overrides config"
  rule, Issue #276) — a read path must never create a settings row as a
  side effect.
"""
from __future__ import annotations

from django.db import models

from persistence.models import TenantScopedModel


class ContextEdge(TenantScopedModel):
    """A derived, machine-suggested edge between two artifacts.

    Additive to the hard-edge trace-link graph, never a substitute for it.
    ``(source, target, edge_kind, origin)`` is unique so a generator's
    upsert-on-unique-constraint + full-recomputation-per-artifact design
    (see ``context_graph.projector``) is replay-safe.
    """

    source = models.ForeignKey(
        "persistence.Artifact",
        on_delete=models.CASCADE,
        related_name="context_edges_from",
    )
    target = models.ForeignKey(
        "persistence.Artifact",
        on_delete=models.CASCADE,
        related_name="context_edges_to",
    )
    edge_kind = models.CharField(
        max_length=32,
        choices=[
            ("related", "Related"),
            ("influences", "Influences"),
            ("refines", "Refines"),
            ("shares-term", "Shares Term"),
            # "contradicts" is intentionally NOT a choice here — resolved as
            # never machine-materialized, only a human-adopted suggestion,
            # out of scope for this plan entirely (Global Constraints).
        ],
    )
    origin = models.CharField(
        max_length=32,
        choices=[
            ("derived-glossary", "Derived: Glossary"),
            ("derived-embedding", "Derived: Embedding"),
            ("derived-cochange", "Derived: Co-change"),
            ("llm-suggested", "LLM Suggested"),
        ],
    )
    confidence = models.FloatField(help_text="0..1 — always 1.0 for deterministic generators.")
    evidence = models.JSONField(
        default=dict,
        blank=True,
        help_text="Human-verifiable justification, e.g. {'term_id': ..., 'term_name': ...}.",
    )
    generator = models.CharField(
        max_length=64,
        help_text="Generator name + version (e.g. 'glossary-v1'), for targeted invalidation.",
    )
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cg_context_edge"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "target", "edge_kind", "origin"],
                name="uq_context_edge",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "source"], name="idx_cg_edge_tenant_source"),
            models.Index(fields=["tenant", "target"], name="idx_cg_edge_tenant_target"),
            models.Index(fields=["tenant", "edge_kind"], name="idx_cg_edge_tenant_kind"),
        ]

    def __str__(self) -> str:  # pragma: no cover — debugging aid only
        return f"{self.source_id} -{self.edge_kind}-> {self.target_id} ({self.origin})"


class WorkspaceContextSettings(TenantScopedModel):
    """Per-workspace Context Graph configuration + operational watermark.

    "Missing row = feature off, defaults apply" — the opposite of
    ``LlmSettings``' "row existence overrides config" rule (Issue #276). A
    read path (:mod:`application.context_service`) must never create this
    row as a side effect; only the settings-write path (Task 9) does.
    """

    workspace = models.OneToOneField(
        "persistence.Workspace", on_delete=models.CASCADE, unique=True
    )
    enabled = models.BooleanField(
        default=False, help_text="Event-sourced maintenance on/off for this workspace."
    )
    schedule_enabled = models.BooleanField(
        default=False,
        help_text="Not used until Folge-Issue B (cron scheduling) — no scheduler reads this in v1.",
    )
    refresh_interval_minutes = models.IntegerField(
        null=True, blank=True, help_text="Unused in v1, see schedule_enabled."
    )
    provider = models.CharField(
        max_length=32,
        default="embedded",
        help_text='Only "embedded" is a valid value in v1 — rejected elsewhere at the write path.',
    )
    enabled_generators = models.JSONField(default=list, blank=True, help_text='e.g. ["glossary"].')
    last_projected_at = models.DateTimeField(null=True, blank=True)
    last_refresh_at = models.DateTimeField(null=True, blank=True)
    last_event_id = models.UUIDField(
        null=True, blank=True, help_text="Watermark: the last outbox event_id this workspace projected."
    )
    last_error = models.TextField(blank=True, default="")
    node_count = models.IntegerField(default=0)
    edge_count = models.IntegerField(default=0)

    class Meta:
        db_table = "cg_workspace_context_settings"

    def __str__(self) -> str:  # pragma: no cover — debugging aid only
        return f"ContextSettings(workspace={self.workspace_id}, enabled={self.enabled})"


__all__ = ["ContextEdge", "WorkspaceContextSettings"]
