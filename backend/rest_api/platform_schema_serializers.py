"""OpenAPI shapes for the platform/status REST surface (#1388).

Three groups of views describe a payload they never render through DRF:

* the **async status polls** in :mod:`rest_api.views`
  (``RequirementHistoryView``, the bundle-compression/consistency task polls and
  ``AttributeSchemaView``),
* the **pending-review queue** (:mod:`rest_api.review_views`),
* the **suggestion / metrics** surfaces
  (:mod:`rest_api.traceability_suggest_views`, :mod:`rest_api.metrics_views`).

Every one of them returns a service dict — ``AuditLogQuery`` rows,
``BundleCompressionService.get_compression_status``,
``ReviewQueueService.PendingReviewItem.to_dict``,
``SuggestLinksResult.to_dict``, ``se_metrics`` results — so the serializers
below exist **for the contract only**. They were transcribed from those
producers, not written to be used as renderers.

Views whose module already owns its domain's serializers (``audit_views``,
``settings_views``, ``prompt_variable_views``) keep them next to the views
instead; this module covers the adapters that carry none.
"""
from __future__ import annotations

from rest_framework import serializers

__all__ = [
    "AttributeSchemaEntrySerializer",
    "BundleCompressionStatusSerializer",
    "ConsistencyStatusSerializer",
    "LinkCandidateSerializer",
    "LinkSuggestionSerializer",
    "MetricCatalogueEntrySerializer",
    "MetricCatalogueSerializer",
    "MetricValuesEntrySerializer",
    "MetricValuesEnvelopeSerializer",
    "MetricsCoverageSerializer",
    "MetricsOpenRisksSerializer",
    "MetricsReportSerializer",
    "MetricsThresholdWarningSerializer",
    "MetricsVerificationCoverageSerializer",
    "MetricsVolatilitySerializer",
    "MetricsVolatileRequirementSerializer",
    "MetricsWorkflowGapSerializer",
    "MetricsWorkflowGapsSerializer",
    "PendingReviewItemSerializer",
    "PendingReviewPageSerializer",
    "RequirementHistoryEntrySerializer",
    "RequirementHistoryResponseSerializer",
    "SuggestLinksCountsSerializer",
    "SuggestLinksDispatchSerializer",
    "SuggestLinksResultSerializer",
    "SuggestLinksStatusSerializer",
]

#: The five task states ``AsyncTaskDispatcher`` reports (#1197 / #448 / GH-796).
_TASK_STATUSES = ["pending", "running", "done", "failed", "not_found"]


# ---------------------------------------------------------------------------
# rest_api.views — status polls and the attribute schema
# ---------------------------------------------------------------------------


class RequirementHistoryEntrySerializer(serializers.Serializer):
    """One audit entry of a requirement's history (``AuditLogQuery`` rows)."""

    id = serializers.CharField()
    actor = serializers.CharField(allow_null=True)
    actor_type = serializers.CharField(allow_null=True)
    operation = serializers.CharField(
        help_text="The audit row's ``op`` (create/update/delete/transition).",
    )
    timestamp = serializers.DateTimeField()
    change_reason = serializers.CharField(allow_blank=True, allow_null=True)
    entity_version = serializers.IntegerField(allow_null=True)
    source = serializers.CharField(allow_blank=True, allow_null=True)


class RequirementHistoryResponseSerializer(serializers.Serializer):
    """``GET /api/v1/requirements/{pk}/history/`` — paginated audit trail."""

    results = RequirementHistoryEntrySerializer(many=True)
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()


class BundleCompressionStatusSerializer(serializers.Serializer):
    """``GET /api/v1/bundle-compression-status/{task_id}/`` (issue #448).

    ``text`` carries the compressed bundle once the task is done; ``result`` is
    the deprecated raw Celery envelope kept for existing clients (new clients
    must read ``text``).
    """

    task_id = serializers.CharField()
    status = serializers.ChoiceField(choices=_TASK_STATUSES)
    text = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="The compressed bundle; null until status='done'.",
    )
    is_mock_fallback = serializers.BooleanField(
        required=False,
        help_text="True when no real LLM ran and 'text' is a placeholder.",
    )
    provider = serializers.CharField(required=False, allow_null=True)
    error = serializers.CharField(required=False, allow_null=True)
    result = serializers.DictField(
        required=False,
        allow_null=True,
        help_text="Deprecated raw Celery envelope: {'result': '<text>'}.",
    )


class ConsistencyStatusSerializer(serializers.Serializer):
    """``GET /api/v1/consistency-status/{task_id}/`` (GH-796).

    An unknown or foreign-tenant task id reports ``status='not_found'`` (ADR-03)
    rather than 403/404, so the status is part of the contract, not an error.
    """

    task_id = serializers.CharField()
    status = serializers.ChoiceField(choices=_TASK_STATUSES)
    result = serializers.DictField(
        required=False,
        allow_null=True,
        help_text="Present when status='done'.",
    )
    error = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Present when status='failed'.",
    )


