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

# REQ-L2-VS-004: pgvector Django integration. Requires the ``pgvector`` package
# (see requirements.txt) and the ``vector`` Postgres extension (provisioned by
# the pgvector/pgvector:pg16 image). Imported at module load because the
# Requirement.embedding field references VectorField/HnswIndex directly.
from pgvector.django import HnswIndex, VectorField

from persistence.encryption import decrypt_secret, encrypt_secret
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


class LifecycleStatus(models.TextChoices):
    """Soft-delete lifecycle status for entities that must not be hard-deleted by users.

    REQ-006: Replaces physical deletion for ArchitectureElement and GlossaryTerm.
    Entities with status 'deleted' are excluded from normal list queries but
    remain in the database for audit purposes. Hard-delete is available only
    via the Django admin panel.
    """

    ACTIVE = "active", "Active"
    OUTDATED = "outdated", "Outdated"
    DEPRECATED = "deprecated", "Deprecated"
    DELETED = "deleted", "Deleted"


class RequirementType(models.TextChoices):
    """Requirement type for SE mask standardization (REQ-L3-RF003-005).

    Classifies requirements by level in specification hierarchy.
    """

    SYREQ = "SyReq", "System Requirement"
    USECASE = "UseCase", "Use Case"
    FEATUREREQ = "FeatureReq", "Feature Requirement"


class RequirementLevel(models.IntegerChoices):
    """V-model requirement hierarchy level (K3).

    Makes the L0-L4 traceability hierarchy an explicit, queryable field instead
    of a naming convention only. NULL means the level has not been assigned yet;
    it must be set deliberately going forward (no backfill for existing rows).
    """

    L0_SYSTEM = 0, "L0 System"
    L1_SUBSYSTEM = 1, "L1 Subsystem"
    L2_COMPONENT = 2, "L2 Component"
    L3_PART = 3, "L3 Part"
    L4_MATERIAL = 4, "L4 Material"


class MoSCoWPriority(models.TextChoices):
    """MoSCoW prioritization framework.

    Visible only for Stakeholder Needs.
    """

    MUST = "Must", "Must Have"
    SHOULD = "Should", "Should Have"
    COULD = "Could", "Could Have"
    WONT = "Won't", "Won't Have"


class ComplexityFibonacci(models.IntegerChoices):
    """Fibonacci scale for complexity estimation (REQ-L3-RF003-005).

    Visible only for SyReq requirements.
    """

    ONE = 1
    TWO = 2
    THREE = 3
    FIVE = 5
    EIGHT = 8
    THIRTEEN = 13
    TWENTY_ONE = 21


class VerificationMethod(models.TextChoices):
    """Verification method choices (REQ-L3-RF003-005).

    Visible only for SyReq requirements.
    """

    TEST = "Test", "Test"
    REVIEW = "Review", "Review"
    ANALYSIS = "Analysis", "Analysis"
    INSPECTION = "Inspection", "Inspection"
    DEMONSTRATION = "Demonstration", "Demonstration"


class TestCaseType(models.TextChoices):
    """Test case type (B6a).

    Promotes the test type from an ``artifact_type`` string prefix
    (e.g. "TestCase:System") to a first-class field. The artifact_type prefix
    approach is deprecated for test typing going forward. NULL means the type
    is unknown / not derivable from the legacy prefix.
    """

    SYSTEM = "system", "System"
    INTEGRATION = "integration", "Integration"
    UNIT = "unit", "Unit"
    INSPECTION = "inspection", "Inspection"
    ANALYSIS = "analysis", "Analysis"
    DEMONSTRATION = "demonstration", "Demonstration"


class ASILLevel(models.TextChoices):
    """ASIL (Automotive Safety Integrity Level) (REQ-L3-RF004-004).

    Used for ArchitectureElement safety classification.
    """

    QM = "QM", "QM (not ASIL)"
    A = "A", "ASIL A"
    B = "B", "ASIL B"
    C = "C", "ASIL C"
    D = "D", "ASIL D"


class MakeOrBuy(models.TextChoices):
    """Make-or-Buy decision for ArchitectureElement (REQ-L3-RF004-004).

    Drives supply chain and sourcing analysis.
    """

    MAKE = "Make", "Make"
    BUY = "Buy", "Buy"
    REUSE = "Reuse", "Reuse"


