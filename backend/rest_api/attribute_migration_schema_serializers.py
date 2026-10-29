"""OpenAPI shapes for the AWMS attribute-migration REST surface (#1388).

:mod:`rest_api.attribute_migration_views` delegates every request to
``application.attribute_migration_service.AttributeMigrationService`` and
returns the service's report dicts unchanged. These serializers describe those
dicts for the generated contract only; nothing is rendered through them.

Source of truth for the shapes below:

* ``AttributeMigrationService._execute`` (the dry-run/apply report),
* ``_empty_outcome`` / ``_summary`` (per-step and run-wide counters),
* ``_scope_effect`` (how far a run reaches, issue #1083),
* ``_run_payload`` (one stored run) and ``rollback`` (the restore report).

Deliberate limit: a *step outcome* carries four generic blocks (``counts``,
``transform_counts``, ``changes``, ``errors``) plus keys that differ per
``op`` (a ``define_attribute`` step reports a definition key, a
``migrate_value`` step reports a transform summary, …). The plan format is a
closed, versioned schema in ``attribute_definitions.migration_plan``; the step
list here documents the generic contract and leaves the op-specific extras
undescribed rather than publishing a shape that is wrong for most steps.
"""
from __future__ import annotations

from rest_framework import serializers

__all__ = [
    "MigrationPlanRequestSerializer",
    "MigrationReportSerializer",
    "MigrationRollbackSerializer",
    "MigrationRunListSerializer",
    "MigrationRunSerializer",
    "MigrationScopeEffectSerializer",
    "MigrationScopeSerializer",
    "MigrationStepOutcomeSerializer",
    "MigrationSummarySerializer",
]

_PRESETS = ["minimal", "standard", "extended"]
_TARGET_SCOPES = ["read", "workspace", "tenant"]
_RUN_MODES = ["dry_run", "apply"]
_RUN_STATUSES = [
    "planned",
    "applied",
    "failed",
    "partial",
    "rolled_back",
    "partially_rolled_back",
]


class MigrationScopeSerializer(serializers.Serializer):
    """The normalized ``scope`` block of an executed plan."""

    tenant = serializers.CharField(
        help_text="'current' or a tenant UUID string.",
    )
    item_type = serializers.CharField()
    preset = serializers.ListField(
        child=serializers.ChoiceField(choices=_PRESETS),
        help_text="Presets the plan was resolved against.",
    )
    workspace = serializers.JSONField(
        help_text="'*' for every workspace, or a list of workspace UUIDs.",
    )


class MigrationScopeEffectSerializer(serializers.Serializer):
    """``_scope_effect`` — how far a run reaches (issue #1083).

    A definition op is tenant-wide by construction (``ad_global_definition`` has
    no ``workspace_id`` and propagates to every on-default workspace row of its
    preset), so ``scope.workspace`` narrows value ops only. The block says that
    outright instead of leaving it to be inferred from the counts.
    """

    target_scope = serializers.ChoiceField(choices=_TARGET_SCOPES)
    value_target_scope = serializers.ChoiceField(choices=_TARGET_SCOPES)
    definition_target_scope = serializers.ChoiceField(
        choices=_TARGET_SCOPES, allow_null=True
    )
    scope_workspace = serializers.JSONField(
        help_text="The plan's raw ``scope.workspace`` value.",
    )
    workspaces_selected = serializers.IntegerField()
    workspaces_in_tenant = serializers.IntegerField()
    definition_presets = serializers.ListField(child=serializers.CharField())
    definition_ops = serializers.ListField(child=serializers.CharField())
    value_ops = serializers.ListField(child=serializers.CharField())
    non_writing_ops = serializers.ListField(child=serializers.CharField())
    warnings = serializers.ListField(child=serializers.CharField())


class MigrationStepCountsSerializer(serializers.Serializer):
    """The per-step ``counts`` block."""

    matched = serializers.IntegerField()
    changed = serializers.IntegerField()
    skipped = serializers.IntegerField()
    failed = serializers.IntegerField()


class MigrationTransformCountsSerializer(serializers.Serializer):
    """The per-step ``transform_counts`` block."""

    applied = serializers.IntegerField()
    skipped = serializers.IntegerField()
    failed = serializers.IntegerField()


