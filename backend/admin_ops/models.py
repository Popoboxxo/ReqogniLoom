"""
ARCH-L1-? AdminOps — Disaster Recovery models (REQ-L1-046).

The DR foundation has a single persistent entity:

* :class:`BackupMetadata` — instance-level bookkeeping for system-wide
  backup operations.

``BackupMetadata`` extends :class:`~persistence.models.AuditableModel`
directly, NOT :class:`~persistence.models.TenantScopedModel`. A backup
is a system-level artefact (it spans tenants, or it represents the
state of the system at a point in time) and therefore carries no
``tenant`` FK. Queries against the table are intentionally NOT
tenant-filtered.

See ``backend/admin_ops/services/INTERFACES.md`` for the public service
surface that operates on this model.
"""
from __future__ import annotations

import uuid

from django.db import models

from persistence.models import AuditableModel, TenantScopedModel


class BackupStatus(models.TextChoices):
    """Lifecycle states of a :class:`BackupMetadata` row (REQ-L1-046)."""

    PENDING = "pending", "Pending"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class BackupType(models.TextChoices):
    """Backup scope (REQ-L1-046).

    ``full``    — every writable model is exported via ``dumpdata``.
    ``partial`` — only the models listed in ``metadata.partial_models`` are
                  exported; the field is reserved for a future wave.
    """

    FULL = "full", "Full"
    PARTIAL = "partial", "Partial"


