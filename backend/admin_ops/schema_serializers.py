"""Request/response shapes for the admin_ops endpoints (#1388).

These serializers exist **for the OpenAPI contract only** — the views in
:mod:`admin_ops.banner_rest`, :mod:`admin_ops.health_rest`,
:mod:`admin_ops.rate_limit_rest` and :mod:`admin_ops.theme_rest` keep building
their responses by hand and validate their writes in place. No runtime
serialization was moved here; the shapes below were transcribed from those
hand-built dicts so a generated client can be written without guessing.

Keeping them in a module of their own lets the admin adapters stay free of DRF
serializer imports (they are plain ``APIView``s by design) while still
publishing a faithful contract.
"""
from __future__ import annotations

from rest_framework import serializers

__all__ = [
    "BackupCreateRequestSerializer",
    "BackupCreateResponseSerializer",
    "BackupListResponseSerializer",
    "BackupMetadataSerializer",
    "BannerSerializer",
    "BannerWriteSerializer",
    "ComponentStatusSerializer",
    "LoginBannerSerializer",
    "RateLimitEffectiveResponseSerializer",
    "RateLimitOverridesWriteSerializer",
    "RecentAuditEventSerializer",
    "RestoreRequestSerializer",
    "RestoreResponseSerializer",
    "RestoreResultSerializer",
    "SystemHealthResponseSerializer",
    "TenantThemeDefaultWriteSerializer",
    "ThemePaletteSerializer",
    "ThemePaletteWriteSerializer",
    "ThemeSelectionSerializer",
    "UserThemePreferenceWriteSerializer",
]


# ---------------------------------------------------------------------------
# System health (GET /api/v1/admin/health/)
# ---------------------------------------------------------------------------


class ComponentStatusSerializer(serializers.Serializer):
    """One row of the health dashboard's ``components`` list."""

    name = serializers.CharField(help_text="Component key, e.g. 'database'.")
    status = serializers.ChoiceField(choices=["ok", "degraded", "down", "unknown"])
    detail = serializers.CharField(
        help_text="Short human-readable status detail (error text when down)."
    )
    # Present on the memory row; omitted by the other probes.
    backend = serializers.CharField(required=False)
    ok = serializers.BooleanField(required=False)
    degraded = serializers.BooleanField(required=False)
    digest_available = serializers.BooleanField(required=False)
    ask_available = serializers.BooleanField(required=False)
    derivation_status = serializers.CharField(required=False)


class RecentAuditEventSerializer(serializers.Serializer):
    """One row of the health dashboard's ``recent_events`` list."""

    id = serializers.CharField()
    actor = serializers.CharField(allow_blank=True, allow_null=True)
    actor_type = serializers.CharField(allow_blank=True, allow_null=True)
    op = serializers.CharField()
    entity_type = serializers.CharField()
    entity_id = serializers.CharField()
    source = serializers.CharField(allow_blank=True, allow_null=True)
    change_reason = serializers.CharField(allow_blank=True)
    timestamp = serializers.DateTimeField(allow_null=True)


class SystemHealthResponseSerializer(serializers.Serializer):
    """``GET /api/v1/admin/health/`` — the aggregated snapshot."""

    components = ComponentStatusSerializer(many=True)
    recent_events = RecentAuditEventSerializer(many=True)


# ---------------------------------------------------------------------------
# Banners (/api/v1/admin/banners/global/, …/banner/, /api/v1/public/banners/login/)
# ---------------------------------------------------------------------------


class BannerSerializer(serializers.Serializer):
    """A banner as returned by the admin-facing endpoints."""

    id = serializers.CharField()
    scope = serializers.CharField()
    workspace_id = serializers.CharField(allow_null=True)
    level = serializers.ChoiceField(choices=["neutral", "info", "warning", "critical"])
    message = serializers.CharField(allow_blank=True)
    enabled = serializers.BooleanField()
    dismissible = serializers.BooleanField()
    show_on_login_page = serializers.BooleanField()
    updated_at = serializers.DateTimeField(allow_null=True)


