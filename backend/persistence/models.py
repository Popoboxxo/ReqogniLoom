"""
COMP-PL-001 EntitySchemaManager — Django ORM models for all 13 domain entities.
COMP-PL-005 PerformanceOptimizationLayer — index declarations (Meta.indexes).

Requirements:
- REQ-L2-PL-004 / REQ-L3-PL001-001 (complete entity schema, 13 entities)
- REQ-L2-PL-005 / REQ-L3-PL001-002 (audit fields on all writable entities)
- REQ-L2-PL-009 / REQ-L3-PL001-003 (FK constraints with explicit on_delete)
- REQ-L2-PL-001 / REQ-L3-PL001-004 (tenant_id FK on all tenant-scoped entities)
- REQ-L2-PL-003 / REQ-L3-PL005-001 (BTree, GIN, tsvector indexes)

Architecture:
- docs/se/L1/Gesamtsystem/L2/PersistenceLayerSystem/Components/
  COMP-PL-001_EntitySchemaManager/L3_COMP-PL-001_EntitySchemaManager_Architecture.md
- docs/se/L1/Gesamtsystem/L2/PersistenceLayerSystem/Components/
  COMP-PL-005_PerformanceOptimizationLayer/L3_COMP-PL-005_PerformanceOptimizationLayer_Architecture.md

Foundation note (ADR-03, ADR-PL-03):
    Other apps import the abstract base classes from this module and subclass them:

        from persistence.models import TenantScopedModel

    Subclassing ``TenantScopedModel`` automatically provides: UUID primary key,
    ``tenant`` FK, audit fields (created_at/created_by/modified_at/modified_by/
    version) and the tenant-isolating default manager (``objects`` =
    :class:`~persistence.tenancy.TenantManager`).
"""
from __future__ import annotations

import uuid

from django.db import models

from persistence.tenancy import TenantManager, UnscopedManager


# ---------------------------------------------------------------------------
# Custom manager for User (AUTH_USER_MODEL compatibility)
# ---------------------------------------------------------------------------


class UserManager(models.Manager):
    """Manager for :class:`User` providing Django auth interface methods.

    ``get_by_natural_key`` is required by ``ModelBackend.authenticate()`` to
    look up users by username. Without it, Django admin login and
    ``django.contrib.auth.authenticate()`` fail.
    """

    def get_by_natural_key(self, username: str):
        """Look up a user by username (case-sensitive, matching AbstractUser)."""
        return self.get(**{self.model.USERNAME_FIELD: username})


# ---------------------------------------------------------------------------
# Domain enums (COMP-PL-001)
# ---------------------------------------------------------------------------


class ElementType(models.TextChoices):
    """Allowed architecture element types (REQ-L2-AS-004).

    Values are lowercase for API consistency.  The human-readable label
    (second tuple element) is used by Django admin and serializer choice
    descriptions only — the stored DB value is always the lowercase key.
    """

    COMPONENT = "component", "Component"
    INTERFACE = "interface", "Interface"
    SUBSYSTEM = "subsystem", "Subsystem"
    LAYER = "layer", "Layer"
    MODULE = "module", "Module"


# ---------------------------------------------------------------------------
# Abstract base classes (COMP-PL-001, ADR-L3-PL-001)
# ---------------------------------------------------------------------------