class CustomFieldType(models.TextChoices):
    """Data type of a workspace-wide custom field (REQ-016).

    ``TEXT``     — free-text single line, stored verbatim.
    ``NUMBER``   — numeric value, stored as its string representation.
    ``DROPDOWN`` — one of a predefined set of options (see
                   :attr:`CustomFieldDefinition.options`).
    """

    TEXT = "text", "Text"
    NUMBER = "number", "Number"
    DROPDOWN = "dropdown", "Dropdown"


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
    # Human-readable name fields (REQ-006). Optional and blank by default so
    # existing users remain valid without a data migration backfill.
    first_name = models.CharField(max_length=150, blank=True, default="")
    last_name = models.CharField(max_length=150, blank=True, default="")
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
    ai_prompts = models.JSONField(
        default=dict,
        blank=True,
        help_text="SN-56: Configurable AI derivation prompts per level.",
    )
    decomposition_link_type = models.CharField(
        max_length=50,
        default="parent-child",
        help_text="Default link type used when decomposing requirements.",
    )
    default_link_type = models.CharField(
        max_length=50,
        default="derives-from",
        help_text="Link type pre-selected when creating a new trace link.",
    )
    language = models.CharField(
        max_length=8,
        default="en",
        blank=True,
        help_text="Per-workspace UI/content language (REQ-133).",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Soft-delete flag. False = workspace is closed (REQ-L1-042).",
    )
    parent_workspace = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sandboxes",
        help_text="SN-33: Source workspace this sandbox was cloned from.",
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

    Deprecated hierarchy mechanism (REQ-L1-030 / REQ-L2-TE-020 direction):
    domain services (RequirementService, StakeholderNeedService, AdrService,
    ...) create their backing Artifact rows without populating ``parent`` and
    express hierarchy exclusively through 'derives-from' / 'parent-child'
    TraceLinks instead (see traceability/types.py LinkType). ``parent`` is
    still writable via the generic ArtifactService and read by a handful of
    call sites (see TODOs at those sites), which makes it a second,
    inconsistently-populated hierarchy mechanism alongside TraceLinks. The
    single source of truth for artifact hierarchy going forward is the
    'derives-from' TraceLink graph. This field is not removed here (would
    require a migration / behavior change for existing callers) — new code
    should not rely on it and existing call sites should migrate to
    TraceLink-based hierarchy queries.
    """

    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        help_text=(
            "Deprecated: use 'derives-from' TraceLink for hierarchy instead. "
            "Populated only via the generic ArtifactService write path; "
            "RequirementService/StakeholderNeedService/AdrService/... leave "
            "this NULL and rely on TraceLinks. Kept for backward "
            "compatibility only — do not add new dependencies on it."
        ),
    )
    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="artifacts"
    )
    artifact_type = models.CharField(max_length=64)
    custom_fields = models.JSONField(
        null=True,
        default=dict,
        blank=True,
        help_text=(
            "REQ-L2-AS-037: User-defined custom attributes as a flat key-value "
            "map. Keys: strings. Values: str, int, float, bool, or null. "
            "A GIN index (pl_artifact_custom_fields_gin) backs JSONB queries."
        ),
    )

    class Meta:
        db_table = "pl_artifact"
        indexes = [
            # REQ-L3-PL005-001: BTree on parent for hierarchy / recursive CTE.
            models.Index(fields=["parent"], name="idx_artifact_parent_btree"),
            # REQ-039: composite indexes for dominant list-filter combinations.
            # RLS always filters on tenant; list endpoints add workspace / type.
            models.Index(fields=["tenant", "workspace"], name="idx_artifact_tnt_ws"),
            models.Index(
                fields=["tenant", "artifact_type"], name="idx_artifact_tnt_type"
            ),
            models.Index(
                fields=["tenant", "workspace", "artifact_type"],
                name="idx_artifact_tnt_ws_type",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.artifact_type}:{self.id}"


class StakeholderNeed(TenantScopedModel):
    """Stakeholder Need entity derived from an artifact.
    
    Represents user/customer desires and problems to be solved.
    """

    artifact = models.OneToOneField(
        Artifact, on_delete=models.CASCADE, related_name="stakeholder_need"
    )
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=64, default="draft")
    moscow_priority = models.CharField(
        max_length=16,
        null=True,
        blank=True,
        choices=MoSCoWPriority.choices,
        help_text="MoSCoW priority",
    )
    uid = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="Unique identifier (read-only, auto-generated)",
    )
    suspect = models.BooleanField(
        default=False,
        help_text="SN-30: Indicates if this need requires review due to upstream changes.",
    )
    lifecycle_status = models.CharField(
        max_length=16,
        choices=LifecycleStatus.choices,
        default=LifecycleStatus.ACTIVE,
        help_text="REQ-006: Soft-delete lifecycle. 'deleted' hides need from normal views; hard-delete via admin only.",
    )

    class Meta:
        db_table = "pl_stakeholder_need"
        indexes = [
            # REQ-039: composite indexes for dominant list-filter combinations.
            models.Index(fields=["tenant", "status"], name="idx_sn_tnt_status"),
            models.Index(
                fields=["tenant", "lifecycle_status"], name="idx_sn_tnt_lifecycle"
            ),
        ]

    def __str__(self) -> str:
        return self.title


class Requirement(TenantScopedModel):
    """Requirement entity derived from an artifact (REQ-L1-001).

    GIN tsvector index on title+description backs full-text search
    (REQ-L3-PL005-001, ADR-09). The index is created via RawSQL in the migration
    because it is an expression index (German config).

    REQ-L3-RF003-005: Supports SE mask standardization via type-dependent fields.
    REQ-L2-RF-025 AC3: Includes uid for stable identification.
    """

    artifact = models.OneToOneField(
        Artifact, on_delete=models.CASCADE, related_name="requirement"
    )
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=64, default="draft")
    type = models.CharField(
        max_length=64,
        choices=RequirementType.choices,
        default=RequirementType.SYREQ,
        help_text="Requirement classification (SyReq, UseCase, FeatureReq)",
    )
    level = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        choices=RequirementLevel.choices,
        help_text=(
            "K3: V-model hierarchy level (0=System, 1=Subsystem, 2=Component, "
            "3=Part, 4=Material). NULL until assigned explicitly."
        ),
    )
    complexity_fibonacci = models.IntegerField(
        null=True,
        blank=True,
        choices=ComplexityFibonacci.choices,
        help_text="Complexity via Fibonacci scale (visible only for SyReq)",
    )
    verification_method = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        choices=VerificationMethod.choices,
        help_text="Verification method (visible only for SyReq)",
    )
    uid = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="Unique identifier (read-only, auto-generated)",
    )
    suspect = models.BooleanField(
        default=False,
        help_text="SN-30: Indicates if this requirement needs review due to upstream changes.",
    )
    lifecycle_status = models.CharField(
        max_length=16,
        choices=LifecycleStatus.choices,
        default=LifecycleStatus.ACTIVE,
        help_text="REQ-006: Soft-delete lifecycle. 'deleted' hides requirement from normal views; hard-delete via admin only.",
    )
    embedding = VectorField(
        dimensions=1536,
        null=True,
        blank=True,
        help_text=(
            "REQ-L2-VS-004: Semantic embedding (1536-dim, OpenAI "
            "text-embedding-3-small compatible) for cosine similarity search. "
            "Best-effort: NULL when no embedding provider is configured."
        ),
    )

    class Meta:
        db_table = "pl_requirement"
        indexes = [
            # REQ-L2-VS-004: HNSW approximate-nearest-neighbour index for
            # cosine-distance similarity queries (embedding <=> query_vector).
            HnswIndex(
                name="pl_req_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
            # REQ-039: composite indexes for dominant list-filter combinations.
            models.Index(fields=["tenant", "status"], name="idx_req_tnt_status"),
            models.Index(
                fields=["tenant", "lifecycle_status"], name="idx_req_tnt_lifecycle"
            ),
        ]

    def __str__(self) -> str:
        return self.title


class ArchitectureElement(TenantScopedModel):
    """Architecture element derived from an artifact (REQ-L1-002).

    REQ-L1-041: Supports hierarchical parent-child relationships via parent_id.
    Level is derived from tree depth (0=root, 1=child of root, etc.) via CTE
    annotation in manager.get_with_level() (REQ-L1-058 AC2).

    REQ-L3-RF004-004: Supports SE mask fields (asil_level, make_or_buy, uid).
    REQ-L2-RF-025 AC3: Includes uid for stable identification.
    """

    artifact = models.OneToOneField(
        Artifact, on_delete=models.CASCADE, related_name="architecture_element"
    )
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    # REQ-006 (D5): free-form field — the ElementType enum no longer
    # restricts stored values. ElementType.choices only supplies the
    # built-in defaults/suggestions; users may introduce new workspace
    # types on the fly (Django choices are Python-level validation only,
    # not a DB constraint, so no migration is required for this change).
    element_type = models.CharField(
        max_length=64,
        blank=True,
        default=ElementType.COMPONENT,
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    asil_level = models.CharField(
        max_length=16,
        null=True,
        blank=True,
        choices=ASILLevel.choices,
        help_text="ASIL level (QM, A, B, C, D) per REQ-L3-RF004-004",
    )
    make_or_buy = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        choices=MakeOrBuy.choices,
        help_text="Make-or-Buy decision per REQ-L3-RF004-004",
    )
    uid = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="Unique identifier (read-only, auto-generated)",
    )
    suspect = models.BooleanField(
        default=False,
        help_text="SN-30: Indicates if this element needs review due to upstream changes.",
    )
    lifecycle_status = models.CharField(
        max_length=16,
        choices=LifecycleStatus.choices,
        default=LifecycleStatus.ACTIVE,
        help_text="REQ-006: Soft-delete lifecycle. 'deleted' hides element from normal views; hard-delete via admin only.",
    )

    class Meta:
        db_table = "pl_architecture_element"
        indexes = [
            # REQ-039: composite indexes for dominant list-filter combinations.
            models.Index(
                fields=["tenant", "element_type"], name="idx_archelem_tnt_type"
            ),
            models.Index(
                fields=["tenant", "lifecycle_status"],
                name="idx_archelem_tnt_lifecyc",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def level(self) -> int:
        """Return tree depth of this element (from annotation or fallback).

        REQ-L1-058 AC2: Prefer .get_with_level() for bulk fetches (CTE-based).
        This property provides compatibility for single-instance access
        and falls back to Python recursion if not annotated.
        """
        # Check if level was annotated by get_with_level()
        if hasattr(self, '_level_annotated'):
            return self._level_annotated
        # Fallback: compute via recursive get_level()
        return self.get_level()

    def get_level(self) -> int:
        """Return tree depth of this element.

        Root (parent=None) → level=0
        Direct child → level=1
        Nested → level=2, etc.

        NOTE: For bulk level retrieval, use manager.get_queryset_with_level()
        which uses DB CTE annotation (avoids N+1 queries, REQ-L1-058 AC2).
        This method is a fallback for single-instance level computation.
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
    embedding = VectorField(
        dimensions=1536,
        null=True,
        blank=True,
        help_text=(
            "REQ-L2-VS-004: Semantic embedding (1536-dim, OpenAI "
            "text-embedding-3-small compatible) for cosine similarity search "
            "over trace links. Best-effort: NULL when no embedding provider is "
            "configured."
        ),
    )

    class Meta:
        db_table = "pl_tracelink"
        indexes = [
            # REQ-L3-PL005-001: composite index for TraceLink graph queries.
            models.Index(
                fields=["source", "target"], name="idx_tracelink_graph"
            ),
            # REQ-L2-VS-004: HNSW approximate-nearest-neighbour index for
            # cosine-distance similarity queries (embedding <=> query_vector).
            HnswIndex(
                name="pl_tracelink_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_id} -[{self.link_type}]-> {self.target_id}"


class TestCase(TenantScopedModel):
    """Test case derived from an artifact (REQ-L1-012)."""
    __test__ = False

    artifact = models.OneToOneField(
        Artifact, on_delete=models.CASCADE, related_name="test_case"
    )
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    steps = models.JSONField(default=list, blank=True)
    test_type = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        choices=TestCaseType.choices,
        help_text=(
            "B6a: Test type (system/integration/unit/inspection/analysis/"
            "demonstration). Replaces the deprecated 'TestCase:<Type>' "
            "artifact_type prefix. NULL when not derivable."
        ),
    )
    uid = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="Unique identifier (read-only, auto-generated)",
    )
    suspect = models.BooleanField(
        default=False,
        help_text="SN-30: Indicates if this test case needs review due to upstream changes.",
    )

    class Meta:
        db_table = "pl_testcase"
        indexes = [
            models.Index(fields=["uid"], name="idx_testcase_uid_btree"),
        ]

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
    __test__ = False

    name = models.CharField(max_length=255)
    uid = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="Unique identifier (read-only, auto-generated)",
    )
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
            ("closed", "Closed"),
        ],
        default="in_progress",
    )
    ci_job_id = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "pl_test_run"
        verbose_name = "Test Run"
        verbose_name_plural = "Test Runs"
        indexes = [
            models.Index(fields=["uid"], name="idx_test_run_uid_btree"),
            # REQ-039: composite indexes for dominant list-filter combinations.
            models.Index(fields=["tenant", "workspace"], name="idx_testrun_tnt_ws"),
            models.Index(
                fields=["tenant", "status"], name="idx_testrun_tnt_status"
            ),
        ]

    def __str__(self) -> str:
        return f"TestRun:{self.name}:{self.status}"


