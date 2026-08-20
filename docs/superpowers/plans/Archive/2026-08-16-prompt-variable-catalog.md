# Prompt Variable Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every LLM prompt template a central, workspace-overridable variable catalog and replace the hard-coded breadth/depth numbers of the architecture-decompose copilot with catalog-managed upper bounds.

**Architecture:** A new tenant-scoped `PromptVariable` model reuses `PromptTemplate`'s exact override mechanics (workspace row > tenant row > factory registry, append-only versions, application-level one-active-row mutex). A single new resolver module (`application/prompt_resolver.py`) replaces the three parallel fallback chains in `AiDerivationService`, `mcp_server/tools/prompt_template.py` and `interview_protocol.py`, and auto-injects every resolved `config` variable into each render call. REST (`/api/v1/prompt-variables/`), MCP (`prompt_variable.*`) and two React surfaces (per-slot variable table in `AiPromptsSection`, plus a new `PromptVariablesSection` management view) expose the catalog.

**Tech Stack:** Django 4.2+ / DRF 3.15+ / PostgreSQL 16 (backend), pytest (backend tests), React 18 + TypeScript 5.5 strict + Vite (frontend), vitest + @testing-library/react (frontend tests), MCP JSON-RPC 2.0 tool groups.

**Spec:** docs/superpowers/specs/2026-08-16-prompt-variable-catalog-design.md

## Global Constraints