class AuditableModel(models.Model):
    """Abstract base providing a UUID primary key and audit fields.

    REQ-L3-PL001-002: ``created_at``/``modified_at`` are managed automatically;
    ``version`` starts at 1 and is incremented by writers (typically via
    ``F('version') + 1`` inside an atomic block — COMP-PL-003).

    ``created_by``/``modified_by`` reference :class:`User` with ``SET_NULL`` so
    that deleting a user does not delete audited rows (REQ-L2-PL-009).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "persistence.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    modified_at = models.DateTimeField(auto_now=True)
    modified_by = models.ForeignKey(
        "persistence.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    version = models.IntegerField(default=1)

    class Meta:
        abstract = True


class TenantScopedModel(AuditableModel):
    """Abstract base for all tenant-scoped entities.

    Adds the non-nullable ``tenant`` FK (``on_delete=PROTECT`` — a tenant with
    data cannot be deleted, REQ-L2-PL-009) and wires the tenant-isolating manager
    as the default ``objects`` manager (REQ-L3-PL001-004, IF-PL-INT-001).

    ``unscoped`` is an explicit escape hatch for cross-tenant maintenance; it does
    NOT apply the tenant filter and must be used deliberately.
    """

    tenant = models.ForeignKey(
        "persistence.Tenant",
        on_delete=models.PROTECT,
        db_index=True,
        related_name="%(class)s_set",
    )

    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        abstract = True
        # Django uses the *base* manager for internal operations (cascade
        # collection, FK/related validation, ``refresh_from_db``). It must NOT
        # be tenant-filtered, otherwise these internals would require a tenant
        # context and could silently drop related rows. The *default* manager
        # (``objects``) stays tenant-scoped for application queries.
        base_manager_name = "unscoped"


# ---------------------------------------------------------------------------
# Root / identity entities (no tenant FK) — COMP-PL-001
# ---------------------------------------------------------------------------


class Tenant(AuditableModel):
    """Tenant root entity (the isolation boundary itself).

    Has no ``tenant`` FK — it IS the tenant. Uses the plain Django manager since
    tenant-scoping does not apply to the tenant table. AuthAndTenancy resolves the
    active tenant from this table before any context is set.
    """

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "pl_tenant"

    def __str__(self) -> str:
        return self.name


class User(AuditableModel):
    """Application user (RBAC subject, REQ-L1-010).

    Membership in a tenant is optional at the schema level (a platform/admin user
    may exist without a tenant), hence ``tenant`` is nullable here and this model
    does NOT inherit ``TenantScopedModel``. AuthAndTenancy (ARCH-L1-011) owns the
    authentication semantics; this is the persisted record only.

    Password storage (REQ-L1-010, password-login extension): ``password`` holds a
    salted hash produced by Django's password hashers (PBKDF2 by default), never
    the plaintext. Use :meth:`set_password` / :meth:`check_password`; never assign
    a raw value to ``password`` directly. An empty ``password`` means "no usable
    password" and never matches via :meth:`check_password`.
    """

    # Django auth interface — identifies the unique identifier field and
    # additional required fields for createsuperuser (AUTH_USER_MODEL compat).
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: list[str] = ["email"]

    # Explicit manager with get_by_natural_key for Django auth backend.
    objects = UserManager()

    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(
        default=False,
        help_text="Designates whether the user can log into the Django admin site.",
    )
    is_superuser = models.BooleanField(
        default=False,
        help_text=(
            "Designates that this user has all permissions without "
            "explicitly assigning them."
        ),
    )
    # Salted password hash (Django hasher format, e.g. "pbkdf2_sha256$..."), not
    # the plaintext. Blank = no usable password set.
    password = models.CharField(max_length=128, blank=True, default="")
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
    )

    class Meta:
        db_table = "pl_user"

    def __str__(self) -> str:
        return self.username

    # -- Django auth interface (needed for AUTH_USER_MODEL compatibility) ------

    def set_password(self, raw_password: str) -> None:
        """Hash and store ``raw_password`` on this instance (not saved to DB).

        Delegates to Django's configured password hashers (PBKDF2 by default).
        The caller is responsible for persisting the change via ``save()``.
        """
        from django.contrib.auth.hashers import make_password

        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Return whether ``raw_password`` matches the stored password hash.

        Returns ``False`` when no usable password is set. Uses Django's
        constant-time verification (``check_password``) to avoid timing leaks.
        """
        from django.contrib.auth.hashers import check_password as _check

        if not self.password:
            return False
        return _check(raw_password, self.password)

    def has_perm(self, perm: str, obj=None) -> bool:
        """Return ``True`` if the user has the given permission.

        Superusers get all permissions; other users get none (the project uses
        its own RBAC layer via auth_tenancy.UserRole for fine-grained access).
        """
        return self.is_active and self.is_superuser

    def has_module_perms(self, app_label: str) -> bool:
        """Return ``True`` if the user has permissions to view the given app."""
        return self.is_active and self.is_superuser

    def get_username(self) -> str:
        """Return the username (Django auth interface compatibility)."""
        return self.username

    @property
    def is_authenticated(self) -> bool:
        """Always ``True`` for User instances (Django auth interface)."""
        return True

    @property
    def is_anonymous(self) -> bool:
        """Always ``False`` for User instances (Django auth interface)."""
        return False