class TestRunResult(TenantScopedModel):
    """Individual TestCase execution result within a TestRun (REQ-L2-AS-030)."""
    __test__ = False

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


class AttributeVisibilityConfig(TenantScopedModel):
    """Admin configuration for field visibility per entity type (REQ-L1-058).

    Allows tenant admins to control which type-dependent fields are visible
    in the UI and whether they are required in forms.

    Constraint: Unique on (tenant_id, entity_type, attribute_name).
    Index: Composite BTree on (tenant_id, entity_type) for fast bulk lookups.

    AC2: Used by RequirementSerializer and ArchitectureElementSerializer
    to conditionally include/exclude type-dependent fields in responses.
    """

    entity_type = models.CharField(
        max_length=64,
        help_text="Target entity type (e.g., 'Requirement', 'ArchitectureElement')",
    )
    attribute_name = models.CharField(
        max_length=128,
        help_text="Field name (e.g., 'moscow_priority', 'asil_level')",
    )
    is_visible = models.BooleanField(
        default=True,
        help_text="Show/hide toggle for frontend",
    )
    is_required = models.BooleanField(
        default=False,
        help_text="Mark as required in forms",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Audit: who created this config",
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Audit: who last modified this config",
    )
    version = models.IntegerField(
        default=1,
        help_text="Audit: version counter",
    )

    class Meta:
        db_table = "pl_attribute_visibility_config"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "entity_type", "attribute_name"],
                name="uq_attrvisib_tenant_entity_attr",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "entity_type"], name="idx_attrvisib_tenant_type"),
        ]

    def __str__(self) -> str:
        visibility_status = "visible" if self.is_visible else "hidden"
        required_status = "required" if self.is_required else "optional"
        return f"{self.entity_type}.{self.attribute_name} ({visibility_status}, {required_status})"