class BackupMetadata(AuditableModel):
    """Instance-level record of a system backup (REQ-L1-046).

    The model is intentionally **not** a ``TenantScopedModel`` — backups
    are system artefacts, not tenant data, and they may legitimately span
    all tenants in the deployment.

    A successful backup carries ``status='completed'`` plus a ``file_path``,
    ``file_size_bytes`` and ``checksum_sha256``. A failed backup carries
    ``status='failed'`` plus a non-empty ``error_message``; ``file_path``
    is NULL in that case. ``pending`` / ``in_progress`` are transient
    states used while a backup is being produced and are not safe to
    restore from.
    """

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    # Inherited from AuditableModel: created_at, created_by, modified_at,
    # modified_by, version. We do NOT re-declare them here.

    status = models.CharField(
        max_length=16,
        choices=BackupStatus.choices,
        default=BackupStatus.PENDING,
        help_text="Lifecycle state. Only 'completed' rows are restorable.",
    )
    backup_type = models.CharField(
        max_length=16,
        choices=BackupType.choices,
        default=BackupType.FULL,
        help_text="Scope of the backup ('full' or 'partial').",
    )
    file_path = models.CharField(
        max_length=512,
        null=True,
        blank=True,
        help_text="Relative path under MEDIA_ROOT to the dumpdata JSON file.",
    )
    file_size_bytes = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Size of the backup file in bytes; NULL for pending/failed rows.",
    )
    checksum_sha256 = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="SHA-256 hex digest of the backup file (64 chars).",
    )
    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Populated when status='failed'.",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Wall-clock time the backup finished writing. "
                  "NULL until status is 'completed' or 'failed'.",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Free-form summary payload — keys used by the foundation: "
            "'tenant_count', 'artifact_count', 'app_counts', "
            "'last_restore_status', 'last_restore_error'."
        ),
    )

    class Meta:
        db_table = "admin_ops_backup_metadata"
        indexes = [
            # Admin list view: filter by status and order by created_at.
            models.Index(
                fields=["status", "created_at"],
                name="idx_backup_status_created",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"Backup({self.id}, {self.status}, {self.backup_type})"

    # -- Convenience predicates (read-only, no business logic) -------------

    @property
    def is_restorable(self) -> bool:
        """Return whether the row is in a state that can be restored from.

        Only ``completed`` backups may be restored. ``pending`` and
        ``in_progress`` are transient; ``failed`` rows are not restorable
        even though the data file may still exist on disk.
        """
        return self.status == BackupStatus.COMPLETED


# ---------------------------------------------------------------------------
# Theme Presets — canonical color-token vocabulary
# ---------------------------------------------------------------------------

#: The canonical set of ``--color-*`` semantic custom properties every
#: :class:`ThemePalette` must define for BOTH modes. A palette is all-or-
#: nothing: imports and seed data are validated against this exact set —
#: no more, no fewer keys.
#:
#: Provenance: the 74 semantic tokens enumerated by the theme-presets plan
#: (the 10 ``--color-artifacttype-*`` constants are deliberately excluded —
#: they are theme-independent branding constants, identical in every theme
#: block of ``tokens.css``) plus the 3 sidebar overlay tokens introduced by
#: the sidebar hard-coded-overlay fix (``--color-nav-overlay-*``), which the
#: plan folds into the canonical set before the seed migration is finalized.
CANONICAL_COLOR_TOKEN_KEYS = frozenset({
    "--color-badge-approved", "--color-badge-approved-text", "--color-badge-danger-bg",
    "--color-badge-danger-text", "--color-badge-draft", "--color-badge-draft-text",
    "--color-badge-info-bg", "--color-badge-info-text", "--color-badge-neutral-bg",
    "--color-badge-neutral-text", "--color-badge-success-bg", "--color-badge-success-text",
    "--color-badge-warning-bg", "--color-badge-warning-text", "--color-border",
    "--color-border-hover", "--color-border-subtle", "--color-card-active-bg", "--color-danger",
    "--color-danger-banner-bg", "--color-danger-dark", "--color-diagram-edge-default",
    "--color-diagram-edge-dependency", "--color-diagram-edge-primary", "--color-diff-added-bg",
    "--color-diff-added-text", "--color-diff-modified-bg", "--color-diff-modified-text",
    "--color-diff-note-bg", "--color-diff-note-text", "--color-diff-removed-bg",
    "--color-diff-removed-text", "--color-diff-unchanged-bg", "--color-diff-unchanged-text",
    "--color-errorboundary-text", "--color-focus", "--color-gradient-ai-end",
    "--color-gradient-ai-start", "--color-level-l0", "--color-level-l1", "--color-level-l3",
    "--color-level-l4", "--color-link-hover", "--color-linktype-badge-bg",
    "--color-linktype-badge-text", "--color-metric-critical", "--color-metric-healthy",
    "--color-metric-neutral", "--color-metric-warning", "--color-nav-active-bg",
    "--color-nav-badge-bg", "--color-nav-badge-text", "--color-nav-bg", "--color-nav-border",
    "--color-nav-hover-bg", "--color-nav-text", "--color-nav-text-muted", "--color-on-primary",
    "--color-primary", "--color-primary-dark", "--color-primary-rgb", "--color-reqtype-default",
    "--color-reqtype-featurereq", "--color-reqtype-syreq", "--color-reqtype-usecase",
    "--color-success", "--color-summary-failed", "--color-summary-notrun", "--color-summary-passed",
    "--color-surface", "--color-surface-raised", "--color-text", "--color-text-muted", "--color-warning",
    # Sidebar overlay tokens (theme-agnostic hover tints / shadows):
    "--color-nav-overlay-hover",
    "--color-nav-overlay-hover-border",
    "--color-nav-overlay-shadow",
})

#: Version tag stored on every palette row so a future token-vocabulary
#: extension can detect (and migrate) palettes written against an older set.
TOKEN_KEYS_VERSION = "v1"


class BannerScope(models.TextChoices):
    """Which surface a :class:`Banner` targets."""

    GLOBAL = "global", "Global"
    WORKSPACE = "workspace", "Workspace"


class BannerLevel(models.TextChoices):
    """Visual/semantic severity of a :class:`Banner`."""

    NEUTRAL = "neutral", "Neutral"
    INFO = "info", "Info"
    WARNING = "warning", "Warning"
    CRITICAL = "critical", "Critical"


class Banner(TenantScopedModel):
    """A dismissible, Markdown announcement banner (System/Workspace Banners).

    Exactly one row exists per scope instance: one ``scope="global"`` row per
    tenant, one ``scope="workspace"`` row per workspace — enforced by the two
    partial unique constraints below, not by application logic alone. Callers
    always write through :meth:`BannerService.upsert_global_banner` /
    :meth:`~BannerService.upsert_workspace_banner`, which use
    ``update_or_create`` so an edit overwrites the existing row instead of
    creating a second one.

    ``workspace`` is NULL iff ``scope == "global"`` — enforced by
    ``ck_banner_workspace_matches_scope``.
    """

    scope = models.CharField(max_length=16, choices=BannerScope.choices)
    workspace = models.ForeignKey(
        "persistence.Workspace",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="banner",
    )
    level = models.CharField(
        max_length=16, choices=BannerLevel.choices, default=BannerLevel.NEUTRAL
    )
    message = models.TextField(blank=True, default="", help_text="Markdown source.")
    enabled = models.BooleanField(default=False)
    dismissible = models.BooleanField(
        default=True,
        help_text=(
            "Whether end users may close the banner (until next login). "
            "A real, independently-editable field — never hardcoded by level."
        ),
    )
    show_on_login_page = models.BooleanField(
        default=False,
        help_text="Ignored unless scope == 'global' — the login page has no workspace context.",
    )

    class Meta:
        db_table = "admin_ops_banner"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"],
                condition=models.Q(scope=BannerScope.GLOBAL),
                name="uq_banner_one_global_per_tenant",
            ),
            models.UniqueConstraint(
                fields=["workspace"],
                condition=models.Q(scope=BannerScope.WORKSPACE),
                name="uq_banner_one_per_workspace",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(scope=BannerScope.GLOBAL, workspace__isnull=True)
                    | models.Q(scope=BannerScope.WORKSPACE, workspace__isnull=False)
                ),
                name="ck_banner_workspace_matches_scope",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"Banner({self.scope}, level={self.level}, enabled={self.enabled})"


class ThemePalette(TenantScopedModel):
    """A named color palette with a complete token set for dark AND light mode.

    Theme Presets feature: replaces the flat 5-entry ``THEMES`` list in the
    frontend with two independent axes (palette x mode). Every row carries
    BOTH modes' full ``--color-*`` maps (exactly
    :data:`CANONICAL_COLOR_TOKEN_KEYS` — no partial palettes); the frontend
    applies the resolved mode's map onto ``document.documentElement`` via
    inline custom properties at runtime.

    ``is_system=True`` rows are the seeded stock palettes ("default",
    "bauhaus", "nordic", "sepia") and are read-only at the REST layer —
    PATCH/DELETE always answer 403, regardless of role. Custom palettes are
    imported by System-Admins only.
    """

    key = models.CharField(max_length=64)
    label = models.CharField(max_length=128)
    is_system = models.BooleanField(default=False)
    dark_tokens = models.JSONField()
    light_tokens = models.JSONField()
    token_keys_version = models.CharField(max_length=16, default=TOKEN_KEYS_VERSION)

    class Meta:
        db_table = "admin_ops_theme_palette"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "key"], name="uq_theme_palette_tenant_key"
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"ThemePalette({self.key}, system={self.is_system})"