class MigrationStepOutcomeSerializer(serializers.Serializer):
    """One executed step of a run (generic contract, see the module docstring)."""

    index = serializers.IntegerField()
    op = serializers.CharField(
        help_text="Plan op name, e.g. 'migrate_value'.",
    )
    target_scope = serializers.ChoiceField(choices=_TARGET_SCOPES)
    counts = MigrationStepCountsSerializer()
    transform_counts = MigrationTransformCountsSerializer(required=False)
    changes = serializers.ListField(
        child=serializers.DictField(),
        help_text="Per-artifact samples, capped by MAX_SAMPLES.",
    )
    errors = serializers.ListField(
        child=serializers.DictField(),
        help_text="Per-artifact failures, capped by MAX_SAMPLES.",
    )
    message = serializers.CharField(required=False, allow_blank=True)


class MigrationSummarySerializer(serializers.Serializer):
    """Run-wide sum over every step (``_summary``)."""

    steps = serializers.IntegerField()
    matched = serializers.IntegerField()
    changed = serializers.IntegerField()
    skipped = serializers.IntegerField()
    failed = serializers.IntegerField()
    steps_failed = serializers.IntegerField()


class MigrationReportSerializer(serializers.Serializer):
    """The dry-run/apply report (``AttributeMigrationService._execute``).

    ``run_id`` is set for both modes: a dry run is recorded as such so its
    report stays retrievable through the run endpoints.
    """

    plan_id = serializers.CharField()
    plan_hash = serializers.CharField(
        help_text="SHA-256 of the normalized plan (re-run detection).",
    )
    mode = serializers.ChoiceField(choices=_RUN_MODES)
    status = serializers.ChoiceField(choices=_RUN_STATUSES)
    scope = MigrationScopeSerializer()
    target_scope = serializers.ChoiceField(choices=_TARGET_SCOPES)
    scope_effect = MigrationScopeEffectSerializer()
    steps = MigrationStepOutcomeSerializer(many=True)
    summary = MigrationSummarySerializer()
    message = serializers.CharField(
        required=False,
        help_text="Diagnostic for a zero-match apply (#1146).",
    )
    run_id = serializers.CharField()


class MigrationPlanRequestSerializer(serializers.Serializer):
    """Body of ``POST /attribute-migration/plan/`` and ``.../apply/``.

    The plan is a versioned, closed document validated by
    ``attribute_definitions.migration_plan.normalize_plan`` — a malformed plan
    answers 400 with the full error list. Only the envelope keys are declared
    here; ``steps`` are op-specific and described by the plan module itself
    (``python -m attribute_definitions.migration_plan --help``-style
    introspection is the supported way to enumerate them).

    The service accepts the plan either directly or wrapped under
    ``{"plan": {...}}``.
    """

    id = serializers.CharField()
    version = serializers.IntegerField(required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    scope = serializers.DictField(
        required=False,
        help_text="tenant / item_type / preset / workspace.",
    )
    mode = serializers.ChoiceField(choices=_RUN_MODES, required=False)
    options = serializers.DictField(required=False)
    steps = serializers.ListField(child=serializers.DictField())


class MigrationRunSerializer(serializers.Serializer):
    """One stored migration run (``_run_payload``)."""

    id = serializers.CharField()
    plan_id = serializers.CharField()
    plan_hash = serializers.CharField()
    mode = serializers.ChoiceField(choices=_RUN_MODES)
    status = serializers.ChoiceField(choices=_RUN_STATUSES)
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)
    actor_type = serializers.CharField()
    actor_label = serializers.CharField(allow_blank=True)
    counts = serializers.DictField(
        help_text="The run's summary counters (see MigrationSummarySerializer).",
    )
    snapshot_reference = serializers.ListField(child=serializers.CharField())
    report = serializers.DictField(
        help_text="The stored report (see MigrationReportSerializer).",
    )


class MigrationRunListSerializer(serializers.Serializer):
    """``GET /attribute-migration/runs/`` envelope."""

    runs = MigrationRunSerializer(many=True)
    count = serializers.IntegerField()


class MigrationRollbackSerializer(serializers.Serializer):
    """``POST /attribute-migration/runs/{run_id}/rollback/`` report.

    ``status`` is never ``rolled_back`` while something stayed changed: a target
    without a before-image (an older run, or a row deleted since) is named in
    ``not_reverted`` and the run ends ``partially_rolled_back``.
    """

    run_id = serializers.CharField()
    status = serializers.ChoiceField(choices=_RUN_STATUSES)
    restored = serializers.IntegerField(
        help_text="restored_artifacts + restored_definitions.",
    )
    restored_artifacts = serializers.IntegerField()
    restored_definitions = serializers.IntegerField()
    not_reverted = serializers.ListField(
        child=serializers.DictField(),
        help_text="Targets a rollback could not revert, with the reason.",
    )
    samples = serializers.ListField(
        child=serializers.DictField(),
        help_text="A capped sample of the restored targets.",
    )
    message = serializers.CharField(required=False, allow_blank=True)