class CustomFieldDefinition(TenantScopedModel):
    """Workspace-wide custom field definition (REQ-016).

    Workspace administrators define custom fields (name, type, required flag and
    — for dropdowns — a fixed option set) centrally per workspace. A definition
    applies to *all* artifacts of the workspace (Requirements, ArchitectureElements,
    TestCases, …) because every concrete artifact type shares the generic
    :class:`Artifact` base. Entered values are stored per artifact instance in
    :class:`CustomFieldValue`.

    Constraint: unique on (workspace, name) — a field name is unique per workspace.
    """

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="custom_field_definitions",
    )
    name = models.CharField(
        max_length=128,
        help_text="Human-readable field label, unique within the workspace.",
    )
    field_type = models.CharField(
        max_length=16,
        choices=CustomFieldType.choices,
        default=CustomFieldType.TEXT,
        help_text="Data type: text, number or dropdown.",
    )
    is_required = models.BooleanField(
        default=False,
        help_text="Whether a value must be provided on the artifact form.",
    )
    options = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Dropdown options as a list of strings. Empty for text/number "
            "fields; required (non-empty) for dropdown fields."
        ),
    )
    order = models.IntegerField(
        default=0,
        help_text="Display order of the field in artifact forms (ascending).",
    )

    class Meta:
        db_table = "pl_custom_field_definition"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "name"],
                name="uq_customfielddef_workspace_name",
            ),
        ]
        indexes = [
            models.Index(
                fields=["workspace"], name="idx_customfielddef_workspace"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.field_type})"