class AttributeSchemaEntrySerializer(serializers.Serializer):
    """One row of ``GET /api/v1/attribute-schema/`` (GitHub #882, #1192).

    The endpoint answers a *bare JSON array* of these rows — one per
    (entity_type, attribute_name) — not an envelope.
    """

    entity_type = serializers.CharField()
    attribute_name = serializers.CharField()
    is_visible = serializers.BooleanField(
        help_text="The workspace's resolved visibility for this attribute.",
    )
    is_required = serializers.BooleanField(
        help_text="Whether the active approval gate demands this field.",
    )
    tier = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Resolved rigor preset, or null when unresolvable.",
    )


# ---------------------------------------------------------------------------
# rest_api.review_views — pending review queue
# ---------------------------------------------------------------------------


class PendingReviewItemSerializer(serializers.Serializer):
    """One row of the pending-review queue (``PendingReviewItem.to_dict``)."""

    item_id = serializers.CharField()
    item_type = serializers.CharField(
        help_text="Workflow item type, e.g. 'Requirement' or 'Adr'.",
    )
    current_state = serializers.CharField()
    workspace_id = serializers.CharField()
    is_proposal = serializers.BooleanField(
        help_text="True for an AI proposal awaiting confirmation.",
    )
    proposed_by = serializers.CharField(
        allow_blank=True,
        help_text="Actor of the newest ->'proposed' history entry, else ''.",
    )
    proposed_at = serializers.CharField(
        allow_blank=True,
        help_text="Timestamp of that entry (ISO-8601), else ''.",
    )
    approval_targets = serializers.ListField(
        child=serializers.CharField(),
        help_text="States reachable through an approval-gated transition.",
    )


class PendingReviewPageSerializer(serializers.Serializer):
    """``StandardPagination`` envelope of the review queue.

    ``next``/``previous`` are absolute URLs (null on the last/first page);
    ``page_size``/``max_page_size`` echo the applied slice size and the
    endpoint's ceiling (#571).
    """

    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    page_size = serializers.IntegerField()
    max_page_size = serializers.IntegerField()
    results = PendingReviewItemSerializer(many=True)


# ---------------------------------------------------------------------------
# rest_api.traceability_suggest_views — N3 suggestion runs
# ---------------------------------------------------------------------------


class LinkCandidateSerializer(serializers.Serializer):
    """One ranked, type-compatible candidate target (``LinkCandidate``)."""

    artifact_id = serializers.CharField()
    title = serializers.CharField()
    artifact_type = serializers.CharField()
    score = serializers.IntegerField(
        help_text="Plain keyword-overlap count against the source artifact.",
    )


class LinkSuggestionSerializer(serializers.Serializer):
    """One suggestion for one real audit finding (``LinkSuggestion``)."""

    finding_index = serializers.IntegerField(
        help_text="Index into the real AuditReport.findings list.",
    )
    rule_id = serializers.CharField()
    source_artifact_id = serializers.CharField()
    ranked_candidates = LinkCandidateSerializer(many=True)
    rationale = serializers.CharField(allow_blank=True)


class SuggestLinksCountsSerializer(serializers.Serializer):
    """The run's ``counts`` block."""

    total_findings = serializers.IntegerField(
        help_text="Findings returned by the underlying audit run (may be capped).",
    )
    eligible_findings = serializers.IntegerField()
    suggestions = serializers.IntegerField()


class SuggestLinksResultSerializer(serializers.Serializer):
    """200 body of the synchronous ``.../suggest-links/`` run (N3, phase 4b)."""

    tier = serializers.CharField()
    provider = serializers.CharField()
    degraded = serializers.BooleanField()
    suggestions = LinkSuggestionSerializer(many=True)
    truncated = serializers.BooleanField(
        help_text="True when the audit run was capped before packaging.",
    )
    total_findings_available = serializers.IntegerField()
    counts = SuggestLinksCountsSerializer()


class SuggestLinksDispatchSerializer(serializers.Serializer):
    """202 body of the ``?async=true`` branch: the Celery task id to poll."""

    task_id = serializers.CharField()


class SuggestLinksStatusSerializer(serializers.Serializer):
    """``GET /api/v1/traceability/suggest-links-status/{task_id}/`` (#1197).

    Same shape as the other task polls, with ``result`` carrying a
    ``SuggestLinksResult`` when the task is done.
    """

    task_id = serializers.CharField()
    status = serializers.ChoiceField(choices=_TASK_STATUSES)
    result = SuggestLinksResultSerializer(
        required=False,
        allow_null=True,
        help_text="Present when status='done'.",
    )
    error = serializers.CharField(required=False, allow_null=True)


# ---------------------------------------------------------------------------
# rest_api.metrics_views — se_metrics read model
# ---------------------------------------------------------------------------


class MetricsVolatileRequirementSerializer(serializers.Serializer):
    """One entry of ``volatility.top10_volatile``."""

    requirement_id = serializers.CharField()
    change_count = serializers.IntegerField()
    title = serializers.CharField(allow_blank=True)