class BannerWriteSerializer(serializers.Serializer):
    """``PUT`` body shared by the global and workspace banner endpoints."""

    level = serializers.ChoiceField(
        choices=["neutral", "info", "warning", "critical"],
        required=False,
        default="neutral",
    )
    message = serializers.CharField(required=False, allow_blank=True, default="")
    enabled = serializers.BooleanField(required=False, default=False)
    dismissible = serializers.BooleanField(required=False, default=True)
    show_on_login_page = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Global banner only; ignored by the workspace endpoint.",
    )


class LoginBannerSerializer(serializers.Serializer):
    """Unauthenticated login-page banner (a deliberately reduced payload)."""

    id = serializers.CharField()
    level = serializers.ChoiceField(choices=["neutral", "info", "warning", "critical"])
    message = serializers.CharField(allow_blank=True)
    dismissible = serializers.BooleanField()
    updated_at = serializers.DateTimeField(allow_null=True)


# ---------------------------------------------------------------------------
# Theme palettes and per-user/tenant theme selection
# ---------------------------------------------------------------------------


class ThemePaletteSerializer(serializers.Serializer):
    """One theme palette (``_palette_to_dict``)."""

    key = serializers.CharField()
    label = serializers.CharField()
    is_system = serializers.BooleanField()
    dark_tokens = serializers.DictField(
        child=serializers.CharField(),
        help_text="Canonical colour-token map for the dark mode.",
    )
    light_tokens = serializers.DictField(
        child=serializers.CharField(),
        help_text="Canonical colour-token map for the light mode.",
    )
    token_keys_version = serializers.IntegerField()


class ThemePaletteWriteSerializer(serializers.Serializer):
    """Import body for ``POST /api/v1/admin/theme-palettes/``."""

    label = serializers.CharField()
    key = serializers.CharField(
        required=False,
        help_text="Defaults to the label lowercased with spaces replaced by '-'.",
    )
    dark_tokens = serializers.DictField(child=serializers.CharField())
    light_tokens = serializers.DictField(child=serializers.CharField())


class ThemePaletteListSerializer(serializers.Serializer):
    """``GET /api/v1/admin/theme-palettes/`` envelope."""

    results = ThemePaletteSerializer(many=True)


class ThemeSelectionSerializer(serializers.Serializer):
    """Current theme selection (``palette_key``/``mode``)."""

    palette_key = serializers.CharField(allow_null=True)
    mode = serializers.ChoiceField(choices=["dark", "light"], allow_null=True)


class UserThemePreferenceWriteSerializer(serializers.Serializer):
    """``PUT /api/v1/users/me/theme-preference/`` body."""

    mode = serializers.ChoiceField(choices=["dark", "light"])
    palette_key = serializers.CharField(required=False, allow_null=True)


class TenantThemeDefaultWriteSerializer(serializers.Serializer):
    """``PUT /api/v1/system/theme-default/`` body."""

    mode = serializers.ChoiceField(choices=["dark", "light"])
    palette_key = serializers.CharField(help_text="Required; must be non-blank.")


# ---------------------------------------------------------------------------
# Rate-limit overrides (/api/v1/admin/rate-limits/ and …/global/)
# ---------------------------------------------------------------------------


class RateLimitScopeSerializer(serializers.Serializer):
    """Effective ceiling for one scope plus the layer it came from."""

    effective = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        help_text="Effective rate string; null/empty means unlimited.",
    )
    source = serializers.ChoiceField(choices=["settings", "global", "tenant"])
    settings_value = serializers.CharField(allow_null=True, allow_blank=True)
    tenant_override = serializers.CharField(allow_null=True, allow_blank=True)
    global_override = serializers.CharField(allow_null=True, allow_blank=True)
    disabled = serializers.BooleanField()