class CustomFieldValue(TenantScopedModel):
    """Persisted value of a custom field for a single artifact instance (REQ-016).

    The FK targets the generic :class:`Artifact` base rather than each concrete
    type, so a single value table serves Requirements, ArchitectureElements and
    TestCases alike (all of which own a 1:1 ``artifact``). The value is stored as
    text; numeric and dropdown values are serialised to their string form and
    validated against the definition at the API boundary.

    Constraint: unique on (definition, artifact) — one value per field per artifact.
    """

    definition = models.ForeignKey(
        CustomFieldDefinition,
        on_delete=models.CASCADE,
        related_name="values",
    )
    artifact = models.ForeignKey(
        Artifact,
        on_delete=models.CASCADE,
        related_name="custom_field_values",
    )
    value = models.TextField(
        blank=True,
        default="",
        help_text="Stored value (string representation).",
    )

    class Meta:
        db_table = "pl_custom_field_value"
        constraints = [
            models.UniqueConstraint(
                fields=["definition", "artifact"],
                name="uq_customfieldvalue_definition_artifact",
            ),
        ]
        indexes = [
            models.Index(
                fields=["artifact"], name="idx_customfieldvalue_artifact"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.definition_id}={self.value!r}"


class GlossaryTerm(TenantScopedModel):
    """Semantic glossary term (REQ-L1-044)."""

    workspace = models.ForeignKey(
        Workspace, on_delete=models.SET_NULL, null=True, blank=True, related_name="glossary_terms"
    )
    term = models.CharField(max_length=255)
    definition = models.TextField()
    synonyms = models.JSONField(default=list, blank=True)
    abbreviation = models.CharField(max_length=64, blank=True)
    version = models.IntegerField(default=1)
    lifecycle_status = models.CharField(
        max_length=16,
        choices=LifecycleStatus.choices,
        default=LifecycleStatus.ACTIVE,
        help_text="REQ-006: Soft-delete lifecycle. 'deleted' hides term from normal views; hard-delete via admin only.",
    )

    class Meta:
        db_table = "pl_glossary_term"
        unique_together = (("workspace", "term"),)

    def __str__(self) -> str:
        return self.term


class GlossaryTermVersion(TenantScopedModel):
    """Immutable version snapshot of GlossaryTerm."""

    term_fk = models.ForeignKey(
        GlossaryTerm, on_delete=models.CASCADE, related_name="versions"
    )
    term_version = models.IntegerField()
    definition = models.TextField()
    synonyms = models.JSONField(default=list, blank=True)
    abbreviation = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = "pl_glossary_term_version"
        unique_together = (("term_fk", "term_version"),)


# ---------------------------------------------------------------------------
# LLM configuration (REQ-L2-LLM-001) — tenant-scoped singleton
# ---------------------------------------------------------------------------


class LlmProvider(models.TextChoices):
    """Supported LLM providers (REQ-L2-LLM-001).

    ``mock`` is the safe default and requires no external credentials.
    """

    ANTHROPIC = "anthropic", "Anthropic"
    OPENAI = "openai", "OpenAI"
    OLLAMA = "ollama", "Ollama"
    MOCK = "mock", "Mock"


class LlmSettings(TenantScopedModel):
    """Per-tenant LLM provider configuration (REQ-L2-LLM-001).

    Singleton per tenant: a unique constraint on ``tenant`` guarantees at most
    one row. The row is created lazily via ``get_or_create`` in the REST layer
    and seeded for existing tenants by the accompanying data migration.

    ``api_key`` holds the raw provider secret. It is never exposed through the
    REST serializer (write-only); readers only learn whether a key is set.

    REQ-081: the secret is encrypted at rest. ``api_key`` is a Python property
    over the ``api_key_encrypted`` column so every existing caller (llm_adapter,
    SettingsService, the REST serializer) keeps reading/writing plaintext
    without changes — only the storage representation changed.
    """

    provider = models.CharField(
        max_length=32,
        choices=LlmProvider.choices,
        default=LlmProvider.MOCK,
        help_text="Active LLM provider. Defaults to the credential-free mock.",
    )
    base_url = models.URLField(
        blank=True,
        default="",
        help_text="Optional base URL override (e.g. for a local Ollama server).",
    )
    # REQ-081: Fernet ciphertext, not plaintext. Never read/write this field
    # directly — use the ``api_key`` property below, which transparently
    # encrypts/decrypts using FIELD_ENCRYPTION_KEY (reqflow/settings.py).
    api_key_encrypted = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Encrypted provider API key (Fernet ciphertext, REQ-081). "
            "Never returned via the REST API. Access via the `api_key` "
            "property, not this field."
        ),
    )
    model_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Free-text model identifier (e.g. 'claude-3-opus-20240229').",
    )

    class Meta:
        db_table = "pl_llm_settings"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"], name="uq_llm_settings_tenant"
            ),
        ]

    def __str__(self) -> str:
        return f"LlmSettings(provider={self.provider})"

    @property
    def api_key(self) -> str:
        """Return the decrypted plaintext API key (REQ-081).

        Transparent over ``api_key_encrypted`` so every pre-existing caller
        that reads ``instance.api_key`` keeps getting plaintext back.
        """
        return decrypt_secret(self.api_key_encrypted)

    @api_key.setter
    def api_key(self, value: str) -> None:
        """Encrypt ``value`` and store it in ``api_key_encrypted`` (REQ-081)."""
        self.api_key_encrypted = encrypt_secret(value or "")

    def get_api_key_masked(self) -> str:
        """Return a masked api_key safe for logging (REQ-081).

        Exposes only the first and last four characters so operators can
        correlate a key without leaking the plaintext secret. Short or empty
        keys are fully masked.
        """
        key = self.api_key or ""
        if len(key) <= 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"