class MetricsVolatilitySerializer(serializers.Serializer):
    """``volatility`` block."""

    total_changes = serializers.IntegerField()
    total_requirements = serializers.IntegerField()
    avg_changes_per_req = serializers.FloatField(allow_null=True)
    top10_volatile = MetricsVolatileRequirementSerializer(many=True)


class MetricsCoverageSerializer(serializers.Serializer):
    """A coverage block (``traceability_coverage``)."""

    total = serializers.IntegerField()
    covered = serializers.IntegerField()
    coverage_percent = serializers.FloatField(allow_null=True)
    uncovered_ids = serializers.ListField(child=serializers.CharField())


class MetricsVerificationCoverageSerializer(serializers.Serializer):
    """``verification_coverage`` block (#1267)."""

    total = serializers.IntegerField()
    covered = serializers.IntegerField()
    coverage_percent = serializers.FloatField(allow_null=True)
    uncovered_ids = serializers.ListField(child=serializers.CharField())


class MetricsWorkflowGapSerializer(serializers.Serializer):
    """One entry of ``workflow_gaps.items``."""

    item_id = serializers.CharField()
    item_type = serializers.CharField()
    missing_state = serializers.CharField()


class MetricsWorkflowGapsSerializer(serializers.Serializer):
    """``workflow_gaps`` block."""

    total_incomplete = serializers.IntegerField()
    items = MetricsWorkflowGapSerializer(many=True)


class MetricsOpenRisksSerializer(serializers.Serializer):
    """``open_risks`` block."""

    total = serializers.IntegerField()
    by_severity = serializers.DictField(
        child=serializers.IntegerField(),
        help_text="severity -> count.",
    )


class MetricsThresholdWarningSerializer(serializers.Serializer):
    """One entry of ``warnings``."""

    metric = serializers.CharField()
    actual = serializers.FloatField(allow_null=True)
    threshold = serializers.FloatField(allow_null=True)
    description = serializers.CharField(allow_blank=True)


class MetricsReportSerializer(serializers.Serializer):
    """``MetricsResult.to_dict()`` — the stable REQ-L2-SM-012 report.

    Returned by ``GET /api/v1/metrics/`` when the ``keys`` query parameter is
    absent (the values envelope below replaces it when ``keys`` is given).
    """

    workspace_id = serializers.CharField()
    computed_at = serializers.DateTimeField()
    timeframe = serializers.CharField()
    volatility = MetricsVolatilitySerializer()
    traceability_coverage = MetricsCoverageSerializer()
    workflow_gaps = MetricsWorkflowGapsSerializer()
    open_risks = MetricsOpenRisksSerializer()
    verification_coverage = MetricsVerificationCoverageSerializer()
    warnings = MetricsThresholdWarningSerializer(many=True)


class MetricValuesEntrySerializer(serializers.Serializer):
    """One requested statistic with its value (issue #1265)."""

    key = serializers.CharField()
    title = serializers.CharField()
    title_key = serializers.CharField(allow_blank=True)
    unit = serializers.CharField(allow_blank=True)
    scope = serializers.CharField()
    expensive = serializers.BooleanField()
    value = serializers.JSONField(
        allow_null=True,
        help_text="The statistic's scalar value; null when its extractor failed.",
    )
    computed_at = serializers.DateTimeField()


class MetricValuesEnvelopeSerializer(serializers.Serializer):
    """``get_metric_values`` envelope (``?keys=`` on ``GET /api/v1/metrics/``)."""

    workspace_id = serializers.CharField()
    computed_at = serializers.DateTimeField()
    timeframe = serializers.CharField()
    metrics = serializers.DictField(
        child=MetricValuesEntrySerializer(),
        help_text="metric key -> value entry.",
    )
    unknown_keys = serializers.ListField(
        child=serializers.CharField(),
        help_text="Requested keys this deployment does not register.",
    )


class MetricCatalogueEntrySerializer(serializers.Serializer):
    """One statistic's metadata (``MetricSpec.to_catalog_entry``)."""

    key = serializers.CharField()
    title = serializers.CharField()
    title_key = serializers.CharField(allow_blank=True)
    unit = serializers.CharField(allow_blank=True)
    scope = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    expensive = serializers.BooleanField(
        help_text="True when computing it is worth an explicit refresh.",
    )
    default_visible = serializers.BooleanField()
    source = serializers.CharField()
    params = serializers.ListField(
        child=serializers.CharField(),
        help_text="Query parameters this statistic accepts.",
    )


class MetricCatalogueSerializer(serializers.Serializer):
    """``GET /api/v1/metrics/catalog/`` — the available statistics (#1265)."""

    metrics = MetricCatalogueEntrySerializer(many=True)
    default_keys = serializers.ListField(
        child=serializers.CharField(),
        help_text="The set a caller with no explicit selection sees.",
    )
    all_keys = serializers.ListField(child=serializers.CharField())