- Phase 3 of the spec (§6, promptfoo test infrastructure) is explicitly OUT OF SCOPE for this plan — it is tracked separately as a GitHub issue. No task below creates `prompt_testing/`, `promptfoo/` or a CI job.
- `_render` semantics stay unchanged: a `str.replace` loop per placeholder, deliberately NOT `.format()`/Jinja2, so JSON braces inside prompt bodies survive (see the existing comment at `backend/application/ai_derivation_service.py:1522-1531`).
- Unknown or omitted placeholders are left literally in place (REQ-046) — a missing value never raises and never silently blanks the text.
- Config-variable resolution order is exactly: **explicit call parameter > workspace `PromptVariable` row > tenant `PromptVariable` row > factory registry default.**
- `data_kwargs` win over auto-injected `config` values on a name collision (spec §3.3).
- `kind="data"` rows are never creatable/editable through REST, MCP or UI — read-only catalog documentation. Only `kind="config"` is CRUD-able.
- `PromptVariable` rows are effectively immutable: a new value is a new row at `version = prior.version + 1`, the prior row is deactivated, never deleted (mirrors `PromptTemplate`).
- Every new tenant-scoped table gets `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` + a `<table>_tenant_isolation` policy in the same migration (pattern: `backend/persistence/migrations/0027_add_prompt_template.py`).
- Layer discipline (ADR-01): DRF views and MCP tool groups never query `persistence.models` directly — they go through `application/` services.
- Admin role (`ROLE_ADMIN`) is required for every prompt-variable read and write on both REST and MCP, mirroring the existing prompt-template gate (fix #101).
- Frontend: the `ui-ratchet` test asserts `style={{` occurrences in `frontend/src/components/` with **strict equality** (`expect(total).toBe(STYLE_BRACE_BASELINE)`, currently 1070). New components must therefore use hoisted `const xStyle: CSSProperties = {...}` + `style={xStyle}` — no inline object literals, no `style={{ ...base, extra }}` spreads.
- Frontend: `i18n-parity.test.ts` requires the identical flattened key set in `frontend/src/i18n/locales/de.json` and `en.json`. Every new key must land in both files in the same commit.
- MCP: adding tools requires regenerating `docs/agent-templates/tool-manifest.json` (`python manage.py export_tool_manifest`) in the same commit, otherwise `mcp_server/tests/test_tool_manifest_drift.py` fails.
- Backend tests run via `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest <path> -q` (requires `docker-compose up -d postgres redis`).
- Frontend tests run via `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm frontend-test sh -c "npm install && npx vitest run <path>"`.
- Commits use Conventional Commits, English, imperative, max 72 chars in the subject line. Work on a feature branch (`feat/prompt-variable-catalog`), never on `main`.
- NEVER run the Playwright E2E suite as part of this plan (project convention, `CLAUDE.md`) — targeted unit/integration tests only.
- **Breaking API change (Phase 2):** `POST /api/v1/workspaces/<id>/architecture/decompose/` and the MCP tool `architecture.decompose` rename their optional `breadth`/`depth` parameters to `max_breadth`/`max_depth`. Both surfaces and the frontend caller are updated inside this plan; no compatibility alias is kept.

---

### Task 1: PromptVariable model + migration

**Files:**
- Modify: `backend/persistence/models.py:1958-2021` (append after `PromptTemplate.save`)
- Create: `backend/persistence/migrations/0062_add_prompt_variable.py`
- Test: `backend/persistence/tests/test_prompt_variable_model.py`

**Interfaces:**
- Consumes: `TenantScopedModel`, `Tenant` (existing, `backend/persistence/models.py`).
- Produces:
  - `PROMPT_VARIABLE_KIND_CONFIG: str = "config"`, `PROMPT_VARIABLE_KIND_DATA: str = "data"`
  - `PROMPT_VARIABLE_TYPES: tuple[str, ...] = ("int", "str", "bool", "json")`
  - `class PromptVariable(TenantScopedModel)` with fields `name: str`, `kind: str`, `var_type: str`, `description: str`, `default_value: str`, `version: int`, `is_active: bool`, `workspace_id: UUID | None`; `save()` raises `django.db.IntegrityError` on a second active row for `(tenant, workspace_id, name)`.
  - db_table `pl_prompt_variable`.

- [ ] **Step 1: Write the failing test**

Create `backend/persistence/tests/test_prompt_variable_model.py`:

```python
"""PromptVariable model — scope uniqueness and defaults (spec §3.1)."""
from __future__ import annotations

import pytest
from django.db import IntegrityError

from persistence.models import (
    PROMPT_VARIABLE_KIND_CONFIG,
    PromptVariable,
    Tenant,
    Workspace,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant_workspace():
    tenant = Tenant.objects.create(name="PV Tenant", slug="pv-tenant")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="PV WS")
        yield tenant, workspace
    finally:
        TenantContext.clear_tenant()


def _make(tenant, **kwargs) -> PromptVariable:
    row = PromptVariable(
        tenant_id=tenant.id,
        name=kwargs.pop("name", "max_breadth"),
        kind=kwargs.pop("kind", PROMPT_VARIABLE_KIND_CONFIG),
        var_type=kwargs.pop("var_type", "int"),
        description=kwargs.pop("description", "Max children per level."),
        default_value=kwargs.pop("default_value", "5"),
        **kwargs,
    )
    row.save()
    return row


def test_defaults_are_version_one_and_active(tenant_workspace):
    tenant, _ws = tenant_workspace

    row = _make(tenant)

    assert row.version == 1
    assert row.is_active is True
    assert row.workspace_id is None


def test_second_active_row_for_same_scope_is_rejected(tenant_workspace):
    tenant, _ws = tenant_workspace
    _make(tenant)

    with pytest.raises(IntegrityError):
        _make(tenant)


def test_workspace_row_and_tenant_row_are_different_scopes(tenant_workspace):
    tenant, workspace = tenant_workspace
    _make(tenant)

    scoped = _make(tenant, workspace_id=workspace.id, default_value="9")

    assert scoped.workspace_id == workspace.id
    assert PromptVariable.objects.filter(is_active=True).count() == 2


def test_inactive_row_does_not_block_a_new_active_row(tenant_workspace):
    tenant, _ws = tenant_workspace
    prior = _make(tenant)
    prior.is_active = False
    prior.save(update_fields=["is_active"])

    successor = _make(tenant, version=2, default_value="7")

    assert successor.version == 2
    assert successor.is_active is True


def test_str_reports_scope_and_version(tenant_workspace):
    tenant, _ws = tenant_workspace

    assert "max_breadth" in str(_make(tenant))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest persistence/tests/test_prompt_variable_model.py -q`

Expected: FAIL with `ImportError: cannot import name 'PROMPT_VARIABLE_KIND_CONFIG' from 'persistence.models'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/persistence/models.py`, directly after the `PromptTemplate` class (before `REVIEW_POLICY_MODES`):

```python
# Prompt-variable catalog (spec §3.1). Two kinds:
#   "config" — pure configuration values (numeric caps, thresholds). Fully
#              CRUD-able from the admin UI, no code deploy needed.
#   "data"   — code-bound values computed from real artifact data (e.g.
#              {req_title}). Registered here for catalog visibility only;
#              never creatable or editable through REST/MCP/UI.
PROMPT_VARIABLE_KIND_CONFIG = "config"
PROMPT_VARIABLE_KIND_DATA = "data"
PROMPT_VARIABLE_KINDS = (PROMPT_VARIABLE_KIND_CONFIG, PROMPT_VARIABLE_KIND_DATA)
PROMPT_VARIABLE_TYPES = ("int", "str", "bool", "json")


class PromptVariable(TenantScopedModel):
    """Named, versioned, workspace-overridable prompt variable (spec §3.1).

    Deliberately a structural copy of :class:`PromptTemplate`: same
    ``workspace_id``-override semantics (``NULL`` = tenant-wide default, a
    non-null value overrides it for that workspace only), same append-only
    versioning (rows are effectively immutable — a new value is a new row and
    the prior one is deactivated), and the same application-level "at most one
    active row per ``(tenant, workspace_id, name)`` scope" rule enforced in
    :meth:`save` rather than via a Postgres partial unique index (this
    codebase has no precedent for ``condition=`` partial indexes in
    ``persistence/migrations/*.py``).

    ``default_value`` stores the JSON serialisation of the value so a single
    TextField can carry all four ``var_type``s without a per-type column.
    """

    name = models.CharField(
        max_length=100,
        help_text="Variable identifier, e.g. 'max_breadth' (open-ended, not an enum).",
    )
    kind = models.CharField(
        max_length=10,
        choices=[(k, k) for k in PROMPT_VARIABLE_KINDS],
        default=PROMPT_VARIABLE_KIND_CONFIG,
        help_text="'config' (data-driven, UI-editable) or 'data' (code-bound, read-only).",
    )
    var_type = models.CharField(
        max_length=20,
        choices=[(t, t) for t in PROMPT_VARIABLE_TYPES],
        default="str",
        help_text="int | str | bool | json — how default_value is deserialised.",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Human-readable purpose, shown in the catalog UI.",
    )
    default_value = models.TextField(
        blank=True,
        default="",
        help_text="JSON-serialised value for this scope.",
    )
    version = models.PositiveIntegerField(
        default=1,
        help_text="Version number within the (tenant, workspace_id, name) scope; starts at 1.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this version is the active one for its scope.",
    )
    workspace_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="Workspace override scope. NULL means tenant-wide default.",
    )

    class Meta:
        db_table = "pl_prompt_variable"
        indexes = [
            models.Index(
                fields=["tenant", "workspace_id", "name"],
                name="ix_prompt_variable_scope",
            ),
        ]

    def __str__(self) -> str:
        scope = f"workspace={self.workspace_id}" if self.workspace_id else "global"
        return f"PromptVariable(name={self.name!r}, {scope}, v{self.version})"

    def save(self, *args: object, **kwargs: object) -> None:
        """Persist the row, enforcing at most one active row per scope.

        Uses the same Tenant-row mutex as :meth:`PromptTemplate.save`: under
        Postgres READ COMMITTED a ``SELECT ... FOR UPDATE`` over a filter that
        matches zero rows takes no lock, so the conflict check is serialised
        by locking the parent ``Tenant`` row (which always exists) instead.

        Raises:
            IntegrityError: If ``is_active=True`` and another row already is
                active for the same ``(tenant, workspace_id, name)`` scope.
        """
        if self.is_active:
            with transaction.atomic():
                Tenant.objects.select_for_update().get(pk=self.tenant_id)
                conflict_exists = (
                    PromptVariable.objects.filter(
                        tenant_id=self.tenant_id,
                        workspace_id=self.workspace_id,
                        name=self.name,
                        is_active=True,
                    )
                    .exclude(pk=self.pk)
                    .exists()
                )
                if conflict_exists:
                    raise IntegrityError(
                        "Another active PromptVariable already exists for "
                        f"(tenant={self.tenant_id}, workspace_id={self.workspace_id}, "
                        f"name={self.name!r})."
                    )
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)
```

Create `backend/persistence/migrations/0062_add_prompt_variable.py`:

```python
"""PromptVariable — prompt-variable catalog (spec §3.1).

Operation order mirrors 0027_add_prompt_template.py:
  1. CreateModel + scope index.
  2. Enable + FORCE Row-Level Security on ``pl_prompt_variable``.

No data seeding: factory defaults live in the code registry
(``application.prompt_variables.PROMPT_VARIABLE_DEFAULTS``), exactly like
``PROMPT_TEMPLATE_DEFAULTS`` does for templates. DB rows exist only for
tenant/workspace overrides and admin-created config variables, so a fresh
tenant needs no seed pass at all.
"""
import django.db.models.deletion
import django.db.models.manager
import uuid
from django.conf import settings
from django.db import migrations, models

_TABLE = "pl_prompt_variable"
_POLICY = f"{_TABLE}_tenant_isolation"

_ENABLE_RLS_SQL = (
    f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;\n"
    f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;\n"
    f"CREATE POLICY {_POLICY} ON {_TABLE}\n"
    f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
    f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
)

_DISABLE_RLS_SQL = (
    f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE};\n"
    f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;\n"
    f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;"
)


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0061_interview_session_rls'),
    ]

    operations = [
        migrations.CreateModel(
            name='PromptVariable',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(help_text="Variable identifier, e.g. 'max_breadth' (open-ended, not an enum).", max_length=100)),
                ('kind', models.CharField(choices=[('config', 'config'), ('data', 'data')], default='config', help_text="'config' (data-driven, UI-editable) or 'data' (code-bound, read-only).", max_length=10)),
                ('var_type', models.CharField(choices=[('int', 'int'), ('str', 'str'), ('bool', 'bool'), ('json', 'json')], default='str', help_text='int | str | bool | json — how default_value is deserialised.', max_length=20)),
                ('description', models.TextField(blank=True, default='', help_text='Human-readable purpose, shown in the catalog UI.')),
                ('default_value', models.TextField(blank=True, default='', help_text='JSON-serialised value for this scope.')),
                ('version', models.PositiveIntegerField(default=1, help_text='Version number within the (tenant, workspace_id, name) scope; starts at 1.')),
                ('is_active', models.BooleanField(default=True, help_text='Whether this version is the active one for its scope.')),
                ('workspace_id', models.UUIDField(blank=True, help_text='Workspace override scope. NULL means tenant-wide default.', null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='persistence.tenant')),
            ],
            options={
                'db_table': 'pl_prompt_variable',
                'indexes': [models.Index(fields=['tenant', 'workspace_id', 'name'], name='ix_prompt_variable_scope')],
            },
            managers=[
                ('objects', django.db.models.manager.Manager()),
                ('unscoped', django.db.models.manager.Manager()),
            ],
        ),
        migrations.RunSQL(sql=_ENABLE_RLS_SQL, reverse_sql=_DISABLE_RLS_SQL),
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest persistence/tests/test_prompt_variable_model.py -q`

Expected: PASS (5 passed)

- [ ] **Step 5: Verify no migration drift**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test python manage.py makemigrations --check --dry-run`

Expected: `No changes detected`

- [ ] **Step 6: Commit**

```bash
git checkout -b feat/prompt-variable-catalog
git add backend/persistence/models.py backend/persistence/migrations/0062_add_prompt_variable.py backend/persistence/tests/test_prompt_variable_model.py
git commit -m "feat: add PromptVariable model for the prompt variable catalog"
```

---

### Task 2: Factory variable registry + value (de)serialisation

**Files:**
- Create: `backend/application/prompt_variables.py`
- Test: `backend/application/tests/test_prompt_variables_registry.py`

**Interfaces:**
- Consumes: `PROMPT_VARIABLE_KIND_CONFIG`, `PROMPT_VARIABLE_KIND_DATA`, `PROMPT_VARIABLE_TYPES` from Task 1.
- Produces:
  - `@dataclass(frozen=True) class PromptVariableSpec` with fields `name: str`, `kind: str`, `var_type: str`, `description: str`, `default_value: Any`
  - `PROMPT_VARIABLE_DEFAULTS: Dict[str, PromptVariableSpec]` — the factory catalog
  - `serialize_variable_value(value: Any) -> str`
  - `deserialize_variable_value(var_type: str, raw: str) -> Any`
  - `class VariableTypeError(ValueError)`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_prompt_variables_registry.py`:

```python
"""Factory prompt-variable registry + value (de)serialisation (spec §3.1)."""
from __future__ import annotations

import pytest

from application.prompt_variables import (
    PROMPT_VARIABLE_DEFAULTS,
    PromptVariableSpec,
    VariableTypeError,
    deserialize_variable_value,
    serialize_variable_value,
)


def test_every_entry_is_a_spec_keyed_by_its_own_name():
    for name, spec in PROMPT_VARIABLE_DEFAULTS.items():
        assert isinstance(spec, PromptVariableSpec)
        assert spec.name == name
        assert spec.kind in ("config", "data")
        assert spec.var_type in ("int", "str", "bool", "json")
        assert spec.description, f"{name} has no description"


def test_known_data_variables_are_registered():
    for name in ("req_title", "need_description", "arch_elements_json"):
        assert PROMPT_VARIABLE_DEFAULTS[name].kind == "data"


def test_data_variables_default_to_an_empty_string():
    assert PROMPT_VARIABLE_DEFAULTS["req_title"].default_value == ""


@pytest.mark.parametrize(
    ("var_type", "raw", "expected"),
    [
        ("int", "5", 5),
        ("str", '"abc"', "abc"),
        ("bool", "true", True),
        ("json", '{"a": 1}', {"a": 1}),
    ],
)
def test_deserialize_returns_the_typed_value(var_type, raw, expected):
    assert deserialize_variable_value(var_type, raw) == expected


def test_serialize_roundtrips_through_deserialize():
    for var_type, value in (("int", 5), ("str", "abc"), ("bool", False), ("json", [1, 2])):
        assert deserialize_variable_value(var_type, serialize_variable_value(value)) == value


def test_deserialize_falls_back_to_the_raw_string_for_str_type():
    """Legacy/hand-edited rows may hold a bare, unquoted string."""
    assert deserialize_variable_value("str", "plain text") == "plain text"


def test_deserialize_rejects_a_wrongly_typed_value():
    with pytest.raises(VariableTypeError):
        deserialize_variable_value("int", '"not a number"')


def test_deserialize_rejects_an_unknown_var_type():
    with pytest.raises(VariableTypeError):
        deserialize_variable_value("decimal", "1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_prompt_variables_registry.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'application.prompt_variables'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/prompt_variables.py`:

```python
"""Factory registry of prompt variables (spec §3.1/§3.2).

This module is the code-side counterpart to ``PromptVariable`` DB rows,
mirroring exactly how ``PROMPT_TEMPLATE_DEFAULTS`` relates to
``PromptTemplate``: the registry below carries the factory default for every
variable the product ships with, and DB rows exist only to *override* those
per tenant or per workspace — plus to hold ``config`` variables an admin
invents at runtime, which have no factory entry at all.

Why a code registry instead of a per-tenant DB seed (spec §3.1 wording):
seeding would have to run for every existing tenant in a data migration *and*
for every tenant created afterwards, duplicating the factory values into N
copies that then drift. Deriving them from code keeps exactly one source of
truth and makes "reset to factory" a deletion rather than a rewrite — the
same reasoning that already governs prompt templates.

``kind="data"`` entries are documentation only: their values are computed by
the code that builds the render call, never read from here.

req_id: REQ-L2-PT-001
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict

from persistence.models import (
    PROMPT_VARIABLE_KIND_CONFIG,
    PROMPT_VARIABLE_KIND_DATA,
    PROMPT_VARIABLE_TYPES,
)


class VariableTypeError(ValueError):
    """Raised when a stored value does not match its declared ``var_type``."""


@dataclass(frozen=True)
class PromptVariableSpec:
    """One factory-registered variable.

    Attributes:
        name:          Placeholder name as it appears in prompt bodies, i.e.
                       ``{name}``.
        kind:          ``"config"`` or ``"data"``.
        var_type:      ``"int"``, ``"str"``, ``"bool"`` or ``"json"``.
        description:   Human-readable purpose, rendered in the catalog UI.
        default_value: Factory value (already typed, not JSON text).
    """

    name: str
    kind: str
    var_type: str
    description: str
    default_value: Any


def _data(name: str, description: str, var_type: str = "str") -> PromptVariableSpec:
    """Build a code-bound (``kind="data"``) spec with an empty default."""
    return PromptVariableSpec(
        name=name,
        kind=PROMPT_VARIABLE_KIND_DATA,
        var_type=var_type,
        description=description,
        default_value="",
    )


def _config(name: str, description: str, var_type: str, default: Any) -> PromptVariableSpec:
    """Build a data-driven (``kind="config"``) spec."""
    return PromptVariableSpec(
        name=name,
        kind=PROMPT_VARIABLE_KIND_CONFIG,
        var_type=var_type,
        description=description,
        default_value=default,
    )


#: Factory catalog. Every ``{placeholder}`` any shipped prompt template uses
#: appears here exactly once, so the UI can document it and the resolver can
#: tell a typo apart from a known name.
PROMPT_VARIABLE_DEFAULTS: Dict[str, PromptVariableSpec] = {
    # --- data (code-bound) -------------------------------------------------
    "n": _data("n", "Number of requirement drafts requested by the caller.", "int"),
    "need_title": _data("need_title", "Title of the source stakeholder need."),
    "need_description": _data(
        "need_description", "Description of the source stakeholder need."
    ),
    "req_title": _data("req_title", "Title of the source requirement."),
    "req_description": _data(
        "req_description", "Description of the source requirement."
    ),
    "arch_elements_json": _data(
        "arch_elements_json",
        "JSON array of the candidate architecture elements (id, name, description).",
        "json",
    ),
    "goals": _data("goals", "Newline-joined list of the workspace's Goal statements."),
    "ae_title": _data("ae_title", "Title of the source architecture element."),
    "ae_description": _data(
        "ae_description", "Description of the source architecture element."
    ),
    "workspace_text": _data(
        "workspace_text",
        "Concatenated requirement/architecture titles and descriptions of a workspace.",
    ),
    "decision_description": _data(
        "decision_description", "Free-text description of the decision to structure."
    ),
    "bundle_markdown": _data(
        "bundle_markdown", "The raw Markdown requirement bundle to compress."
    ),
    "answers_text": _data(
        "answers_text", "The interview answers collected so far, as text."
    ),
    "candidates_json": _data(
        "candidates_json",
        "JSON array of candidate artifacts that passed the structural pre-filter.",
        "json",
    ),
    "artifact_type": _data(
        "artifact_type", "PascalCase artifact type the interview is capturing."
    ),
    "phase_name": _data("phase_name", "Name of the current interview protocol phase."),
    "transcript_json": _data(
        "transcript_json",
        "JSON list of {role, text, timestamp} interview turns so far.",
        "json",
    ),
    "current_phase_fragment": _data(
        "current_phase_fragment", "Prompt fragment of the current interview phase."
    ),
    "collected_fields_json": _data(
        "collected_fields_json",
        "JSON object of interview field values collected so far.",
        "json",
    ),
    "missing_fields_json": _data(
        "missing_fields_json",
        "JSON list of {name, type, choices} for fields still needed.",
        "json",
    ),
    "grounding_snapshot_json": _data(
        "grounding_snapshot_json",
        "JSON snapshot of possibly related existing artifacts.",
        "json",
    ),
    "user_message": _data("user_message", "The user's latest interview message."),
}


def serialize_variable_value(value: Any) -> str:
    """Return the JSON text stored in ``PromptVariable.default_value``."""
    return json.dumps(value)


def deserialize_variable_value(var_type: str, raw: str) -> Any:
    """Return the typed value encoded in *raw* for *var_type*.

    ``"str"`` tolerates a bare, unquoted body so a hand-edited row (or an
    older import) is still readable instead of hard-failing.

    Raises:
        VariableTypeError: Unknown *var_type*, malformed JSON, or a value
            whose Python type does not match *var_type*.
    """
    if var_type not in PROMPT_VARIABLE_TYPES:
        raise VariableTypeError(
            f"Unknown var_type {var_type!r}; expected one of {PROMPT_VARIABLE_TYPES}."
        )
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        if var_type == "str":
            return raw
        raise VariableTypeError(
            f"Value for a {var_type!r} variable is not valid JSON: {raw!r}"
        ) from exc

    if var_type == "int":
        # bool is a subclass of int — reject it explicitly.
        if isinstance(parsed, bool) or not isinstance(parsed, int):
            raise VariableTypeError(f"Expected an int value, got {parsed!r}.")
        return parsed
    if var_type == "bool":
        if not isinstance(parsed, bool):
            raise VariableTypeError(f"Expected a bool value, got {parsed!r}.")
        return parsed
    if var_type == "str":
        return parsed if isinstance(parsed, str) else raw
    return parsed


__all__ = [
    "PROMPT_VARIABLE_DEFAULTS",
    "PromptVariableSpec",
    "VariableTypeError",
    "deserialize_variable_value",
    "serialize_variable_value",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_prompt_variables_registry.py -q`

Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/prompt_variables.py backend/application/tests/test_prompt_variables_registry.py
git commit -m "feat: add factory prompt variable registry and value codec"
```

---

### Task 3: PromptVariable scope/version helpers

**Files:**
- Create: `backend/application/prompt_variable_versioning.py`
- Test: `backend/application/tests/test_prompt_variable_versioning.py`

**Interfaces:**
- Consumes: `PromptVariable` (Task 1), `atomic_transaction` (`persistence.transactions`, existing).
- Produces:
  - `get_active_variable(*, tenant_id: UUID, name: str, workspace_id: UUID | None = None) -> PromptVariable | None`
  - `list_active_variables(*, tenant_id: UUID, workspace_id: UUID | None = None) -> list[PromptVariable]`
  - `publish_new_variable_version(*, tenant_id: UUID, name: str, kind: str, var_type: str, description: str, default_value: str, workspace_id: UUID | None = None) -> PromptVariable`
  - `deactivate_variable_scope(*, tenant_id: UUID, name: str, workspace_id: UUID | None = None) -> bool`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_prompt_variable_versioning.py`:

```python
"""Scope/version helpers for PromptVariable (mirrors prompt_template_versioning)."""
from __future__ import annotations

import pytest

from application.prompt_variable_versioning import (
    deactivate_variable_scope,
    get_active_variable,
    list_active_variables,
    publish_new_variable_version,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant_workspace():
    from persistence.models import Tenant, Workspace

    tenant = Tenant.objects.create(name="PVV Tenant", slug="pvv-tenant")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="PVV WS")
        yield tenant, workspace
    finally:
        TenantContext.clear_tenant()


def _publish(tenant_id, value: str, **kwargs):
    return publish_new_variable_version(
        tenant_id=tenant_id,
        name=kwargs.pop("name", "max_breadth"),
        kind=kwargs.pop("kind", "config"),
        var_type=kwargs.pop("var_type", "int"),
        description=kwargs.pop("description", "Max children per level."),
        default_value=value,
        **kwargs,
    )


def test_returns_none_when_nothing_published(tenant_workspace):
    tenant, _ws = tenant_workspace

    assert get_active_variable(tenant_id=tenant.id, name="max_breadth") is None


def test_publishing_creates_version_one(tenant_workspace):
    tenant, _ws = tenant_workspace

    row = _publish(tenant.id, "5")

    assert row.version == 1
    assert row.is_active is True


def test_republishing_bumps_the_version_and_deactivates_the_prior_row(tenant_workspace):
    tenant, _ws = tenant_workspace
    _publish(tenant.id, "5")

    second = _publish(tenant.id, "8")

    assert second.version == 2
    active = get_active_variable(tenant_id=tenant.id, name="max_breadth")
    assert active is not None
    assert active.default_value == "8"


def test_workspace_none_selects_the_tenant_wide_scope(tenant_workspace):
    tenant, workspace = tenant_workspace
    _publish(tenant.id, "9", workspace_id=workspace.id)

    assert get_active_variable(tenant_id=tenant.id, name="max_breadth") is None
    scoped = get_active_variable(
        tenant_id=tenant.id, name="max_breadth", workspace_id=workspace.id
    )
    assert scoped is not None
    assert scoped.default_value == "9"


def test_list_without_workspace_filter_returns_every_scope(tenant_workspace):
    tenant, workspace = tenant_workspace
    _publish(tenant.id, "5")
    _publish(tenant.id, "9", workspace_id=workspace.id)

    rows = list_active_variables(tenant_id=tenant.id)

    assert len(rows) == 2


def test_list_with_workspace_filter_returns_only_that_workspace(tenant_workspace):
    tenant, workspace = tenant_workspace
    _publish(tenant.id, "5")
    _publish(tenant.id, "9", workspace_id=workspace.id)

    rows = list_active_variables(tenant_id=tenant.id, workspace_id=workspace.id)

    assert [r.default_value for r in rows] == ["9"]


def test_deactivate_reports_whether_a_row_was_active(tenant_workspace):
    tenant, _ws = tenant_workspace
    _publish(tenant.id, "5")

    assert deactivate_variable_scope(tenant_id=tenant.id, name="max_breadth") is True
    assert deactivate_variable_scope(tenant_id=tenant.id, name="max_breadth") is False
    assert get_active_variable(tenant_id=tenant.id, name="max_breadth") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_prompt_variable_versioning.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'application.prompt_variable_versioning'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/prompt_variable_versioning.py`:

```python
"""Shared PromptVariable version-bump helpers (spec §3.1).

Structural twin of ``application/prompt_template_versioning.py``: the REST
views, the MCP tool group and the resolver all need the same "deactivate
whatever row is active for a (tenant, workspace_id, name) scope, then create
the next version and mark it active" operation, so it lives in exactly one
place.

``PromptVariable.save()`` already enforces "at most one active row per scope"
via its own Tenant-row mutex — these helpers only sequence the deactivate +
create pair inside one transaction so a crash between the two steps can never
leave the scope with zero active rows.
"""
from __future__ import annotations

from uuid import UUID

from persistence.models import PromptVariable
from persistence.transactions import atomic_transaction


def get_active_variable(
    *, tenant_id: UUID, name: str, workspace_id: UUID | None = None
) -> PromptVariable | None:
    """Return the active row for one exact scope, or ``None``.

    ``workspace_id=None`` selects the *tenant-wide* scope (``None`` is the
    real column value there); it does not mean "any workspace" — use
    :func:`list_active_variables` for an unfiltered listing.
    """
    return PromptVariable.objects.filter(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        name=name,
        is_active=True,
    ).first()


def list_active_variables(
    *, tenant_id: UUID, workspace_id: UUID | None = None
) -> list[PromptVariable]:
    """Return the tenant's active variable rows, ordered by name.

    Unlike :func:`get_active_variable`, ``workspace_id=None`` here means *no
    workspace filter at all*: the result then contains both tenant-wide rows
    and every workspace-scoped row.
    """
    qs = PromptVariable.objects.filter(tenant_id=tenant_id, is_active=True)
    if workspace_id is not None:
        qs = qs.filter(workspace_id=workspace_id)
    return list(qs.order_by("name"))


@atomic_transaction
def deactivate_variable_scope(
    *, tenant_id: UUID, name: str, workspace_id: UUID | None = None
) -> bool:
    """Deactivate the active row for one exact scope, if there is one.

    Rows are never deleted; the scope is simply left with zero active rows so
    the resolution chain (workspace -> tenant -> factory) falls through.

    Returns:
        ``True`` if a row was deactivated, ``False`` if the scope had none.
    """
    prior = get_active_variable(
        tenant_id=tenant_id, name=name, workspace_id=workspace_id
    )
    if prior is None:
        return False
    prior.is_active = False
    prior.save(update_fields=["is_active"])
    return True


@atomic_transaction
def publish_new_variable_version(
    *,
    tenant_id: UUID,
    name: str,
    kind: str,
    var_type: str,
    description: str,
    default_value: str,
    workspace_id: UUID | None = None,
) -> PromptVariable:
    """Deactivate the current active row for the scope (if any); create N+1."""
    prior = get_active_variable(
        tenant_id=tenant_id, name=name, workspace_id=workspace_id
    )

    next_version = (prior.version + 1) if prior is not None else 1
    if prior is not None:
        prior.is_active = False
        prior.save(update_fields=["is_active"])

    new_row = PromptVariable(
        tenant_id=tenant_id,
        name=name,
        kind=kind,
        var_type=var_type,
        description=description,
        default_value=default_value,
        version=next_version,
        is_active=True,
        workspace_id=workspace_id,
    )
    new_row.save()
    return new_row


__all__ = [
    "deactivate_variable_scope",
    "get_active_variable",
    "list_active_variables",
    "publish_new_variable_version",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_prompt_variable_versioning.py -q`

Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/prompt_variable_versioning.py backend/application/tests/test_prompt_variable_versioning.py
git commit -m "feat: add PromptVariable scope and version helpers"
```

---

### Task 4: Consolidated slot registry with declared data variables

**Files:**
- Create: `backend/application/prompt_slots.py`
- Test: `backend/application/tests/test_prompt_slots_registry.py`

**Interfaces:**
- Consumes: `PROMPT_TEMPLATE_DEFAULTS` (`application.ai_derivation_service`), `INTERVIEW_PROTOCOL_DEFAULTS` (`application.interview_protocol`), `PROMPT_VARIABLE_DEFAULTS` (Task 2).
- Produces:
  - `@dataclass(frozen=True) class PromptSlotSpec` with `name: str`, `default_content: str`, `data_variables: tuple[str, ...]`
  - `get_prompt_slots() -> Dict[str, PromptSlotSpec]`
  - `get_slot_default(name: str) -> str | None`
  - `get_slot_data_variables(name: str) -> tuple[str, ...]`
  - `INTERVIEW_PROTOCOL_DATA_VARIABLES: tuple[str, ...]`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_prompt_slots_registry.py`:

```python
"""Canonical slot registry: one entry per slot, with declared data variables."""
from __future__ import annotations

from application.ai_derivation_service import PROMPT_TEMPLATE_DEFAULTS
from application.interview_protocol import INTERVIEW_PROTOCOL_DEFAULTS
from application.prompt_slots import (
    PromptSlotSpec,
    get_prompt_slots,
    get_slot_data_variables,
    get_slot_default,
)
from application.prompt_variables import PROMPT_VARIABLE_DEFAULTS


def test_registry_covers_both_source_registries():
    slots = get_prompt_slots()

    for name in PROMPT_TEMPLATE_DEFAULTS:
        assert name in slots
    for name in INTERVIEW_PROTOCOL_DEFAULTS:
        assert name in slots


def test_every_entry_is_a_spec_keyed_by_its_own_name():
    for name, spec in get_prompt_slots().items():
        assert isinstance(spec, PromptSlotSpec)
        assert spec.name == name
        assert spec.default_content


def test_default_content_matches_the_source_registry():
    assert get_slot_default("need_to_sysreq") == PROMPT_TEMPLATE_DEFAULTS["need_to_sysreq"]


def test_unknown_slot_has_no_default_and_no_data_variables():
    assert get_slot_default("nope_not_a_slot") is None
    assert get_slot_data_variables("nope_not_a_slot") == ()


def test_declared_data_variables_are_registered_in_the_variable_catalog():
    for name, spec in get_prompt_slots().items():
        for var in spec.data_variables:
            assert var in PROMPT_VARIABLE_DEFAULTS, f"{name} declares unknown {var}"
            assert PROMPT_VARIABLE_DEFAULTS[var].kind == "data"


def test_need_to_sysreq_declares_its_three_data_variables():
    assert set(get_slot_data_variables("need_to_sysreq")) == {
        "n",
        "need_title",
        "need_description",
    }


def test_interview_protocol_slots_share_one_data_variable_set():
    for name in INTERVIEW_PROTOCOL_DEFAULTS:
        assert "artifact_type" in get_slot_data_variables(name)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_prompt_slots_registry.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'application.prompt_slots'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/prompt_slots.py`:

```python
"""Canonical prompt-slot registry (spec §3.2).

Before this module the factory defaults lived in three places that each knew
about a different subset: ``persistence.models.PROMPT_TEMPLATE_DEFAULTS`` (3
entries), ``application.ai_derivation_service.PROMPT_TEMPLATE_DEFAULTS`` (the
11-slot merge) and ``application.interview_protocol.INTERVIEW_PROTOCOL_DEFAULTS``
(one per in-scope artifact type). This module merges them into ONE lookup and
adds the piece the spec asks for: which ``data`` variables each slot's render
call supplies (``PromptSlotSpec.data_variables``).

``config`` variables are deliberately NOT declared per slot — they are
resolved wholesale for the active tenant/workspace on every render call (see
``application.prompt_resolver.resolve_and_render``), so an admin can
reference a newly created ``config`` variable in any prompt body without a
developer "enabling" it first.

The two source registries are imported lazily inside :func:`get_prompt_slots`
because ``ai_derivation_service`` imports back into ``application/*`` — the
same lazy-import idiom ``SettingsService._all_prompt_defaults`` already uses
for this exact cycle.

req_id: REQ-L2-PT-001
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class PromptSlotSpec:
    """One prompt slot: its factory body plus the data variables it is fed."""

    name: str
    default_content: str
    data_variables: Tuple[str, ...]


#: Every ``interview.protocol.<Type>`` slot is rendered with the same set.
INTERVIEW_PROTOCOL_DATA_VARIABLES: Tuple[str, ...] = (
    "artifact_type",
    "phase_name",
    "collected_fields_json",
    "missing_fields_json",
    "grounding_snapshot_json",
)

#: Data variables per named slot. Code-bound by definition: the values come
#: from the service that builds the render call, so this map only changes
#: together with that code (spec §3.2 — no junction table).
_DATA_VARIABLES_BY_SLOT: Dict[str, Tuple[str, ...]] = {
    "need_to_sysreq": ("n", "need_title", "need_description"),
    "sysreq_to_arch_assign": ("req_title", "req_description", "arch_elements_json"),
    "sysreq_decompose_next_level": (
        "req_title",
        "req_description",
        "arch_elements_json",
    ),
    "goal_aggregate": ("goals",),
    "testcase_derive": ("req_title", "req_description"),
    "architecture_to_risk": ("ae_title", "ae_description"),
    "workspace_to_glossary": ("workspace_text",),
    "decision_to_adr": ("decision_description",),
    "bundle_compression": ("bundle_markdown",),
    "interview.grounding_rank": ("answers_text", "candidates_json"),
    "interview.chat_turn": (
        "artifact_type",
        "transcript_json",
        "current_phase_fragment",
        "missing_fields_json",
        "grounding_snapshot_json",
        "user_message",
    ),
}


def get_prompt_slots() -> Dict[str, PromptSlotSpec]:
    """Return the merged factory registry, keyed by slot name.

    Rebuilt per call (cheap dict comprehension over ~19 entries) so a test
    that monkeypatches one of the source registries sees the change — caching
    it would pin whatever the first caller observed.
    """
    from application.ai_derivation_service import PROMPT_TEMPLATE_DEFAULTS
    from application.interview_protocol import INTERVIEW_PROTOCOL_DEFAULTS

    merged: Dict[str, str] = {
        **PROMPT_TEMPLATE_DEFAULTS,
        **INTERVIEW_PROTOCOL_DEFAULTS,
    }
    slots: Dict[str, PromptSlotSpec] = {}
    for name, content in merged.items():
        if name.startswith("interview.protocol."):
            data_variables = INTERVIEW_PROTOCOL_DATA_VARIABLES
        else:
            data_variables = _DATA_VARIABLES_BY_SLOT.get(name, ())
        slots[name] = PromptSlotSpec(
            name=name, default_content=content, data_variables=data_variables
        )
    return slots


def get_slot_default(name: str) -> str | None:
    """Return the factory body for *name*, or ``None`` for an unknown slot."""
    spec = get_prompt_slots().get(name)
    return spec.default_content if spec is not None else None


def get_slot_data_variables(name: str) -> Tuple[str, ...]:
    """Return the declared data variables of *name* (empty for unknown slots)."""
    spec = get_prompt_slots().get(name)
    return spec.data_variables if spec is not None else ()


__all__ = [
    "INTERVIEW_PROTOCOL_DATA_VARIABLES",
    "PromptSlotSpec",
    "get_prompt_slots",
    "get_slot_data_variables",
    "get_slot_default",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_prompt_slots_registry.py -q`

Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/prompt_slots.py backend/application/tests/test_prompt_slots_registry.py
git commit -m "feat: consolidate prompt slot registry with data variables"
```

---

### Task 5: Shared resolver (`resolve_and_render`)

**Files:**
- Create: `backend/application/prompt_resolver.py`
- Test: `backend/application/tests/test_prompt_resolver.py`

**Interfaces:**
- Consumes: `get_active_template` (`application.prompt_template_versioning`, existing), `get_slot_default` / `get_slot_data_variables` (Task 4), `list_active_variables` (Task 3), `PROMPT_VARIABLE_DEFAULTS` / `deserialize_variable_value` / `VariableTypeError` (Task 2), `AuthContext` (`auth_tenancy.context`, existing), `ValidationError` (`application.base`, existing).
- Produces:
  - `PLACEHOLDER_PATTERN: re.Pattern[str]`
  - `class PromptSlotNotFoundError(ValidationError)`
  - `extract_placeholders(content: str) -> list[str]`
  - `render_template(content: str, **values: Any) -> str`
  - `try_resolve_template_content(slot_name: str, ctx: AuthContext, workspace_id: UUID | str | None = None) -> str | None`
  - `resolve_template_content(slot_name: str, ctx: AuthContext, workspace_id: UUID | str | None = None) -> str`
  - `resolve_config_values(ctx: AuthContext, workspace_id: UUID | str | None = None, *, overrides: Dict[str, Any] | None = None) -> Dict[str, Any]`
  - `resolve_and_render(slot_name: str, ctx: AuthContext, workspace_id: UUID | str | None = None, *, config_overrides: Dict[str, Any] | None = None, **data_kwargs: Any) -> str`
  - `unknown_placeholders(content: str, slot_name: str, ctx: AuthContext, workspace_id: UUID | str | None = None) -> list[str]`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_prompt_resolver.py`:

```python
"""Shared prompt resolver — the single resolution path (spec §3.3, §8)."""
from __future__ import annotations

import pytest

from application.prompt_resolver import (
    PromptSlotNotFoundError,
    extract_placeholders,
    render_template,
    resolve_and_render,
    resolve_config_values,
    resolve_template_content,
    try_resolve_template_content,
    unknown_placeholders,
)
from application.prompt_template_versioning import publish_new_version
from application.prompt_variable_versioning import publish_new_variable_version
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="PR Tenant", slug="pr-tenant")
    user = User.objects.create(username="pr-user", email="pr@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="PR WS")
        ctx = AuthContext(user_id=user.id, tenant_id=tenant.id, active_roles=("admin",))
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()


def _publish_config(tenant_id, name, value, workspace_id=None):
    return publish_new_variable_version(
        tenant_id=tenant_id,
        name=name,
        kind="config",
        var_type="int",
        description="test cap",
        default_value=value,
        workspace_id=workspace_id,
    )


def test_extract_placeholders_ignores_json_braces():
    content = 'Use {max_breadth}. Respond with {"title": "x"} only.'

    assert extract_placeholders(content) == ["max_breadth"]


def test_render_template_leaves_unknown_placeholders_untouched():
    assert render_template("a {x} b {y}", x=1) == "a 1 b {y}"


def test_template_resolution_prefers_workspace_then_tenant_then_factory(ctx_workspace):
    ctx, workspace = ctx_workspace

    assert "stakeholder need" in resolve_template_content(
        "need_to_sysreq", ctx, workspace.id
    )

    publish_new_version(tenant_id=ctx.tenant_id, name="need_to_sysreq", content="TENANT")
    assert resolve_template_content("need_to_sysreq", ctx, workspace.id) == "TENANT"

    publish_new_version(
        tenant_id=ctx.tenant_id,
        name="need_to_sysreq",
        content="WORKSPACE",
        workspace_id=workspace.id,
    )
    assert resolve_template_content("need_to_sysreq", ctx, workspace.id) == "WORKSPACE"
    assert resolve_template_content("need_to_sysreq", ctx, None) == "TENANT"


def test_unknown_slot_raises_instead_of_returning_an_empty_string(ctx_workspace):
    ctx, workspace = ctx_workspace

    with pytest.raises(PromptSlotNotFoundError):
        resolve_template_content("no_such_slot", ctx, workspace.id)


def test_try_resolve_returns_none_for_an_unknown_slot(ctx_workspace):
    ctx, workspace = ctx_workspace

    assert try_resolve_template_content("no_such_slot", ctx, workspace.id) is None


def test_config_values_fall_back_to_the_factory_registry(ctx_workspace, monkeypatch):
    from application import prompt_variables

    monkeypatch.setitem(
        prompt_variables.PROMPT_VARIABLE_DEFAULTS,
        "max_breadth",
        prompt_variables.PromptVariableSpec(
            name="max_breadth",
            kind="config",
            var_type="int",
            description="cap",
            default_value=5,
        ),
    )
    ctx, workspace = ctx_workspace

    assert resolve_config_values(ctx, workspace.id)["max_breadth"] == 5


def test_config_values_prefer_workspace_over_tenant_over_factory(ctx_workspace):
    ctx, workspace = ctx_workspace
    _publish_config(ctx.tenant_id, "max_breadth", "4")
    assert resolve_config_values(ctx, workspace.id)["max_breadth"] == 4

    _publish_config(ctx.tenant_id, "max_breadth", "7", workspace_id=workspace.id)
    assert resolve_config_values(ctx, workspace.id)["max_breadth"] == 7
    assert resolve_config_values(ctx, None)["max_breadth"] == 4


def test_explicit_override_wins_over_every_stored_scope(ctx_workspace):
    ctx, workspace = ctx_workspace
    _publish_config(ctx.tenant_id, "max_breadth", "4")
    _publish_config(ctx.tenant_id, "max_breadth", "7", workspace_id=workspace.id)

    values = resolve_config_values(ctx, workspace.id, overrides={"max_breadth": 2})

    assert values["max_breadth"] == 2


def test_none_valued_override_is_ignored(ctx_workspace):
    """A caller forwarding an omitted optional parameter must not blank a value."""
    ctx, workspace = ctx_workspace
    _publish_config(ctx.tenant_id, "max_breadth", "4")

    values = resolve_config_values(ctx, workspace.id, overrides={"max_breadth": None})

    assert values["max_breadth"] == 4


def test_data_kind_rows_are_never_injected_as_config(ctx_workspace):
    ctx, workspace = ctx_workspace
    publish_new_variable_version(
        tenant_id=ctx.tenant_id,
        name="req_title",
        kind="data",
        var_type="str",
        description="code-bound",
        default_value='"leak"',
    )

    assert "req_title" not in resolve_config_values(ctx, workspace.id)


def test_resolve_and_render_injects_config_and_data(ctx_workspace):
    ctx, workspace = ctx_workspace
    publish_new_version(
        tenant_id=ctx.tenant_id,
        name="need_to_sysreq",
        content="cap={max_breadth} title={need_title}",
    )
    _publish_config(ctx.tenant_id, "max_breadth", "6")

    rendered = resolve_and_render("need_to_sysreq", ctx, workspace.id, need_title="Login")

    assert rendered == "cap=6 title=Login"


def test_data_kwargs_win_over_a_config_name_collision(ctx_workspace):
    ctx, workspace = ctx_workspace
    publish_new_version(
        tenant_id=ctx.tenant_id, name="need_to_sysreq", content="v={max_breadth}"
    )
    _publish_config(ctx.tenant_id, "max_breadth", "6")

    rendered = resolve_and_render("need_to_sysreq", ctx, workspace.id, max_breadth="DATA")

    assert rendered == "v=DATA"


def test_unknown_placeholders_reports_only_undeclared_names(ctx_workspace):
    ctx, workspace = ctx_workspace
    _publish_config(ctx.tenant_id, "max_breadth", "6")

    unknown = unknown_placeholders(
        "{need_title} {max_breadth} {typoo}", "need_to_sysreq", ctx, workspace.id
    )

    assert unknown == ["typoo"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_prompt_resolver.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'application.prompt_resolver'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/prompt_resolver.py`:

```python
"""The single prompt resolution + render path (spec §3.3).

Replaces three independently written fallback chains that each implemented
"workspace override -> tenant-global row -> factory default" separately:

  * ``AiDerivationService._get_template_content`` + ``_render``
  * ``mcp_server/tools/prompt_template.py::_handle_get``
  * ``application/interview_protocol.py::get_protocol``

On top of that single chain it adds what the catalog feature needs: every
``config`` variable resolved for the active tenant/workspace is injected into
each render call automatically, so an admin can reference a newly created
``config`` variable from any prompt body without a code change.

Resolution order per config variable (mirrors the LLM-provider config chain
in ``llm_adapter/providers.py``):
    explicit call parameter > workspace row > tenant row > factory default.

``render_template`` keeps ``AiDerivationService._render``'s exact semantics —
a per-placeholder ``str.replace`` loop, never ``str.format``/Jinja2 — so JSON
braces inside a customised prompt body survive untouched and an omitted
placeholder is left literally in place (REQ-046).

req_id: REQ-L2-PT-001
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from persistence.models import PROMPT_VARIABLE_KIND_CONFIG

from application.base import ValidationError
from application.prompt_slots import get_slot_data_variables, get_slot_default
from application.prompt_template_versioning import get_active_template
from application.prompt_variable_versioning import list_active_variables
from application.prompt_variables import (
    PROMPT_VARIABLE_DEFAULTS,
    VariableTypeError,
    deserialize_variable_value,
)

#: Matches ``{name}`` placeholders only — a JSON object like ``{"a": 1}`` has
#: a quote directly after the brace and therefore never matches.
PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_.]*)\}")


class PromptSlotNotFoundError(ValidationError):
    """Raised when a slot has neither an active row nor a factory default."""


def _as_uuid(workspace_id: UUID | str | None) -> Optional[UUID]:
    """Coerce a workspace id to ``UUID``; ``None`` stays ``None``."""
    if workspace_id is None:
        return None
    if isinstance(workspace_id, UUID):
        return workspace_id
    return UUID(str(workspace_id))


def extract_placeholders(content: str) -> List[str]:
    """Return every ``{name}`` placeholder in *content*, in first-seen order."""
    seen: List[str] = []
    for match in PLACEHOLDER_PATTERN.finditer(content or ""):
        name = match.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def render_template(content: str, **values: Any) -> str:
    """Substitute ``{name}`` placeholders without touching other braces."""
    rendered = content
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


def try_resolve_template_content(
    slot_name: str, ctx: AuthContext, workspace_id: UUID | str | None = None
) -> Optional[str]:
    """Return the effective body for *slot_name*, or ``None`` if there is none.

    Chain, most specific first: active workspace row (only consulted when
    *workspace_id* is given) -> active tenant-wide row -> factory default.
    """
    scope = _as_uuid(workspace_id)
    if scope is not None:
        row = get_active_template(
            tenant_id=ctx.tenant_id, name=slot_name, workspace_id=scope
        )
        if row is not None:
            return row.content
    row = get_active_template(tenant_id=ctx.tenant_id, name=slot_name, workspace_id=None)
    if row is not None:
        return row.content
    return get_slot_default(slot_name)


def resolve_template_content(
    slot_name: str, ctx: AuthContext, workspace_id: UUID | str | None = None
) -> str:
    """Like :func:`try_resolve_template_content`, but fails loudly.

    Raises:
        PromptSlotNotFoundError: No active row and no factory default — a
            clear error beats silently rendering an empty prompt (spec §8).
    """
    content = try_resolve_template_content(slot_name, ctx, workspace_id)
    if content is None:
        raise PromptSlotNotFoundError(
            f"No prompt template named {slot_name!r} exists for this tenant, "
            "and it is not a factory-default slot."
        )
    return content


def resolve_config_values(
    ctx: AuthContext,
    workspace_id: UUID | str | None = None,
    *,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return every ``config`` variable resolved for this tenant/workspace.

    Args:
        ctx:          Caller's auth context (supplies the tenant).
        workspace_id: Workspace whose overrides apply, or ``None``.
        overrides:    Explicit per-call values (e.g. an MCP tool parameter)
                      that outrank every stored scope. Entries whose value is
                      ``None`` are ignored, so a caller can forward an omitted
                      optional parameter without blanking the stored value.

    Returns:
        ``{variable_name: typed_value}``. ``data``-kind entries are never
        included — their values come from the calling code, not the catalog.
    """
    scope = _as_uuid(workspace_id)
    values: Dict[str, Any] = {
        name: spec.default_value
        for name, spec in PROMPT_VARIABLE_DEFAULTS.items()
        if spec.kind == PROMPT_VARIABLE_KIND_CONFIG
    }

    rows = list_active_variables(tenant_id=ctx.tenant_id)
    tenant_rows = [r for r in rows if r.workspace_id is None]
    workspace_rows = (
        [r for r in rows if r.workspace_id == scope] if scope is not None else []
    )
    for row in (*tenant_rows, *workspace_rows):
        if row.kind != PROMPT_VARIABLE_KIND_CONFIG:
            continue
        try:
            values[row.name] = deserialize_variable_value(row.var_type, row.default_value)
        except VariableTypeError:
            # A malformed stored value must not break every render call —
            # fall through to whatever the lower precedence level supplied.
            continue

    for name, value in (overrides or {}).items():
        if value is not None:
            values[name] = value
    return values


def resolve_and_render(
    slot_name: str,
    ctx: AuthContext,
    workspace_id: UUID | str | None = None,
    *,
    config_overrides: Optional[Dict[str, Any]] = None,
    **data_kwargs: Any,
) -> str:
    """Resolve *slot_name*'s body and render it with config + data values.

    ``data_kwargs`` win on a name collision with a ``config`` variable — the
    code-supplied artifact data is always the more specific answer.

    Raises:
        PromptSlotNotFoundError: See :func:`resolve_template_content`.
    """
    content = resolve_template_content(slot_name, ctx, workspace_id)
    config_values = resolve_config_values(ctx, workspace_id, overrides=config_overrides)
    return render_template(content, **{**config_values, **data_kwargs})


def unknown_placeholders(
    content: str,
    slot_name: str,
    ctx: AuthContext,
    workspace_id: UUID | str | None = None,
) -> List[str]:
    """Return placeholders in *content* that nothing can ever fill.

    A name counts as known when it is a declared ``data`` variable of
    *slot_name* or a resolvable ``config`` variable. Everything else is
    almost certainly a typo (spec §5) — reported, never blocking.
    """
    known = set(get_slot_data_variables(slot_name))
    known.update(resolve_config_values(ctx, workspace_id))
    return [name for name in extract_placeholders(content) if name not in known]


__all__ = [
    "PLACEHOLDER_PATTERN",
    "PromptSlotNotFoundError",
    "extract_placeholders",
    "render_template",
    "resolve_and_render",
    "resolve_config_values",
    "resolve_template_content",
    "try_resolve_template_content",
    "unknown_placeholders",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_prompt_resolver.py -q`

Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/prompt_resolver.py backend/application/tests/test_prompt_resolver.py
git commit -m "feat: add shared prompt resolver with config auto-injection"
```

---

### Task 6: PromptVariableService (Layer 2 facade)

**Files:**
- Create: `backend/application/prompt_variable_service.py`
- Test: `backend/application/tests/test_prompt_variable_service.py`

**Interfaces:**
- Consumes: Task 2 (`PROMPT_VARIABLE_DEFAULTS`, `PromptVariableSpec`, `serialize_variable_value`, `deserialize_variable_value`, `VariableTypeError`), Task 3 (all four versioning helpers), `ServiceBase`, `NotFoundError`, `ValidationError` (`application.base`, existing).
- Produces:
  - `class PromptVariableService(ServiceBase)`
    - `list_variables(ctx: AuthContext, *, workspace_id: UUID | None = None) -> list[dict[str, Any]]`
    - `get_variable(ctx: AuthContext, name: str, *, workspace_id: UUID | None = None) -> dict[str, Any]`
    - `set_variable(ctx: AuthContext, *, name: str, value: Any, workspace_id: UUID | None = None, var_type: str | None = None, description: str | None = None) -> dict[str, Any]`
    - `clear_variable(ctx: AuthContext, *, name: str, workspace_id: UUID | None = None) -> dict[str, Any]`
- Wire format of one variable state dict (used verbatim by REST, MCP and the frontend):
  `{"name", "kind", "var_type", "description", "factory_default", "global_value", "global_version", "workspace_value", "workspace_version", "has_workspace_override", "effective_value", "effective_scope", "is_editable"}`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_prompt_variable_service.py`:

```python
"""PromptVariableService — catalog CRUD + wire format (spec §3.1)."""
from __future__ import annotations

import pytest

from application.base import NotFoundError, ValidationError
from application.prompt_variable_service import PromptVariableService
from application.prompt_variables import PROMPT_VARIABLE_DEFAULTS, PromptVariableSpec
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="PVS Tenant", slug="pvs-tenant")
    user = User.objects.create(username="pvs-user", email="pvs@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="PVS WS")
        ctx = AuthContext(user_id=user.id, tenant_id=tenant.id, active_roles=("admin",))
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def factory_cap(monkeypatch):
    monkeypatch.setitem(
        PROMPT_VARIABLE_DEFAULTS,
        "max_breadth",
        PromptVariableSpec(
            name="max_breadth",
            kind="config",
            var_type="int",
            description="Max child elements per level.",
            default_value=5,
        ),
    )


def test_list_includes_factory_entries_with_factory_scope(ctx_workspace, factory_cap):
    ctx, workspace = ctx_workspace

    entry = next(
        v
        for v in PromptVariableService().list_variables(ctx, workspace_id=workspace.id)
        if v["name"] == "max_breadth"
    )

    assert entry["kind"] == "config"
    assert entry["factory_default"] == 5
    assert entry["effective_value"] == 5
    assert entry["effective_scope"] == "factory"
    assert entry["is_editable"] is True


def test_data_variables_are_listed_read_only(ctx_workspace):
    ctx, workspace = ctx_workspace

    entry = next(
        v
        for v in PromptVariableService().list_variables(ctx, workspace_id=workspace.id)
        if v["name"] == "req_title"
    )

    assert entry["kind"] == "data"
    assert entry["is_editable"] is False


def test_set_variable_publishes_a_tenant_default(ctx_workspace, factory_cap):
    ctx, _ws = ctx_workspace

    state = PromptVariableService().set_variable(ctx, name="max_breadth", value=8)

    assert state["global_value"] == 8
    assert state["global_version"] == 1
    assert state["effective_value"] == 8
    assert state["effective_scope"] == "global"


def test_set_variable_publishes_a_workspace_override(ctx_workspace, factory_cap):
    ctx, workspace = ctx_workspace
    svc = PromptVariableService()
    svc.set_variable(ctx, name="max_breadth", value=8)

    state = svc.set_variable(ctx, name="max_breadth", value=2, workspace_id=workspace.id)

    assert state["workspace_value"] == 2
    assert state["has_workspace_override"] is True
    assert state["effective_value"] == 2
    assert state["effective_scope"] == "workspace"


def test_clear_variable_falls_back_to_the_next_scope(ctx_workspace, factory_cap):
    ctx, workspace = ctx_workspace
    svc = PromptVariableService()
    svc.set_variable(ctx, name="max_breadth", value=8)
    svc.set_variable(ctx, name="max_breadth", value=2, workspace_id=workspace.id)

    state = svc.clear_variable(ctx, name="max_breadth", workspace_id=workspace.id)

    assert state["has_workspace_override"] is False
    assert state["effective_value"] == 8
    assert state["effective_scope"] == "global"


def test_a_brand_new_config_variable_needs_no_factory_entry(ctx_workspace):
    ctx, workspace = ctx_workspace

    state = PromptVariableService().set_variable(
        ctx,
        name="review_depth_hint",
        value="be thorough",
        var_type="str",
        description="Extra instruction appended by admins.",
    )

    assert state["factory_default"] is None
    assert state["var_type"] == "str"
    assert state["effective_value"] == "be thorough"
    names = [
        v["name"]
        for v in PromptVariableService().list_variables(ctx, workspace_id=workspace.id)
    ]
    assert "review_depth_hint" in names


def test_setting_a_data_variable_is_rejected(ctx_workspace):
    ctx, _ws = ctx_workspace

    with pytest.raises(ValidationError):
        PromptVariableService().set_variable(ctx, name="req_title", value="nope")


def test_setting_a_wrongly_typed_value_is_rejected(ctx_workspace, factory_cap):
    ctx, _ws = ctx_workspace

    with pytest.raises(ValidationError):
        PromptVariableService().set_variable(ctx, name="max_breadth", value="five")


def test_get_variable_raises_for_an_unknown_name(ctx_workspace):
    ctx, workspace = ctx_workspace

    with pytest.raises(NotFoundError):
        PromptVariableService().get_variable(
            ctx, "does_not_exist", workspace_id=workspace.id
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_prompt_variable_service.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'application.prompt_variable_service'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/prompt_variable_service.py`:

```python
"""COMP-AS-PV PromptVariableService — prompt variable catalog (spec §3.1).

Single entry point (ADR-01) for everything REST, MCP and the admin UI need
from the catalog: listing every variable with its per-scope state, publishing
a tenant-wide or workspace-scoped override, and dropping an override again.

The wire dict this service returns is deliberately shaped like
``SettingsService._build_slot_state``'s prompt-slot dict — same
``*_value``/``*_version``/``has_workspace_override``/``effective_*``
vocabulary — so the frontend can reuse the origin-badge pattern it already
renders for prompt slots.

``kind="data"`` rows are catalog documentation only: they list read-only and
every write path rejects them, because their values are computed by the code
that builds the render call and nothing an admin types could reach them.

req_id: REQ-L2-PT-001
leaf_id: COMP-AS-PV
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from django.db import IntegrityError

from auth_tenancy.context import AuthContext
from persistence.models import (
    PROMPT_VARIABLE_KIND_CONFIG,
    PROMPT_VARIABLE_KIND_DATA,
    PROMPT_VARIABLE_TYPES,
    PromptVariable,
)

from application.base import NotFoundError, ServiceBase, ValidationError
from application.prompt_variable_versioning import (
    deactivate_variable_scope,
    get_active_variable,
    list_active_variables,
    publish_new_variable_version,
)
from application.prompt_variables import (
    PROMPT_VARIABLE_DEFAULTS,
    PromptVariableSpec,
    VariableTypeError,
    deserialize_variable_value,
    serialize_variable_value,
)


def _row_value(row: PromptVariable) -> Any:
    """Deserialise a row's stored value, tolerating a malformed body."""
    try:
        return deserialize_variable_value(row.var_type, row.default_value)
    except VariableTypeError:
        return row.default_value


class PromptVariableService(ServiceBase):
    """Layer-2 facade over the ``PromptVariable`` catalog."""

    @staticmethod
    def _build_state(
        name: str,
        *,
        spec: Optional[PromptVariableSpec],
        global_row: Optional[PromptVariable],
        workspace_row: Optional[PromptVariable],
    ) -> Dict[str, Any]:
        """Resolve one variable's per-scope rows into the wire representation.

        Precedence mirrors ``application.prompt_resolver.resolve_config_values``
        exactly: workspace row > tenant row > factory registry.
        """
        reference = workspace_row or global_row
        if spec is not None:
            kind = spec.kind
            var_type = spec.var_type
            description = spec.description
            factory_default = spec.default_value
        elif reference is not None:
            kind = reference.kind
            var_type = reference.var_type
            description = reference.description
            factory_default = None
        else:  # pragma: no cover — callers never build a state from nothing
            kind = PROMPT_VARIABLE_KIND_CONFIG
            var_type = "str"
            description = ""
            factory_default = None

        if workspace_row is not None:
            effective, scope = _row_value(workspace_row), "workspace"
        elif global_row is not None:
            effective, scope = _row_value(global_row), "global"
        else:
            effective, scope = factory_default, "factory"

        return {
            "name": name,
            "kind": kind,
            "var_type": var_type,
            "description": description,
            "factory_default": factory_default,
            "global_value": _row_value(global_row) if global_row else None,
            "global_version": global_row.version if global_row else None,
            "workspace_value": _row_value(workspace_row) if workspace_row else None,
            "workspace_version": workspace_row.version if workspace_row else None,
            "has_workspace_override": workspace_row is not None,
            "effective_value": effective,
            "effective_scope": scope,
            "is_editable": kind == PROMPT_VARIABLE_KIND_CONFIG,
        }

    def list_variables(
        self, ctx: AuthContext, *, workspace_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """Return every catalog variable with its per-scope state, name-sorted.

        The result is the union of the factory registry and every name that
        already has an active row for this tenant — a ``config`` variable
        invented at runtime would otherwise be invisible to the UI that
        created it.
        """
        self._set_tenant_context(ctx)
        # One query for all active rows, resolved in memory: per-name lookups
        # would be 2 queries x variable count for a page rendering all of them.
        rows = list_active_variables(tenant_id=ctx.tenant_id)
        global_rows = {r.name: r for r in rows if r.workspace_id is None}
        workspace_rows = (
            {r.name: r for r in rows if r.workspace_id == workspace_id}
            if workspace_id is not None
            else {}
        )
        names = set(PROMPT_VARIABLE_DEFAULTS) | {r.name for r in rows}
        return [
            self._build_state(
                name,
                spec=PROMPT_VARIABLE_DEFAULTS.get(name),
                global_row=global_rows.get(name),
                workspace_row=workspace_rows.get(name),
            )
            for name in sorted(names)
        ]

    def _state(
        self, ctx: AuthContext, name: str, *, workspace_id: Optional[UUID]
    ) -> Dict[str, Any]:
        """Fetch one variable's rows and resolve them (single-name read path)."""
        return self._build_state(
            name,
            spec=PROMPT_VARIABLE_DEFAULTS.get(name),
            global_row=get_active_variable(
                tenant_id=ctx.tenant_id, name=name, workspace_id=None
            ),
            workspace_row=(
                get_active_variable(
                    tenant_id=ctx.tenant_id, name=name, workspace_id=workspace_id
                )
                if workspace_id is not None
                else None
            ),
        )

    def get_variable(
        self, ctx: AuthContext, name: str, *, workspace_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Return one variable's state.

        Raises:
            NotFoundError: The name is neither factory-registered nor backed
                by an active row — a clear error instead of a silent empty
                value (spec §8).
        """
        self._set_tenant_context(ctx)
        state = self._state(ctx, name, workspace_id=workspace_id)
        if (
            name not in PROMPT_VARIABLE_DEFAULTS
            and state["global_value"] is None
            and state["workspace_value"] is None
        ):
            raise NotFoundError(f"PromptVariable {name!r} not found for this tenant.")
        return state

    def set_variable(
        self,
        ctx: AuthContext,
        *,
        name: str,
        value: Any,
        workspace_id: Optional[UUID] = None,
        var_type: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Publish a new active version of *name* for the given scope.

        Args:
            ctx:          Caller's auth context.
            name:         Variable name (open-ended — a name with no factory
                          entry creates a brand-new ``config`` variable).
            value:        Typed value; validated against the effective
                          ``var_type``.
            workspace_id: Workspace to override for, or ``None`` for the
                          tenant-wide default.
            var_type:     Type for a name that has no factory entry yet
                          (defaults to ``"str"``); ignored for known names,
                          whose type is owned by the registry.
            description:  Documentation for a new variable.

        Raises:
            ValidationError: The name is a ``data`` variable, the declared
                type is unknown, the value does not match the type, or a
                concurrent writer published for the same scope first.
        """
        self._set_tenant_context(ctx)
        spec = PROMPT_VARIABLE_DEFAULTS.get(name)
        existing = get_active_variable(
            tenant_id=ctx.tenant_id, name=name, workspace_id=None
        ) or get_active_variable(
            tenant_id=ctx.tenant_id, name=name, workspace_id=workspace_id
        )

        if spec is not None:
            kind = spec.kind
            effective_type = spec.var_type
            effective_description = description or spec.description
        elif existing is not None:
            kind = existing.kind
            effective_type = existing.var_type
            effective_description = (
                description if description is not None else existing.description
            )
        else:
            kind = PROMPT_VARIABLE_KIND_CONFIG
            effective_type = var_type or "str"
            effective_description = description or ""

        if kind == PROMPT_VARIABLE_KIND_DATA:
            raise ValidationError(
                f"PromptVariable {name!r} is code-bound (kind='data'); its value "
                "is computed by the system and cannot be set."
            )
        if effective_type not in PROMPT_VARIABLE_TYPES:
            raise ValidationError(
                f"Unknown var_type {effective_type!r}; expected one of "
                f"{', '.join(PROMPT_VARIABLE_TYPES)}."
            )

        serialized = serialize_variable_value(value)
        try:
            deserialize_variable_value(effective_type, serialized)
        except VariableTypeError as exc:
            raise ValidationError(str(exc)) from exc

        try:
            publish_new_variable_version(
                tenant_id=ctx.tenant_id,
                name=name,
                kind=PROMPT_VARIABLE_KIND_CONFIG,
                var_type=effective_type,
                description=effective_description,
                default_value=serialized,
                workspace_id=workspace_id,
            )
        except IntegrityError as exc:
            raise ValidationError(
                f"Could not publish a new version for {name!r}: {exc}"
            ) from exc
        return self._state(ctx, name, workspace_id=workspace_id)

    def clear_variable(
        self, ctx: AuthContext, *, name: str, workspace_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Drop *name*'s active row at the given scope (idempotent).

        Clearing a workspace scope restores the tenant default; clearing the
        tenant scope restores the factory value. Rows are deactivated, never
        deleted, so the version history stays auditable.
        """
        self._set_tenant_context(ctx)
        deactivate_variable_scope(
            tenant_id=ctx.tenant_id, name=name, workspace_id=workspace_id
        )
        return self._state(ctx, name, workspace_id=workspace_id)


__all__ = ["PromptVariableService"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_prompt_variable_service.py -q`

Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/prompt_variable_service.py backend/application/tests/test_prompt_variable_service.py
git commit -m "feat: add PromptVariableService catalog facade"
```

---

### Task 7: Route AiDerivationService through the resolver + regression snapshot

**Files:**
- Modify: `backend/application/ai_derivation_service.py:1485-1531` (replace the bodies of `_get_template_content` and `_render`)
- Test: `backend/application/tests/test_prompt_render_regression.py`

**Interfaces:**
- Consumes: `resolve_template_content`, `render_template`, `resolve_and_render` (Task 5); `get_prompt_slots` (Task 4).
- Produces: unchanged public signatures — `AiDerivationService._get_template_content(ctx, name, workspace_id=None) -> str` and `AiDerivationService._render(template, **values) -> str` keep working for their 12 existing call sites (`ai_derivation_service` x7, `main_goal_service` x1, `bundle_compression_service` x2, `interview_service` x2), but now delegate to the single resolver.
- Additionally produces: `AiDerivationService._resolve_and_render(ctx, name, workspace_id=None, *, config_overrides=None, **data_kwargs) -> str` — the preferred call shape for flows that want config auto-injection.

**Design note:** the two staticmethods are kept as thin delegating wrappers rather than deleted. Deleting them would touch 12 call sites plus their tests in one commit for zero behavioural gain; keeping them means there is still exactly ONE implementation of the chain (in `prompt_resolver`), which is what spec §3.3 actually asks for.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_prompt_render_regression.py`:

```python
"""Regression snapshot: every shipped template renders unchanged (spec §7.1).

The catalog migration rewires how prompt bodies are resolved and rendered.
This pins the observable outcome: for every slot the product ships, rendering
the factory body with its declared data variables must produce byte-identical
output before and after the rewiring, and the resolver must agree with the
legacy ``AiDerivationService`` entry points on every slot.
"""
from __future__ import annotations

import pytest

from application.ai_derivation_service import AiDerivationService
from application.prompt_resolver import render_template, resolve_template_content
from application.prompt_slots import get_prompt_slots
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="RG Tenant", slug="rg-tenant")
    user = User.objects.create(username="rg-user", email="rg@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="RG WS")
        ctx = AuthContext(user_id=user.id, tenant_id=tenant.id, active_roles=("admin",))
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()


def _sample_values(spec) -> dict:
    """Deterministic placeholder values, one per declared data variable."""
    return {name: f"<{name}>" for name in spec.data_variables}


def test_every_shipped_slot_has_a_factory_body(ctx_workspace):
    ctx, workspace = ctx_workspace

    for name in get_prompt_slots():
        assert resolve_template_content(name, ctx, workspace.id)


def test_legacy_entry_point_agrees_with_the_resolver_on_every_slot(ctx_workspace):
    ctx, workspace = ctx_workspace

    for name in get_prompt_slots():
        assert AiDerivationService._get_template_content(
            ctx, name, workspace_id=workspace.id
        ) == resolve_template_content(name, ctx, workspace.id)


def test_rendering_every_slot_substitutes_all_declared_data_variables(ctx_workspace):
    ctx, workspace = ctx_workspace

    for name, spec in get_prompt_slots().items():
        values = _sample_values(spec)
        rendered = render_template(
            resolve_template_content(name, ctx, workspace.id), **values
        )
        for var in spec.data_variables:
            assert "{" + var + "}" not in rendered, f"{name} kept {var} unrendered"


def test_json_braces_in_a_body_survive_rendering(ctx_workspace):
    """The str.replace loop must never touch JSON braces (REQ-046)."""
    ctx, workspace = ctx_workspace

    rendered = render_template(
        'Return {"title": "x"} for {req_title}', req_title="Login"
    )

    assert rendered == 'Return {"title": "x"} for Login'


def test_legacy_render_matches_the_resolver_render():
    body = 'a {x} {"json": 1} {y}'

    assert AiDerivationService._render(body, x=1) == render_template(body, x=1)


def test_config_injection_does_not_alter_a_body_without_config_placeholders(
    ctx_workspace,
):
    """Auto-injection is additive: bodies that reference no config var are unchanged."""
    ctx, workspace = ctx_workspace
    svc = AiDerivationService()

    body = resolve_template_content("testcase_derive", ctx, workspace.id)
    legacy = svc._render(body, req_title="T", req_description="D")
    injected = svc._resolve_and_render(
        ctx, "testcase_derive", workspace.id, req_title="T", req_description="D"
    )

    assert injected == legacy
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_prompt_render_regression.py -q`

Expected: FAIL with `AttributeError: type object 'AiDerivationService' has no attribute '_resolve_and_render'`

- [ ] **Step 3: Write minimal implementation**

In `backend/application/ai_derivation_service.py`, replace the whole `_get_template_content` staticmethod (currently lines 1485-1519) and the `_render` staticmethod (currently lines 1521-1531) with:

```python
    @staticmethod
    def _get_template_content(
        ctx: AuthContext, name: str, workspace_id: "UUID | None" = None
    ) -> str:
        """Return the effective prompt content for *name* (REQ-L2-PT-001).

        Thin delegation to :func:`application.prompt_resolver.resolve_template_content`
        — the fallback chain (workspace override -> tenant-global row ->
        factory default) now has exactly one implementation, shared with the
        MCP ``prompt_template.get`` tool and ``interview_protocol.get_protocol``.

        Kept as a staticmethod rather than deleted because 12 call sites
        across four services address it; the behaviour is unchanged except
        that an unknown slot now raises
        :class:`~application.prompt_resolver.PromptSlotNotFoundError`
        (a ``ValidationError`` subclass) instead of a bare ``KeyError``.
        """
        from application.prompt_resolver import resolve_template_content

        return resolve_template_content(name, ctx, workspace_id)

    @staticmethod
    def _render(template: str, **values: Any) -> str:
        """Substitute ``{name}`` placeholders without touching other braces.

        Delegates to :func:`application.prompt_resolver.render_template`; a
        literal ``str.format`` call would choke on JSON braces embedded in a
        user-customised prompt, so placeholders are replaced individually.
        """
        from application.prompt_resolver import render_template

        return render_template(template, **values)

    @staticmethod
    def _resolve_and_render(
        ctx: AuthContext,
        name: str,
        workspace_id: "UUID | None" = None,
        *,
        config_overrides: "Dict[str, Any] | None" = None,
        **data_kwargs: Any,
    ) -> str:
        """Resolve *name* and render it with catalog config + data values.

        Preferred over the ``_get_template_content`` + ``_render`` pair for
        new flows: every ``config`` variable of the active tenant/workspace is
        injected automatically, so an admin-created variable becomes usable in
        this prompt without a code change (spec §3.2).
        """
        from application.prompt_resolver import resolve_and_render

        return resolve_and_render(
            name,
            ctx,
            workspace_id,
            config_overrides=config_overrides,
            **data_kwargs,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_prompt_render_regression.py -q`

Expected: PASS (6 passed)

- [ ] **Step 5: Verify the existing consumers still pass**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_ai_derivation_service.py application/tests/test_main_goal_service.py application/tests/test_bundle_compression_service.py application/tests/test_interview_service.py -q`

Expected: PASS (no new failures)

- [ ] **Step 6: Commit**

```bash
git add backend/application/ai_derivation_service.py backend/application/tests/test_prompt_render_regression.py
git commit -m "refactor: route AiDerivationService prompts through the resolver"
```

---

### Task 8: Route the MCP and interview read paths through the resolver

**Files:**
- Modify: `backend/mcp_server/tools/prompt_template.py:109-118` (drop `_ALL_FACTORY_DEFAULTS`), `backend/mcp_server/tools/prompt_template.py:247-283` (`_handle_get`)
- Modify: `backend/application/interview_protocol.py:142-186` (`get_protocol`)
- Test: `backend/application/tests/test_prompt_resolver_consumers.py`

**Interfaces:**
- Consumes: `try_resolve_template_content` (Task 5), `get_prompt_slots` (Task 4).
- Produces: no new public symbols. `prompt_template.get` keeps its `{"slot", "content"}` success payload and its `NOT_FOUND` error contract; `get_protocol(ctx, artifact_type, workspace_id) -> ProtocolConfig` keeps its signature.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_prompt_resolver_consumers.py`:

```python
"""The MCP + interview read paths resolve through the shared resolver."""
from __future__ import annotations

import pytest

from application.interview_protocol import get_protocol
from application.prompt_template_versioning import publish_new_version
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="PRC Tenant", slug="prc-tenant")
    user = User.objects.create(username="prc-user", email="prc@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="PRC WS")
        ctx = AuthContext(user_id=user.id, tenant_id=tenant.id, active_roles=("admin",))
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()


def test_mcp_get_reads_the_factory_default_for_a_known_slot(ctx_workspace):
    from mcp_server.tools.prompt_template import PromptTemplateToolGroup

    ctx, _ws = ctx_workspace

    result = PromptTemplateToolGroup()._handle_get(
        params={"slot": "testcase_derive"}, auth_context=ctx, api_key="k"
    )

    assert result.success is True
    assert "test engineer" in result.data["content"]


def test_mcp_get_prefers_a_workspace_override(ctx_workspace):
    from mcp_server.tools.prompt_template import PromptTemplateToolGroup

    ctx, workspace = ctx_workspace
    publish_new_version(
        tenant_id=ctx.tenant_id,
        name="testcase_derive",
        content="WS BODY",
        workspace_id=workspace.id,
    )

    result = PromptTemplateToolGroup()._handle_get(
        params={"slot": "testcase_derive", "workspace_id": str(workspace.id)},
        auth_context=ctx,
        api_key="k",
    )

    assert result.data["content"] == "WS BODY"


def test_mcp_get_reports_not_found_for_an_unknown_slot(ctx_workspace):
    from mcp_server.tools.prompt_template import PromptTemplateToolGroup

    ctx, _ws = ctx_workspace

    result = PromptTemplateToolGroup()._handle_get(
        params={"slot": "no_such_slot"}, auth_context=ctx, api_key="k"
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_mcp_get_resolves_an_interview_protocol_slot(ctx_workspace):
    from mcp_server.tools.prompt_template import PromptTemplateToolGroup

    ctx, _ws = ctx_workspace

    result = PromptTemplateToolGroup()._handle_get(
        params={"slot": "interview.protocol.Requirement"},
        auth_context=ctx,
        api_key="k",
    )

    assert result.success is True
    assert "phases" in result.data["content"]


def test_get_protocol_still_falls_back_to_the_factory_yaml(ctx_workspace):
    ctx, workspace = ctx_workspace

    protocol = get_protocol(ctx, "Requirement", workspace.id)

    assert protocol.phases


def test_get_protocol_prefers_a_workspace_override(ctx_workspace):
    ctx, workspace = ctx_workspace
    publish_new_version(
        tenant_id=ctx.tenant_id,
        name="interview.protocol.Requirement",
        content=(
            "phases:\n"
            "  - name: only_phase\n"
            '    prompt_fragment: "Ask everything at once."\n'
        ),
        workspace_id=workspace.id,
    )

    protocol = get_protocol(ctx, "Requirement", workspace.id)

    assert [p.name for p in protocol.phases] == ["only_phase"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_prompt_resolver_consumers.py -q`

Expected: PASS for the pre-existing behaviours but FAIL on `test_mcp_get_resolves_an_interview_protocol_slot` only after the refactor is wrong — run it first to record the green baseline, then keep it green through Step 3. (If any test fails here, the fixture's `AuthContext` construction is wrong; fix that before proceeding.)

- [ ] **Step 3: Write minimal implementation**

In `backend/mcp_server/tools/prompt_template.py`, delete the `_ALL_FACTORY_DEFAULTS` dict and its two registry imports (lines 84-91 and 109-118) and replace `_handle_get`'s body with:

```python
    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        slot = require_param(params, "slot")
        workspace_id = optional_uuid(params, "workspace_id")

        # Spec §3.3: the workspace-first / tenant-global / factory-default
        # precedence now lives in exactly one place
        # (application.prompt_resolver), shared with AiDerivationService and
        # interview_protocol.get_protocol — this tool no longer keeps its own
        # merged factory-default table.
        content = try_resolve_template_content(str(slot), auth_context, workspace_id)
        if content is not None:
            return ToolResult.ok({"slot": slot, "content": content})

        return ToolResult.error(
            "NOT_FOUND",
            f"No prompt template named '{slot}' exists for this tenant, and "
            "it is not one of the factory-default slots. Known "
            f"factory-default slots: {', '.join(sorted(get_prompt_slots()))}. "
            "Use prompt_template.create to define a new one.",
        )
```

Add these imports to the module's import block (keeping PEP 8 order — local imports after third-party):

```python
from application.interview_protocol import (
    ProtocolValidationError,
    parse_protocol_yaml,
)
from application.prompt_resolver import try_resolve_template_content
from application.prompt_slots import get_prompt_slots
```

In `backend/application/interview_protocol.py`, replace `get_protocol`'s body with:

```python
def get_protocol(ctx, artifact_type: str, workspace_id) -> ProtocolConfig:
    """Resolve the effective protocol for *artifact_type* in *workspace_id*.

    Delegates the workspace -> tenant-global -> factory-default chain to
    ``application.prompt_resolver.try_resolve_template_content`` (spec §3.3),
    then parses and validates the resolved YAML. ``try_``-flavoured because a
    missing protocol must surface as :class:`ProtocolValidationError` with an
    artifact-type-specific message, not as a generic slot error.

    Imported lazily: ``prompt_resolver`` imports ``prompt_slots``, which reads
    this module's ``INTERVIEW_PROTOCOL_DEFAULTS`` — a module-level import here
    would close that cycle at import time.
    """
    from application.prompt_resolver import try_resolve_template_content

    name = f"interview.protocol.{artifact_type}"
    content = try_resolve_template_content(name, ctx, workspace_id)
    if content is None:
        raise ProtocolValidationError(
            f"No interview protocol configured or defaulted for artifact_type={artifact_type!r}."
        )
    return parse_protocol_yaml(content)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_prompt_resolver_consumers.py application/tests/test_interview_protocol.py mcp_server/tests/test_prompt_template_tool_group.py -q`

Expected: PASS (all green)

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/tools/prompt_template.py backend/application/interview_protocol.py backend/application/tests/test_prompt_resolver_consumers.py
git commit -m "refactor: unify MCP and interview prompt reads on the resolver"
```

---

### Task 9: REST endpoints for the variable catalog

**Files:**
- Create: `backend/rest_api/prompt_variable_views.py`
- Modify: `backend/rest_api/urls.py:292-315` (add two routes next to the prompt-template slot routes)
- Test: `backend/rest_api/tests/test_prompt_variables.py`

**Interfaces:**
- Consumes: `PromptVariableService` (Task 6), `ROLE_ADMIN` (`auth_tenancy.models`, existing), `build_error_response` / `detect_lang` (`rest_api.serializers`, existing), `get_auth_context` (`rest_api.auth_enforcer`, existing).
- Produces:
  - `class PromptVariableWriteSerializer(serializers.Serializer)` with fields `value` (JSONField, required), `var_type` (CharField, optional), `description` (CharField, optional, blank allowed)
  - `class PromptVariableListView(APIView)` — `GET /api/v1/prompt-variables/[?workspace_id=<uuid>]` → `{"variables": [...], "count": int, "workspace_id": str | None}`
  - `class PromptVariableDetailView(APIView)` — `PUT`/`DELETE /api/v1/prompt-variables/<name>/[?workspace_id=<uuid>]` → one variable state dict
  - URL names `prompt-variables` and `prompt-variable-detail`

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_prompt_variables.py`:

```python
"""REST endpoints for the prompt variable catalog (spec §3.1, §5)."""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET="test-secret-not-a-real-key",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)

_LIST_URL = "/api/v1/prompt-variables/"


@pytest.fixture
def pv_ctx(db):
    tenant = Tenant.objects.create(name="PVR T", slug="pvr-t", is_active=True)
    admin = User.objects.create(username="pvradmin", email="pvradmin@t.test", tenant=tenant)
    admin.set_password("pvrpass123")
    admin.save(update_fields=["password"])
    editor = User.objects.create(username="pvreditor", email="pvreditor@t.test", tenant=tenant)
    editor.set_password("pvrpass123")
    editor.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="PVR WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        UserRole.objects.create(
            tenant=tenant, user=editor, workspace=workspace, role=ROLE_EDITOR
        )
        yield tenant, workspace
    finally:
        clear_request_tenant()


def _client(username: str = "pvradmin") -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": "pvrpass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


@override_settings(**_JWT_OVERRIDES)
def test_list_returns_the_catalog_with_kinds(pv_ctx):
    _tenant, workspace = pv_ctx

    resp = _client().get(f"{_LIST_URL}?workspace_id={workspace.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == len(body["variables"])
    kinds = {v["name"]: v["kind"] for v in body["variables"]}
    assert kinds["req_title"] == "data"


@override_settings(**_JWT_OVERRIDES)
def test_list_requires_admin(pv_ctx):
    resp = _client("pvreditor").get(_LIST_URL)

    assert resp.status_code == 403


@override_settings(**_JWT_OVERRIDES)
def test_put_publishes_a_workspace_override(pv_ctx):
    _tenant, workspace = pv_ctx

    resp = _client().put(
        f"{_LIST_URL}review_depth_hint/?workspace_id={workspace.id}",
        {"value": "be thorough", "var_type": "str", "description": "Extra hint."},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["workspace_value"] == "be thorough"
    assert body["effective_scope"] == "workspace"
    assert body["is_editable"] is True


@override_settings(**_JWT_OVERRIDES)
def test_put_rejects_a_data_variable(pv_ctx):
    resp = _client().put(
        f"{_LIST_URL}req_title/", {"value": "nope"}, format="json"
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


@override_settings(**_JWT_OVERRIDES)
def test_put_rejects_a_bad_workspace_id(pv_ctx):
    resp = _client().put(
        f"{_LIST_URL}review_depth_hint/?workspace_id=not-a-uuid",
        {"value": "x"},
        format="json",
    )

    assert resp.status_code == 400


@override_settings(**_JWT_OVERRIDES)
def test_delete_drops_the_override_and_returns_the_new_state(pv_ctx):
    _tenant, workspace = pv_ctx
    client = _client()
    client.put(
        f"{_LIST_URL}review_depth_hint/", {"value": "tenant", "var_type": "str"}, format="json"
    )
    client.put(
        f"{_LIST_URL}review_depth_hint/?workspace_id={workspace.id}",
        {"value": "ws"},
        format="json",
    )

    resp = client.delete(f"{_LIST_URL}review_depth_hint/?workspace_id={workspace.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["has_workspace_override"] is False
    assert body["effective_value"] == "tenant"


@override_settings(**_JWT_OVERRIDES)
def test_put_requires_admin(pv_ctx):
    resp = _client("pvreditor").put(
        f"{_LIST_URL}review_depth_hint/", {"value": "x"}, format="json"
    )

    assert resp.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest rest_api/tests/test_prompt_variables.py -q`

Expected: FAIL with 404 responses (the routes do not exist yet)

- [ ] **Step 3: Write minimal implementation**

Create `backend/rest_api/prompt_variable_views.py`:

```python
"""Prompt variable catalog REST endpoints (spec §3.1, §5).

Mirrors the prompt-template *slot* API (``rest_api/settings_views.py``,
issue #119) one-for-one — same admin gate, same ``?workspace_id=`` scope
parameter, same "PUT publishes, DELETE drops the override, both return the
now-effective state" contract — so the frontend can reuse its scope-switch
and origin-badge patterns unchanged.

  GET    /api/v1/prompt-variables/[?workspace_id=<uuid>]
  PUT    /api/v1/prompt-variables/<name>/[?workspace_id=<uuid>]
  DELETE /api/v1/prompt-variables/<name>/[?workspace_id=<uuid>]

``name`` is deliberately not validated against the factory registry: a PUT to
an unknown name is how a brand-new ``config`` variable is created (spec §3.2,
"einfach erweiterbar"). Writes to a ``kind="data"`` name are rejected by
``PromptVariableService.set_variable`` with a 400.

req_id: REQ-L2-PT-001
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import NotFoundError, ValidationError
from application.prompt_variable_service import PromptVariableService
from auth_tenancy.models import ROLE_ADMIN
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


class PromptVariableWriteSerializer(serializers.Serializer):
    """Body of PUT /prompt-variables/<name>/.

    ``value`` is a ``JSONField`` because a variable may be an int, string,
    bool or arbitrary JSON — the concrete type is validated against the
    variable's ``var_type`` inside the service, which owns that knowledge.
    """

    value = serializers.JSONField()
    var_type = serializers.CharField(required=False)
    description = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=False
    )


class _PromptVariableAdminMixin:
    """Shared admin gate + ``workspace_id`` query-param parsing."""

    def _forbidden(self, lang: str) -> Response:
        """Return the 403 body used by every prompt-variable endpoint."""
        return Response(
            build_error_response(
                "PERMISSION_DENIED",
                lang,
                message="Admin role required to access prompt variables.",
            ),
            status=status.HTTP_403_FORBIDDEN,
        )

    def _parse_workspace_id(self, request: Request) -> "UUID | None":
        """Return the ``?workspace_id=`` scope, or ``None`` for tenant-global.

        Raises:
            ValueError: The parameter was present but not a valid UUID.
        """
        raw = request.query_params.get("workspace_id")
        if raw in (None, ""):
            return None
        return UUID(raw)

    def _bad_workspace_id(self, lang: str) -> Response:
        """Return the 400 body for a malformed ``workspace_id``."""
        return Response(
            build_error_response(
                "VALIDATION_ERROR",
                lang,
                message="'workspace_id' must be a valid UUID.",
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )


class PromptVariableListView(_PromptVariableAdminMixin, APIView):
    """GET /api/v1/prompt-variables/[?workspace_id=<uuid>]."""

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return every catalog variable with its per-scope state."""
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)
        try:
            workspace_id = self._parse_workspace_id(request)
        except ValueError:
            return self._bad_workspace_id(lang)

        variables = PromptVariableService().list_variables(
            ctx, workspace_id=workspace_id
        )
        return Response(
            {
                "variables": variables,
                "count": len(variables),
                "workspace_id": str(workspace_id) if workspace_id else None,
            }
        )


class PromptVariableDetailView(_PromptVariableAdminMixin, APIView):
    """PUT/DELETE /api/v1/prompt-variables/<name>/[?workspace_id=<uuid>]."""

    def put(self, request: Request, name: str, *args: Any, **kwargs: Any) -> Response:
        """Publish a new active version of ``name`` for the requested scope."""
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)
        try:
            workspace_id = self._parse_workspace_id(request)
        except ValueError:
            return self._bad_workspace_id(lang)

        ser = PromptVariableWriteSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            state = PromptVariableService().set_variable(
                ctx,
                name=name,
                value=ser.validated_data["value"],
                workspace_id=workspace_id,
                var_type=ser.validated_data.get("var_type"),
                description=ser.validated_data.get("description"),
            )
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(state)

    def delete(
        self, request: Request, name: str, *args: Any, **kwargs: Any
    ) -> Response:
        """Drop ``name``'s override at the requested scope (idempotent)."""
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)
        try:
            workspace_id = self._parse_workspace_id(request)
        except ValueError:
            return self._bad_workspace_id(lang)

        try:
            state = PromptVariableService().clear_variable(
                ctx, name=name, workspace_id=workspace_id
            )
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        # 200 with the now-effective state rather than 204: the caller's next
        # question is always "so what applies now?", and the inherited value
        # is not derivable client-side without a second round trip.
        return Response(state)


__all__ = [
    "PromptVariableDetailView",
    "PromptVariableListView",
    "PromptVariableWriteSerializer",
]
```

In `backend/rest_api/urls.py`, add the import next to the other view-module imports:

```python
from rest_api.prompt_variable_views import (
    PromptVariableDetailView,
    PromptVariableListView,
)
```

and add these two routes directly after the `prompt-templates/` route (around line 315):

```python
    # Prompt variable catalog (spec §3.1) — admin-only, same scope semantics
    # as the prompt-template slot API above.
    path(
        "prompt-variables/",
        PromptVariableListView.as_view(),
        name="prompt-variables",
    ),
    path(
        "prompt-variables/<str:name>/",
        PromptVariableDetailView.as_view(),
        name="prompt-variable-detail",
    ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest rest_api/tests/test_prompt_variables.py -q`

Expected: PASS (7 passed)

- [ ] **Step 5: Verify the OpenAPI schema still builds**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test python manage.py spectacular --file /tmp/schema.yaml`

Expected: exit code 0 (warnings are acceptable, errors are not)

- [ ] **Step 6: Commit**

```bash
git add backend/rest_api/prompt_variable_views.py backend/rest_api/urls.py backend/rest_api/tests/test_prompt_variables.py
git commit -m "feat: expose prompt variable catalog over REST"
```

---

### Task 10: MCP tool group for the variable catalog

**Files:**
- Create: `backend/mcp_server/tools/prompt_variable.py`
- Modify: `backend/mcp_server/tool_registry.py:60-125` (add write-tool names), `backend/mcp_server/tool_registry.py:460-525` (register the group)
- Modify: `docs/agent-templates/tool-manifest.json` (regenerated artifact)
- Test: `backend/mcp_server/tests/test_prompt_variable_tool_group.py`

**Interfaces:**
- Consumes: `PromptVariableService` (Task 6), `BaseToolGroup`, `ToolResult`, `require_param`, `optional_uuid`, `write_mcp_audit` (`mcp_server.tools.base`, existing).
- Produces:
  - `class PromptVariableToolGroup(BaseToolGroup)` registered under the `prompt_variable` prefix, exposing `prompt_variable.list`, `prompt_variable.get`, `prompt_variable.set`, `prompt_variable.clear`.

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_prompt_variable_tool_group.py`:

```python
"""MCP prompt_variable tool group (spec §3.1)."""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="PVT Tenant", slug="pvt-tenant")
    user = User.objects.create(username="pvt-user", email="pvt@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="PVT WS")
        admin = AuthContext(
            user_id=user.id, tenant_id=tenant.id, active_roles=("admin",)
        )
        viewer = AuthContext(
            user_id=user.id, tenant_id=tenant.id, active_roles=("viewer",)
        )
        yield admin, viewer, workspace
    finally:
        TenantContext.clear_tenant()


def _group():
    from mcp_server.tools.prompt_variable import PromptVariableToolGroup

    return PromptVariableToolGroup()


def test_schema_declares_all_four_tools():
    names = {s["name"] for s in _group().get_tool_schemas()}

    assert names == {
        "prompt_variable.list",
        "prompt_variable.get",
        "prompt_variable.set",
        "prompt_variable.clear",
    }


def test_list_returns_the_catalog(ctx_workspace):
    admin, _viewer, workspace = ctx_workspace

    result = _group()._handle_list(
        params={"workspace_id": str(workspace.id)}, auth_context=admin, api_key="k"
    )

    assert result.success is True
    assert result.data["count"] == len(result.data["variables"])


def test_set_creates_a_new_config_variable(ctx_workspace):
    admin, _viewer, _ws = ctx_workspace

    result = _group()._handle_set(
        params={"name": "review_depth_hint", "value": "be thorough", "var_type": "str"},
        auth_context=admin,
        api_key="k",
    )

    assert result.success is True
    assert result.data["variable"]["effective_value"] == "be thorough"


def test_set_is_admin_gated(ctx_workspace):
    _admin, viewer, _ws = ctx_workspace

    result = _group()._handle_set(
        params={"name": "review_depth_hint", "value": "x"},
        auth_context=viewer,
        api_key="k",
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


def test_set_rejects_a_data_variable(ctx_workspace):
    admin, _viewer, _ws = ctx_workspace

    result = _group()._handle_set(
        params={"name": "req_title", "value": "nope"}, auth_context=admin, api_key="k"
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_get_reports_not_found_for_an_unknown_name(ctx_workspace):
    admin, _viewer, _ws = ctx_workspace

    result = _group()._handle_get(
        params={"name": "does_not_exist"}, auth_context=admin, api_key="k"
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_clear_returns_the_now_effective_state(ctx_workspace):
    admin, _viewer, workspace = ctx_workspace
    group = _group()
    group._handle_set(
        params={"name": "review_depth_hint", "value": "tenant", "var_type": "str"},
        auth_context=admin,
        api_key="k",
    )
    group._handle_set(
        params={
            "name": "review_depth_hint",
            "value": "ws",
            "workspace_id": str(workspace.id),
        },
        auth_context=admin,
        api_key="k",
    )

    result = group._handle_clear(
        params={"name": "review_depth_hint", "workspace_id": str(workspace.id)},
        auth_context=admin,
        api_key="k",
    )

    assert result.data["variable"]["effective_value"] == "tenant"


def test_write_tools_are_registered_as_writes():
    from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

    assert "prompt_variable.set" in _WRITE_TOOL_PREFIXES
    assert "prompt_variable.clear" in _WRITE_TOOL_PREFIXES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest mcp_server/tests/test_prompt_variable_tool_group.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_server.tools.prompt_variable'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/mcp_server/tools/prompt_variable.py`:

```python
"""MCP tool group for the prompt variable catalog (spec §3.1).

leaf_id : COMP-MC-PV
req_id  : REQ-L2-PT-001 (tenant-scoped editable prompt configuration),
          REQ-L2-MC-012 (MCP audit trail for write tools)

Exposes four tools, all admin-gated (mirroring the ``prompt_template`` group's
``_check_admin``: without it any valid API key could rewrite the numeric caps
that bound every AI derivation, a prompt-injection-adjacent vector):

  prompt_variable.list(workspace_id?) -> {variables, count}
  prompt_variable.get(name, workspace_id?) -> {variable}
  prompt_variable.set(name, value, workspace_id?, var_type?, description?)
  prompt_variable.clear(name, workspace_id?) -> {variable}

``.set`` on a ``kind="data"`` name is refused with VALIDATION_ERROR — those
values are computed from artifact data by the code that builds the render
call, so there is nothing an agent could meaningfully store. ``.set`` on an
unknown name creates a new ``config`` variable, which is the point of the
catalog: a prompt body can reference ``{new_name}`` immediately afterwards
with no code change.

All reads are admin-gated too (not just writes): the catalog carries free-text
descriptions of a tenant's AI configuration.
"""
from __future__ import annotations

from typing import Any, Dict

from application.base import NotFoundError, ValidationError
from application.prompt_variable_service import PromptVariableService
from auth_tenancy.context import AuthContext

from mcp_server.tools.base import (
    BaseToolGroup,
    ToolResult,
    optional_uuid,
    require_param,
    write_mcp_audit,
)


class PromptVariableToolGroup(BaseToolGroup):
    """Prompt variable catalog tool group (read + write, tenant-scoped)."""

    _TOOL_MAP = {
        "prompt_variable.list": "_handle_list",
        "prompt_variable.get": "_handle_get",
        "prompt_variable.set": "_handle_set",
        "prompt_variable.clear": "_handle_clear",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "prompt_variable.list",
            "description": (
                "List every prompt variable in the catalog with its factory, "
                "tenant and workspace value plus the resolved effective value "
                "and its origin. kind='config' entries are editable; "
                "kind='data' entries are code-bound documentation."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "Optional workspace scope whose overrides to resolve.",
                    },
                },
            },
        },
        {
            "name": "prompt_variable.get",
            "description": (
                "Return one prompt variable's per-scope state and resolved "
                "effective value. NOT_FOUND when the name is neither "
                "factory-registered nor stored for this tenant."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Variable name."},
                    "workspace_id": {
                        "type": "string",
                        "description": "Optional workspace scope whose override to resolve.",
                    },
                },
                "required": ["name"],
            },
        },
        {
            "name": "prompt_variable.set",
            "description": (
                "Publish a new active version of a config prompt variable for "
                "a (tenant, workspace_id, name) scope. Omitting workspace_id "
                "writes the tenant-wide default. An unknown name creates a new "
                "config variable usable in any prompt body immediately. "
                "kind='data' names are rejected (write, audited, admin-only)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Variable name."},
                    "value": {
                        "description": "New value; must match the variable's var_type.",
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": "Optional workspace scope. Omit for the tenant default.",
                    },
                    "var_type": {
                        "type": "string",
                        "description": (
                            "int | str | bool | json — only used when creating a "
                            "name that has no factory entry yet (default 'str')."
                        ),
                    },
                    "description": {
                        "type": "string",
                        "description": "Documentation shown in the catalog UI.",
                    },
                },
                "required": ["name", "value"],
            },
        },
        {
            "name": "prompt_variable.clear",
            "description": (
                "Drop a prompt variable's active row at the given scope so it "
                "falls back to the next level (workspace -> tenant -> factory). "
                "Idempotent; returns the now-effective state "
                "(write, audited, admin-only)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Variable name."},
                    "workspace_id": {
                        "type": "string",
                        "description": "Optional workspace scope whose override to drop.",
                    },
                },
                "required": ["name"],
            },
        },
    ]

    @staticmethod
    def _check_admin(auth_context: AuthContext) -> "ToolResult | None":
        """Return a ``PERMISSION_DENIED`` ToolResult if the caller is not admin."""
        if auth_context.has_role("admin"):
            return None
        return ToolResult.error(
            "PERMISSION_DENIED",
            f"Permission denied: role 'admin' required, "
            f"user has {auth_context.active_roles}",
        )

    def _handle_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        denied = self._check_admin(auth_context)
        if denied is not None:
            return denied
        workspace_id = optional_uuid(params, "workspace_id")
        variables = PromptVariableService().list_variables(
            auth_context, workspace_id=workspace_id
        )
        return ToolResult.ok({"variables": variables, "count": len(variables)})

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        denied = self._check_admin(auth_context)
        if denied is not None:
            return denied
        name = require_param(params, "name")
        workspace_id = optional_uuid(params, "workspace_id")
        try:
            variable = PromptVariableService().get_variable(
                auth_context, str(name), workspace_id=workspace_id
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok({"variable": variable})

    def _handle_set(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        denied = self._check_admin(auth_context)
        if denied is not None:
            return denied
        name = require_param(params, "name")
        if "value" not in params:
            return ToolResult.error(
                "VALIDATION_ERROR", "Required parameter 'value' is missing."
            )
        workspace_id = optional_uuid(params, "workspace_id")
        try:
            variable = PromptVariableService().set_variable(
                auth_context,
                name=str(name),
                value=params["value"],
                workspace_id=workspace_id,
                var_type=params.get("var_type"),
                description=params.get("description"),
            )
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="update",
            entity_type="PromptVariable",
            entity_id=auth_context.tenant_id,
            tool_name="prompt_variable.set",
            api_key=api_key,
            details={"name": str(name)},
        )
        return ToolResult.ok({"variable": variable})

    def _handle_clear(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        denied = self._check_admin(auth_context)
        if denied is not None:
            return denied
        name = require_param(params, "name")
        workspace_id = optional_uuid(params, "workspace_id")
        variable = PromptVariableService().clear_variable(
            auth_context, name=str(name), workspace_id=workspace_id
        )
        write_mcp_audit(
            ctx=auth_context,
            operation="delete",
            entity_type="PromptVariable",
            entity_id=auth_context.tenant_id,
            tool_name="prompt_variable.clear",
            api_key=api_key,
            details={"name": str(name)},
        )
        return ToolResult.ok({"variable": variable})


__all__ = ["PromptVariableToolGroup"]
```

In `backend/mcp_server/tool_registry.py`, add to `_WRITE_TOOL_PREFIXES` right after the `prompt_template.*` entries:

```python
    "prompt_variable.set",
    "prompt_variable.clear",
```

add `"prompt_variable.list"` and `"prompt_variable.get"` to the `_READ_ONLY_TOOL_NAMES` frozenset (next to the other read-only names), add the import next to `from mcp_server.tools.prompt_template import PromptTemplateToolGroup`:

```python
        from mcp_server.tools.prompt_variable import PromptVariableToolGroup
```

and add the registration entry inside the `self.register_groups({...})` call, right after `"prompt_template": PromptTemplateToolGroup(),`:

```python
            # Prompt variable catalog (spec §3.1): the config layer the
            # prompt_template group's bodies reference via {placeholders}.
            "prompt_variable": PromptVariableToolGroup(),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest mcp_server/tests/test_prompt_variable_tool_group.py mcp_server/tests/test_tool_registry.py -q`

Expected: PASS

- [ ] **Step 5: Regenerate the tool manifest**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test python manage.py export_tool_manifest`

Then: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest mcp_server/tests/test_tool_manifest_drift.py -q`

Expected: PASS (manifest now contains the four `prompt_variable.*` tools)

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/tools/prompt_variable.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_prompt_variable_tool_group.py docs/agent-templates/tool-manifest.json
git commit -m "feat: add prompt_variable MCP tool group"
```

---

### Task 11: Auto-injection proof (no code change needed for a new variable)

**Files:**
- Test: `backend/application/tests/test_prompt_variable_auto_injection.py`

**Interfaces:**
- Consumes: `PromptVariableService.set_variable` (Task 6), `resolve_and_render` (Task 5), `publish_new_version` (`application.prompt_template_versioning`, existing), `AiDerivationService._resolve_and_render` (Task 7).
- Produces: no production code — this task is the acceptance test for spec §8's "Auto-Injection" bullet. If it fails, the defect is in Task 5 or Task 6.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_prompt_variable_auto_injection.py`:

```python
"""A brand-new config variable works with zero code changes (spec §3.2, §8)."""
from __future__ import annotations

import pytest

from application.ai_derivation_service import AiDerivationService
from application.prompt_resolver import resolve_and_render, unknown_placeholders
from application.prompt_template_versioning import publish_new_version
from application.prompt_variable_service import PromptVariableService
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="AI Tenant", slug="ai-tenant")
    user = User.objects.create(username="ai-user", email="ai@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="AI WS")
        ctx = AuthContext(user_id=user.id, tenant_id=tenant.id, active_roles=("admin",))
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()


def test_a_new_config_variable_appears_in_a_rendered_prompt(ctx_workspace):
    ctx, workspace = ctx_workspace
    # 1. An admin invents a variable — pure data, no deploy.
    PromptVariableService().set_variable(
        ctx,
        name="tone_hint",
        value="Write in a terse, engineering tone.",
        var_type="str",
        description="Extra style instruction appended to derivation prompts.",
    )
    # 2. An admin references it in an existing slot's body — also pure data.
    publish_new_version(
        tenant_id=ctx.tenant_id,
        name="testcase_derive",
        content="Derive a test for {req_title}. {tone_hint}",
    )

    rendered = resolve_and_render(
        "testcase_derive", ctx, workspace.id, req_title="Login"
    )

    assert rendered == "Derive a test for Login. Write in a terse, engineering tone."


def test_the_same_holds_through_the_service_entry_point(ctx_workspace):
    ctx, workspace = ctx_workspace
    PromptVariableService().set_variable(
        ctx, name="tone_hint", value="Be terse.", var_type="str"
    )
    publish_new_version(
        tenant_id=ctx.tenant_id, name="testcase_derive", content="{tone_hint}"
    )

    assert (
        AiDerivationService._resolve_and_render(ctx, "testcase_derive", workspace.id)
        == "Be terse."
    )


def test_a_workspace_override_of_the_new_variable_takes_effect(ctx_workspace):
    ctx, workspace = ctx_workspace
    svc = PromptVariableService()
    svc.set_variable(ctx, name="tone_hint", value="tenant tone", var_type="str")
    svc.set_variable(
        ctx, name="tone_hint", value="workspace tone", workspace_id=workspace.id
    )
    publish_new_version(
        tenant_id=ctx.tenant_id, name="testcase_derive", content="{tone_hint}"
    )

    assert resolve_and_render("testcase_derive", ctx, workspace.id) == "workspace tone"
    assert resolve_and_render("testcase_derive", ctx, None) == "tenant tone"


def test_the_new_variable_is_not_reported_as_an_unknown_placeholder(ctx_workspace):
    ctx, workspace = ctx_workspace
    PromptVariableService().set_variable(
        ctx, name="tone_hint", value="x", var_type="str"
    )

    assert (
        unknown_placeholders("{tone_hint}", "testcase_derive", ctx, workspace.id) == []
    )


def test_clearing_the_variable_leaves_the_placeholder_literal(ctx_workspace):
    """Removing a variable must not blank the text — REQ-046 leaves it as-is."""
    ctx, workspace = ctx_workspace
    svc = PromptVariableService()
    svc.set_variable(ctx, name="tone_hint", value="x", var_type="str")
    publish_new_version(
        tenant_id=ctx.tenant_id, name="testcase_derive", content="[{tone_hint}]"
    )
    svc.clear_variable(ctx, name="tone_hint")

    assert resolve_and_render("testcase_derive", ctx, workspace.id) == "[{tone_hint}]"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_prompt_variable_auto_injection.py -q`

Expected: PASS immediately if Tasks 5 and 6 are correct. If any test fails, the defect is in `resolve_config_values` (Task 5) or `set_variable` (Task 6) — fix there, do not weaken the assertions.

- [ ] **Step 3: Run the whole Phase 1 backend surface**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests persistence/tests rest_api/tests mcp_server/tests -q`

Expected: no new failures compared to the pre-branch baseline

- [ ] **Step 4: Commit**

```bash
git add backend/application/tests/test_prompt_variable_auto_injection.py
git commit -m "test: prove config variables auto-inject without code changes"
```

---

### Task 12: Migrate architecture-decompose into the catalog

**Files:**
- Modify: `backend/application/architecture_decompose_service.py:88-103` (drop `_MAX_BREADTH`/`_MAX_DEPTH`, rewrite `ARCH_DECOMPOSE_PROMPT_TEMPLATE`), `:317-385` (`generate_draft`), `:654-763` (`_complete_tree`), `:787-821` (`_flatten_tree`)
- Modify: `backend/application/prompt_variables.py` (add `element_title`, `max_breadth`, `max_depth`)
- Modify: `backend/application/prompt_slots.py` (register `architecture_decompose_tree`)
- Modify: `backend/application/settings_service.py:329-346` (`_all_prompt_defaults` reads the consolidated registry)
- Test: `backend/application/tests/test_architecture_decompose_catalog.py`

**Interfaces:**
- Consumes: `resolve_and_render`, `resolve_config_values` (Task 5); `get_prompt_slots` (Task 4).
- Produces:
  - Slot name `architecture_decompose_tree` in the canonical registry (therefore visible/editable in `AiPromptsSection` and via `prompt_template.*`).
  - Config variables `max_breadth` (int, factory default 5) and `max_depth` (int, factory default 3); data variable `element_title`.
  - `ArchitectureDecomposeService.generate_draft(ctx, element_id, *, max_breadth: int | None = None, max_depth: int | None = None) -> DecompositionDraft`
  - `ArchitectureDecomposeService._complete_tree(*, ctx, workspace_id, element_title, max_breadth, max_depth, artifact_id) -> Tuple[list, str, bool]`
  - `ArchitectureDecomposeService._flatten_tree(raw_tree, *, max_breadth, max_depth) -> List[DraftNode]`
  - `ARCH_DECOMPOSE_PROMPT_TEMPLATE` stays exported, now as the factory body of the new slot.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_architecture_decompose_catalog.py`:

```python
"""N1 decompose reads its prompt + caps from the catalog (spec §4)."""
from __future__ import annotations

import pytest

from application.architecture_decompose_service import (
    ARCH_DECOMPOSE_PROMPT_TEMPLATE,
    ArchitectureDecomposeService,
)
from application.prompt_resolver import resolve_template_content
from application.prompt_slots import get_prompt_slots
from application.prompt_variable_service import PromptVariableService
from application.prompt_variables import PROMPT_VARIABLE_DEFAULTS
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="AD Tenant", slug="ad-tenant")
    user = User.objects.create(username="ad-user", email="ad@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="AD WS")
        ctx = AuthContext(user_id=user.id, tenant_id=tenant.id, active_roles=("admin",))
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()


def _tree(breadth: int, depth: int) -> list:
    """Build a nested provider tree with *breadth* children on *depth* levels."""

    def _level(prefix: str, remaining: int) -> list:
        if remaining == 0:
            return []
        return [
            {
                "title": f"{prefix}{i}",
                "description": "d",
                "element_type": "component",
                "requirement": {"title": f"req {prefix}{i}"},
                "children": _level(f"{prefix}{i}.", remaining - 1),
            }
            for i in range(breadth)
        ]

    return _level("c", depth)


def test_the_decompose_prompt_is_a_registered_slot():
    assert "architecture_decompose_tree" in get_prompt_slots()


def test_the_slot_declares_element_title_as_its_data_variable():
    spec = get_prompt_slots()["architecture_decompose_tree"]

    assert spec.data_variables == ("element_title",)


def test_the_factory_body_references_the_two_config_caps():
    assert "{max_breadth}" in ARCH_DECOMPOSE_PROMPT_TEMPLATE
    assert "{max_depth}" in ARCH_DECOMPOSE_PROMPT_TEMPLATE
    assert "{breadth}" not in ARCH_DECOMPOSE_PROMPT_TEMPLATE
    assert "{depth}" not in ARCH_DECOMPOSE_PROMPT_TEMPLATE


def test_the_caps_are_registered_config_variables():
    assert PROMPT_VARIABLE_DEFAULTS["max_breadth"].kind == "config"
    assert PROMPT_VARIABLE_DEFAULTS["max_breadth"].default_value == 5
    assert PROMPT_VARIABLE_DEFAULTS["max_depth"].default_value == 3


def test_the_slot_resolves_and_is_workspace_overridable(ctx_workspace):
    from application.prompt_template_versioning import publish_new_version

    ctx, workspace = ctx_workspace
    assert resolve_template_content(
        "architecture_decompose_tree", ctx, workspace.id
    ) == ARCH_DECOMPOSE_PROMPT_TEMPLATE

    publish_new_version(
        tenant_id=ctx.tenant_id,
        name="architecture_decompose_tree",
        content="CUSTOM {element_title}",
        workspace_id=workspace.id,
    )

    assert (
        resolve_template_content("architecture_decompose_tree", ctx, workspace.id)
        == "CUSTOM {element_title}"
    )


def test_module_level_cap_constants_are_gone():
    import application.architecture_decompose_service as mod

    assert not hasattr(mod, "_MAX_BREADTH")
    assert not hasattr(mod, "_MAX_DEPTH")


def test_flatten_clamps_breadth_to_the_resolved_cap():
    nodes = ArchitectureDecomposeService()._flatten_tree(
        _tree(breadth=6, depth=1), max_breadth=2, max_depth=3
    )

    assert len(nodes) == 2


def test_flatten_clamps_depth_to_the_resolved_cap():
    nodes = ArchitectureDecomposeService()._flatten_tree(
        _tree(breadth=1, depth=4), max_breadth=5, max_depth=2
    )

    assert max(n.temp_id.count(".") for n in nodes) == 1


def test_the_prompt_carries_the_workspace_overridden_caps(ctx_workspace, monkeypatch):
    ctx, workspace = ctx_workspace
    PromptVariableService().set_variable(
        ctx, name="max_breadth", value=2, workspace_id=workspace.id
    )
    captured: dict = {}

    class _Provider:
        def complete(self, prompt, *, purpose, context):
            captured["prompt"] = prompt
            captured["context"] = context
            return "[]"

    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda: _Provider()
    )

    ArchitectureDecomposeService()._complete_tree(
        ctx=ctx,
        workspace_id=workspace.id,
        element_title="Payment",
        max_breadth=2,
        max_depth=3,
        artifact_id="00000000-0000-0000-0000-000000000000",
    )

    assert "Payment" in captured["prompt"]
    assert "at most 2" in captured["prompt"]
    assert captured["context"]["max_breadth"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_architecture_decompose_catalog.py -q`

Expected: FAIL with `KeyError: 'architecture_decompose_tree'`

- [ ] **Step 3: Write minimal implementation**

In `backend/application/prompt_variables.py`, add to `PROMPT_VARIABLE_DEFAULTS` — the data entry next to the other `_data(...)` rows and a new config block after them:

```python
    "element_title": _data(
        "element_title", "Title of the architecture element being decomposed."
    ),
    # --- config (data-driven, admin-editable) ------------------------------
    "max_breadth": _config(
        "max_breadth",
        "Upper bound on child elements the AI may propose per level. Not a "
        "target — the AI decides the real number from the content.",
        "int",
        5,
    ),
    "max_depth": _config(
        "max_depth",
        "Upper bound on decomposition levels the AI may propose in one draft.",
        "int",
        3,
    ),
```

In `backend/application/prompt_slots.py`, add the slot's data variables to `_DATA_VARIABLES_BY_SLOT`:

```python
    "architecture_decompose_tree": ("element_title",),
```

and merge the N1 body into `get_prompt_slots`'s lazy import block:

```python
def get_prompt_slots() -> Dict[str, PromptSlotSpec]:
    """Return the merged factory registry, keyed by slot name.

    Rebuilt per call (cheap dict comprehension over ~20 entries) so a test
    that monkeypatches one of the source registries sees the change — caching
    it would pin whatever the first caller observed.
    """
    from application.ai_derivation_service import PROMPT_TEMPLATE_DEFAULTS
    from application.architecture_decompose_service import (
        ARCH_DECOMPOSE_PROMPT_TEMPLATE,
    )
    from application.interview_protocol import INTERVIEW_PROTOCOL_DEFAULTS

    merged: Dict[str, str] = {
        **PROMPT_TEMPLATE_DEFAULTS,
        **INTERVIEW_PROTOCOL_DEFAULTS,
        # Spec §4: N1 no longer bypasses the catalog — its prompt is a regular
        # slot, editable through AiPromptsSection like every other one.
        "architecture_decompose_tree": ARCH_DECOMPOSE_PROMPT_TEMPLATE,
    }
    slots: Dict[str, PromptSlotSpec] = {}
    for name, content in merged.items():
        if name.startswith("interview.protocol."):
            data_variables = INTERVIEW_PROTOCOL_DATA_VARIABLES
        else:
            data_variables = _DATA_VARIABLES_BY_SLOT.get(name, ())
        slots[name] = PromptSlotSpec(
            name=name, default_content=content, data_variables=data_variables
        )
    return slots
```

In `backend/application/settings_service.py`, replace `_all_prompt_defaults`'s body so the slot UI covers every registry entry (including the new N1 slot):

```python
    @staticmethod
    def _all_prompt_defaults() -> dict[str, str]:
        """Return the canonical factory-default registry for every slot.

        Reads ``application.prompt_slots`` — the one consolidated registry
        (spec §3.2) — instead of ``ai_derivation_service``'s
        derive-flow-only dict, so slots owned by other services (e.g.
        ``architecture_decompose_tree``) are editable in the slot UI too.

        Imported lazily because ``prompt_slots`` lazily imports
        ``ai_derivation_service``, which imports this module — a module-level
        import here would close that cycle.
        """
        from application.prompt_slots import get_prompt_slots

        return {name: spec.default_content for name, spec in get_prompt_slots().items()}
```

In `backend/application/architecture_decompose_service.py`, replace the `_MAX_BREADTH`/`_MAX_DEPTH` constants and the prompt constant (lines 88-103) with:

```python
# Prompt slot for the recursive decomposition (llm_adapter capability
# ``arch_decompose_tree``). Spec §4: this is now a regular catalog slot
# (``architecture_decompose_tree``) rather than a module-private constant, so
# it is visible and editable in the prompt admin UI like every other prompt.
# The blast-radius bounds it used to hard-code (_MAX_BREADTH/_MAX_DEPTH) are
# now the ``max_breadth``/``max_depth`` config variables, resolvable per
# workspace.
ARCH_DECOMPOSE_PROMPT_SLOT = "architecture_decompose_tree"

ARCH_DECOMPOSE_PROMPT_TEMPLATE = (
    "Analyse the architecture element '{element_title}' and the requirements "
    "allocated to it. Decompose it into the child elements that are actually "
    "justified by its content — mirror real cohesion, do not split "
    "artificially. Choose the number of children and the number of levels "
    "yourself; use at most {max_breadth} child elements per level and at most "
    "{max_depth} levels in total. For each child element propose a concise "
    "title, a description, and a single derived requirement (title, "
    "description, rationale) that the child element must satisfy. Return a "
    "JSON array of nodes, each optionally carrying a nested 'children' array."
)
```

Replace `generate_draft`'s signature and its clamping block (lines 317-371) with:

```python
    def generate_draft(
        self,
        ctx: AuthContext,
        element_id: UUID | str,
        *,
        max_breadth: Optional[int] = None,
        max_depth: Optional[int] = None,
    ) -> DecompositionDraft:
        """Propose a decomposition for *element_id* (no DB writes).

        Args:
            ctx: Authenticated, tenant-scoped context.
            element_id: The ArchitectureElement (Subsystem) to decompose.
            max_breadth: Upper bound on children per level. ``None`` resolves
                the ``max_breadth`` config variable for this workspace.
            max_depth: Upper bound on levels. ``None`` resolves the
                ``max_depth`` config variable for this workspace.

        Returns:
            A :class:`DecompositionDraft` for review — nothing is persisted.

        Raises:
            DecompositionNotAvailableError: Workspace is minimal-rigor.
            NotFoundError: The element does not exist for this tenant.
            ValidationError: The element has no allocated anchor requirement.
        """
        from application.prompt_resolver import resolve_config_values

        self._set_tenant_context(ctx)

        element = (
            ArchitectureElement.objects.select_related("artifact")
            .filter(id=element_id)
            .first()
        )
        if element is None:
            raise NotFoundError(f"ArchitectureElement {element_id} not found")

        workspace_id = str(element.artifact.workspace_id)
        self._assert_preset_allows(workspace_id)

        anchor = self._resolve_anchor_requirement(element)
        if anchor is None:
            raise ValidationError(
                "The selected architecture element has no allocated requirement "
                "to derive from. Allocate a requirement to it before running "
                "architecture.decompose (the derived requirements need a parent "
                "to satisfy ARCH-003/TRACE-P5)."
            )

        # Explicit call parameter > workspace row > tenant row > factory
        # default (spec §3.3). A caller-supplied cap is still floored at 1 so a
        # zero or negative value cannot produce an empty draft.
        caps = resolve_config_values(
            ctx,
            workspace_id,
            overrides={"max_breadth": max_breadth, "max_depth": max_depth},
        )
        resolved_breadth = max(1, int(caps["max_breadth"]))
        resolved_depth = max(1, int(caps["max_depth"]))

        raw_tree, provider_name, degraded = self._complete_tree(
            ctx=ctx,
            workspace_id=workspace_id,
            element_title=element.title,
            max_breadth=resolved_breadth,
            max_depth=resolved_depth,
            artifact_id=str(element.artifact_id),
        )
        nodes = self._flatten_tree(
            raw_tree, max_breadth=resolved_breadth, max_depth=resolved_depth
        )
        if not nodes:
            raise ValidationError(
                "The LLM returned no decomposition nodes for this element."
            )

        return DecompositionDraft(
            workspace_id=workspace_id,
            root_element_id=str(element.id),
            parent_requirement_id=str(anchor.id),
            provider=provider_name,
            degraded=degraded,
            nodes=nodes,
        )
```

In `_complete_tree`, change the signature and the prompt construction (the `def _complete_tree` line plus the `prompt = ...` / `context = ...` block, lines 654-697); everything after `provider_name = getattr(...)` stays byte-identical:

```python
    def _complete_tree(
        self,
        *,
        ctx: AuthContext,
        workspace_id: str,
        element_title: str,
        max_breadth: int,
        max_depth: int,
        artifact_id: str,
    ) -> Tuple[list, str, bool]:
        """Call the LLM provider for a decomposition tree (graceful degradation).

        Returns ``(parsed_tree, provider_name, degraded)``. On any provider
        error it degrades to the credential-free deterministic mock so the
        draft flow never crashes (§4 Phase 4a: "mit mock ... kein Crash").

        The prompt body now comes from the ``architecture_decompose_tree``
        catalog slot and is rendered by the shared resolver, so a workspace
        can customise both the wording and the caps (spec §4). Note the
        deliberate switch away from ``str.format``: the body may legitimately
        contain JSON braces once an admin edits it, which ``.format`` would
        reject.
        """
        from django.conf import settings

        from application.ai_derivation_service import LlmResponseError
        from application.prompt_resolver import resolve_and_render
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.providers import (
            LlmNotConfiguredError,
            LlmProviderUnknownError,
            MockLlmProvider,
            get_provider,
        )
        from llm_adapter.token_tracking import is_over_daily_limit, record_token_usage

        prompt = resolve_and_render(
            ARCH_DECOMPOSE_PROMPT_SLOT,
            ctx,
            workspace_id,
            config_overrides={"max_breadth": max_breadth, "max_depth": max_depth},
            element_title=element_title,
        )
        context = {
            "element_title": element_title,
            "max_breadth": max_breadth,
            "max_depth": max_depth,
        }
        provider_name = getattr(settings, "LLM_PROVIDER", "mock")
```

Replace `_flatten_tree` (lines 787-821) with:

```python
    def _flatten_tree(
        self, raw_tree: list, *, max_breadth: int, max_depth: int
    ) -> List[DraftNode]:
        """Flatten a nested provider tree into a pre-order :class:`DraftNode` list.

        Assigns stable ``temp_id``s (``n1``, ``n1.1`` …) and wires
        ``parent_temp_id`` so :meth:`commit_draft` can process parents before
        children in a single pass.

        Also enforces the resolved caps as a hard safety net (§3.1
        blast-radius concern): the prompt merely *asks* the model for at most
        ``max_breadth`` children over at most ``max_depth`` levels, so a model
        that ignores the instruction is clamped here rather than allowed to
        expand the commit transaction without bound.
        """
        nodes: List[DraftNode] = []

        def _walk(items: list, parent_temp_id: Optional[str], prefix: str, level: int) -> None:
            kept = 0
            for item in items:
                if kept >= max_breadth:
                    break
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title", "")).strip()
                if not title:
                    continue
                kept += 1
                temp_id = f"{prefix}{kept}"
                nodes.append(
                    DraftNode(
                        temp_id=temp_id,
                        parent_temp_id=parent_temp_id,
                        title=title,
                        description=str(item.get("description", "")),
                        element_type=str(item.get("element_type") or "component"),
                        requirement=DraftRequirement.from_dict(
                            item.get("requirement") or {}
                        ),
                    )
                )
                children = item.get("children")
                if level < max_depth and isinstance(children, list) and children:
                    _walk(children, temp_id, f"{temp_id}.", level + 1)

        _walk(raw_tree, None, "n", 1)
        return nodes
```

Finally extend the module's `__all__` with `"ARCH_DECOMPOSE_PROMPT_SLOT"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_architecture_decompose_catalog.py -q`

Expected: PASS (9 passed)

- [ ] **Step 5: Verify the existing N1 suite and the slot UI backend still pass**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_architecture_decompose.py application/tests/test_settings_service.py rest_api/tests/test_prompt_template_slots.py -q`

Expected: PASS — update only call sites that still pass `breadth=`/`depth=` to `generate_draft`; do not relax assertions.

- [ ] **Step 6: Commit**

```bash
git add backend/application/architecture_decompose_service.py backend/application/prompt_variables.py backend/application/prompt_slots.py backend/application/settings_service.py backend/application/tests/test_architecture_decompose_catalog.py
git commit -m "feat: move architecture decompose prompt and caps into the catalog"
```

---

### Task 13: Rename breadth/depth to max_breadth/max_depth on REST and MCP

**Files:**
- Modify: `backend/rest_api/architecture_decompose_views.py:43-48` (serializer), `:70-78` (service call)
- Modify: `backend/mcp_server/tools/architecture.py:226-247` (tool schema), `:594-611` (handler)
- Modify: `docs/agent-templates/tool-manifest.json` (regenerated artifact)
- Test: `backend/rest_api/tests/test_architecture_decompose_caps.py`

**Interfaces:**
- Consumes: `ArchitectureDecomposeService.generate_draft(ctx, element_id, *, max_breadth=None, max_depth=None)` (Task 12).
- Produces:
  - `GenerateDraftRequestSerializer` fields: `element_id` (UUIDField, required), `max_breadth` (IntegerField, optional, `min_value=1`), `max_depth` (IntegerField, optional, `min_value=1`).
  - MCP `architecture.decompose` input schema properties: `element_id` (required), `max_breadth`, `max_depth` (both optional integers).
  - **Breaking:** `breadth`/`depth` are no longer accepted by either surface.

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_architecture_decompose_caps.py`:

```python
"""REST + MCP surface of the renamed decompose caps (spec §4)."""
from __future__ import annotations

import pytest

from rest_api.architecture_decompose_views import GenerateDraftRequestSerializer

_ELEMENT_ID = "11111111-1111-1111-1111-111111111111"


def test_serializer_accepts_the_new_cap_names():
    ser = GenerateDraftRequestSerializer(
        data={"element_id": _ELEMENT_ID, "max_breadth": 4, "max_depth": 2}
    )

    assert ser.is_valid(), ser.errors
    assert ser.validated_data["max_breadth"] == 4
    assert ser.validated_data["max_depth"] == 2


def test_serializer_ignores_the_removed_legacy_names():
    ser = GenerateDraftRequestSerializer(
        data={"element_id": _ELEMENT_ID, "breadth": 4, "depth": 2}
    )

    assert ser.is_valid(), ser.errors
    assert "max_breadth" not in ser.validated_data
    assert "max_depth" not in ser.validated_data


def test_serializer_rejects_a_cap_below_one():
    ser = GenerateDraftRequestSerializer(
        data={"element_id": _ELEMENT_ID, "max_breadth": 0}
    )

    assert not ser.is_valid()
    assert "max_breadth" in ser.errors


def test_serializer_has_no_upper_bound_on_the_caps():
    """The cap is admin policy now, not a hard-coded 5/3 (spec §4)."""
    ser = GenerateDraftRequestSerializer(
        data={"element_id": _ELEMENT_ID, "max_breadth": 12, "max_depth": 6}
    )

    assert ser.is_valid(), ser.errors


def test_mcp_schema_declares_the_new_cap_names():
    from mcp_server.tools.architecture import ArchitectureToolGroup

    schema = next(
        s
        for s in ArchitectureToolGroup().get_tool_schemas()
        if s["name"] == "architecture.decompose"
    )
    properties = schema["inputSchema"]["properties"]

    assert set(properties) == {"element_id", "max_breadth", "max_depth"}


@pytest.mark.django_db
def test_mcp_handler_forwards_the_caps(monkeypatch):
    from application import architecture_decompose_service as svc_mod
    from auth_tenancy.context import AuthContext
    from mcp_server.tools.architecture import ArchitectureToolGroup

    captured: dict = {}

    class _Svc:
        def generate_draft(self, ctx, element_id, *, max_breadth=None, max_depth=None):
            captured["max_breadth"] = max_breadth
            captured["max_depth"] = max_depth
            raise svc_mod.NotFoundError("stop here")

    monkeypatch.setattr(svc_mod, "ArchitectureDecomposeService", _Svc)
    ctx = AuthContext(
        user_id=None, tenant_id=None, active_roles=("editor",)
    )

    ArchitectureToolGroup()._handle_decompose(
        params={"element_id": _ELEMENT_ID, "max_breadth": 4, "max_depth": 2},
        auth_context=ctx,
        api_key="k",
    )

    assert captured == {"max_breadth": 4, "max_depth": 2}


@pytest.mark.django_db
def test_mcp_handler_passes_none_when_the_caps_are_omitted(monkeypatch):
    from application import architecture_decompose_service as svc_mod
    from auth_tenancy.context import AuthContext
    from mcp_server.tools.architecture import ArchitectureToolGroup

    captured: dict = {}

    class _Svc:
        def generate_draft(self, ctx, element_id, *, max_breadth=None, max_depth=None):
            captured["max_breadth"] = max_breadth
            captured["max_depth"] = max_depth
            raise svc_mod.NotFoundError("stop here")

    monkeypatch.setattr(svc_mod, "ArchitectureDecomposeService", _Svc)
    ctx = AuthContext(user_id=None, tenant_id=None, active_roles=("editor",))

    ArchitectureToolGroup()._handle_decompose(
        params={"element_id": _ELEMENT_ID}, auth_context=ctx, api_key="k"
    )

    assert captured == {"max_breadth": None, "max_depth": None}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest rest_api/tests/test_architecture_decompose_caps.py -q`

Expected: FAIL with `KeyError: 'max_breadth'` / `assert set(properties) == {...}` mismatch

- [ ] **Step 3: Write minimal implementation**

In `backend/rest_api/architecture_decompose_views.py`, replace the serializer:

```python
class GenerateDraftRequestSerializer(serializers.Serializer):
    """Body of POST .../architecture/decompose/.

    Spec §4 (breaking change): the former ``breadth``/``depth`` target numbers
    are gone. ``max_breadth``/``max_depth`` are optional *upper bounds*; when
    omitted the workspace's ``max_breadth``/``max_depth`` config variables
    apply. No ``max_value`` is declared — the ceiling is admin policy in the
    variable catalog now, not a hard-coded 5/3 in this serializer.
    """

    element_id = serializers.UUIDField()
    max_breadth = serializers.IntegerField(required=False, min_value=1)
    max_depth = serializers.IntegerField(required=False, min_value=1)
```

and the service call inside `WorkspaceArchitectureDecomposeView.post`:

```python
            draft = ArchitectureDecomposeService().generate_draft(
                get_auth_context(request),
                data["element_id"],
                max_breadth=data.get("max_breadth"),
                max_depth=data.get("max_depth"),
            )
```

In `backend/mcp_server/tools/architecture.py`, replace the `architecture.decompose` schema's description and properties:

```python
        {
            "name": "architecture.decompose",
            "description": (
                "SysEng 2.0 N1: generate a non-persistent decomposition draft "
                "for an ArchitectureElement (child elements + derived "
                "requirements + internal trace links). The AI decides how many "
                "children and levels are justified by the content; max_breadth "
                "and max_depth are optional upper bounds that override the "
                "workspace's configured caps for this call only. Review the "
                "returned draft, then persist it via "
                "architecture.decompose_commit. Available only in "
                "standard/extended rigor."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "element_id": {
                        "type": "string",
                        "description": "UUID of the ArchitectureElement (Subsystem) to decompose.",
                    },
                    "max_breadth": {
                        "type": "integer",
                        "description": (
                            "Upper bound on child elements per level. Omit to use "
                            "the workspace's configured max_breadth."
                        ),
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": (
                            "Upper bound on decomposition levels. Omit to use the "
                            "workspace's configured max_depth."
                        ),
                    },
                },
                "required": ["element_id"],
            },
        },
```

and the handler body:

```python
    def _handle_decompose(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """architecture.decompose — generate a non-persistent decomposition draft."""
        from application.architecture_decompose_service import (
            ArchitectureDecomposeService,
            DecompositionNotAvailableError,
        )

        element_id = require_uuid(params, "element_id")
        # None (not a literal default) so the workspace's configured caps win
        # when the caller omits the parameter — spec §3.3's precedence chain.
        raw_breadth = params.get("max_breadth")
        raw_depth = params.get("max_depth")
        try:
            max_breadth = int(raw_breadth) if raw_breadth is not None else None
            max_depth = int(raw_depth) if raw_depth is not None else None
        except (TypeError, ValueError):
            return ToolResult.error(
                "VALIDATION_ERROR", "'max_breadth' and 'max_depth' must be integers."
            )
        try:
            draft = ArchitectureDecomposeService().generate_draft(
                auth_context,
                element_id,
                max_breadth=max_breadth,
                max_depth=max_depth,
            )
        except DecompositionNotAvailableError as exc:
            return ToolResult.error("FEATURE_NOT_ENABLED", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({"draft": draft.to_dict()})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest rest_api/tests/test_architecture_decompose_caps.py -q`

Expected: PASS (7 passed)

- [ ] **Step 5: Regenerate the tool manifest and re-run the N1 suites**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test python manage.py export_tool_manifest`

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest mcp_server/tests rest_api/tests/test_architecture.py application/tests/test_architecture_decompose.py -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/rest_api/architecture_decompose_views.py backend/mcp_server/tools/architecture.py backend/rest_api/tests/test_architecture_decompose_caps.py docs/agent-templates/tool-manifest.json
git commit -m "feat!: rename decompose breadth/depth to max_breadth/max_depth"
```

---

### Task 14: `n` becomes the `max_requirements_per_need` config variable

**Files:**
- Modify: `backend/persistence/models.py:1866-1872` (`DEFAULT_NEED_TO_SYSREQ` wording)
- Modify: `backend/application/prompt_variables.py` (drop the `n` data entry, add the config entry)
- Modify: `backend/application/prompt_slots.py` (`need_to_sysreq` data variables)
- Modify: `backend/application/ai_derivation_service.py:402-458` (`derive_requirements_from_need`)
- Modify: `backend/rest_api/views.py:543-560` and `:573-590` (two `n` parse sites)
- Modify: `backend/mcp_server/tools/ai_derivation.py:134-142` (`n` parse site)
- Test: `backend/application/tests/test_max_requirements_per_need.py`

**Interfaces:**
- Consumes: `resolve_and_render` (Task 5), `PromptVariableService` (Task 6).
- Produces:
  - Config variable `max_requirements_per_need` (int, factory default 3).
  - `AiDerivationService.derive_requirements_from_need(ctx, stakeholder_need_id, n: int | None = None) -> Dict[str, Any]` — `n` stays the public REST/MCP parameter name (no breaking change there) but is now just an explicit override of the config variable; `None` means "use the configured value".
  - `need_to_sysreq` slot data variables shrink to `("need_title", "need_description")`.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_max_requirements_per_need.py`:

```python
"""`n` becomes a catalog config variable (spec §4, last paragraph)."""
from __future__ import annotations

import pytest

from application.ai_derivation_service import AiDerivationService
from application.prompt_resolver import resolve_and_render
from application.prompt_slots import get_slot_data_variables
from application.prompt_variable_service import PromptVariableService
from application.prompt_variables import PROMPT_VARIABLE_DEFAULTS
from auth_tenancy.context import AuthContext
from persistence.models import DEFAULT_NEED_TO_SYSREQ
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="MR Tenant", slug="mr-tenant")
    user = User.objects.create(username="mr-user", email="mr@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="MR WS")
        ctx = AuthContext(user_id=user.id, tenant_id=tenant.id, active_roles=("admin",))
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()


def test_the_variable_is_a_registered_config_entry():
    spec = PROMPT_VARIABLE_DEFAULTS["max_requirements_per_need"]

    assert spec.kind == "config"
    assert spec.var_type == "int"
    assert spec.default_value == 3


def test_the_factory_prompt_asks_for_an_upper_bound_not_an_exact_count():
    assert "{max_requirements_per_need}" in DEFAULT_NEED_TO_SYSREQ
    assert "{n}" not in DEFAULT_NEED_TO_SYSREQ
    assert "at most" in DEFAULT_NEED_TO_SYSREQ


def test_n_is_no_longer_a_declared_data_variable():
    assert set(get_slot_data_variables("need_to_sysreq")) == {
        "need_title",
        "need_description",
    }
    assert "n" not in PROMPT_VARIABLE_DEFAULTS


def test_the_factory_value_lands_in_the_rendered_prompt(ctx_workspace):
    ctx, workspace = ctx_workspace

    rendered = resolve_and_render(
        "need_to_sysreq",
        ctx,
        workspace.id,
        need_title="Login",
        need_description="Users log in.",
    )

    assert "at most 3" in rendered


def test_a_workspace_override_changes_the_rendered_prompt(ctx_workspace):
    ctx, workspace = ctx_workspace
    PromptVariableService().set_variable(
        ctx, name="max_requirements_per_need", value=7, workspace_id=workspace.id
    )

    rendered = resolve_and_render(
        "need_to_sysreq", ctx, workspace.id, need_title="Login", need_description="d"
    )

    assert "at most 7" in rendered


def test_an_explicit_n_still_wins_over_the_configured_value(ctx_workspace):
    ctx, workspace = ctx_workspace
    PromptVariableService().set_variable(
        ctx, name="max_requirements_per_need", value=7, workspace_id=workspace.id
    )

    rendered = resolve_and_render(
        "need_to_sysreq",
        ctx,
        workspace.id,
        config_overrides={"max_requirements_per_need": 2},
        need_title="Login",
        need_description="d",
    )

    assert "at most 2" in rendered


def test_derive_forwards_an_explicit_n_as_a_config_override(ctx_workspace, monkeypatch):
    """`n=None` must reach the resolver as "no override", not as literal None."""
    ctx, workspace = ctx_workspace
    from persistence.models import Artifact, StakeholderNeed

    artifact = Artifact.objects.create(
        tenant_id=ctx.tenant_id,
        workspace_id=workspace.id,
        artifact_type="StakeholderNeed",
        title="Need",
    )
    need = StakeholderNeed.objects.create(
        tenant_id=ctx.tenant_id, artifact=artifact, title="Need", description="d"
    )
    captured: dict = {}

    def _fake_render(slot, c, ws, *, config_overrides=None, **data):
        captured["config_overrides"] = config_overrides
        return "prompt"

    monkeypatch.setattr(
        "application.ai_derivation_service.AiDerivationService._resolve_and_render",
        staticmethod(_fake_render),
    )
    monkeypatch.setattr(
        AiDerivationService, "_complete_json_list", lambda *a, **k: []
    )

    AiDerivationService().derive_requirements_from_need(ctx, need.id, n=5)
    assert captured["config_overrides"] == {"max_requirements_per_need": 5}

    AiDerivationService().derive_requirements_from_need(ctx, need.id)
    assert captured["config_overrides"] == {"max_requirements_per_need": None}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_max_requirements_per_need.py -q`

Expected: FAIL with `KeyError: 'max_requirements_per_need'`

- [ ] **Step 3: Write minimal implementation**

In `backend/persistence/models.py`, replace `DEFAULT_NEED_TO_SYSREQ`:

```python
DEFAULT_NEED_TO_SYSREQ = (
    "Given the following stakeholder need, generate at most "
    "{max_requirements_per_need} system-level requirements — produce only as "
    "many as the need actually justifies. Each requirement must be specific, "
    "measurable, and testable. Return a JSON array of objects with fields: "
    "title (string), description (string), rationale (string).\n\n"
    "Stakeholder Need:\nTitle: {need_title}\nDescription: {need_description}"
)
```

In `backend/application/prompt_variables.py`, delete the `"n": _data(...)` entry and add to the config block:

```python
    "max_requirements_per_need": _config(
        "max_requirements_per_need",
        "Upper bound on requirement drafts derived from one stakeholder need. "
        "Not a target — the AI produces only as many as the need justifies.",
        "int",
        3,
    ),
```

In `backend/application/prompt_slots.py`, change the `need_to_sysreq` entry of `_DATA_VARIABLES_BY_SLOT`:

```python
    "need_to_sysreq": ("need_title", "need_description"),
```

In `backend/application/ai_derivation_service.py`, replace `derive_requirements_from_need`'s signature, the `count` line and the template/prompt block (lines 402-447) with:

```python
    def derive_requirements_from_need(
        self,
        ctx: AuthContext,
        stakeholder_need_id: UUID | str,
        n: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Flow 1: propose system requirements for a stakeholder need.

        Args:
            ctx: Authenticated, tenant-scoped context.
            stakeholder_need_id: Source stakeholder need.
            n: Explicit upper bound for this call, overriding the workspace's
                ``max_requirements_per_need`` config variable. ``None`` (the
                default) means "use the configured value" — spec §4 turned
                this from a hard-coded 3 into catalog configuration.

        Returns:
            ``{"drafts": [{title, description, rationale, suggested_parent_id}]}``.

        Raises:
            NotFoundError: The stakeholder need does not exist for this tenant.
            LlmResponseError: The provider returned non-JSON content.
        """
        self._set_tenant_context(ctx)
        count = max(1, int(n)) if n is not None else None

        need = (
            StakeholderNeed.objects.select_related("artifact")
            .filter(id=stakeholder_need_id)
            .first()
        )
        if need is None:
            raise NotFoundError(f"StakeholderNeed {stakeholder_need_id} not found")

        prompt = self._resolve_and_render(
            ctx,
            "need_to_sysreq",
            need.artifact.workspace_id,
            config_overrides={"max_requirements_per_need": count},
            need_title=need.title,
            need_description=truncate_prompt_content(need.description or ""),
        )

        items = self._complete_json_list(
            prompt,
            purpose="need_to_sysreq",
            artifact_id=need.artifact_id,
            context={"max_requirements_per_need": count},
        )
```

In `backend/rest_api/views.py`, replace both `n` parse blocks (lines 543-550 and 573-580) with:

```python
        raw_n = request.data.get("n") if isinstance(request.data, dict) else None
        try:
            # None means "use the workspace's max_requirements_per_need"
            # config variable — an explicit value overrides it for this call.
            n = int(raw_n) if raw_n is not None else None
        except (TypeError, ValueError):
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="'n' must be an integer"),
                status=status.HTTP_400_BAD_REQUEST,
            )
```

In `backend/mcp_server/tools/ai_derivation.py`, replace the `n` parse block (lines 134-139) with:

```python
    n_raw = params.get("n")
    try:
        # None means "use the workspace's max_requirements_per_need" config
        # variable; an explicit value overrides it for this call only.
        n = int(n_raw) if n_raw is not None else None
    except (TypeError, ValueError):
        return ToolResult.error("VALIDATION_ERROR", "'n' must be an integer.")
```

and update that tool's schema description for `n`:

```python
                    "n": {
                        "type": "integer",
                        "description": (
                            "Optional upper bound on requirement drafts. Omit to "
                            "use the workspace's configured "
                            "max_requirements_per_need (default 3)."
                        ),
                    },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_max_requirements_per_need.py -q`

Expected: PASS (7 passed)

Finally update the Task-4 assertion that still expects the old three-variable set. In `backend/application/tests/test_prompt_slots_registry.py`, replace `test_need_to_sysreq_declares_its_three_data_variables` with:

```python
def test_need_to_sysreq_declares_its_two_data_variables():
    """``n`` became the ``max_requirements_per_need`` config variable (spec §4)."""
    assert set(get_slot_data_variables("need_to_sysreq")) == {
        "need_title",
        "need_description",
    }
```

- [ ] **Step 5: Re-run the derive surfaces**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest application/tests/test_ai_derivation_service.py application/tests/test_prompt_render_regression.py application/tests/test_prompt_slots_registry.py application/tests/test_prompt_variables_registry.py mcp_server/tests -q`

Expected: PASS

- [ ] **Step 6: Regenerate the tool manifest and commit**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test python manage.py export_tool_manifest`

```bash
git add backend/persistence/models.py backend/application/prompt_variables.py backend/application/prompt_slots.py backend/application/ai_derivation_service.py backend/rest_api/views.py backend/mcp_server/tools/ai_derivation.py backend/application/tests/test_max_requirements_per_need.py backend/application/tests/test_prompt_slots_registry.py docs/agent-templates/tool-manifest.json
git commit -m "feat: make requirement draft count a catalog config variable"
```

---

### Task 15: Slot payload gains variables + unknown-placeholder warnings

**Files:**
- Modify: `backend/application/settings_service.py:349-394` (`_build_slot_state`), `:396-418` (`_slot_state`), `:420-458` (`list_prompt_slots`), `:460-498` (`set_prompt_slot`), `:500-542` (`clear_prompt_slot`)
- Test: `backend/rest_api/tests/test_prompt_slot_variable_annotations.py`

**Interfaces:**
- Consumes: `unknown_placeholders`, `extract_placeholders`, `resolve_config_values` (Task 5); `get_slot_data_variables` (Task 4).
- Produces: three new keys on every prompt-slot wire dict returned by `GET /prompt-templates/slots/`, `PUT` and `DELETE`:
  - `data_variables: list[str]` — the slot's declared code-bound variables
  - `config_variables: list[str]` — config variables actually referenced in the effective body
  - `unknown_placeholders: list[str]` — `{placeholders}` that neither list can fill
- Also produces: `SettingsService._slot_annotations(ctx, name, content, workspace_id) -> tuple[list[str], list[str], list[str]]`

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_prompt_slot_variable_annotations.py`:

```python
"""Prompt slots report their variables and unknown placeholders (spec §5)."""
from __future__ import annotations

import pytest

from application.prompt_variable_service import PromptVariableService
from application.settings_service import SettingsService
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="SA Tenant", slug="sa-tenant")
    user = User.objects.create(username="sa-user", email="sa@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="SA WS")
        ctx = AuthContext(user_id=user.id, tenant_id=tenant.id, active_roles=("admin",))
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()


def _slot(ctx, workspace_id, name):
    return next(
        s
        for s in SettingsService().list_prompt_slots(ctx, workspace_id=workspace_id)
        if s["name"] == name
    )


def test_slots_report_their_declared_data_variables(ctx_workspace):
    ctx, workspace = ctx_workspace

    slot = _slot(ctx, workspace.id, "testcase_derive")

    assert set(slot["data_variables"]) == {"req_title", "req_description"}


def test_slots_report_the_config_variables_their_body_references(ctx_workspace):
    ctx, workspace = ctx_workspace

    slot = _slot(ctx, workspace.id, "architecture_decompose_tree")

    assert set(slot["config_variables"]) == {"max_breadth", "max_depth"}


def test_a_clean_body_reports_no_unknown_placeholders(ctx_workspace):
    ctx, workspace = ctx_workspace

    assert _slot(ctx, workspace.id, "testcase_derive")["unknown_placeholders"] == []


def test_saving_a_body_with_a_typo_reports_it_without_blocking(ctx_workspace):
    ctx, workspace = ctx_workspace

    state = SettingsService().set_prompt_slot(
        ctx,
        name="testcase_derive",
        content="Derive a test for {req_title} and {req_titel}.",
        workspace_id=workspace.id,
    )

    assert state["unknown_placeholders"] == ["req_titel"]
    assert state["effective_content"].endswith("{req_titel}.")


def test_a_newly_created_config_variable_stops_being_unknown(ctx_workspace):
    ctx, workspace = ctx_workspace
    svc = SettingsService()
    svc.set_prompt_slot(
        ctx,
        name="testcase_derive",
        content="{req_title} {tone_hint}",
        workspace_id=workspace.id,
    )
    assert _slot(ctx, workspace.id, "testcase_derive")["unknown_placeholders"] == [
        "tone_hint"
    ]

    PromptVariableService().set_variable(
        ctx, name="tone_hint", value="Be terse.", var_type="str"
    )

    slot = _slot(ctx, workspace.id, "testcase_derive")
    assert slot["unknown_placeholders"] == []
    assert slot["config_variables"] == ["tone_hint"]


def test_clearing_an_override_reannotates_against_the_inherited_body(ctx_workspace):
    ctx, workspace = ctx_workspace
    svc = SettingsService()
    svc.set_prompt_slot(
        ctx,
        name="testcase_derive",
        content="{req_title} {typo_here}",
        workspace_id=workspace.id,
    )

    state = svc.clear_prompt_slot(
        ctx, name="testcase_derive", workspace_id=workspace.id
    )

    assert state["unknown_placeholders"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest rest_api/tests/test_prompt_slot_variable_annotations.py -q`

Expected: FAIL with `KeyError: 'data_variables'`

- [ ] **Step 3: Write minimal implementation**

In `backend/application/settings_service.py`, add the annotation helper next to `_build_slot_state`:

```python
    @staticmethod
    def _slot_annotations(
        ctx: AuthContext,
        name: str,
        content: str,
        workspace_id: UUID | None,
    ) -> tuple[list[str], list[str], list[str]]:
        """Return ``(data_variables, config_variables, unknown_placeholders)``.

        ``config_variables`` lists only the config names the *effective body*
        actually references — spec §5 asks the UI to show what this prompt
        uses, not the whole catalog. ``unknown_placeholders`` is the typo
        warning: a ``{name}`` that is neither a declared data variable of this
        slot nor a resolvable config variable can never be filled.

        Imported lazily for the same import-cycle reason as
        :meth:`_all_prompt_defaults`.
        """
        from application.prompt_resolver import (
            extract_placeholders,
            resolve_config_values,
            unknown_placeholders,
        )
        from application.prompt_slots import get_slot_data_variables

        data_variables = list(get_slot_data_variables(name))
        config_names = set(resolve_config_values(ctx, workspace_id))
        config_variables = [
            placeholder
            for placeholder in extract_placeholders(content or "")
            if placeholder in config_names
        ]
        unknown = unknown_placeholders(content or "", name, ctx, workspace_id)
        return data_variables, config_variables, unknown
```

Extend `_build_slot_state`'s signature and returned dict:

```python
    @staticmethod
    def _build_slot_state(
        name: str,
        *,
        global_row: PromptTemplate | None,
        workspace_row: PromptTemplate | None,
        factory_default: str | None,
        data_variables: list[str] | None = None,
        config_variables: list[str] | None = None,
        unknown_placeholders: list[str] | None = None,
    ) -> dict[str, Any]:
```

and append these three keys to the returned dict (after `"effective_scope": scope,`):

```python
            "data_variables": data_variables or [],
            "config_variables": config_variables or [],
            "unknown_placeholders": unknown_placeholders or [],
```

Replace `_slot_state`'s body so it annotates the resolved content:

```python
    def _slot_state(
        self,
        ctx: AuthContext,
        name: str,
        *,
        workspace_id: UUID | None,
        factory_default: str | None,
    ) -> dict[str, Any]:
        """Fetch one slot's rows, resolve them, and annotate its variables."""
        state = self._build_slot_state(
            name,
            global_row=get_active_template(
                tenant_id=ctx.tenant_id, name=name, workspace_id=None
            ),
            workspace_row=(
                get_active_template(
                    tenant_id=ctx.tenant_id, name=name, workspace_id=workspace_id
                )
                if workspace_id is not None
                else None
            ),
            factory_default=factory_default,
        )
        data_vars, config_vars, unknown = self._slot_annotations(
            ctx, name, state["effective_content"], workspace_id
        )
        state["data_variables"] = data_vars
        state["config_variables"] = config_vars
        state["unknown_placeholders"] = unknown
        return state
```

and in `list_prompt_slots`, replace the returned list comprehension with an annotating loop:

```python
        names = set(defaults) | {r.name for r in rows}
        slots: list[dict[str, Any]] = []
        for name in sorted(names):
            state = self._build_slot_state(
                name,
                global_row=global_rows.get(name),
                workspace_row=workspace_rows.get(name),
                factory_default=defaults.get(name),
            )
            data_vars, config_vars, unknown = self._slot_annotations(
                ctx, name, state["effective_content"], workspace_id
            )
            state["data_variables"] = data_vars
            state["config_variables"] = config_vars
            state["unknown_placeholders"] = unknown
            slots.append(state)
        return slots
```

`set_prompt_slot` and `clear_prompt_slot` need no change — both already return `self._slot_state(...)`, which now carries the annotations.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest rest_api/tests/test_prompt_slot_variable_annotations.py rest_api/tests/test_prompt_template_slots.py application/tests/test_settings_service.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/application/settings_service.py backend/rest_api/tests/test_prompt_slot_variable_annotations.py
git commit -m "feat: annotate prompt slots with variables and unknown placeholders"
```

---

### Task 16: Frontend API client for the variable catalog

**Files:**
- Create: `frontend/src/api/prompt-variables.ts`
- Modify: `frontend/src/api/prompt-templates.ts:30-45` (extend `PromptSlotState`)
- Test: `frontend/src/test/promptVariablesApi.test.ts`

**Interfaces:**
- Consumes: `apiClient` (`frontend/src/api/client.ts`, existing) and the REST contract of Task 9 + Task 15.
- Produces:
  - `export type PromptVariableKind = "config" | "data"`
  - `export type PromptVariableType = "int" | "str" | "bool" | "json"`
  - `export type PromptVariableScope = "workspace" | "global" | "factory"`
  - `export interface PromptVariableState` — mirrors Task 6's wire dict
  - `export interface PromptVariableList { variables: PromptVariableState[]; count: number; workspace_id: string | null }`
  - `export interface SaveVariableOptions { varType?: PromptVariableType; description?: string }`
  - `export const promptVariablesApi` with `list(workspaceId?)`, `save(name, value, workspaceId?, options?)`, `clear(name, workspaceId?)`
  - `PromptSlotState` gains `data_variables: string[]`, `config_variables: string[]`, `unknown_placeholders: string[]`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/promptVariablesApi.test.ts`:

```ts
/**
 * ARCH-L1-001 ReactFrontend — prompt variable API wrapper (spec §3.1, §5).
 *
 * Pins the URL shapes and payloads, which is the part a component test with a
 * mocked module can never catch.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const get = vi.fn();
const put = vi.fn();
const del = vi.fn();

vi.mock("../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => get(...args),
    put: (...args: unknown[]) => put(...args),
    delete: (...args: unknown[]) => del(...args),
  },
}));

const WORKSPACE_ID = "11111111-1111-1111-1111-111111111111";

describe("promptVariablesApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    get.mockResolvedValue({ variables: [], count: 0, workspace_id: null });
    put.mockResolvedValue({});
    del.mockResolvedValue({});
  });

  it("lists tenant-global variables without a query string", async () => {
    const { promptVariablesApi } = await import("../api/prompt-variables");

    await promptVariablesApi.list();

    expect(get).toHaveBeenCalledWith("/prompt-variables/");
  });

  it("lists workspace-scoped variables with an encoded query string", async () => {
    const { promptVariablesApi } = await import("../api/prompt-variables");

    await promptVariablesApi.list(WORKSPACE_ID);

    expect(get).toHaveBeenCalledWith(
      `/prompt-variables/?workspace_id=${WORKSPACE_ID}`
    );
  });

  it("saves a value as a JSON body at the requested scope", async () => {
    const { promptVariablesApi } = await import("../api/prompt-variables");

    await promptVariablesApi.save("max_breadth", 4, WORKSPACE_ID);

    expect(put).toHaveBeenCalledWith(
      `/prompt-variables/max_breadth/?workspace_id=${WORKSPACE_ID}`,
      { value: 4 }
    );
  });

  it("passes var_type and description when creating a new variable", async () => {
    const { promptVariablesApi } = await import("../api/prompt-variables");

    await promptVariablesApi.save("tone_hint", "Be terse.", null, {
      varType: "str",
      description: "Style instruction.",
    });

    expect(put).toHaveBeenCalledWith("/prompt-variables/tone_hint/", {
      value: "Be terse.",
      var_type: "str",
      description: "Style instruction.",
    });
  });

  it("encodes the variable name in the path", async () => {
    const { promptVariablesApi } = await import("../api/prompt-variables");

    await promptVariablesApi.clear("weird name");

    expect(del).toHaveBeenCalledWith("/prompt-variables/weird%20name/");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm frontend-test sh -c "npm install && npx vitest run src/test/promptVariablesApi.test.ts"`

Expected: FAIL with `Failed to resolve import "../api/prompt-variables"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/api/prompt-variables.ts`:

```ts
/**
 * ARCH-L1-001 ReactFrontend — prompt variable catalog API (spec §3.1, §5).
 *
 * leaf_id: COMP-RF-001 (WorkspaceSettings — admin configuration)
 * req_id:  REQ-L2-PT-001 (Tenant-scoped editable LLM prompt configuration)
 *
 * Wraps the catalog endpoints, which mirror the prompt-template slot API's
 * scope semantics exactly:
 *
 *   GET    /prompt-variables/[?workspace_id=]        → every variable + state
 *   PUT    /prompt-variables/<name>/[?workspace_id=] → publish a new version
 *   DELETE /prompt-variables/<name>/[?workspace_id=] → drop that scope's row
 *
 * Resolution mirrors the backend resolver: workspace override → tenant
 * default → factory value.
 */

import { apiClient } from "./client";

/** Whether a variable is admin-editable config or code-bound data. */
export type PromptVariableKind = "config" | "data";

/** How the stored value is typed. */
export type PromptVariableType = "int" | "str" | "bool" | "json";

/** Which scope an effective variable value came from. */
export type PromptVariableScope = "workspace" | "global" | "factory";

/** One catalog variable with its value at every scope. */
export interface PromptVariableState {
  /** Placeholder name as used in prompt bodies, i.e. `{name}`. */
  name: string;
  kind: PromptVariableKind;
  var_type: PromptVariableType;
  description: string;
  /** Factory value, or `null` for a variable created at runtime. */
  factory_default: unknown;
  /** Active tenant-wide value, or `null` when never customised. */
  global_value: unknown;
  global_version: number | null;
  /** Active workspace override, or `null` when the workspace inherits. */
  workspace_value: unknown;
  workspace_version: number | null;
  has_workspace_override: boolean;
  /** The value that actually applies at the requested scope. */
  effective_value: unknown;
  effective_scope: PromptVariableScope;
  /** False for `kind: "data"` — those are documentation only. */
  is_editable: boolean;
}

/** Read shape returned by GET /prompt-variables/. */
export interface PromptVariableList {
  variables: PromptVariableState[];
  count: number;
  /** Echo of the requested workspace scope (`null` = tenant-global view). */
  workspace_id: string | null;
}

/** Extra fields only needed when introducing a brand-new variable. */
export interface SaveVariableOptions {
  varType?: PromptVariableType;
  description?: string;
}

/** Build the `?workspace_id=` suffix for a scope (empty for tenant-global). */
function scopeQuery(workspaceId?: string | null): string {
  return workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
}

export const promptVariablesApi = {
  /**
   * List every catalog variable. Pass a `workspaceId` to also resolve that
   * workspace's overrides; omit it for the tenant-global view only.
   */
  async list(workspaceId?: string | null): Promise<PromptVariableList> {
    return apiClient.get<PromptVariableList>(
      `/prompt-variables/${scopeQuery(workspaceId)}`
    );
  },

  /**
   * Publish a new version of `name` for the given scope. Omitting
   * `workspaceId` writes the tenant-wide default instead of an override.
   * `options` only matters for a name the backend has no factory entry for.
   */
  async save(
    name: string,
    value: unknown,
    workspaceId?: string | null,
    options: SaveVariableOptions = {}
  ): Promise<PromptVariableState> {
    const body: Record<string, unknown> = { value };
    if (options.varType !== undefined) body.var_type = options.varType;
    if (options.description !== undefined) body.description = options.description;
    return apiClient.put<PromptVariableState>(
      `/prompt-variables/${encodeURIComponent(name)}/${scopeQuery(workspaceId)}`,
      body
    );
  },

  /**
   * Drop `name`'s row at the given scope. Clearing a workspace scope restores
   * the tenant default; clearing the tenant scope restores the factory value.
   * Returns the now-effective state.
   */
  async clear(
    name: string,
    workspaceId?: string | null
  ): Promise<PromptVariableState> {
    return apiClient.delete<PromptVariableState>(
      `/prompt-variables/${encodeURIComponent(name)}/${scopeQuery(workspaceId)}`
    );
  },
};
```

In `frontend/src/api/prompt-templates.ts`, add three fields to `PromptSlotState` after `effective_scope`:

```ts
  /** Code-bound variables this slot's render call supplies. */
  data_variables: string[];
  /** Config variables the effective body actually references. */
  config_variables: string[];
  /** `{placeholders}` nothing can fill — almost certainly typos. */
  unknown_placeholders: string[];
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm frontend-test sh -c "npm install && npx vitest run src/test/promptVariablesApi.test.ts"`

Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/prompt-variables.ts frontend/src/api/prompt-templates.ts frontend/src/test/promptVariablesApi.test.ts
git commit -m "feat: add prompt variable API client"
```

---

### Task 17: Per-slot variable table in AiPromptsSection

**Files:**
- Create: `frontend/src/components/WorkspaceSettings/PromptVariableTable.tsx`
- Modify: `frontend/src/components/WorkspaceSettings/AiPromptsSection.tsx:363-437` (render the table + warning under each editor)
- Modify: `frontend/src/components/WorkspaceSettings/AiPromptsSection.test.tsx:38-51` (extend the `slot()` helper)
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`
- Test: `frontend/src/test/PromptVariableTable.test.tsx`

**Interfaces:**
- Consumes: `PromptVariableState`, `PromptVariableScope` (Task 16); `PromptSlotState` (Task 16, extended).
- Produces:
  - `export interface PromptVariableTableProps { slotName: string; variableNames: string[]; variables: PromptVariableState[] }`
  - `export function PromptVariableTable(props: PromptVariableTableProps): JSX.Element | null`
  - data-testids: `prompt-vars-<slotName>`, `prompt-var-<slotName>-<variableName>`, `prompt-var-<slotName>-<variableName>-origin`, `prompt-<slotName>-unknown-placeholders`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/PromptVariableTable.test.tsx`:

```tsx
/**
 * ARCH-L1-001 ReactFrontend — per-slot prompt variable table (spec §5).
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { PromptVariableTable } from "../components/WorkspaceSettings/PromptVariableTable";
import type { PromptVariableState } from "../api/prompt-variables";

vi.mock("react-i18next", () => {
  const t = (_key: string, fallback?: string): string => fallback ?? _key;
  return { useTranslation: () => ({ t }) };
});

function variable(
  name: string,
  overrides: Partial<PromptVariableState> = {}
): PromptVariableState {
  return {
    name,
    kind: "data",
    var_type: "str",
    description: `desc ${name}`,
    factory_default: "",
    global_value: null,
    global_version: null,
    workspace_value: null,
    workspace_version: null,
    has_workspace_override: false,
    effective_value: "",
    effective_scope: "factory",
    is_editable: false,
    ...overrides,
  };
}

const VARIABLES: PromptVariableState[] = [
  variable("req_title"),
  variable("max_breadth", {
    kind: "config",
    var_type: "int",
    factory_default: 5,
    workspace_value: 2,
    workspace_version: 1,
    has_workspace_override: true,
    effective_value: 2,
    effective_scope: "workspace",
    is_editable: true,
  }),
];

describe("PromptVariableTable (spec §5)", () => {
  it("renders one row per referenced variable", () => {
    render(
      <PromptVariableTable
        slotName="testcase_derive"
        variableNames={["req_title", "max_breadth"]}
        variables={VARIABLES}
      />
    );

    expect(
      screen.getByTestId("prompt-var-testcase_derive-req_title")
    ).toBeTruthy();
    expect(
      screen.getByTestId("prompt-var-testcase_derive-max_breadth")
    ).toBeTruthy();
  });

  it("shows the effective value and its origin badge", () => {
    render(
      <PromptVariableTable
        slotName="testcase_derive"
        variableNames={["max_breadth"]}
        variables={VARIABLES}
      />
    );

    const row = screen.getByTestId("prompt-var-testcase_derive-max_breadth");
    expect(row.textContent).toContain("2");
    expect(
      screen.getByTestId("prompt-var-testcase_derive-max_breadth-origin")
        .textContent
    ).toContain("Workspace-Override");
  });

  it("labels a data variable as code-bound", () => {
    render(
      <PromptVariableTable
        slotName="testcase_derive"
        variableNames={["req_title"]}
        variables={VARIABLES}
      />
    );

    expect(
      screen.getByTestId("prompt-var-testcase_derive-req_title").textContent
    ).toContain("code-gebunden");
  });

  it("renders nothing when the slot references no known variable", () => {
    const { container } = render(
      <PromptVariableTable
        slotName="testcase_derive"
        variableNames={[]}
        variables={VARIABLES}
      />
    );

    expect(container.firstChild).toBeNull();
  });

  it("skips a referenced name the catalog does not know", () => {
    render(
      <PromptVariableTable
        slotName="testcase_derive"
        variableNames={["req_title", "ghost"]}
        variables={VARIABLES}
      />
    );

    expect(screen.queryByTestId("prompt-var-testcase_derive-ghost")).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm frontend-test sh -c "npm install && npx vitest run src/test/PromptVariableTable.test.tsx"`

Expected: FAIL with `Failed to resolve import ".../PromptVariableTable"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/WorkspaceSettings/PromptVariableTable.tsx`:

```tsx
/**
 * ARCH-L1-001 ReactFrontend — per-slot prompt variable table (spec §5).
 *
 * leaf_id: COMP-RF-001 (WorkspaceSettings — admin configuration)
 * req_id:  REQ-L2-PT-001
 *
 * Renders, under one prompt editor, the variables that prompt actually uses:
 * its declared `data` variables (code-bound, documentation only) plus every
 * `config` variable its body references. Read-only by design — editing a
 * value happens in the central variable management section, so a value is
 * never editable in two places with two different scopes.
 *
 * All styles are hoisted module constants rather than inline object literals:
 * the `ui-ratchet` test asserts the project-wide `style={{` count with strict
 * equality, so a new component must not add any.
 */

import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";

import type {
  PromptVariableScope,
  PromptVariableState,
} from "../../api/prompt-variables";

export interface PromptVariableTableProps {
  /** Slot the table belongs to — only used to build stable data-testids. */
  slotName: string;
  /** Variable names this slot references, in display order. */
  variableNames: string[];
  /** The full catalog, as loaded once by the parent section. */
  variables: PromptVariableState[];
}

const wrapperStyle: CSSProperties = {
  marginTop: "var(--space-2)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  overflow: "hidden",
};

const tableStyle: CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: "var(--font-size-xs, 0.75rem)",
};

const headCellStyle: CSSProperties = {
  textAlign: "left",
  padding: "var(--space-1) var(--space-2)",
  background: "var(--color-surface-raised)",
  color: "var(--color-text-muted)",
  fontWeight: 600,
};

const cellStyle: CSSProperties = {
  padding: "var(--space-1) var(--space-2)",
  borderTop: "1px solid var(--color-border)",
  color: "var(--color-text)",
  verticalAlign: "top",
};

const monoCellStyle: CSSProperties = {
  ...cellStyle,
  fontFamily: "var(--font-mono, monospace)",
};

const badgeStyle: CSSProperties = {
  display: "inline-block",
  padding: "0 var(--space-2)",
  borderRadius: "var(--radius-sm, 4px)",
  border: "1px solid var(--color-border)",
  color: "var(--color-text-muted)",
  fontWeight: 500,
};

/** Render a variable value for display without collapsing falsy values. */
function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

export function PromptVariableTable({
  slotName,
  variableNames,
  variables,
}: PromptVariableTableProps): JSX.Element | null {
  const { t } = useTranslation();

  const byName = new Map(variables.map((v) => [v.name, v]));
  const rows = variableNames
    .map((name) => byName.get(name))
    .filter((v): v is PromptVariableState => v !== undefined);

  if (rows.length === 0) return null;

  const originLabel = (origin: PromptVariableScope): string => {
    if (origin === "workspace") {
      return t("settings.promptVariables.origin.workspace", "Workspace-Override");
    }
    if (origin === "global") {
      return t("settings.promptVariables.origin.global", "Globaler Standard");
    }
    return t("settings.promptVariables.origin.factory", "Werkseinstellung");
  };

  return (
    <div style={wrapperStyle} data-testid={`prompt-vars-${slotName}`}>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={headCellStyle}>
              {t("settings.promptVariables.columnName", "Variable")}
            </th>
            <th style={headCellStyle}>
              {t("settings.promptVariables.columnKind", "Art")}
            </th>
            <th style={headCellStyle}>
              {t("settings.promptVariables.columnType", "Typ")}
            </th>
            <th style={headCellStyle}>
              {t("settings.promptVariables.columnDescription", "Beschreibung")}
            </th>
            <th style={headCellStyle}>
              {t("settings.promptVariables.columnValue", "Effektiver Wert")}
            </th>
            <th style={headCellStyle}>
              {t("settings.promptVariables.columnOrigin", "Herkunft")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name} data-testid={`prompt-var-${slotName}-${row.name}`}>
              <td style={monoCellStyle}>{`{${row.name}}`}</td>
              <td style={cellStyle}>
                {row.kind === "config"
                  ? t("settings.promptVariables.kindConfig", "konfigurierbar")
                  : t("settings.promptVariables.kindData", "code-gebunden")}
              </td>
              <td style={cellStyle}>{row.var_type}</td>
              <td style={cellStyle}>{row.description}</td>
              <td style={monoCellStyle}>
                {row.kind === "config"
                  ? formatValue(row.effective_value)
                  : t(
                      "settings.promptVariables.computedValue",
                      "wird vom System berechnet"
                    )}
              </td>
              <td style={cellStyle}>
                <span
                  style={badgeStyle}
                  data-testid={`prompt-var-${slotName}-${row.name}-origin`}
                >
                  {row.kind === "config"
                    ? originLabel(row.effective_scope)
                    : t("settings.promptVariables.originCode", "Code")}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

In `frontend/src/components/WorkspaceSettings/AiPromptsSection.tsx`:

1. Add imports:

```tsx
import { promptVariablesApi, type PromptVariableState } from "../../api/prompt-variables";
import { PromptVariableTable } from "./PromptVariableTable";
```

2. Add hoisted style constants next to the existing ones:

```tsx
const warningStyle: React.CSSProperties = {
  marginTop: "var(--space-2)",
  padding: "var(--space-2) var(--space-3)",
  background: "var(--color-badge-warning-bg)",
  color: "var(--color-badge-warning-text)",
  borderRadius: "var(--radius-sm)",
  fontSize: "var(--font-size-sm)",
};
```

3. Add catalog state and load it alongside the slots — replace the `load` callback:

```tsx
  const [variables, setVariables] = useState<PromptVariableState[]>([]);

  const load = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      const [data, catalog] = await Promise.all([
        promptTemplatesApi.listSlots(workspaceId),
        promptVariablesApi.list(workspaceId),
      ]);
      setSlots(orderSlots(data.slots));
      setVariables(catalog.variables);
      setDrafts({});
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);
```

4. Inside the `orderedSlots.map(...)` render, directly after the button row's closing `</div>` and before the closing `</div>` of the slot block, insert:

```tsx
            <PromptVariableTable
              slotName={slot.name}
              variableNames={[...slot.data_variables, ...slot.config_variables]}
              variables={variables}
            />
            {slot.unknown_placeholders.length > 0 && (
              <p
                style={warningStyle}
                data-testid={`prompt-${slot.name}-unknown-placeholders`}
              >
                {t(
                  "settings.promptTemplates.unknownPlaceholders",
                  "Unbekannte Platzhalter — sie bleiben im Prompt-Text stehen:"
                )}{" "}
                {slot.unknown_placeholders.map((p) => `{${p}}`).join(", ")}
              </p>
            )}
```

5. In `frontend/src/components/WorkspaceSettings/AiPromptsSection.test.tsx`, extend the `slot()` helper's returned object with the three new fields and mock the new API module:

```tsx
vi.mock("../../api/prompt-variables", () => ({
  promptVariablesApi: {
    list: vi.fn().mockResolvedValue({ variables: [], count: 0, workspace_id: null }),
    save: vi.fn(),
    clear: vi.fn(),
  },
}));
```

```tsx
    data_variables: [],
    config_variables: [],
    unknown_placeholders: [],
```

6. Add these keys to BOTH `frontend/src/i18n/locales/de.json` and `en.json` under `settings` (parity test):

```json
    "promptVariables": {
      "title": "Prompt-Variablen",
      "description": "Zentral verwaltete Werte, die in Prompt-Texten als {name} referenziert werden. 'code-gebunden' bedeutet: der Wert wird vom System aus echten Artefaktdaten berechnet.",
      "columnName": "Variable",
      "columnKind": "Art",
      "columnType": "Typ",
      "columnDescription": "Beschreibung",
      "columnValue": "Effektiver Wert",
      "columnOrigin": "Herkunft",
      "kindConfig": "konfigurierbar",
      "kindData": "code-gebunden",
      "computedValue": "wird vom System berechnet",
      "originCode": "Code",
      "origin": {
        "workspace": "Workspace-Override",
        "global": "Globaler Standard",
        "factory": "Werkseinstellung"
      }
    }
```

and the English equivalents under the same paths in `en.json` (`"title": "Prompt Variables"`, `"kindConfig": "configurable"`, `"kindData": "code-bound"`, `"computedValue": "computed by the system"`, `"origin.workspace": "Workspace override"`, `"origin.global": "Global default"`, `"origin.factory": "Factory default"`), plus in both files under `settings.promptTemplates`:

```json
      "unknownPlaceholders": "Unbekannte Platzhalter — sie bleiben im Prompt-Text stehen:"
```
(EN: `"Unknown placeholders — they stay literally in the prompt text:"`)

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm frontend-test sh -c "npm install && npx vitest run src/test/PromptVariableTable.test.tsx src/components/WorkspaceSettings/AiPromptsSection.test.tsx src/test/i18n-parity.test.ts src/test/ui-ratchet.test.ts"`

Expected: PASS — if `ui-ratchet` reports a higher `style={{` count, an inline object literal slipped in; convert it to a hoisted constant rather than raising the baseline.

- [ ] **Step 5: Type-check the changed frontend surface**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm frontend-test sh -c "npm install && npx tsc -p tsconfig.build.json --noEmit"`

Expected: no new errors (this config, not the dirty default `tsconfig.json`, is the real gate)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/WorkspaceSettings/PromptVariableTable.tsx frontend/src/components/WorkspaceSettings/AiPromptsSection.tsx frontend/src/components/WorkspaceSettings/AiPromptsSection.test.tsx frontend/src/test/PromptVariableTable.test.tsx frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json
git commit -m "feat: show per-slot prompt variables and placeholder warnings"
```

---

### Task 18: Central variable management section

**Files:**
- Create: `frontend/src/components/WorkspaceSettings/PromptVariablesSection.tsx`
- Modify: `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx:36-38` (import), `:556-564` (mount on the `llm` tab)
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`
- Test: `frontend/src/test/PromptVariablesSection.test.tsx`

**Interfaces:**
- Consumes: `promptVariablesApi`, `PromptVariableState`, `PromptVariableType` (Task 16); `extractErrorMessage` (`frontend/src/api/client.ts`, existing).
- Produces:
  - `export interface PromptVariablesSectionProps { workspaceId: string }`
  - `export function PromptVariablesSection(props: PromptVariablesSectionProps): JSX.Element`
  - data-testids: `prompt-variables-section`, `prompt-variables-scope-select`, `prompt-variables-error`, `prompt-variable-row-<name>`, `prompt-variable-<name>-input`, `prompt-variable-<name>-save`, `prompt-variable-<name>-reset`, `prompt-variable-<name>-origin`, `prompt-variable-new-name`, `prompt-variable-new-type`, `prompt-variable-new-description`, `prompt-variable-new-value`, `prompt-variable-new-save`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/PromptVariablesSection.test.tsx`:

```tsx
/**
 * ARCH-L1-001 ReactFrontend — central prompt variable management (spec §5).
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PromptVariablesSection } from "../components/WorkspaceSettings/PromptVariablesSection";
import type { PromptVariableState } from "../api/prompt-variables";

vi.mock("react-i18next", () => {
  const t = (_key: string, fallback?: string): string => fallback ?? _key;
  return { useTranslation: () => ({ t }) };
});
vi.mock("../api/client", () => ({
  extractErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));

const list = vi.fn();
const save = vi.fn();
const clear = vi.fn();
vi.mock("../api/prompt-variables", () => ({
  promptVariablesApi: {
    list: (...args: unknown[]) => list(...args),
    save: (...args: unknown[]) => save(...args),
    clear: (...args: unknown[]) => clear(...args),
  },
}));

const WORKSPACE_ID = "11111111-1111-1111-1111-111111111111";

function variable(
  name: string,
  overrides: Partial<PromptVariableState> = {}
): PromptVariableState {
  return {
    name,
    kind: "config",
    var_type: "int",
    description: `desc ${name}`,
    factory_default: 5,
    global_value: null,
    global_version: null,
    workspace_value: null,
    workspace_version: null,
    has_workspace_override: false,
    effective_value: 5,
    effective_scope: "factory",
    is_editable: true,
    ...overrides,
  };
}

const VARIABLES: PromptVariableState[] = [
  variable("max_breadth"),
  variable("req_title", {
    kind: "data",
    var_type: "str",
    factory_default: "",
    effective_value: "",
    is_editable: false,
  }),
];

describe("PromptVariablesSection (spec §5)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    list.mockResolvedValue({
      variables: VARIABLES,
      count: VARIABLES.length,
      workspace_id: WORKSPACE_ID,
    });
    save.mockImplementation(async (name: string, value: unknown) =>
      variable(name, {
        workspace_value: value,
        workspace_version: 1,
        has_workspace_override: true,
        effective_value: value,
        effective_scope: "workspace",
      })
    );
    clear.mockImplementation(async (name: string) => variable(name));
  });

  it("lists every catalog variable", async () => {
    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);

    expect(
      await screen.findByTestId("prompt-variable-row-max_breadth")
    ).toBeTruthy();
    expect(screen.getByTestId("prompt-variable-row-req_title")).toBeTruthy();
  });

  it("renders data variables without an editable input", async () => {
    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);
    await screen.findByTestId("prompt-variable-row-req_title");

    expect(screen.queryByTestId("prompt-variable-req_title-input")).toBeNull();
    expect(screen.queryByTestId("prompt-variable-req_title-save")).toBeNull();
  });

  it("saves a config value as a workspace override", async () => {
    const user = userEvent.setup();
    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);
    const input = await screen.findByTestId("prompt-variable-max_breadth-input");

    await user.clear(input);
    await user.type(input, "2");
    await user.click(screen.getByTestId("prompt-variable-max_breadth-save"));

    await waitFor(() =>
      expect(save).toHaveBeenCalledWith("max_breadth", 2, WORKSPACE_ID)
    );
    expect(
      screen.getByTestId("prompt-variable-max_breadth-origin").textContent
    ).toContain("Workspace-Override");
  });

  it("writes the tenant default when the global scope is selected", async () => {
    const user = userEvent.setup();
    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);
    await screen.findByTestId("prompt-variable-max_breadth-input");

    await user.selectOptions(
      screen.getByTestId("prompt-variables-scope-select"),
      "global"
    );
    await user.click(screen.getByTestId("prompt-variable-max_breadth-save"));

    await waitFor(() =>
      expect(save).toHaveBeenCalledWith("max_breadth", 5, null)
    );
  });

  it("drops an override via reset", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue({
      variables: [
        variable("max_breadth", {
          workspace_value: 2,
          workspace_version: 1,
          has_workspace_override: true,
          effective_value: 2,
          effective_scope: "workspace",
        }),
      ],
      count: 1,
      workspace_id: WORKSPACE_ID,
    });
    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);
    await screen.findByTestId("prompt-variable-max_breadth-input");

    await user.click(screen.getByTestId("prompt-variable-max_breadth-reset"));

    await waitFor(() =>
      expect(clear).toHaveBeenCalledWith("max_breadth", WORKSPACE_ID)
    );
  });

  it("creates a brand-new config variable", async () => {
    const user = userEvent.setup();
    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);
    await screen.findByTestId("prompt-variable-new-name");

    await user.type(screen.getByTestId("prompt-variable-new-name"), "tone_hint");
    await user.selectOptions(screen.getByTestId("prompt-variable-new-type"), "str");
    await user.type(
      screen.getByTestId("prompt-variable-new-description"),
      "Style instruction."
    );
    await user.type(screen.getByTestId("prompt-variable-new-value"), "Be terse.");
    await user.click(screen.getByTestId("prompt-variable-new-save"));

    await waitFor(() =>
      expect(save).toHaveBeenCalledWith("tone_hint", "Be terse.", WORKSPACE_ID, {
        varType: "str",
        description: "Style instruction.",
      })
    );
  });

  it("surfaces a save error", async () => {
    const user = userEvent.setup();
    save.mockRejectedValue(new Error("boom"));
    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);
    await screen.findByTestId("prompt-variable-max_breadth-input");

    await user.click(screen.getByTestId("prompt-variable-max_breadth-save"));

    expect(
      (await screen.findByTestId("prompt-variables-error")).textContent
    ).toContain("boom");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm frontend-test sh -c "npm install && npx vitest run src/test/PromptVariablesSection.test.tsx"`

Expected: FAIL with `Failed to resolve import ".../PromptVariablesSection"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/WorkspaceSettings/PromptVariablesSection.tsx`:

```tsx
/**
 * ARCH-L1-001 ReactFrontend — central prompt variable management (spec §5).
 *
 * leaf_id: COMP-RF-001 (WorkspaceSettings — admin configuration)
 * req_id:  REQ-L2-PT-001
 *
 * The one place where a variable's value is edited, deliberately separate
 * from the per-slot tables in `AiPromptsSection`: a variable is shared by
 * every prompt that references it, so editing it inside one prompt's editor
 * would misrepresent the blast radius of the change.
 *
 * Scope switch mirrors `AiPromptsSection`: "workspace" writes an override for
 * the active workspace, "global" writes the tenant-wide default.
 * `kind: "data"` rows render read-only with a "code-bound" note.
 *
 * All styles are hoisted module constants (no inline `style={{` literals) —
 * the `ui-ratchet` test asserts the project-wide count with strict equality.
 */

import type { CSSProperties } from "react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { extractErrorMessage } from "../../api/client";
import {
  promptVariablesApi,
  type PromptVariableState,
  type PromptVariableType,
} from "../../api/prompt-variables";

export interface PromptVariablesSectionProps {
  /** Workspace whose overrides are edited when the scope is "workspace". */
  workspaceId: string;
}

/** Which scope the admin is currently editing. */
type EditScope = "workspace" | "global";

const VARIABLE_TYPES: readonly PromptVariableType[] = [
  "str",
  "int",
  "bool",
  "json",
] as const;

const sectionStyle: CSSProperties = {
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-lg)",
  padding: "var(--space-5)",
  marginBottom: "var(--space-5)",
  boxShadow: "var(--shadow-card)",
};

const headingStyle: CSSProperties = {
  fontSize: "var(--font-size-lg)",
  fontWeight: 600,
  color: "var(--color-text)",
  margin: "0 0 var(--space-4) 0",
};

const hintStyle: CSSProperties = {
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text-muted)",
  marginBottom: "var(--space-4)",
};

const rowStyle: CSSProperties = {
  display: "flex",
  alignItems: "flex-start",
  gap: "var(--space-3)",
  flexWrap: "wrap",
  padding: "var(--space-2) 0",
  borderTop: "1px solid var(--color-border)",
};

const nameStyle: CSSProperties = {
  fontFamily: "var(--font-mono, monospace)",
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text)",
  minWidth: "14rem",
};

const descriptionStyle: CSSProperties = {
  flex: 1,
  minWidth: "16rem",
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text-muted)",
};

const inputStyle: CSSProperties = {
  width: "10rem",
  padding: "var(--space-1) var(--space-2)",
  background: "var(--color-surface-raised)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

const selectStyle: CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  background: "var(--color-surface-raised)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

const primaryButtonStyle: CSSProperties = {
  background: "var(--color-primary)",
  color: "white",
  border: "none",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-1) var(--space-3)",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  cursor: "pointer",
};

const secondaryButtonStyle: CSSProperties = {
  background: "transparent",
  color: "var(--color-text-muted)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-1) var(--space-3)",
  fontSize: "var(--font-size-sm)",
  cursor: "pointer",
};

const badgeStyle: CSSProperties = {
  display: "inline-block",
  padding: "0 var(--space-2)",
  borderRadius: "var(--radius-sm, 4px)",
  border: "1px solid var(--color-border)",
  fontSize: "var(--font-size-xs, 0.75rem)",
  color: "var(--color-text-muted)",
  fontWeight: 500,
};

const errorStyle: CSSProperties = {
  color: "var(--color-danger)",
  marginBottom: "var(--space-3)",
};

const scopeRowStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "var(--space-3)",
  marginBottom: "var(--space-4)",
};

const createRowStyle: CSSProperties = {
  display: "flex",
  alignItems: "flex-end",
  gap: "var(--space-2)",
  flexWrap: "wrap",
  marginTop: "var(--space-4)",
  paddingTop: "var(--space-3)",
  borderTop: "1px solid var(--color-border)",
};

const labelStyle: CSSProperties = {
  display: "block",
  marginBottom: "var(--space-1)",
  fontWeight: 600,
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

/** The value shown for a variable at the scope currently being edited. */
function valueForScope(
  variable: PromptVariableState,
  scope: EditScope
): unknown {
  if (scope === "workspace") return variable.effective_value;
  return variable.global_value ?? variable.factory_default;
}

/** Where the shown value comes from, at the scope being edited. */
function originForScope(
  variable: PromptVariableState,
  scope: EditScope
): string {
  if (scope === "workspace") return variable.effective_scope;
  return variable.global_value === null ? "factory" : "global";
}

/** Turn the raw input text back into the variable's declared type. */
function parseValue(raw: string, varType: PromptVariableType): unknown {
  if (varType === "int") return Number.parseInt(raw, 10);
  if (varType === "bool") return raw === "true";
  if (varType === "json") {
    try {
      return JSON.parse(raw);
    } catch {
      return raw;
    }
  }
  return raw;
}

/** Render a value into the text an input field shows. */
function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

export function PromptVariablesSection({
  workspaceId,
}: PromptVariablesSectionProps): JSX.Element {
  const { t } = useTranslation();
  const [scope, setScope] = useState<EditScope>("workspace");
  const [variables, setVariables] = useState<PromptVariableState[]>([]);
  // Only variables the admin actually edited appear here — an absent entry
  // means "show whatever the server last reported".
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [busyName, setBusyName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState<PromptVariableType>("str");
  const [newDescription, setNewDescription] = useState("");
  const [newValue, setNewValue] = useState("");

  const load = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      const data = await promptVariablesApi.list(workspaceId);
      setVariables(data.variables);
      setDrafts({});
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const targetScopeId = (): string | null =>
    scope === "workspace" ? workspaceId : null;

  const handleScopeChange = (next: EditScope): void => {
    // Drafts are scope-specific: keeping them would carry a workspace edit
    // into a tenant-wide save.
    setScope(next);
    setDrafts({});
    setError(null);
  };

  /** Replace one variable in local state with the server's post-write truth. */
  const applyUpdated = (updated: PromptVariableState): void => {
    setVariables((prev) => {
      const exists = prev.some((v) => v.name === updated.name);
      return exists
        ? prev.map((v) => (v.name === updated.name ? updated : v))
        : [...prev, updated].sort((a, b) => a.name.localeCompare(b.name));
    });
    setDrafts((prev) => {
      const next = { ...prev };
      delete next[updated.name];
      return next;
    });
  };

  const handleSave = async (variable: PromptVariableState): Promise<void> => {
    setBusyName(variable.name);
    setError(null);
    try {
      const raw = drafts[variable.name] ?? displayValue(valueForScope(variable, scope));
      const updated = await promptVariablesApi.save(
        variable.name,
        parseValue(raw, variable.var_type),
        targetScopeId()
      );
      applyUpdated(updated);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusyName(null);
    }
  };

  const handleReset = async (variable: PromptVariableState): Promise<void> => {
    setBusyName(variable.name);
    setError(null);
    try {
      applyUpdated(await promptVariablesApi.clear(variable.name, targetScopeId()));
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusyName(null);
    }
  };

  const handleCreate = async (): Promise<void> => {
    const name = newName.trim();
    if (!name) return;
    setBusyName(name);
    setError(null);
    try {
      const updated = await promptVariablesApi.save(
        name,
        parseValue(newValue, newType),
        targetScopeId(),
        { varType: newType, description: newDescription }
      );
      applyUpdated(updated);
      setNewName("");
      setNewDescription("");
      setNewValue("");
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusyName(null);
    }
  };

  const originLabel = (origin: string): string => {
    if (origin === "workspace") {
      return t("settings.promptVariables.origin.workspace", "Workspace-Override");
    }
    if (origin === "global") {
      return t("settings.promptVariables.origin.global", "Globaler Standard");
    }
    return t("settings.promptVariables.origin.factory", "Werkseinstellung");
  };

  if (isLoading) {
    return (
      <section style={sectionStyle} data-testid="prompt-variables-section">
        <h3 style={headingStyle}>
          {t("settings.promptVariables.title", "Prompt-Variablen")}
        </h3>
        <p>{t("loading", "Loading...")}</p>
      </section>
    );
  }

  return (
    <section style={sectionStyle} data-testid="prompt-variables-section">
      <h3 style={headingStyle}>
        {t("settings.promptVariables.title", "Prompt-Variablen")}
      </h3>
      <p style={hintStyle}>
        {t(
          "settings.promptVariables.description",
          "Zentral verwaltete Werte, die in Prompt-Texten als {name} referenziert werden. 'code-gebunden' bedeutet: der Wert wird vom System aus echten Artefaktdaten berechnet."
        )}
      </p>

      <div style={scopeRowStyle}>
        <label htmlFor="prompt-variables-scope" style={labelStyle}>
          {t("settings.promptTemplates.scope", "Geltungsbereich")}
        </label>
        <select
          id="prompt-variables-scope"
          data-testid="prompt-variables-scope-select"
          value={scope}
          onChange={(e) => handleScopeChange(e.target.value as EditScope)}
          style={selectStyle}
        >
          <option value="workspace">
            {t("settings.promptTemplates.scopeWorkspace", "Nur dieser Workspace")}
          </option>
          <option value="global">
            {t("settings.promptTemplates.scopeGlobal", "Global (alle Workspaces)")}
          </option>
        </select>
      </div>

      {error && (
        <p data-testid="prompt-variables-error" style={errorStyle}>
          {error}
        </p>
      )}

      {variables.map((variable) => {
        const isBusy = busyName === variable.name;
        const origin = originForScope(variable, scope);
        const value = drafts[variable.name] ?? displayValue(valueForScope(variable, scope));
        return (
          <div
            key={variable.name}
            style={rowStyle}
            data-testid={`prompt-variable-row-${variable.name}`}
          >
            <span style={nameStyle}>{`{${variable.name}}`}</span>
            <span style={descriptionStyle}>{variable.description}</span>
            {variable.is_editable ? (
              <>
                <input
                  data-testid={`prompt-variable-${variable.name}-input`}
                  value={value}
                  disabled={isBusy}
                  onChange={(e) =>
                    setDrafts((prev) => ({ ...prev, [variable.name]: e.target.value }))
                  }
                  style={inputStyle}
                />
                <button
                  type="button"
                  data-testid={`prompt-variable-${variable.name}-save`}
                  onClick={() => void handleSave(variable)}
                  disabled={isBusy}
                  style={primaryButtonStyle}
                >
                  {t("save", "Save")}
                </button>
                <button
                  type="button"
                  data-testid={`prompt-variable-${variable.name}-reset`}
                  onClick={() => void handleReset(variable)}
                  disabled={isBusy || origin !== scope}
                  style={secondaryButtonStyle}
                >
                  {t("settings.promptTemplates.resetToGlobal", "Override entfernen")}
                </button>
                <span
                  style={badgeStyle}
                  data-testid={`prompt-variable-${variable.name}-origin`}
                >
                  {originLabel(origin)}
                </span>
              </>
            ) : (
              <span
                style={badgeStyle}
                data-testid={`prompt-variable-${variable.name}-origin`}
              >
                {t("settings.promptVariables.kindData", "code-gebunden")}
              </span>
            )}
          </div>
        );
      })}

      <div style={createRowStyle}>
        <label style={labelStyle} htmlFor="prompt-variable-new-name">
          {t("settings.promptVariables.newName", "Neue Variable")}
          <input
            id="prompt-variable-new-name"
            data-testid="prompt-variable-new-name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            style={inputStyle}
          />
        </label>
        <label style={labelStyle} htmlFor="prompt-variable-new-type">
          {t("settings.promptVariables.columnType", "Typ")}
          <select
            id="prompt-variable-new-type"
            data-testid="prompt-variable-new-type"
            value={newType}
            onChange={(e) => setNewType(e.target.value as PromptVariableType)}
            style={selectStyle}
          >
            {VARIABLE_TYPES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label style={labelStyle} htmlFor="prompt-variable-new-description">
          {t("settings.promptVariables.columnDescription", "Beschreibung")}
          <input
            id="prompt-variable-new-description"
            data-testid="prompt-variable-new-description"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            style={inputStyle}
          />
        </label>
        <label style={labelStyle} htmlFor="prompt-variable-new-value">
          {t("settings.promptVariables.columnValue", "Effektiver Wert")}
          <input
            id="prompt-variable-new-value"
            data-testid="prompt-variable-new-value"
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
            style={inputStyle}
          />
        </label>
        <button
          type="button"
          data-testid="prompt-variable-new-save"
          onClick={() => void handleCreate()}
          disabled={busyName !== null}
          style={primaryButtonStyle}
        >
          {t("settings.promptVariables.create", "Anlegen")}
        </button>
      </div>
    </section>
  );
}
```

In `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx`, add the import next to `AiPromptsSection`:

```tsx
import { PromptVariablesSection } from "./PromptVariablesSection";
```

and mount it on the `llm` tab, after `AiPromptsSection`:

```tsx
            <AiPromptsSection workspaceId={activeWorkspace.id} />
            {/* Prompt variable catalog (spec §5): the central place every
                {placeholder} value is managed, across all prompt slots. */}
            <PromptVariablesSection workspaceId={activeWorkspace.id} />
```

Add these keys to BOTH locale files under `settings.promptVariables` (parity test):

```json
      "newName": "Neue Variable",
      "create": "Anlegen"
```
(EN: `"newName": "New variable"`, `"create": "Create"`)

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm frontend-test sh -c "npm install && npx vitest run src/test/PromptVariablesSection.test.tsx src/components/WorkspaceSettings/WorkspaceSettings.test.tsx src/test/i18n-parity.test.ts src/test/ui-ratchet.test.ts"`

Expected: PASS (8 passed in the new file, no regressions elsewhere)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/WorkspaceSettings/PromptVariablesSection.tsx frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx frontend/src/test/PromptVariablesSection.test.tsx frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json
git commit -m "feat: add central prompt variable management section"
```

---

### Task 19: Rebuild the decompose panel around upper bounds

**Files:**
- Modify: `frontend/src/api/architectureDecompose.ts:56-76` (`GenerateDraftOptions` + request body)
- Modify: `frontend/src/components/ArchitectureDecompose/ArchitectureDecomposePanel.tsx:104-202` (state, defaults from the catalog, labels, help text)
- Modify: `frontend/src/test/ArchitectureDecomposePanel.test.tsx` (mock the catalog API)
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`
- Test: `frontend/src/test/ArchitectureDecomposeCaps.test.tsx`

**Interfaces:**
- Consumes: `promptVariablesApi.list` (Task 16); the REST contract of Task 13.
- Produces:
  - `export interface GenerateDraftOptions { maxBreadth?: number; maxDepth?: number }` — request body keys `max_breadth` / `max_depth`
  - `ArchitectureDecomposePanel` keeps its props (`workspaceId`, `element`, `onCommitted`) and its existing data-testids `arch-decompose-breadth` / `arch-decompose-depth` (stable E2E selectors), gains `arch-decompose-caps-hint`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/ArchitectureDecomposeCaps.test.tsx`:

```tsx
/**
 * ARCH-L1-001 ReactFrontend — decompose caps come from the catalog (spec §4).
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ArchitectureDecomposePanel } from "../components/ArchitectureDecompose/ArchitectureDecomposePanel";
import type { PromptVariableState } from "../api/prompt-variables";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../api/client", () => ({
  extractErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));

const generate = vi.fn();
const commit = vi.fn();
vi.mock("../api/architectureDecompose", () => ({
  architectureDecomposeApi: {
    generate: (...args: unknown[]) => generate(...args),
    commit: (...args: unknown[]) => commit(...args),
  },
}));

const listVariables = vi.fn();
vi.mock("../api/prompt-variables", () => ({
  promptVariablesApi: {
    list: (...args: unknown[]) => listVariables(...args),
    save: vi.fn(),
    clear: vi.fn(),
  },
}));

function capVariable(name: string, value: number): PromptVariableState {
  return {
    name,
    kind: "config",
    var_type: "int",
    description: `desc ${name}`,
    factory_default: value,
    global_value: null,
    global_version: null,
    workspace_value: null,
    workspace_version: null,
    has_workspace_override: false,
    effective_value: value,
    effective_scope: "factory",
    is_editable: true,
  };
}

function renderPanel() {
  return render(
    <ArchitectureDecomposePanel
      workspaceId="ws-1"
      element={{ id: "el-1", title: "Payment Subsystem" }}
    />
  );
}

describe("ArchitectureDecomposePanel caps (spec §4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listVariables.mockResolvedValue({
      variables: [capVariable("max_breadth", 5), capVariable("max_depth", 3)],
      count: 2,
      workspace_id: "ws-1",
    });
    generate.mockResolvedValue({
      workspace_id: "ws-1",
      root_element_id: "el-1",
      parent_requirement_id: "req-1",
      provider: "mock",
      degraded: false,
      nodes: [],
    });
  });

  it("seeds the inputs from the catalog instead of hard-coded 2/1", async () => {
    renderPanel();

    await waitFor(() =>
      expect(
        (screen.getByTestId("arch-decompose-breadth") as HTMLInputElement).value
      ).toBe("5")
    );
    expect(
      (screen.getByTestId("arch-decompose-depth") as HTMLInputElement).value
    ).toBe("3");
  });

  it("resolves the caps for the panel's workspace", async () => {
    renderPanel();

    await waitFor(() => expect(listVariables).toHaveBeenCalledWith("ws-1"));
  });

  it("sends the renamed cap parameters", async () => {
    const user = userEvent.setup();
    renderPanel();
    await waitFor(() =>
      expect(
        (screen.getByTestId("arch-decompose-breadth") as HTMLInputElement).value
      ).toBe("5")
    );

    await user.click(screen.getByTestId("arch-decompose-generate"));

    await waitFor(() =>
      expect(generate).toHaveBeenCalledWith("ws-1", "el-1", {
        maxBreadth: 5,
        maxDepth: 3,
      })
    );
  });

  it("explains that the numbers are upper bounds, not targets", async () => {
    renderPanel();

    expect(
      (await screen.findByTestId("arch-decompose-caps-hint")).textContent
    ).toContain("archDecompose.capsHint");
  });

  it("falls back to 5/3 when the catalog cannot be read", async () => {
    listVariables.mockRejectedValue(new Error("nope"));
    renderPanel();

    await waitFor(() =>
      expect(
        (screen.getByTestId("arch-decompose-breadth") as HTMLInputElement).value
      ).toBe("5")
    );
    expect(
      (screen.getByTestId("arch-decompose-depth") as HTMLInputElement).value
    ).toBe("3");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm frontend-test sh -c "npm install && npx vitest run src/test/ArchitectureDecomposeCaps.test.tsx"`

Expected: FAIL — the input still shows `2` and `generate` is called with `{ breadth, depth }`

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/api/architectureDecompose.ts`, replace `GenerateDraftOptions` and the `generate` body:

```ts
/**
 * Optional *upper bounds* for one decompose call (spec §4). Omitting a value
 * leaves the workspace's configured `max_breadth`/`max_depth` in force — the
 * AI decides the actual structure from the element's content.
 */
export interface GenerateDraftOptions {
  maxBreadth?: number;
  maxDepth?: number;
}

export const architectureDecomposeApi = {
  /** Generate a non-persistent decomposition draft for an ArchitectureElement. */
  generate(
    workspaceId: UUID,
    elementId: UUID,
    options: GenerateDraftOptions = {}
  ): Promise<DecompositionDraft> {
    return apiClient.post<DecompositionDraft>(
      `/workspaces/${workspaceId}/architecture/decompose/`,
      {
        element_id: elementId,
        ...(options.maxBreadth != null ? { max_breadth: options.maxBreadth } : {}),
        ...(options.maxDepth != null ? { max_depth: options.maxDepth } : {}),
      }
    );
  },

  /** Commit a reviewed draft in one transaction (rolled back on any failure). */
  commit(workspaceId: UUID, draft: DecompositionDraft): Promise<CommitResult> {
    return apiClient.post<CommitResult>(
      `/workspaces/${workspaceId}/architecture/decompose/commit/`,
      { draft }
    );
  },
};
```

In `frontend/src/components/ArchitectureDecompose/ArchitectureDecomposePanel.tsx`:

1. Add the import and two fallback constants:

```tsx
import { promptVariablesApi } from "../../api/prompt-variables";

/**
 * Used only when the variable catalog cannot be read (e.g. a non-admin user
 * whose token cannot list prompt variables). Matches the backend factory
 * defaults so the panel behaves identically either way.
 */
const FALLBACK_MAX_BREADTH = 5;
const FALLBACK_MAX_DEPTH = 3;

/** Read one int-valued config variable out of a catalog listing. */
function capFromCatalog(
  variables: { name: string; effective_value: unknown }[],
  name: string,
  fallback: number
): number {
  const found = variables.find((v) => v.name === name);
  const value = Number(found?.effective_value);
  return Number.isFinite(value) && value >= 1 ? value : fallback;
}
```

2. Replace the two `useState` initialisers and add a catalog effect:

```tsx
  const [maxBreadth, setMaxBreadth] = useState<number>(FALLBACK_MAX_BREADTH);
  const [maxDepth, setMaxDepth] = useState<number>(FALLBACK_MAX_DEPTH);

  // Defaults come from the variable catalog (spec §4) rather than hard-coded
  // 2/1, so a workspace that raised its caps sees them here too. A failure is
  // silent on purpose: the fallbacks equal the backend factory values, so the
  // panel stays usable instead of blocking on an admin-only read.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const catalog = await promptVariablesApi.list(workspaceId);
        if (cancelled) return;
        setMaxBreadth(
          capFromCatalog(catalog.variables, "max_breadth", FALLBACK_MAX_BREADTH)
        );
        setMaxDepth(
          capFromCatalog(catalog.variables, "max_depth", FALLBACK_MAX_DEPTH)
        );
      } catch {
        // Keep the fallbacks.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);
```

(add `useEffect` to the existing `react` import).

3. Replace `handleGenerate`'s API call and dependency list:

```tsx
      const next = await architectureDecomposeApi.generate(
        workspaceId,
        element.id,
        { maxBreadth, maxDepth }
      );
```
```tsx
  }, [workspaceId, element.id, maxBreadth, maxDepth]);
```

4. Replace the two number fields and add the hint (note: `max` upper bounds are dropped — the ceiling is admin policy now):

```tsx
        <label style={styles.field}>
          <span style={styles.muted}>{t("archDecompose.maxBreadth")}</span>
          <input
            type="number"
            min={1}
            value={maxBreadth}
            disabled={busy}
            onChange={(e) => setMaxBreadth(Number(e.target.value))}
            style={styles.numberInput}
            data-testid="arch-decompose-breadth"
          />
        </label>
        <label style={styles.field}>
          <span style={styles.muted}>{t("archDecompose.maxDepth")}</span>
          <input
            type="number"
            min={1}
            value={maxDepth}
            disabled={busy}
            onChange={(e) => setMaxDepth(Number(e.target.value))}
            style={styles.numberInput}
            data-testid="arch-decompose-depth"
          />
        </label>
```

and directly after the closing `</div>` of `styles.controls`:

```tsx
      <p style={styles.muted} data-testid="arch-decompose-caps-hint">
        {t("archDecompose.capsHint")}
      </p>
```

5. In `frontend/src/test/ArchitectureDecomposePanel.test.tsx`, add the catalog mock so the existing suite keeps passing:

```tsx
vi.mock("../api/prompt-variables", () => ({
  promptVariablesApi: {
    list: vi.fn().mockResolvedValue({ variables: [], count: 0, workspace_id: null }),
    save: vi.fn(),
    clear: vi.fn(),
  },
}));
```

6. In BOTH locale files, replace the `archDecompose.breadth`/`archDecompose.depth` keys with the new ones (removing the old keys keeps the parity test and the UI honest):

de.json:
```json
    "maxBreadth": "Max. Kinder je Ebene",
    "maxDepth": "Max. Ebenen",
    "capsHint": "Die KI entscheidet anhand des Inhalts, wie viele Kind-Elemente und Ebenen fachlich sinnvoll sind. Diese Zahlen sind nur Obergrenzen, keine Zielvorgabe.",
```

en.json:
```json
    "maxBreadth": "Max. children per level",
    "maxDepth": "Max. levels",
    "capsHint": "The AI decides from the content how many child elements and levels are justified. These numbers are upper bounds only, not a target.",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm frontend-test sh -c "npm install && npx vitest run src/test/ArchitectureDecomposeCaps.test.tsx src/test/ArchitectureDecomposePanel.test.tsx src/test/i18n-parity.test.ts src/test/ui-ratchet.test.ts"`

Expected: PASS (5 passed in the new file, no regressions)

- [ ] **Step 5: Type-check and run the whole frontend suite**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm frontend-test sh -c "npm install && npx tsc -p tsconfig.build.json --noEmit && npm test"`

Expected: no type errors, no new test failures

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/architectureDecompose.ts frontend/src/components/ArchitectureDecompose/ArchitectureDecomposePanel.tsx frontend/src/test/ArchitectureDecomposeCaps.test.tsx frontend/src/test/ArchitectureDecomposePanel.test.tsx frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json
git commit -m "feat: present decompose numbers as upper bounds from the catalog"
```

---

## Final verification (after Task 19)

- [ ] **Backend suite**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test`

Expected: no failures beyond the pre-existing red set on `main` — capture the baseline before starting the branch and diff against it.

- [ ] **Frontend suite**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm frontend-test`

Expected: all green (including `i18n-parity` and `ui-ratchet`)

- [ ] **Migration check**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test python manage.py makemigrations --check --dry-run`

Expected: `No changes detected`

- [ ] **MCP manifest check**

Run: `docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test pytest mcp_server/tests/test_tool_manifest_drift.py -q`

Expected: PASS

- [ ] **Manual browser walkthrough** (UI changes were made, so this is required)

1. `docker-compose up -d`, log in as an admin.
2. Workspace Settings → tab "LLM & Prompts": the `architecture_decompose_tree` slot now has its own editor; every editor shows a variable table underneath with Name/Art/Typ/Beschreibung/Wert/Herkunft.
3. Type `{typo_here}` into a prompt body, save: the warning line appears and the text is still saved.
4. Scroll to "Prompt-Variablen": change `max_breadth` to 2 at workspace scope, save — badge flips to "Workspace-Override".
5. Create a variable `tone_hint` (type `str`), reference `{tone_hint}` in the `testcase_derive` body, save: the warning disappears and the variable shows in that slot's table.
6. Open an architecture element → "KI-Zerlegung": the fields read "Max. Kinder je Ebene"/"Max. Ebenen", are pre-filled with 2/3, and the hint text explains they are upper bounds. Generate a draft and confirm it holds within the caps.
7. Check both viewports (desktop ~1440px and ~768px) for table overflow.

- [ ] **Hand the branch to the `git` agent** for the PR (do not push from the implementing session).