# ---------------------------------------------------------------------------
# Prompt templates (REQ-L2-PT-001) — tenant-scoped singleton
# ---------------------------------------------------------------------------

# Read-only default prompt content. Kept at module level so the data migration
# can seed identical values without importing model behaviour.
DEFAULT_NEED_TO_SYSREQ = (
    "Given the following stakeholder need, generate {n} system-level "
    "requirements. Each requirement must be specific, measurable, and testable. "
    "Return a JSON array of objects with fields: title (string), description "
    "(string), rationale (string).\n\nStakeholder Need:\nTitle: {need_title}\n"
    "Description: {need_description}"
)

DEFAULT_SYSREQ_TO_ARCH_ASSIGN = (
    "Given the following system requirement and the available architecture "
    "elements, suggest which architecture elements should be responsible for "
    "implementing it. Return a JSON array of architecture element IDs from the "
    "provided list.\n\nSystem Requirement:\n{req_title}: {req_description}\n\n"
    "Available Architecture Elements:\n{arch_elements_json}"
)

DEFAULT_SYSREQ_DECOMPOSE_NEXT_LEVEL = (
    "Decompose the following system requirement into more detailed requirements "
    "for the next architecture level. Requirements may be assigned to different "
    "architecture elements. Return a JSON array of objects with fields: title "
    "(string), description (string), rationale (string), "
    "suggested_arch_element_id (string or null).\n\nParent Requirement:\n"
    "{req_title}: {req_description}\n\nArchitecture Elements at this level:\n"
    "{arch_elements_json}"
)