class RateLimitEffectiveResponseSerializer(serializers.Serializer):
    """Response of every rate-limit read/write."""

    tenant_id = serializers.CharField()
    scopes = serializers.DictField(child=RateLimitScopeSerializer())
    updated_at = serializers.DateTimeField()


class RateLimitOverridesWriteSerializer(serializers.Serializer):
    """``PUT`` body: ``{"overrides": {"<scope>": "<rate>" | null}}``."""

    overrides = serializers.DictField(
        child=serializers.CharField(allow_null=True, allow_blank=True),
        help_text=(
            "Map of scope name to rate string. A null value deletes the "
            "override; an empty string stores 'unlimited'."
        ),
    )


# ---------------------------------------------------------------------------
# Disaster recovery (/api/v1/admin/backups/ and /api/v1/admin/restore/)
# ---------------------------------------------------------------------------
#
# Transcribed from ``admin_ops.rest._backup_to_dict`` / ``_restore_result_to_dict``
# (and the bodies the two views parse), for the contract only: the views keep
# returning the hand-built dicts (#1388).


class BackupMetadataSerializer(serializers.Serializer):
    """One ``BackupMetadata`` row (``_backup_to_dict``)."""

    id = serializers.CharField()
    status = serializers.CharField(
        help_text="BackupStatus value, e.g. 'completed' or 'failed'.",
    )
    backup_type = serializers.CharField(help_text="'full' or 'partial'.")
    file_path = serializers.CharField(allow_blank=True)
    file_size_bytes = serializers.IntegerField(allow_null=True)
    checksum_sha256 = serializers.CharField(allow_blank=True)
    error_message = serializers.CharField(allow_blank=True)
    metadata = serializers.DictField(
        help_text="Free-form metadata; carries 'reason' when one was given.",
    )
    completed_at = serializers.DateTimeField(required=False, allow_null=True)
    is_restorable = serializers.BooleanField()
    created_at = serializers.DateTimeField(required=False, allow_null=True)
    created_by = serializers.CharField(allow_null=True)


class BackupListResponseSerializer(serializers.Serializer):
    """``GET /api/v1/admin/backups/`` envelope."""

    backups = BackupMetadataSerializer(many=True)


class BackupCreateRequestSerializer(serializers.Serializer):
    """Body of ``POST /api/v1/admin/backups/`` (both fields optional)."""

    reason = serializers.CharField(required=False, allow_blank=True)
    backup_type = serializers.ChoiceField(
        choices=["full", "partial"],
        required=False,
        help_text="Defaults to 'full'.",
    )


class BackupCreateResponseSerializer(serializers.Serializer):
    """201 body of ``POST /api/v1/admin/backups/``."""

    backup = BackupMetadataSerializer()


class RestoreRequestSerializer(serializers.Serializer):
    """Body of ``POST /api/v1/admin/restore/``.

    ``confirmation_text`` must equal the literal ``"RESTORE"`` (case-sensitive);
    a mismatch is a 400. ``restore_type`` is advisory — the service always runs
    a full restore.
    """

    backup_id = serializers.UUIDField()
    confirmation_text = serializers.CharField(
        help_text="Must equal 'RESTORE'.",
    )
    restore_type = serializers.ChoiceField(
        choices=["full", "partial"], required=False
    )


class RestoreResultSerializer(serializers.Serializer):
    """One ``RestoreResult`` (``_restore_result_to_dict``)."""

    backup_id = serializers.CharField()
    started_at = serializers.DateTimeField(required=False, allow_null=True)
    completed_at = serializers.DateTimeField(required=False, allow_null=True)
    restored_tables = serializers.ListField(child=serializers.CharField())
    rows_per_table = serializers.DictField(
        child=serializers.IntegerField(),
        help_text="table name -> restored row count.",
    )


class RestoreResponseSerializer(serializers.Serializer):
    """200 body of ``POST /api/v1/admin/restore/``."""

    restore = RestoreResultSerializer()