# ---------------------------------------------------------------------------
# Tenant-scoped entities — COMP-PL-001
# ---------------------------------------------------------------------------


class Role(TenantScopedModel):
    """RBAC role with a JSON permission set (REQ-L1-010)."""

    name = models.CharField(max_length=150)
    permissions = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "pl_role"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"], name="uq_role_tenant_name"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Workspace(TenantScopedModel):
    """Workspace — preset/configuration scope within a tenant (REQ-L1-008).

    Lifecycle fields (REQ-L1-042):
      ``is_active``  — soft-delete flag; False means the workspace is closed.
      ``closed_at``  — timestamp when the workspace was closed (nullable).
      ``closed_by``  — user who closed the workspace (nullable, SET_NULL).
    """

    name = models.CharField(max_length=255)
    preset = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Soft-delete flag. False = workspace is closed (REQ-L1-042).",
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the workspace was closed.",
    )
    closed_by = models.ForeignKey(
        "persistence.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="User who closed this workspace.",
    )

    class Meta:
        db_table = "pl_workspace"

    def __str__(self) -> str:
        return self.name


class Artifact(TenantScopedModel):
    """Generic hierarchical artifact (ADR-05, REQ-L1-001).

    Self-referential ``parent`` FK forms the decomposition tree. ``on_delete=
    CASCADE`` deletes children with their parent (REQ-L2-PL-009). The BTree index
    on ``parent`` backs recursive-CTE tree queries (REQ-L3-PL005-001).
    """

    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="artifacts"
    )
    artifact_type = models.CharField(max_length=64)

    class Meta:
        db_table = "pl_artifact"
        indexes = [
            # REQ-L3-PL005-001: BTree on parent for hierarchy / recursive CTE.
            models.Index(fields=["parent"], name="idx_artifact_parent_btree"),
        ]

    def __str__(self) -> str:
        return f"{self.artifact_type}:{self.id}"


class Requirement(TenantScopedModel):
    """Requirement entity derived from an artifact (REQ-L1-001).

    GIN tsvector index on title+description backs full-text search
    (REQ-L3-PL005-001, ADR-09). The index is created via RawSQL in the migration
    because it is an expression index (German config).
    """

    artifact = models.OneToOneField(
        Artifact, on_delete=models.CASCADE, related_name="requirement"
    )
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=64, default="draft")

    class Meta:
        db_table = "pl_requirement"

    def __str__(self) -> str:
        return self.title


class ArchitectureElement(TenantScopedModel):
    """Architecture element derived from an artifact (REQ-L1-002).

    REQ-L1-041: Supports hierarchical parent-child relationships via parent_id.
    Level is derived from tree depth (0=root, 1=child of root, etc.).
    """

    artifact = models.OneToOneField(
        Artifact, on_delete=models.CASCADE, related_name="architecture_element"
    )
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    element_type = models.CharField(
        max_length=64,
        blank=True,
        choices=ElementType.choices,
        default=ElementType.COMPONENT,
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )

    class Meta:
        db_table = "pl_architecture_element"

    def __str__(self) -> str:
        return self.title

    def get_level(self) -> int:
        """Return tree depth of this element.

        Root (parent=None) → level=0
        Direct child → level=1
        Nested → level=2, etc.

        Recursively traverses parent chain.
        """
        if self.parent_id is None:
            return 0
        # Fetch parent and recurse
        parent = ArchitectureElement.objects.filter(id=self.parent_id).first()
        if parent is None:
            return 0  # Orphaned child fallback
        return 1 + parent.get_level()