# Canonical slot registry — maps slot name → default content.
PROMPT_TEMPLATE_DEFAULTS: dict[str, str] = {
    "need_to_sysreq": DEFAULT_NEED_TO_SYSREQ,
    "sysreq_to_arch_assign": DEFAULT_SYSREQ_TO_ARCH_ASSIGN,
    "sysreq_decompose_next_level": DEFAULT_SYSREQ_DECOMPOSE_NEXT_LEVEL,
}


class PromptTemplate(TenantScopedModel):
    """Per-tenant editable LLM prompt templates (REQ-L2-PT-001).

    Singleton per tenant (unique constraint on ``tenant``). Each field is a
    prompt "slot" whose factory default is stored in ``PROMPT_TEMPLATE_DEFAULTS``.
    ``reset_slot`` / ``reset_all`` restore the default content for a slot.
    """

    #: Read-only default constants (mirrors module-level defaults for callers
    #: that hold a model instance).
    DEFAULTS = PROMPT_TEMPLATE_DEFAULTS

    need_to_sysreq = models.TextField(
        default=DEFAULT_NEED_TO_SYSREQ,
        help_text="Prompt: stakeholder need -> system requirements.",
    )
    sysreq_to_arch_assign = models.TextField(
        default=DEFAULT_SYSREQ_TO_ARCH_ASSIGN,
        help_text="Prompt: system requirement -> architecture assignment.",
    )
    sysreq_decompose_next_level = models.TextField(
        default=DEFAULT_SYSREQ_DECOMPOSE_NEXT_LEVEL,
        help_text="Prompt: decompose system requirement to the next level.",
    )

    class Meta:
        db_table = "pl_prompt_template"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"], name="uq_prompt_template_tenant"
            ),
        ]

    def __str__(self) -> str:
        return f"PromptTemplate(tenant={self.tenant_id})"

    def get_slot(self, slot_name: str) -> str:
        """Return the current content for ``slot_name``.

        Raises:
            KeyError: If ``slot_name`` is not a known prompt slot.
        """
        if slot_name not in PROMPT_TEMPLATE_DEFAULTS:
            raise KeyError(slot_name)
        return getattr(self, slot_name)

    def reset_slot(self, slot_name: str) -> None:
        """Restore ``slot_name`` to its factory default (not saved)."""
        if slot_name not in PROMPT_TEMPLATE_DEFAULTS:
            raise KeyError(slot_name)
        setattr(self, slot_name, PROMPT_TEMPLATE_DEFAULTS[slot_name])

    def reset_all(self) -> None:
        """Restore every slot to its factory default (not saved)."""
        for slot_name, default in PROMPT_TEMPLATE_DEFAULTS.items():
            setattr(self, slot_name, default)