# ---------------------------------------------------------------------------
# Theme Presets — per-user preference and tenant-wide default
# ---------------------------------------------------------------------------

MODE_DARK = "dark"
MODE_LIGHT = "light"
MODE_CHOICES = ((MODE_DARK, "Dark"), (MODE_LIGHT, "Light"))


class UserThemePreference(TenantScopedModel):
    """A user's personal theme choice: one row per user (OneToOne).

    Resolution order in the frontend: user preference > tenant default >
    built-in fallback ("default"/dark). The palette/mode pair is stored
    denormalized as plain strings so a deleted custom palette degrades to a
    frontend-side fallback instead of cascading anywhere.
    """

    user = models.OneToOneField(
        "persistence.User",
        on_delete=models.CASCADE,
        related_name="theme_preference",
    )
    palette_key = models.CharField(max_length=64)
    mode = models.CharField(max_length=8, choices=MODE_CHOICES)

    class Meta:
        db_table = "admin_ops_user_theme_preference"

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"UserThemePreference(user={self.user_id}, {self.palette_key}/{self.mode})"


class TenantThemeDefault(TenantScopedModel):
    """The tenant-wide default theme, set by a System-Admin.

    Exactly one row per tenant — enforced by the unique constraint below,
    same shape as ``Banner``'s global-scope uniqueness. Writers use
    ``update_or_create`` so an edit overwrites the existing row.
    """

    palette_key = models.CharField(max_length=64)
    mode = models.CharField(max_length=8, choices=MODE_CHOICES)

    class Meta:
        db_table = "admin_ops_tenant_theme_default"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"], name="uq_tenant_theme_default_one_per_tenant"
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"TenantThemeDefault(tenant={self.tenant_id}, {self.palette_key}/{self.mode})"


__all__ = [
    "BackupMetadata",
    "BackupStatus",
    "BackupType",
    "Banner",
    "BannerScope",
    "BannerLevel",
    "CANONICAL_COLOR_TOKEN_KEYS",
    "MODE_CHOICES",
    "MODE_DARK",
    "MODE_LIGHT",
    "TOKEN_KEYS_VERSION",
    "TenantThemeDefault",
    "ThemePalette",
    "UserThemePreference",
]