class TraceLink(TenantScopedModel):
    """Directed trace link between two artifacts (ADR-05, REQ-L1-003).

    Both endpoints cascade-delete: removing either endpoint removes the link
    (REQ-L2-PL-009). The composite index on (source, target) backs graph
    traversal queries (REQ-L3-PL005-001).
    """

    source = models.ForeignKey(
        Artifact, on_delete=models.CASCADE, related_name="outgoing_links"
    )
    target = models.ForeignKey(
        Artifact, on_delete=models.CASCADE, related_name="incoming_links"
    )
    link_type = models.CharField(max_length=64)

    class Meta:
        db_table = "pl_tracelink"
        indexes = [
            # REQ-L3-PL005-001: composite index for TraceLink graph queries.
            models.Index(
                fields=["source", "target"], name="idx_tracelink_graph"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_id} -[{self.link_type}]-> {self.target_id}"


class TestCase(TenantScopedModel):
    """Test case derived from an artifact (REQ-L1-012)."""

    artifact = models.OneToOneField(
        Artifact, on_delete=models.CASCADE, related_name="test_case"
    )
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    steps = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "pl_testcase"

    def __str__(self) -> str:
        return self.title


class WorkflowDefinition(TenantScopedModel):
    """Workflow definition (state machine config, ADR-06, REQ-L1-009)."""

    artifact = models.ForeignKey(
        Artifact, on_delete=models.CASCADE, related_name="workflow_definitions"
    )
    name = models.CharField(max_length=255)
    workflow_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "pl_workflow_definition"

    def __str__(self) -> str:
        return self.name


class WorkflowState(TenantScopedModel):
    """Current workflow state of a requirement (REQ-L1-009)."""

    requirement = models.ForeignKey(
        Requirement, on_delete=models.CASCADE, related_name="workflow_states"
    )
    definition = models.ForeignKey(
        WorkflowDefinition, on_delete=models.PROTECT, related_name="states"
    )
    current_state = models.CharField(max_length=128)

    class Meta:
        db_table = "pl_workflow_state"

    def __str__(self) -> str:
        return self.current_state


class AuditLogEntry(TenantScopedModel):
    """Append-only audit log entry (REQ-L1-011, ADR-10).

    The actor reference uses ``SET_NULL`` so removing a user does not erase the
    audit history (REQ-L2-PL-009).
    """

    action = models.CharField(max_length=64)
    object_type = models.CharField(max_length=128)
    object_id = models.UUIDField(null=True, blank=True)
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "pl_audit_log_entry"
        indexes = [
            models.Index(
                fields=["object_type", "object_id"],
                name="idx_audit_object",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.action}:{self.object_type}:{self.object_id}"


class TestRun(TenantScopedModel):
    """TestRun entity — group of TestCase executions (REQ-L2-AS-030).

    Not linked to Artifact hierarchy — operational record for test execution runs.
    """

    name = models.CharField(max_length=255)
    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="test_runs"
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=32,
        choices=[
            ("in_progress", "In Progress"),
            ("passed", "Passed"),
            ("failed", "Failed"),
            ("partial", "Partial"),
        ],
        default="in_progress",
    )
    ci_job_id = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "pl_test_run"
        verbose_name = "Test Run"
        verbose_name_plural = "Test Runs"

    def __str__(self) -> str:
        return f"TestRun:{self.name}:{self.status}"


class TestRunResult(TenantScopedModel):
    """Individual TestCase execution result within a TestRun (REQ-L2-AS-030)."""

    test_run = models.ForeignKey(
        TestRun, on_delete=models.CASCADE, related_name="results"
    )
    test_case = models.ForeignKey(
        TestCase, on_delete=models.SET_NULL, null=True, blank=True, related_name="run_results"
    )
    test_case_title = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(
        max_length=32,
        choices=[
            ("passed", "Passed"),
            ("failed", "Failed"),
            ("blocked", "Blocked"),
            ("not_run", "Not Run"),
        ],
        default="not_run",
    )
    executed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    message = models.TextField(blank=True, default="")

    class Meta:
        db_table = "pl_test_run_result"
        verbose_name = "Test Run Result"
        verbose_name_plural = "Test Run Results"

    def __str__(self) -> str:
        return f"Result:{self.test_case_title}:{self.status}"


# Public foundation surface. Other apps import from here.
__all__ = [
    "AuditableModel",
    "TenantScopedModel",
    "Tenant",
    "User",
    "Role",
    "Workspace",
    "Artifact",
    "Requirement",
    "ElementType",
    "ArchitectureElement",
    "TraceLink",
    "TestCase",
    "WorkflowDefinition",
    "WorkflowState",
    "AuditLogEntry",
    "TestRun",
    "TestRunResult",
]