# ---------------------------------------------------------------------------
# Token usage accounting (REQ-106) — tenant-scoped, append-only
# ---------------------------------------------------------------------------


class TokenUsageRecord(TenantScopedModel):
    """Per-call LLM token consumption record (REQ-106).

    One row is written after every successful LLM capability call so token
    consumption can be aggregated per tenant and enforced against a configurable
    daily limit (``settings.TENANT_TOKEN_LIMIT_PER_DAY``).

    The stable LLM interface (``LlmResult.token_usage``) only exposes a single
    combined total, so callers that only know the total store it in
    ``input_tokens`` and leave ``output_tokens`` at 0. Aggregation always sums
    both columns, so the total is preserved regardless of how a provider splits
    the count. ``workspace_id`` is an optional soft reference (no FK) because the
    workspace is not always known at the LLM adapter boundary.
    """

    workspace_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="Optional workspace this call is attributed to (soft reference).",
    )
    provider = models.CharField(
        max_length=64,
        help_text="Provider name that served the call (e.g. 'anthropic', 'mock').",
    )
    capability = models.CharField(
        max_length=64,
        help_text="Capability invoked (e.g. 'validate_artifact').",
    )
    input_tokens = models.IntegerField(
        default=0,
        help_text="Prompt/input tokens (holds the combined total when a provider "
        "only exposes a single token count).",
    )
    output_tokens = models.IntegerField(
        default=0,
        help_text="Completion/output tokens (0 when only a combined total is known).",
    )

    class Meta:
        db_table = "pl_token_usage_record"
        indexes = [
            # REQ-106: aggregation queries filter by tenant and time window.
            models.Index(
                fields=["tenant", "created_at"], name="idx_tokenusage_tnt_created"
            ),
        ]

    def __str__(self) -> str:
        return (
            f"TokenUsage(tenant={self.tenant_id}, provider={self.provider}, "
            f"total={self.total_tokens})"
        )

    @property
    def total_tokens(self) -> int:
        """Return the combined input + output token count for this record."""
        return int(self.input_tokens or 0) + int(self.output_tokens or 0)


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
    "RequirementType",
    "RequirementLevel",
    "MoSCoWPriority",
    "ComplexityFibonacci",
    "VerificationMethod",
    "ElementType",
    "ArchitectureElement",
    "ASILLevel",
    "MakeOrBuy",
    "AttributeVisibilityConfig",
    "TraceLink",
    "TestCase",
    "TestCaseType",
    "WorkflowDefinition",
    "WorkflowState",
    "AuditLogEntry",
    "TestRun",
    "TestRunResult",
    "GlossaryTerm",
    "GlossaryTermVersion",
    "LlmProvider",
    "LlmSettings",
    "TokenUsageRecord",
    "PromptTemplate",
    "PROMPT_TEMPLATE_DEFAULTS",
    "DEFAULT_NEED_TO_SYSREQ",
    "DEFAULT_SYSREQ_TO_ARCH_ASSIGN",
    "DEFAULT_SYSREQ_DECOMPOSE_NEXT_LEVEL",
]
