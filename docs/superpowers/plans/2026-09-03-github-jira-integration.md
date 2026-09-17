# GitHub- und Jira-Anbindung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-stage GitHub/Jira bridge — link-only external references, inbound webhook-driven state sync, and outbound issue creation plus agent tools — on top of the existing Artifact/TraceLink/Workflow/Outbox foundation.

**Architecture:** A new Django app `backend/integrations/` (Ext layer, same shape as `diagram/`, `icd/`, `test_runs/`) owns three tables (`ExternalRef`, `IntegrationConfig`, `ExternalSystemCredential`), a service facade, two public webhook receiver views, and two outbound adapters. `ExternalRef` is Artifact-backed (own `pl_artifact` row with `artifact_type="ExternalRef"`) so a `references` TraceLink can point at it. Inbound events resolve tenant from a config id in the URL, arm the tenant context explicitly (no auth layer runs on a public endpoint), then update `last_seen_status` and optionally fire a workflow transition declared as `external_trigger` on the transition itself. Outbound reuses the already-wired `DomainEventBus` subscriber path that `WebhookDispatcher` proved.

**Tech Stack:** Django 5.2 + DRF, PostgreSQL 16 with RLS, `requests` (already pinned in `backend/requirements.txt`), `cryptography`/Fernet via `persistence.encryption`, React 18 + TypeScript strict, i18next, pytest + vitest.

**Spec:** docs/superpowers/specs/2026-09-03-github-jira-integration-design.md

## Global Constraints

- Shell aliases used in every `Run:` line below (define them once per session):
  - `PYTEST='docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest'`
  - `VITEST='docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c'`
  - `MANAGE='docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py'`
- Branch policy: work on `feat/github-jira-integration`. Never commit on `main`.
- Commit messages: Conventional Commits, English, imperative, max 72 chars in the first line.
- **Spec dependency order:** specs 1–7 of the audit series ship before this one. This plan consumes, and does not re-implement: `LinkType` catalog + `references` link type (spec 3), `AuthContext.actor_type` / `ApiKey.scope` / `TraceLink.proposed_by`/`proposed_at` (spec 4), `ARTIFACT_CREATION_ADAPTERS` + grounding seam (spec 5), `integration.*` group name reserved in the MCP manifest filter (spec 7).
- Every DRF view must run under an armed tenant context. The two webhook receivers have **no** authentication class, so they arm it themselves via `persistence.middleware.set_request_tenant` / `clear_request_tenant` in a `try/finally` — `TenantContext.set_tenant` alone is not enough (it satisfies the ORM filter but leaves the Postgres RLS session variable unset).
- No direct ORM in `rest_api/*_views.py` or `mcp_server/tools/*.py` — the ratchet in `backend/rest_api/tests/test_architecture.py` enforces a 0 ceiling for new files.
- Every new `operation=` string passed to `ServiceBase._audit` / `write_mcp_audit` must be added to `AuditEntry.OP_CHOICES` (`backend/audit/models.py:194`), guarded by `backend/audit/tests/test_op_vocabulary.py`. Reuse `create` / `delete` / `transition` wherever a REST pendant exists.
- Every new MCP tool is WRITE-gated by default (fail-closed). Read-only tools must be listed explicitly in `_READ_ONLY_TOOL_NAMES` (`backend/mcp_server/tool_registry.py:205`) and every new tool needs an entry in `_TOOL_TARGETS` (`backend/mcp_server/workspace_scope.py:103`) or must require `workspace_id`.
- Frontend: named exports only, kebab-case file names for new non-component modules, `data-testid` on every interactive element, colours/sizes only from `styles/tokens.css` custom properties (no hex literals, no `color: "white"`, no `rgba()`).
- New tables are tenant-scoped (`TenantScopedModel`) and each needs its RLS policy migration; DDL runs as the DB owner, which the test overlay already uses.
- Secrets: never log a Jira webhook URL query string, never log a PAT, never put a token in an error message.

## OPEN QUESTIONS

1. **`WorkflowHistoryEntry` has no actor columns.** `backend/workflow/models.py:237` declares only `transitioned_by: CharField`. Spec 8 §4.2 requires `actor_type="system"` + `client_name` there, and spec 4 (KI-Vorschlag) §4.2 assumes the same two columns exist — but spec 4's own migration list (§7) never adds them. Ownership is therefore undefined across the two specs. **Default taken here (non-blocking):** Task 17 of this plan adds `actor_type` + `client_name` to `WorkflowHistoryEntry`. If spec 4's implementation already added them, Task 17 collapses to only the `AuditEntry.ACTOR_TYPE_SYSTEM` half — verify with `grep -n "actor_type" backend/workflow/models.py` before starting the task.

## Deviations from the spec (decided, not open)

- **Webhook route carries the config id:** `POST /api/v1/integrations/{github,jira}/webhook/<uuid:config_id>/` instead of the spec's bare `.../webhook/`. Reason: the receiver is unauthenticated, so nothing supplies a tenant; without a discriminator the server would have to HMAC every payload against every tenant's secret (an O(all-tenants) crypto scan and a cross-tenant oracle), and no RLS-guarded query can run before a tenant is armed. The config id is not a credential — the HMAC secret (GitHub) / query token (Jira) still authenticates.
- **`ExternalRef.repo` added** (not in the spec's model sketch). Without it, `external_id="142"` matches issue 142 of *every* connected repository on the inbound path. `repo` holds `owner/repo` for GitHub and the project key for Jira.
- **`ExternalSystemCredential.api_base_url` + `account_email` added.** Jira Cloud authenticates with `email:token` Basic auth against a per-tenant host; GitHub Enterprise needs a base URL. The spec's four fields cannot address a Jira instance at all.
- **No webhook delivery-dedup table.** Re-delivery is made harmless instead: the status write is an idempotent upsert and the trigger is skipped when `current_state` already equals the target. A dedup table would be a whole entity for a case the two existing guards already cover.
- **`system_transition` refuses `signature_gate: true` transitions.** A system actor cannot produce a signature seal; failing closed is the only safe reading of the spec's "kein `allowed_roles`-Check".

## File Structure

```
backend/integrations/
  __init__.py
  apps.py                      # IntegrationsConfig, ready() wires the outbound subscriber
  constants.py                 # SYSTEM_CHOICES, KIND_CHOICES, SYSTEM_GITHUB, SYSTEM_JIRA
  models.py                    # ExternalRef, IntegrationConfig, ExternalSystemCredential
  url_parser.py                # parse_external_url -> ParsedExternalUrl
  dto.py                       # ExternalRefDTO
  service.py                   # ExternalRefService (link/list/unlink)
  config_service.py            # IntegrationConfigService, CredentialService
  signatures.py                # verify_github_signature, verify_jira_token
  events.py                    # NormalizedExternalEvent, normalize_github_event, normalize_jira_event
  triggers.py                  # find_external_trigger_target
  inbound.py                   # InboundIntegrationService.apply_event
  adapters.py                  # GitHubIssueAdapter, JiraIssueAdapter, ADAPTERS
  outbound.py                  # OutboundIntegrationSubscriber (event-bus)
  outbound_tools.py            # service functions behind the integration.* MCP tools
  serializers.py               # DRF serializers for the three models
  rest.py                      # authenticated REST views
  webhook_views.py             # the two public receivers
  throttling.py                # WebhookInRateThrottle
  urls.py                      # url patterns, included from rest_api/urls.py
  migrations/0001_initial.py                        # ExternalRef
  migrations/0002_rls_policies.py                   # int_external_ref
  migrations/0003_references_external_ref_pair.py   # link-type amendment backfill
  migrations/0004_integration_config.py
  migrations/0005_integration_config_rls.py
  migrations/0006_external_credential.py
  migrations/0007_external_credential_rls.py
  tests/__init__.py
  tests/conftest.py            # tenant/workspace/ctx/requirement/workflow fixtures
  tests/test_models.py
  tests/test_rls_policies.py
  tests/test_url_parser.py
  tests/test_references_pair.py
  tests/test_external_ref_service.py
  tests/test_resolver_registration.py
  tests/test_rest_external_refs.py
  tests/test_mcp_external_refs.py
  tests/test_integration_config_model.py
  tests/test_signatures.py
  tests/test_events.py
  tests/test_system_actor_type.py
  tests/test_triggers.py
  tests/test_inbound.py
  tests/test_webhook_views.py
  tests/test_config_rest.py
  tests/test_credentials.py
  tests/test_adapters.py
  tests/test_outbound.py
  tests/test_mcp_integration_tools.py
  tests/test_grounding.py
  tests/test_mismatches.py
  tests/test_smoke_stage_coverage.py

backend/mcp_server/tools/integration.py            # IntegrationToolGroup (4 tools)
backend/workflow/tests/test_system_transition.py

frontend/src/api/integrations.ts
frontend/src/api/integrations.test.ts
frontend/src/components/shared/ExternalRefChip.tsx
frontend/src/components/shared/LinkExternalDialog.tsx
frontend/src/components/shared/ArtifactInspector/ExternalPanel.tsx
frontend/src/components/shared/ArtifactInspector/ExternalPanel.module.css
frontend/src/components/SystemSettings/IntegrationsTab.tsx
frontend/src/components/DashboardViews/ExternalMismatchCard.tsx
```

---

# Stage 1 — Link-Only

### Task 1: `integrations` app skeleton and `ExternalRef` model

**Files:**
- Create: `backend/integrations/__init__.py`
- Create: `backend/integrations/apps.py`
- Create: `backend/integrations/constants.py`
- Create: `backend/integrations/models.py`
- Create: `backend/integrations/migrations/__init__.py`
- Create: `backend/integrations/tests/__init__.py`
- Create: `backend/integrations/tests/test_models.py`
- Modify: `backend/reqogniloom/settings.py` (add `"integrations"` to `INSTALLED_APPS`)

**Interfaces:**
- Consumes: `persistence.models.TenantScopedModel`, `persistence.models.Artifact`, `persistence.models.Workspace`
- Produces: `integrations.constants.SYSTEM_GITHUB`, `SYSTEM_JIRA`, `SYSTEM_CHOICES`, `KIND_CHOICES`; `integrations.models.ExternalRef`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_models.py
"""ExternalRef persistence contract."""
from __future__ import annotations

import uuid

import pytest
from django.db.utils import IntegrityError

from integrations.constants import SYSTEM_GITHUB
from integrations.models import ExternalRef
from persistence.models import Artifact, Tenant, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture()
def workspace(db):
    tenant = Tenant.objects.create(name="t-extref")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws-extref")
    yield ws
    TenantContext.clear_tenant()


def _artifact(workspace, artifact_type: str) -> Artifact:
    return Artifact.objects.create(
        tenant=workspace.tenant, workspace=workspace, artifact_type=artifact_type
    )


@pytest.mark.django_db
def test_external_ref_is_artifact_backed(workspace):
    subject = _artifact(workspace, "Requirement")
    backing = _artifact(workspace, "ExternalRef")

    ref = ExternalRef.objects.create(
        tenant=workspace.tenant,
        artifact=subject,
        backing_artifact=backing,
        system=SYSTEM_GITHUB,
        repo="acme/widgets",
        external_id="142",
        url="https://github.com/acme/widgets/issues/142",
        kind="issue",
    )

    assert backing.external_ref == ref
    assert list(subject.external_refs.all()) == [ref]


@pytest.mark.django_db
def test_same_target_cannot_be_linked_twice(workspace):
    subject = _artifact(workspace, "Requirement")
    common = dict(
        tenant=workspace.tenant,
        artifact=subject,
        system=SYSTEM_GITHUB,
        repo="acme/widgets",
        external_id="142",
        url="https://github.com/acme/widgets/issues/142",
        kind="issue",
    )
    ExternalRef.objects.create(backing_artifact=_artifact(workspace, "ExternalRef"), **common)

    with pytest.raises(IntegrityError):
        ExternalRef.objects.create(
            backing_artifact=_artifact(workspace, "ExternalRef"), **common
        )


@pytest.mark.django_db
def test_external_id_is_scoped_per_repo(workspace):
    subject = _artifact(workspace, "Requirement")
    for repo in ("acme/widgets", "acme/gadgets"):
        ExternalRef.objects.create(
            tenant=workspace.tenant,
            artifact=subject,
            backing_artifact=_artifact(workspace, "ExternalRef"),
            system=SYSTEM_GITHUB,
            repo=repo,
            external_id="142",
            url=f"https://github.com/{repo}/issues/142",
            kind="issue",
        )
    assert ExternalRef.objects.filter(artifact=subject).count() == 2
    assert uuid.UUID(str(subject.id))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_models.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'integrations'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/integrations/__init__.py
```

```python
# backend/integrations/apps.py
"""App configuration for the GitHub/Jira integration subsystem."""
from __future__ import annotations

from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    """External-system integration (GitHub, Jira).

    Owns ExternalRef (Artifact-backed external reference), IntegrationConfig
    (per-workspace inbound/outbound configuration) and
    ExternalSystemCredential (per-workspace PAT, Fernet-encrypted).
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations"
    verbose_name = "External System Integration"
```

```python
# backend/integrations/constants.py
"""Shared vocabulary for the integration subsystem."""
from __future__ import annotations

SYSTEM_GITHUB = "github"
SYSTEM_JIRA = "jira"

SYSTEM_CHOICES = [
    (SYSTEM_GITHUB, "GitHub"),
    (SYSTEM_JIRA, "Jira"),
]

KIND_ISSUE = "issue"
KIND_PR = "pr"
KIND_EPIC = "epic"

KIND_CHOICES = [
    (KIND_ISSUE, "Issue"),
    (KIND_PR, "Pull Request"),
    (KIND_EPIC, "Epic"),
]

#: ``Artifact.artifact_type`` of the dedicated row backing an ExternalRef.
EXTERNAL_REF_ARTIFACT_TYPE = "ExternalRef"

__all__ = [
    "EXTERNAL_REF_ARTIFACT_TYPE",
    "KIND_CHOICES",
    "KIND_EPIC",
    "KIND_ISSUE",
    "KIND_PR",
    "SYSTEM_CHOICES",
    "SYSTEM_GITHUB",
    "SYSTEM_JIRA",
]
```

```python
# backend/integrations/models.py
"""Persistence for the GitHub/Jira integration subsystem."""
from __future__ import annotations

from django.db import models

from integrations.constants import KIND_CHOICES, SYSTEM_CHOICES
from persistence.models import TenantScopedModel


class ExternalRef(TenantScopedModel):
    """A link from a ReqogniLoom artifact to an issue/PR/epic in GitHub or Jira.

    Two Artifact relations on purpose:

    * ``artifact`` is the ReqogniLoom artifact being linked (Requirement,
      Issue, ...).
    * ``backing_artifact`` is a dedicated ``pl_artifact`` row with
      ``artifact_type="ExternalRef"``. ``TraceLink.source``/``.target`` always
      point at an Artifact, so a ``references`` link can only reach an
      external reference through a backing row of its own.

    ``repo`` is not in the design sketch but is load-bearing: GitHub issue
    numbers are per-repository and Jira keys are per-project, so
    ``external_id`` alone would match the wrong object on the inbound path
    as soon as a workspace connects a second repository.
    """

    artifact = models.ForeignKey(
        "persistence.Artifact",
        on_delete=models.CASCADE,
        related_name="external_refs",
    )
    backing_artifact = models.OneToOneField(
        "persistence.Artifact",
        on_delete=models.CASCADE,
        related_name="external_ref",
    )
    system = models.CharField(max_length=32, choices=SYSTEM_CHOICES)
    repo = models.CharField(
        max_length=255,
        blank=True,
        help_text="GitHub 'owner/repo' or Jira project key.",
    )
    external_id = models.CharField(max_length=128)
    url = models.URLField(max_length=2048)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    last_seen_status = models.CharField(max_length=64, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "int_external_ref"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "artifact", "system", "repo", "external_id"],
                name="uq_external_ref_target",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "system", "repo", "external_id"],
                name="idx_extref_lookup",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.system}:{self.repo}#{self.external_id}"


__all__ = ["ExternalRef"]
```

In `backend/reqogniloom/settings.py`, add `"integrations",` to `INSTALLED_APPS` directly after the `"icd",` entry.

Then generate the migration:

Run: `$MANAGE makemigrations integrations`
Expected: creates `backend/integrations/migrations/0001_initial.py`

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_models.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations backend/reqogniloom/settings.py
git commit -m "feat: add integrations app with ExternalRef model"
```

---

### Task 2: Row-Level-Security policy for `int_external_ref`

**Files:**
- Create: `backend/integrations/migrations/0002_rls_policies.py`
- Create: `backend/integrations/tests/test_rls_policies.py`

**Interfaces:**
- Consumes: `persistence.middleware.set_request_tenant`, `clear_request_tenant`
- Produces: policy `int_external_ref_tenant_isolation`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_rls_policies.py
"""RLS backstop for int_external_ref (defense-in-depth layer 2)."""
from __future__ import annotations

import pytest
from django.db import connection

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Tenant, Workspace


@pytest.mark.django_db(transaction=True)
def test_external_ref_rows_are_invisible_to_another_tenant():
    from integrations.models import ExternalRef

    tenant_a = Tenant.objects.create(name="rls-a")
    tenant_b = Tenant.objects.create(name="rls-b")

    set_request_tenant(tenant_a.id)
    try:
        ws = Workspace.objects.create(tenant=tenant_a, name="ws-a")
        ExternalRef.objects.create(
            tenant=tenant_a,
            artifact=Artifact.objects.create(
                tenant=tenant_a, workspace=ws, artifact_type="Requirement"
            ),
            backing_artifact=Artifact.objects.create(
                tenant=tenant_a, workspace=ws, artifact_type="ExternalRef"
            ),
            system="github",
            repo="acme/widgets",
            external_id="1",
            url="https://github.com/acme/widgets/issues/1",
            kind="issue",
        )
    finally:
        clear_request_tenant()

    set_request_tenant(tenant_b.id)
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT count(*) FROM int_external_ref")
            assert cur.fetchone()[0] == 0, (
                "RLS must hide another tenant's ExternalRef rows even on raw SQL"
            )
    finally:
        clear_request_tenant()


@pytest.mark.django_db(transaction=True)
def test_policy_exists():
    with connection.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_policies "
            "WHERE tablename = 'int_external_ref' "
            "AND policyname = 'int_external_ref_tenant_isolation'"
        )
        assert cur.fetchone()[0] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_rls_policies.py -q`
Expected: FAIL — `assert 1 == 0` on the raw-SQL count (no policy, rows visible) and `assert 0 == 1` on the policy lookup

- [ ] **Step 3: Write minimal implementation**

```python
# backend/integrations/migrations/0002_rls_policies.py
"""COMP-PL-006 RLS backstop for the integration tables.

Layer 1 (TenantManager) already filters every ORM read; this is the DB-level
second layer required for every tenant-scoped table (ADR-03,
persistence/migrations/0003_rls_policies.py). ``app.current_tenant`` is set per
request by ``persistence.middleware.set_request_tenant``; an unset value
matches no rows.
"""
from __future__ import annotations

from django.db import migrations

_TENANT_TABLES = ["int_external_ref"]


def _enable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
            f"CREATE POLICY {policy} ON {table}\n"
            f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
            f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
        )
    return "\n".join(parts)


def _disable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"DROP POLICY IF EXISTS {policy} ON {table};\n"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )
    return "\n".join(parts)


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0001_initial"),
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_rls_policies.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations/migrations/0002_rls_policies.py backend/integrations/tests/test_rls_policies.py
git commit -m "feat: add RLS policy for int_external_ref"
```

---

### Task 3: GitHub/Jira URL parser

**Files:**
- Create: `backend/integrations/url_parser.py`
- Create: `backend/integrations/tests/test_url_parser.py`

**Interfaces:**
- Consumes: `integrations.constants.SYSTEM_GITHUB`, `SYSTEM_JIRA`, `KIND_ISSUE`, `KIND_PR`
- Produces: `integrations.url_parser.ParsedExternalUrl(system, repo, external_id, kind, url)`, `parse_external_url(url: str) -> ParsedExternalUrl`, `ExternalUrlError`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_url_parser.py
"""URL-paste parsing: the only entry point users touch in stage 1."""
from __future__ import annotations

import pytest

from integrations.url_parser import ExternalUrlError, parse_external_url


@pytest.mark.parametrize(
    "url,system,repo,external_id,kind",
    [
        (
            "https://github.com/acme/widgets/issues/142",
            "github",
            "acme/widgets",
            "142",
            "issue",
        ),
        (
            "https://github.com/acme/widgets/pull/7",
            "github",
            "acme/widgets",
            "7",
            "pr",
        ),
        (
            "https://github.com/acme/widgets/issues/142#issuecomment-9",
            "github",
            "acme/widgets",
            "142",
            "issue",
        ),
        (
            "https://acme.atlassian.net/browse/PROJ-42",
            "jira",
            "PROJ",
            "PROJ-42",
            "issue",
        ),
        (
            "https://jira.acme.example/browse/ABC-1?filter=x",
            "jira",
            "ABC",
            "ABC-1",
            "issue",
        ),
    ],
)
def test_recognised_urls(url, system, repo, external_id, kind):
    parsed = parse_external_url(url)
    assert (parsed.system, parsed.repo, parsed.external_id, parsed.kind) == (
        system,
        repo,
        external_id,
        kind,
    )


def test_trailing_whitespace_is_tolerated():
    parsed = parse_external_url("  https://github.com/acme/widgets/issues/9  ")
    assert parsed.url == "https://github.com/acme/widgets/issues/9"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not-a-url",
        "https://github.com/acme/widgets",
        "https://github.com/acme/widgets/issues/abc",
        "https://example.com/browse/PROJ-42",
        "javascript:alert(1)",
    ],
)
def test_unrecognised_urls_raise(url):
    with pytest.raises(ExternalUrlError):
        parse_external_url(url)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_url_parser.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'integrations.url_parser'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/integrations/url_parser.py
"""Parse a pasted GitHub/Jira URL into the fields ExternalRef stores.

Deliberately pattern-based and offline: pasting a link must not depend on a
credential being configured, and stage 1 is "visibility without sync".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from integrations.constants import KIND_ISSUE, KIND_PR, SYSTEM_GITHUB, SYSTEM_JIRA


class ExternalUrlError(ValueError):
    """Raised when a URL matches no known GitHub/Jira shape."""


@dataclass(frozen=True)
class ParsedExternalUrl:
    """Result of :func:`parse_external_url`."""

    system: str
    repo: str
    external_id: str
    kind: str
    url: str


_GITHUB_RE = re.compile(
    r"^/(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<kind>issues|pull)/(?P<number>\d+)/?$"
)
_JIRA_RE = re.compile(r"^/browse/(?P<key>(?P<project>[A-Z][A-Z0-9_]+)-\d+)/?$")

_GITHUB_KIND = {"issues": KIND_ISSUE, "pull": KIND_PR}


def parse_external_url(url: str) -> ParsedExternalUrl:
    """Return the ExternalRef fields encoded in *url*.

    Args:
        url: A GitHub issue/PR URL or a Jira browse URL, with or without
            surrounding whitespace, query string or fragment.

    Returns:
        The parsed reference. ``url`` on the result is normalised: whitespace
        stripped, query and fragment removed, so the same target always
        produces the same stored URL.

    Raises:
        ExternalUrlError: The URL is empty, not http(s), or matches neither
            the GitHub nor the Jira shape.
    """
    candidate = (url or "").strip()
    if not candidate:
        raise ExternalUrlError("URL is empty")

    parts = urlsplit(candidate)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ExternalUrlError(f"Unsupported URL scheme: {candidate!r}")

    normalised = f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"
    host = parts.netloc.lower().split(":")[0]

    if host in ("github.com", "www.github.com"):
        match = _GITHUB_RE.match(parts.path)
        if match is None:
            raise ExternalUrlError(f"Not a GitHub issue or pull-request URL: {candidate!r}")
        return ParsedExternalUrl(
            system=SYSTEM_GITHUB,
            repo=f"{match['owner']}/{match['repo']}",
            external_id=match["number"],
            kind=_GITHUB_KIND[match["kind"]],
            url=normalised,
        )

    match = _JIRA_RE.match(parts.path)
    if match is not None:
        return ParsedExternalUrl(
            system=SYSTEM_JIRA,
            repo=match["project"],
            external_id=match["key"],
            kind=KIND_ISSUE,
            url=normalised,
        )

    raise ExternalUrlError(f"Unrecognised external URL: {candidate!r}")


__all__ = ["ExternalUrlError", "ParsedExternalUrl", "parse_external_url"]
```

Note: `test_unrecognised_urls_raise` includes `https://example.com/browse/PROJ-42`, which the Jira branch *would* match on path alone. Keep it failing by requiring a Jira-shaped host — extend the Jira branch guard to `if match is not None and ("atlassian.net" in host or "jira" in host):` before returning, and let anything else fall through to the final `raise`.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_url_parser.py -q`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations/url_parser.py backend/integrations/tests/test_url_parser.py
git commit -m "feat: parse GitHub and Jira URLs into ExternalRef fields"
```

---

### Task 4: `references` link-type target amendment

**Files:**
- Modify: `backend/link_types/seed_data.py` (add the `ExternalRef` pair to the `references` entry created by spec 3)
- Create: `backend/integrations/migrations/0003_references_external_ref_pair.py`
- Create: `backend/integrations/tests/test_references_pair.py`

**Interfaces:**
- Consumes: `link_types.models.GlobalLinkTypeDefinition`, `link_types.models.WorkspaceLinkTypeDefinition` (spec 3)
- Produces: `references.allowed_pairs` contains `{"source_type": "*", "target_type": "ExternalRef"}` in every seeded global row and every non-customized workspace copy

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_references_pair.py
"""Traceability-Semantik amendment: 'references' must accept ExternalRef.

The traceability spec (2026-09-03-traceability-semantik-design.md, §3.2)
lists GlossaryTerm/Diagram/Icd; the amendment recorded in that same section
adds ExternalRef. Without the pair, TraceLinkService.create_trace_link
rejects the link every ExternalRef needs.
"""
from __future__ import annotations

import pytest

from link_types.models import GlobalLinkTypeDefinition, WorkspaceLinkTypeDefinition
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext

_PAIR = {"source_type": "*", "target_type": "ExternalRef"}


@pytest.mark.django_db
def test_seeded_global_references_accepts_external_ref():
    tenant = Tenant.objects.create(name="t-refpair")
    TenantContext.set_tenant(tenant.id)
    try:
        from link_types.services import bootstrap_global_definitions

        bootstrap_global_definitions(tenant_id=tenant.id)
        row = GlobalLinkTypeDefinition.objects.get(key="references")
        assert _PAIR in row.definition_json["allowed_pairs"]
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_workspace_copy_inherits_the_pair():
    tenant = Tenant.objects.create(name="t-refpair-ws")
    TenantContext.set_tenant(tenant.id)
    try:
        from link_types.services import bootstrap_global_definitions, resolve_for_workspace

        bootstrap_global_definitions(tenant_id=tenant.id)
        ws = Workspace.objects.create(tenant=tenant, name="ws")
        resolve_for_workspace(workspace_id=ws.id)
        row = WorkspaceLinkTypeDefinition.objects.get(workspace_id=ws.id, key="references")
        assert _PAIR in row.definition_json["allowed_pairs"]
    finally:
        TenantContext.clear_tenant()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_references_pair.py -q`
Expected: FAIL with `assert {'source_type': '*', 'target_type': 'ExternalRef'} in [...]`

- [ ] **Step 3: Write minimal implementation**

In `backend/link_types/seed_data.py`, extend the `references` entry's `allowed_pairs` list with the fourth pair:

```python
        "allowed_pairs": [
            {"source_type": "*", "target_type": "GlossaryTerm"},
            {"source_type": "*", "target_type": "Diagram"},
            {"source_type": "*", "target_type": "Icd"},
            # Amendment (GitHub/Jira integration spec §3.1): ExternalRef is a
            # fourth Artifact-backed reference target, same shape as the three
            # above.
            {"source_type": "*", "target_type": "ExternalRef"},
        ],
```

```python
# backend/integrations/migrations/0003_references_external_ref_pair.py
"""Backfill the 'references' -> ExternalRef pair into already-seeded rows.

The seed constant change only affects tenants bootstrapped after it. This
migration adds the pair to existing GlobalLinkTypeDefinition rows and to every
WorkspaceLinkTypeDefinition copy that has not been customized — customized
copies belong to their workspace admin and are left untouched, exactly like
every other propagation in the link-type/workflow/attribute inheritance seam.
"""
from __future__ import annotations

from django.db import migrations

_PAIR = {"source_type": "*", "target_type": "ExternalRef"}


def _add_pair(definition_json: dict) -> bool:
    pairs = definition_json.setdefault("allowed_pairs", [])
    if _PAIR in pairs:
        return False
    pairs.append(_PAIR)
    return True


def forwards(apps, schema_editor):
    GlobalLinkTypeDefinition = apps.get_model("link_types", "GlobalLinkTypeDefinition")
    WorkspaceLinkTypeDefinition = apps.get_model(
        "link_types", "WorkspaceLinkTypeDefinition"
    )

    for row in GlobalLinkTypeDefinition.objects.filter(key="references"):
        if _add_pair(row.definition_json):
            row.save(update_fields=["definition_json"])

    for row in WorkspaceLinkTypeDefinition.objects.filter(
        key="references", is_customized=False
    ):
        if _add_pair(row.definition_json):
            row.save(update_fields=["definition_json"])


def backwards(apps, schema_editor):
    GlobalLinkTypeDefinition = apps.get_model("link_types", "GlobalLinkTypeDefinition")
    WorkspaceLinkTypeDefinition = apps.get_model(
        "link_types", "WorkspaceLinkTypeDefinition"
    )
    for model in (GlobalLinkTypeDefinition, WorkspaceLinkTypeDefinition):
        for row in model.objects.filter(key="references"):
            pairs = row.definition_json.get("allowed_pairs", [])
            if _PAIR in pairs:
                pairs.remove(_PAIR)
                row.save(update_fields=["definition_json"])


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0002_rls_policies"),
        ("link_types", "0001_initial"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_references_pair.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/link_types/seed_data.py backend/integrations/migrations/0003_references_external_ref_pair.py backend/integrations/tests/test_references_pair.py
git commit -m "feat: allow references links to target ExternalRef"
```

---

### Task 5: `ExternalRefService.link_external`

**Files:**
- Create: `backend/integrations/dto.py`
- Create: `backend/integrations/service.py`
- Create: `backend/integrations/tests/test_external_ref_service.py`

**Interfaces:**
- Consumes: `application.base.ServiceBase`, `application.trace_link_service.TraceLinkService.resolve_entity_to_artifact_id(entity_id, ctx)` and `.create_trace_link(source_id, target_id, link_type, ctx)`, `integrations.url_parser.parse_external_url`
- Produces: `integrations.dto.ExternalRefDTO`, `integrations.service.ExternalRefService.link_external(ctx, *, artifact_id: UUID, url: str) -> ExternalRefDTO`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_external_ref_service.py
"""ExternalRefService: backing artifact + references link in one transaction."""
from __future__ import annotations

import pytest

from application.base import ValidationError
from integrations.constants import EXTERNAL_REF_ARTIFACT_TYPE
from integrations.models import ExternalRef
from integrations.service import ExternalRefService
from persistence.models import Artifact, TraceLink


@pytest.mark.django_db
def test_link_external_creates_backing_artifact_and_reference_link(
    editor_ctx, requirement
):
    dto = ExternalRefService().link_external(
        editor_ctx,
        artifact_id=requirement.id,
        url="https://github.com/acme/widgets/issues/142",
    )

    ref = ExternalRef.objects.get(id=dto.id)
    assert ref.system == "github"
    assert ref.repo == "acme/widgets"
    assert ref.external_id == "142"
    assert ref.kind == "issue"

    backing = Artifact.objects.get(id=ref.backing_artifact_id)
    assert backing.artifact_type == EXTERNAL_REF_ARTIFACT_TYPE
    assert backing.workspace_id == requirement.artifact.workspace_id

    assert TraceLink.objects.filter(
        source_id=requirement.artifact_id,
        target_id=backing.id,
        link_type="references",
    ).exists()


@pytest.mark.django_db
def test_link_external_accepts_a_raw_artifact_id(editor_ctx, requirement):
    dto = ExternalRefService().link_external(
        editor_ctx,
        artifact_id=requirement.artifact_id,
        url="https://github.com/acme/widgets/issues/7",
    )
    assert str(dto.artifact_id) == str(requirement.artifact_id)


@pytest.mark.django_db
def test_link_external_rejects_an_unparseable_url(editor_ctx, requirement):
    with pytest.raises(ValidationError):
        ExternalRefService().link_external(
            editor_ctx, artifact_id=requirement.id, url="https://example.com/nope"
        )
    assert not ExternalRef.objects.exists()


@pytest.mark.django_db
def test_link_external_rolls_back_completely_on_link_failure(
    editor_ctx, requirement, monkeypatch
):
    from application import trace_link_service

    def boom(*args, **kwargs):
        raise RuntimeError("link engine down")

    monkeypatch.setattr(
        trace_link_service.TraceLinkService, "create_trace_link", boom
    )

    with pytest.raises(RuntimeError):
        ExternalRefService().link_external(
            editor_ctx,
            artifact_id=requirement.id,
            url="https://github.com/acme/widgets/issues/8",
        )

    assert not ExternalRef.objects.exists()
    assert not Artifact.objects.filter(
        artifact_type=EXTERNAL_REF_ARTIFACT_TYPE
    ).exists(), "the backing artifact must not survive a failed link"


@pytest.mark.django_db
def test_link_external_marks_agent_authored_links_as_proposed(agent_ctx, requirement):
    """Spec §5.2: an agent-created ExternalRef link is a proposal (spec 4 §5)."""
    dto = ExternalRefService().link_external(
        agent_ctx,
        artifact_id=requirement.id,
        url="https://github.com/acme/widgets/issues/11",
    )
    link = TraceLink.objects.get(target_id=dto.backing_artifact_id)
    assert link.proposed_by_id == agent_ctx.api_key_id
    assert link.proposed_at is not None
```

Add the shared fixtures used above:

```python
# backend/integrations/tests/conftest.py
"""Fixtures shared by the integrations test modules."""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, Workspace


@pytest.fixture()
def tenant(db):
    return Tenant.objects.create(name=f"t-{uuid.uuid4().hex[:8]}")


@pytest.fixture()
def armed_tenant(tenant):
    set_request_tenant(tenant.id)
    yield tenant
    clear_request_tenant()


@pytest.fixture()
def workspace(armed_tenant):
    return Workspace.objects.create(tenant=armed_tenant, name="ws")


@pytest.fixture()
def editor_ctx(workspace):
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=workspace.tenant_id,
        active_roles=("editor",),
        auth_method=AuthMethod.JWT,
        workspace_id=workspace.id,
    )


@pytest.fixture()
def agent_ctx(workspace):
    """An API-key principal acting as an agent (spec 4 §3)."""
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=workspace.tenant_id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid.uuid4(),
        workspace_id=workspace.id,
        actor_type="agent",
    )


@pytest.fixture()
def requirement(workspace):
    artifact = Artifact.objects.create(
        tenant=workspace.tenant, workspace=workspace, artifact_type="Requirement"
    )
    return Requirement.objects.create(
        tenant=workspace.tenant,
        artifact=artifact,
        workspace=workspace,
        title="Linked requirement",
        description="",
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_external_ref_service.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'integrations.service'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/integrations/dto.py
"""Transport-agnostic shapes returned by the integration services."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from uuid import UUID


@dataclass(frozen=True)
class ExternalRefDTO:
    """One external reference, ready for REST/MCP serialisation."""

    id: UUID
    artifact_id: UUID
    backing_artifact_id: UUID
    system: str
    repo: str
    external_id: str
    url: str
    kind: str
    last_seen_status: str
    synced_at: Optional[datetime]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe mapping.

        Every UUID and datetime is stringified here: the MCP transport
        serialises tool payloads with stdlib ``json.dumps``, which raises on
        both types (DRF hides this because its encoder handles them).
        """
        return {
            "id": str(self.id),
            "artifact_id": str(self.artifact_id),
            "backing_artifact_id": str(self.backing_artifact_id),
            "system": self.system,
            "repo": self.repo,
            "external_id": self.external_id,
            "url": self.url,
            "kind": self.kind,
            "last_seen_status": self.last_seen_status,
            "synced_at": self.synced_at.isoformat() if self.synced_at else None,
        }


__all__ = ["ExternalRefDTO"]
```

```python
# backend/integrations/service.py
"""ExternalRefService — stage 1 of the GitHub/Jira bridge (link-only).

ADR-01: this module is the single entry point for external references. REST
views (integrations/rest.py) and MCP tools (mcp_server/tools/integration.py)
call it and never touch the ORM themselves.
"""
from __future__ import annotations

import logging
from uuid import UUID

from django.db import transaction

from application.base import NotFoundError, ServiceBase, ValidationError
from application.trace_link_service import TraceLinkService
from integrations.constants import EXTERNAL_REF_ARTIFACT_TYPE
from integrations.dto import ExternalRefDTO
from integrations.models import ExternalRef
from integrations.url_parser import ExternalUrlError, parse_external_url

logger = logging.getLogger(__name__)

#: Link type connecting an artifact to its ExternalRef backing artifact.
#: Amended into the catalog by integrations/migrations/0003.
REFERENCES_LINK_TYPE = "references"


def _to_dto(ref: ExternalRef) -> ExternalRefDTO:
    return ExternalRefDTO(
        id=ref.id,
        artifact_id=ref.artifact_id,
        backing_artifact_id=ref.backing_artifact_id,
        system=ref.system,
        repo=ref.repo,
        external_id=ref.external_id,
        url=ref.url,
        kind=ref.kind,
        last_seen_status=ref.last_seen_status,
        synced_at=ref.synced_at,
    )


class ExternalRefService(ServiceBase):
    """Create, list and remove links to GitHub/Jira objects."""

    def __init__(self) -> None:
        self._trace_links = TraceLinkService()

    def link_external(self, ctx, *, artifact_id: UUID, url: str) -> ExternalRefDTO:
        """Link the artifact behind *artifact_id* to the object *url* names.

        *artifact_id* may be an ``Artifact`` id or a domain-entity id
        (``Requirement.id``, ``Adr.id``, ...) — both id spaces reach the same
        artifact through ``TraceLinkService.resolve_entity_to_artifact_id``,
        so callers never have to know which one they hold (#414).

        Args:
            ctx: Resolved AuthContext; must carry a write-capable role.
            artifact_id: Artifact or domain-entity id to attach the link to.
            url: Pasted GitHub issue/PR or Jira browse URL.

        Returns:
            The created reference.

        Raises:
            ValidationError: *url* matches no known GitHub/Jira shape, or the
                same target is already linked to this artifact.
            NotFoundError: *artifact_id* resolves to nothing in this tenant.
            PermissionDeniedError: *ctx* has no write role.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        try:
            parsed = parse_external_url(url)
        except ExternalUrlError as exc:
            raise ValidationError(str(exc)) from exc

        from persistence.models import Artifact

        resolved_id = self._trace_links.resolve_entity_to_artifact_id(artifact_id, ctx)
        subject = Artifact.objects.filter(id=resolved_id).first()
        if subject is None:
            raise NotFoundError(f"Artifact {artifact_id} not found")

        if ExternalRef.objects.filter(
            artifact_id=subject.id,
            system=parsed.system,
            repo=parsed.repo,
            external_id=parsed.external_id,
        ).exists():
            raise ValidationError(
                f"{parsed.system} {parsed.repo}#{parsed.external_id} "
                "is already linked to this artifact"
            )

        with transaction.atomic():
            backing = Artifact.objects.create(
                tenant_id=ctx.tenant_id,
                workspace_id=subject.workspace_id,
                artifact_type=EXTERNAL_REF_ARTIFACT_TYPE,
            )
            ref = ExternalRef.objects.create(
                tenant_id=ctx.tenant_id,
                artifact=subject,
                backing_artifact=backing,
                system=parsed.system,
                repo=parsed.repo,
                external_id=parsed.external_id,
                url=parsed.url,
                kind=parsed.kind,
            )
            self._trace_links.create_trace_link(
                subject.id, backing.id, REFERENCES_LINK_TYPE, ctx
            )
            self._audit(ctx, "create", "ExternalRef", ref.id, details=ref.url)

        return _to_dto(ref)


__all__ = ["ExternalRefService", "REFERENCES_LINK_TYPE"]
```

Fix the `_audit` call to match its signature (`details` is a dict): use `details={"url": ref.url, "system": ref.system}`.

The `proposed_by`/`proposed_at` expectation of the last test is satisfied by `TraceLinkService.create_trace_link` itself (spec 4 §5 makes it set both when `ctx.actor_type == "agent"`); no code here.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_external_ref_service.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations/dto.py backend/integrations/service.py backend/integrations/tests/
git commit -m "feat: add ExternalRefService.link_external"
```

---

### Task 6: `list_external` and `unlink_external`

**Files:**
- Modify: `backend/integrations/service.py` (add two methods)
- Modify: `backend/integrations/tests/test_external_ref_service.py` (append)

**Interfaces:**
- Consumes: `ExternalRefService.link_external` (Task 5)
- Produces: `ExternalRefService.list_external(ctx, *, artifact_id: UUID) -> list[ExternalRefDTO]`, `ExternalRefService.unlink_external(ctx, *, external_ref_id: UUID) -> None`

- [ ] **Step 1: Write the failing test**

```python
# appended to backend/integrations/tests/test_external_ref_service.py
@pytest.mark.django_db
def test_list_external_returns_refs_for_either_id_space(editor_ctx, requirement):
    service = ExternalRefService()
    service.link_external(
        editor_ctx,
        artifact_id=requirement.id,
        url="https://github.com/acme/widgets/issues/1",
    )
    service.link_external(
        editor_ctx,
        artifact_id=requirement.id,
        url="https://acme.atlassian.net/browse/PROJ-9",
    )

    by_domain_id = service.list_external(editor_ctx, artifact_id=requirement.id)
    by_artifact_id = service.list_external(
        editor_ctx, artifact_id=requirement.artifact_id
    )

    assert {r.external_id for r in by_domain_id} == {"1", "PROJ-9"}
    assert [r.id for r in by_domain_id] == [r.id for r in by_artifact_id]


@pytest.mark.django_db
def test_list_external_is_empty_for_an_unlinked_artifact(editor_ctx, requirement):
    assert ExternalRefService().list_external(
        editor_ctx, artifact_id=requirement.id
    ) == []


@pytest.mark.django_db
def test_unlink_external_removes_ref_backing_artifact_and_link(
    editor_ctx, requirement
):
    service = ExternalRefService()
    dto = service.link_external(
        editor_ctx,
        artifact_id=requirement.id,
        url="https://github.com/acme/widgets/issues/3",
    )

    service.unlink_external(editor_ctx, external_ref_id=dto.id)

    assert not ExternalRef.objects.filter(id=dto.id).exists()
    assert not Artifact.objects.filter(id=dto.backing_artifact_id).exists()
    assert not TraceLink.objects.filter(target_id=dto.backing_artifact_id).exists()


@pytest.mark.django_db
def test_unlink_external_raises_for_an_unknown_id(editor_ctx):
    import uuid as _uuid

    from application.base import NotFoundError

    with pytest.raises(NotFoundError):
        ExternalRefService().unlink_external(
            editor_ctx, external_ref_id=_uuid.uuid4()
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_external_ref_service.py -q -k "list_external or unlink"`
Expected: FAIL with `AttributeError: 'ExternalRefService' object has no attribute 'list_external'`

- [ ] **Step 3: Write minimal implementation**

```python
# appended to the ExternalRefService class in backend/integrations/service.py
    def list_external(self, ctx, *, artifact_id: UUID) -> list[ExternalRefDTO]:
        """Return every external reference attached to *artifact_id*.

        Accepts an Artifact id or a domain-entity id, like
        :meth:`link_external`. Ordering is stable (system, then external id)
        so the UI chip row does not reshuffle between reloads.

        Raises:
            NotFoundError: *artifact_id* resolves to nothing in this tenant.
        """
        self._set_tenant_context(ctx)
        resolved_id = self._trace_links.resolve_entity_to_artifact_id(artifact_id, ctx)
        rows = ExternalRef.objects.filter(artifact_id=resolved_id).order_by(
            "system", "repo", "external_id"
        )
        return [_to_dto(row) for row in rows]

    def unlink_external(self, ctx, *, external_ref_id: UUID) -> None:
        """Delete an external reference and everything that only exists for it.

        Deleting the backing Artifact cascades to the ``references`` TraceLink
        and to the ExternalRef row itself, so this is one DELETE, not three —
        and no orphan can survive a partial failure.

        Raises:
            NotFoundError: no such reference in this tenant.
            PermissionDeniedError: *ctx* has no write role.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        from persistence.models import Artifact

        ref = ExternalRef.objects.filter(id=external_ref_id).first()
        if ref is None:
            raise NotFoundError(f"ExternalRef {external_ref_id} not found")

        backing_id = ref.backing_artifact_id
        with transaction.atomic():
            self._audit(
                ctx,
                "delete",
                "ExternalRef",
                ref.id,
                details={"url": ref.url, "system": ref.system},
            )
            Artifact.objects.filter(id=backing_id).delete()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_external_ref_service.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations/service.py backend/integrations/tests/test_external_ref_service.py
git commit -m "feat: add list and unlink to ExternalRefService"
```

---

### Task 7: Register `ExternalRef` in the workspace and artifact resolvers

**Files:**
- Modify: `backend/application/workspace_lookup.py:69-100` (`ENTITY_SPECS`)
- Modify: `backend/traceability/service.py:497-543` (`_domain_model_registry`)
- Create: `backend/integrations/tests/test_resolver_registration.py`

**Interfaces:**
- Consumes: `application.workspace_lookup.resolve_owning_workspace_id`, `traceability.service.resolve_artifacts`
- Produces: entity key `"external_ref"` resolvable by workspace; `resolve_artifacts` returns `entity_type="ExternalRef"` for a backing artifact

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_resolver_registration.py
"""ExternalRef must be resolvable by both cross-cutting id resolvers.

Without the workspace_lookup entry the MCP workspace-scope gate cannot scope
a tool call that names an external_ref_id; without the traceability registry
entry a 'references' link to an ExternalRef renders as an unresolved node.
"""
from __future__ import annotations

import pytest

from application.workspace_lookup import ENTITY_SPECS, resolve_owning_workspace_id
from integrations.service import ExternalRefService
from traceability.service import resolve_artifacts


def test_external_ref_is_a_known_entity_key():
    assert "external_ref" in ENTITY_SPECS
    assert ENTITY_SPECS["external_ref"].workspace_field == "artifact__workspace_id"


@pytest.mark.django_db
def test_workspace_resolves_from_an_external_ref_id(editor_ctx, requirement, workspace):
    dto = ExternalRefService().link_external(
        editor_ctx,
        artifact_id=requirement.id,
        url="https://github.com/acme/widgets/issues/21",
    )
    assert str(resolve_owning_workspace_id("external_ref", dto.id)) == str(workspace.id)


@pytest.mark.django_db
def test_backing_artifact_resolves_to_the_external_ref(editor_ctx, requirement):
    dto = ExternalRefService().link_external(
        editor_ctx,
        artifact_id=requirement.id,
        url="https://github.com/acme/widgets/issues/22",
    )
    resolved = resolve_artifacts([dto.backing_artifact_id], editor_ctx.tenant_id)
    assert len(resolved) == 1
    assert resolved[0].resolved is True
    assert resolved[0].entity_type == "ExternalRef"
    assert resolved[0].entity_id == str(dto.id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_resolver_registration.py -q`
Expected: FAIL with `assert 'external_ref' in {...}`

- [ ] **Step 3: Write minimal implementation**

In `backend/application/workspace_lookup.py`, add to `ENTITY_SPECS` after the `"diagram"` entry:

```python
    # GitHub/Jira integration: ExternalRef carries no workspace column of its
    # own — it lives in the workspace of the artifact it annotates.
    "external_ref": EntityWorkspaceSpec(
        "integrations.models.ExternalRef",
        workspace_field="artifact__workspace_id",
    ),
```

In `backend/traceability/service.py::_domain_model_registry`, import and append the tenth entry:

```python
    from integrations.models import ExternalRef
```

```python
        ("MainGoal", MainGoal, False),
        # GitHub/Jira integration: the backing artifact of an external
        # reference. TenantScopedModel, so True like the four persistence
        # models above.
        ("ExternalRef", ExternalRef, True),
    ]
```

`ExternalRef` is *not* added to `ARTIFACT_BACKED_ENTITY_KEYS` — that tuple is the probe order for tools that take an `artifact_id` meaning "a domain entity a user names", and no tool takes an ExternalRef id under an `artifact_id` parameter.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_resolver_registration.py traceability/tests -q`
Expected: PASS (3 passed in the new module, no regression in `traceability/tests`)

- [ ] **Step 5: Commit**

```bash
git add backend/application/workspace_lookup.py backend/traceability/service.py backend/integrations/tests/test_resolver_registration.py
git commit -m "feat: register ExternalRef in workspace and artifact resolvers"
```

---

### Task 8: REST endpoints for external references

**Files:**
- Create: `backend/integrations/serializers.py`
- Create: `backend/integrations/rest.py`
- Create: `backend/integrations/urls.py`
- Modify: `backend/rest_api/urls.py:672` (include the integrations urls just before `path("", include(router.urls))`)
- Create: `backend/integrations/tests/test_rest_external_refs.py`

**Interfaces:**
- Consumes: `integrations.service.ExternalRefService`
- Produces: `GET/POST /api/v1/artifacts/<uuid:artifact_id>/external-refs/`, `DELETE /api/v1/external-refs/<uuid:pk>/`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_rest_external_refs.py
"""REST surface for stage 1."""
from __future__ import annotations

import uuid

import pytest


@pytest.mark.django_db
def test_post_creates_a_reference(api_client_editor, requirement):
    response = api_client_editor.post(
        f"/api/v1/artifacts/{requirement.id}/external-refs/",
        {"url": "https://github.com/acme/widgets/issues/142"},
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["system"] == "github"
    assert response.data["repo"] == "acme/widgets"
    assert response.data["external_id"] == "142"
    assert response.data["kind"] == "issue"


@pytest.mark.django_db
def test_get_lists_references(api_client_editor, requirement):
    api_client_editor.post(
        f"/api/v1/artifacts/{requirement.id}/external-refs/",
        {"url": "https://github.com/acme/widgets/issues/1"},
        format="json",
    )
    response = api_client_editor.get(
        f"/api/v1/artifacts/{requirement.id}/external-refs/"
    )
    assert response.status_code == 200
    assert [r["external_id"] for r in response.data] == ["1"]


@pytest.mark.django_db
def test_post_with_an_unparseable_url_is_400(api_client_editor, requirement):
    response = api_client_editor.post(
        f"/api/v1/artifacts/{requirement.id}/external-refs/",
        {"url": "https://example.com/nope"},
        format="json",
    )
    assert response.status_code == 400
    assert response.data["error"]["code"]


@pytest.mark.django_db
def test_delete_removes_the_reference(api_client_editor, requirement):
    created = api_client_editor.post(
        f"/api/v1/artifacts/{requirement.id}/external-refs/",
        {"url": "https://github.com/acme/widgets/issues/5"},
        format="json",
    )
    response = api_client_editor.delete(
        f"/api/v1/external-refs/{created.data['id']}/"
    )
    assert response.status_code == 204
    assert (
        api_client_editor.get(
            f"/api/v1/artifacts/{requirement.id}/external-refs/"
        ).data
        == []
    )


@pytest.mark.django_db
def test_delete_of_an_unknown_id_is_404(api_client_editor):
    response = api_client_editor.delete(f"/api/v1/external-refs/{uuid.uuid4()}/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_anonymous_access_is_401(api_client_anonymous, requirement):
    response = api_client_anonymous.get(
        f"/api/v1/artifacts/{requirement.id}/external-refs/"
    )
    assert response.status_code == 401
```

Reuse the authenticated client fixtures already provided by `backend/rest_api/tests/conftest.py`; import them into the integrations test package by adding to `backend/integrations/tests/conftest.py`:

```python
pytest_plugins = ["rest_api.tests.conftest"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_rest_external_refs.py -q`
Expected: FAIL — all six with 404 (route not registered)

- [ ] **Step 3: Write minimal implementation**

```python
# backend/integrations/serializers.py
"""DRF serializers for the integration subsystem."""
from __future__ import annotations

from rest_framework import serializers


class ExternalRefSerializer(serializers.Serializer):
    """Read shape of an ExternalRefDTO."""

    id = serializers.UUIDField(read_only=True)
    artifact_id = serializers.UUIDField(read_only=True)
    backing_artifact_id = serializers.UUIDField(read_only=True)
    system = serializers.CharField(read_only=True)
    repo = serializers.CharField(read_only=True)
    external_id = serializers.CharField(read_only=True)
    url = serializers.CharField(read_only=True)
    kind = serializers.CharField(read_only=True)
    last_seen_status = serializers.CharField(read_only=True)
    synced_at = serializers.DateTimeField(read_only=True, allow_null=True)


class ExternalRefCreateSerializer(serializers.Serializer):
    """Write shape: one pasted URL, everything else is derived server-side."""

    url = serializers.CharField(max_length=2048)


__all__ = ["ExternalRefCreateSerializer", "ExternalRefSerializer"]
```

```python
# backend/integrations/rest.py
"""Authenticated REST views for the integration subsystem.

Every view delegates to integrations.service / integrations.config_service —
no ORM access here (ADR-01, mirrors the rest_api ratchet even though this
module sits outside its scan).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.serializers import ExternalRefCreateSerializer, ExternalRefSerializer
from integrations.service import ExternalRefService


class ArtifactExternalRefsView(APIView):
    """``/api/v1/artifacts/<artifact_id>/external-refs/`` — list and create."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = ExternalRefService()

    def get(self, request: Request, artifact_id: UUID, **kwargs: Any) -> Response:
        """Return every external reference attached to the artifact."""
        refs = self._service.list_external(
            request.auth_context, artifact_id=artifact_id
        )
        return Response(ExternalRefSerializer([r.to_dict() for r in refs], many=True).data)

    def post(self, request: Request, artifact_id: UUID, **kwargs: Any) -> Response:
        """Create a reference from a pasted GitHub/Jira URL."""
        payload = ExternalRefCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        dto = self._service.link_external(
            request.auth_context,
            artifact_id=artifact_id,
            url=payload.validated_data["url"],
        )
        return Response(
            ExternalRefSerializer(dto.to_dict()).data, status=status.HTTP_201_CREATED
        )


class ExternalRefDetailView(APIView):
    """``/api/v1/external-refs/<pk>/`` — delete."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = ExternalRefService()

    def delete(self, request: Request, pk: UUID, **kwargs: Any) -> Response:
        """Remove the reference, its backing artifact and its trace link."""
        self._service.unlink_external(request.auth_context, external_ref_id=pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


__all__ = ["ArtifactExternalRefsView", "ExternalRefDetailView"]
```

```python
# backend/integrations/urls.py
"""URL patterns for the integration subsystem, included under /api/v1/."""
from __future__ import annotations

from django.urls import path

from integrations.rest import ArtifactExternalRefsView, ExternalRefDetailView

urlpatterns = [
    path(
        "artifacts/<uuid:artifact_id>/external-refs/",
        ArtifactExternalRefsView.as_view(),
        name="api-v1-artifact-external-refs",
    ),
    path(
        "external-refs/<uuid:pk>/",
        ExternalRefDetailView.as_view(),
        name="api-v1-external-ref-detail",
    ),
]
```

In `backend/rest_api/urls.py`, add the include immediately **before** `path("", include(router.urls))` so the explicit `artifacts/<uuid>/external-refs/` route is matched before the ArtifactViewSet's catch-all detail route:

```python
    # GitHub/Jira integration (spec 2026-09-03) — must precede the router
    # include: the ArtifactViewSet detail route would otherwise swallow
    # "artifacts/<id>/external-refs/" as an unknown detail action.
    path("", include("integrations.urls")),
```

Confirm how `request.auth_context` is exposed by `rest_api.auth_enforcer.BearerTokenAuthentication` and use the same accessor the other APIViews use (grep one call site in `backend/admin_ops/rest.py`); adjust the two `request.auth_context` reads to match exactly.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_rest_external_refs.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations/serializers.py backend/integrations/rest.py backend/integrations/urls.py backend/rest_api/urls.py backend/integrations/tests/test_rest_external_refs.py
git commit -m "feat: expose external references over REST"
```

---

### Task 9: MCP tools `artifact.link_external` / `artifact.list_external`

**Files:**
- Create: `backend/mcp_server/tools/integration.py`
- Modify: `backend/mcp_server/tool_registry.py:501-560` (import and register the group)
- Modify: `backend/mcp_server/tool_registry.py:205` (`_READ_ONLY_TOOL_NAMES` — add `artifact.list_external`)
- Modify: `backend/mcp_server/workspace_scope.py:103` (`_TOOL_TARGETS` — add both tools)
- Create: `backend/integrations/tests/test_mcp_external_refs.py`

**Interfaces:**
- Consumes: `integrations.service.ExternalRefService`, `mcp_server.tools.base.BaseToolGroup`, `require_param`, `require_uuid`, `write_mcp_audit`
- Produces: `IntegrationToolGroup` with `artifact.link_external`, `artifact.list_external`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_mcp_external_refs.py
"""MCP surface for stage 1 — dispatch through the real registry."""
from __future__ import annotations

import pytest

from mcp_server.tool_registry import TenantToolRegistry
from mcp_server.workspace_scope import _TOOL_TARGETS


def test_both_tools_are_workspace_scoped():
    assert "artifact.link_external" in _TOOL_TARGETS
    assert "artifact.list_external" in _TOOL_TARGETS


def test_only_the_read_tool_is_read_only():
    from mcp_server.tool_registry import _READ_ONLY_TOOL_NAMES

    assert "artifact.list_external" in _READ_ONLY_TOOL_NAMES
    assert "artifact.link_external" not in _READ_ONLY_TOOL_NAMES


def test_both_tools_appear_in_the_manifest():
    names = {schema["name"] for schema in TenantToolRegistry().all_tool_schemas()}
    assert {"artifact.link_external", "artifact.list_external"} <= names


@pytest.mark.django_db
def test_link_then_list_round_trips(editor_ctx, requirement):
    from mcp_server.tools.integration import IntegrationToolGroup

    group = IntegrationToolGroup()
    created = group.execute_tool(
        "artifact.link_external",
        {
            "artifact_id": str(requirement.id),
            "url": "https://github.com/acme/widgets/issues/77",
        },
        editor_ctx,
    )
    assert created.is_error is False
    assert created.data["external_ref"]["external_id"] == "77"

    listed = group.execute_tool(
        "artifact.list_external", {"artifact_id": str(requirement.id)}, editor_ctx
    )
    assert [r["external_id"] for r in listed.data["external_refs"]] == ["77"]


@pytest.mark.django_db
def test_payload_is_stdlib_json_serialisable(editor_ctx, requirement):
    """The MCP transport uses stdlib json.dumps — a UUID in the payload 500s."""
    import json

    from mcp_server.tools.integration import IntegrationToolGroup

    result = IntegrationToolGroup().execute_tool(
        "artifact.link_external",
        {
            "artifact_id": str(requirement.id),
            "url": "https://github.com/acme/widgets/issues/78",
        },
        editor_ctx,
    )
    json.dumps(result.data)


@pytest.mark.django_db
def test_unknown_parameter_is_rejected(editor_ctx, requirement):
    from mcp_server.tools.base import ParameterError
    from mcp_server.tools.integration import IntegrationToolGroup

    with pytest.raises(ParameterError):
        IntegrationToolGroup().execute_tool(
            "artifact.link_external",
            {
                "artifact_id": str(requirement.id),
                "url": "https://github.com/acme/widgets/issues/79",
                "typo": 1,
            },
            editor_ctx,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_mcp_external_refs.py -q`
Expected: FAIL with `assert 'artifact.link_external' in {...}` / `ModuleNotFoundError: No module named 'mcp_server.tools.integration'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/mcp_server/tools/integration.py
"""IntegrationToolGroup — GitHub/Jira tools (spec 2026-09-03).

Stage 1 ships the two artifact-scoped link tools. Stage 3 adds
``integration.github.create_issue`` / ``integration.jira.sync`` to the same
group (see Task 26).

ADR-01: every handler delegates to integrations.service; no ORM here (the
mcp_server/tools ratchet in rest_api/tests/test_architecture.py enforces a
ceiling of 0 for new modules).
"""
from __future__ import annotations

from typing import Any, Dict

from auth_tenancy.context import AuthContext
from integrations.service import ExternalRefService
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, require_param, require_uuid


class IntegrationToolGroup(BaseToolGroup):
    """External-system tools: link an artifact to a GitHub/Jira object."""

    _TOOL_MAP = {
        "artifact.link_external": "_handle_link_external",
        "artifact.list_external": "_handle_list_external",
    }
    _TOOL_SCHEMAS = [
        {
            "name": "artifact.link_external",
            "description": (
                "Link an artifact to a GitHub issue/pull request or a Jira "
                "issue by pasting its URL. Creates a 'references' trace link "
                "to a dedicated ExternalRef artifact."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "artifact_id": {"type": "string", "format": "uuid"},
                    "url": {"type": "string"},
                },
                "required": ["artifact_id", "url"],
            },
        },
        {
            "name": "artifact.list_external",
            "description": "List the external references attached to an artifact.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "artifact_id": {"type": "string", "format": "uuid"},
                },
                "required": ["artifact_id"],
            },
        },
    ]

    def __init__(self) -> None:
        self._service = ExternalRefService()

    def _handle_link_external(
        self, params: Dict[str, Any], auth_context: AuthContext
    ) -> ToolResult:
        """Create one external reference from a pasted URL."""
        artifact_id = require_uuid(params, "artifact_id")
        url = require_param(params, "url")
        dto = self._service.link_external(
            auth_context, artifact_id=artifact_id, url=url
        )
        return ToolResult(data={"external_ref": dto.to_dict()})

    def _handle_list_external(
        self, params: Dict[str, Any], auth_context: AuthContext
    ) -> ToolResult:
        """Return every external reference of one artifact."""
        artifact_id = require_uuid(params, "artifact_id")
        refs = self._service.list_external(auth_context, artifact_id=artifact_id)
        return ToolResult(data={"external_refs": [r.to_dict() for r in refs]})


__all__ = ["IntegrationToolGroup"]
```

Match `_TOOL_MAP` / `_TOOL_SCHEMAS` / `execute_tool` / `ToolResult` to the exact shapes in `backend/mcp_server/tools/memory.py` and `backend/mcp_server/tools/base.py` — including the `reject_unknown_params` call every group makes before dispatching, which is what makes `test_unknown_parameter_is_rejected` pass.

Never put a top-level `content` key in a tool payload (it collides with the MCP result envelope) — hence `external_ref` / `external_refs`.

In `backend/mcp_server/tool_registry.py`, add the import next to the other group imports and the entry to the `self.register_groups({...})` mapping:

```python
        from mcp_server.tools.integration import IntegrationToolGroup
```

```python
            "integration": IntegrationToolGroup(),
```

Add to `_READ_ONLY_TOOL_NAMES`:

```python
        # GitHub/Jira integration: listing an artifact's external references
        # reads only ExternalRef rows — same class as diagram.query.
        "artifact.list_external",
```

In `backend/mcp_server/workspace_scope.py::_TOOL_TARGETS`:

```python
    "artifact.link_external": _artifact_or_domain("artifact_id"),
    "artifact.list_external": _artifact_or_domain("artifact_id"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_mcp_external_refs.py mcp_server/tests/test_mcp_workspace_scope.py -q`
Expected: PASS (6 passed in the new module, workspace-scope ratchet still green)

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/tools/integration.py backend/mcp_server/tool_registry.py backend/mcp_server/workspace_scope.py backend/integrations/tests/test_mcp_external_refs.py
git commit -m "feat: add artifact.link_external and artifact.list_external MCP tools"
```

---

### Task 10: Frontend API module

**Files:**
- Create: `frontend/src/api/integrations.ts`
- Create: `frontend/src/api/integrations.test.ts`

**Interfaces:**
- Consumes: `frontend/src/api/client.ts` (the shared axios instance)
- Produces: `ExternalRef` type; `integrationsApi.listExternalRefs(artifactId)`, `.linkExternal(artifactId, url)`, `.unlinkExternal(externalRefId)`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/api/integrations.test.ts
import { describe, expect, it, vi, beforeEach } from "vitest";

import { apiClient } from "./client";
import { integrationsApi } from "./integrations";

describe("integrationsApi", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("lists external refs for an artifact", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({
      data: [
        {
          id: "1",
          artifact_id: "a",
          backing_artifact_id: "b",
          system: "github",
          repo: "acme/widgets",
          external_id: "142",
          url: "https://github.com/acme/widgets/issues/142",
          kind: "issue",
          last_seen_status: "open",
          synced_at: null,
        },
      ],
    });

    const refs = await integrationsApi.listExternalRefs("a");

    expect(get).toHaveBeenCalledWith("/artifacts/a/external-refs/");
    expect(refs[0].externalId).toBe("142");
    expect(refs[0].lastSeenStatus).toBe("open");
  });

  it("posts only the url when linking", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({
      data: {
        id: "1",
        artifact_id: "a",
        backing_artifact_id: "b",
        system: "jira",
        repo: "PROJ",
        external_id: "PROJ-42",
        url: "https://acme.atlassian.net/browse/PROJ-42",
        kind: "issue",
        last_seen_status: "",
        synced_at: null,
      },
    });

    const ref = await integrationsApi.linkExternal(
      "a",
      "https://acme.atlassian.net/browse/PROJ-42",
    );

    expect(post).toHaveBeenCalledWith("/artifacts/a/external-refs/", {
      url: "https://acme.atlassian.net/browse/PROJ-42",
    });
    expect(ref.system).toBe("jira");
  });

  it("deletes by external ref id", async () => {
    const del = vi.spyOn(apiClient, "delete").mockResolvedValue({ data: null });
    await integrationsApi.unlinkExternal("1");
    expect(del).toHaveBeenCalledWith("/external-refs/1/");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$VITEST "npx vitest run src/api/integrations.test.ts --testTimeout=30000"`
Expected: FAIL with `Failed to resolve import "./integrations"`

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/src/api/integrations.ts
/**
 * REST wrapper for the GitHub/Jira integration endpoints
 * (spec docs/superpowers/specs/2026-09-03-github-jira-integration-design.md).
 */
import { apiClient } from "./client";
import type { UUID } from "../types";

export type ExternalSystem = "github" | "jira";
export type ExternalRefKind = "issue" | "pr" | "epic";

export interface ExternalRef {
  id: UUID;
  artifactId: UUID;
  backingArtifactId: UUID;
  system: ExternalSystem;
  repo: string;
  externalId: string;
  url: string;
  kind: ExternalRefKind;
  lastSeenStatus: string;
  syncedAt: string | null;
}

interface ExternalRefWire {
  id: UUID;
  artifact_id: UUID;
  backing_artifact_id: UUID;
  system: ExternalSystem;
  repo: string;
  external_id: string;
  url: string;
  kind: ExternalRefKind;
  last_seen_status: string;
  synced_at: string | null;
}

function toExternalRef(wire: ExternalRefWire): ExternalRef {
  return {
    id: wire.id,
    artifactId: wire.artifact_id,
    backingArtifactId: wire.backing_artifact_id,
    system: wire.system,
    repo: wire.repo,
    externalId: wire.external_id,
    url: wire.url,
    kind: wire.kind,
    lastSeenStatus: wire.last_seen_status,
    syncedAt: wire.synced_at,
  };
}

export const integrationsApi = {
  async listExternalRefs(artifactId: UUID): Promise<ExternalRef[]> {
    const response = await apiClient.get<ExternalRefWire[]>(
      `/artifacts/${artifactId}/external-refs/`,
    );
    return response.data.map(toExternalRef);
  },

  async linkExternal(artifactId: UUID, url: string): Promise<ExternalRef> {
    const response = await apiClient.post<ExternalRefWire>(
      `/artifacts/${artifactId}/external-refs/`,
      { url },
    );
    return toExternalRef(response.data);
  },

  async unlinkExternal(externalRefId: UUID): Promise<void> {
    await apiClient.delete(`/external-refs/${externalRefId}/`);
  },
};
```

Check the exact export name of the axios instance in `frontend/src/api/client.ts` (it may be `apiClient` or a default-less named export with a different name) and align both the module and the test.

- [ ] **Step 4: Run test to verify it passes**

Run: `$VITEST "npx vitest run src/api/integrations.test.ts --testTimeout=30000"`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/integrations.ts frontend/src/api/integrations.test.ts
git commit -m "feat: add integrations API wrapper"
```

---

### Task 11: `ExternalRefChip` component

**Files:**
- Create: `frontend/src/components/shared/ExternalRefChip.tsx`
- Create: `frontend/src/components/shared/ExternalRefChip.test.tsx`
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`

**Interfaces:**
- Consumes: `ExternalRef` from `api/integrations`
- Produces: `ExternalRefChip({ externalRef }: { externalRef: ExternalRef })`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/shared/ExternalRefChip.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ExternalRefChip } from "./ExternalRefChip";
import type { ExternalRef } from "../../api/integrations";

const base: ExternalRef = {
  id: "1",
  artifactId: "a",
  backingArtifactId: "b",
  system: "github",
  repo: "acme/widgets",
  externalId: "142",
  url: "https://github.com/acme/widgets/issues/142",
  kind: "issue",
  lastSeenStatus: "open",
  syncedAt: null,
};

describe("ExternalRefChip", () => {
  it("renders system, id and last seen status", () => {
    render(<ExternalRefChip externalRef={base} />);
    const link = screen.getByTestId("external-ref-chip-1");
    expect(link).toHaveTextContent("GH #142");
    expect(link).toHaveTextContent("open");
  });

  it("omits the status separator when no status is known", () => {
    render(<ExternalRefChip externalRef={{ ...base, lastSeenStatus: "" }} />);
    expect(screen.getByTestId("external-ref-chip-1").textContent).toBe("GH #142");
  });

  it("labels Jira references with their key", () => {
    render(
      <ExternalRefChip
        externalRef={{
          ...base,
          system: "jira",
          externalId: "PROJ-42",
          repo: "PROJ",
          lastSeenStatus: "",
        }}
      />,
    );
    expect(screen.getByTestId("external-ref-chip-1")).toHaveTextContent("PROJ-42");
  });

  it("opens the target in a new tab without leaking the referrer", () => {
    render(<ExternalRefChip externalRef={base} />);
    const link = screen.getByTestId("external-ref-chip-1");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveAccessibleName(/acme\/widgets/);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$VITEST "npx vitest run src/components/shared/ExternalRefChip.test.tsx --testTimeout=30000"`
Expected: FAIL with `Failed to resolve import "./ExternalRefChip"`

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/shared/ExternalRefChip.tsx
/**
 * One external reference rendered as a compact chip next to the status badge
 * ("GH #142 · open"). Click opens the object in GitHub/Jira.
 */
import { useTranslation } from "react-i18next";

import { badgeBase } from "../../utils/badgeBase";
import type { ExternalRef } from "../../api/integrations";

export interface ExternalRefChipProps {
  externalRef: ExternalRef;
}

const SYSTEM_PREFIX: Record<ExternalRef["system"], string> = {
  github: "GH",
  jira: "JIRA",
};

function chipLabel(ref: ExternalRef): string {
  if (ref.system === "github") return `GH #${ref.externalId}`;
  return ref.externalId;
}

export function ExternalRefChip({ externalRef }: ExternalRefChipProps): JSX.Element {
  const { t } = useTranslation();
  const label = chipLabel(externalRef);
  const text = externalRef.lastSeenStatus
    ? `${label} · ${externalRef.lastSeenStatus}`
    : label;

  return (
    <a
      data-testid={`external-ref-chip-${externalRef.id}`}
      href={externalRef.url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={t("integrations.chipAria", {
        defaultValue: "Open {{label}} in {{repo}}",
        label,
        repo: externalRef.repo,
      })}
      title={externalRef.url}
      style={{
        ...badgeBase,
        color: "var(--color-text)",
        background: "var(--color-surface-muted)",
        border: "1px solid var(--color-border)",
        textDecoration: "none",
      }}
    >
      {text}
    </a>
  );
}
```

`SYSTEM_PREFIX` is unused once `chipLabel` covers both systems — delete it rather than leave a dead constant.

Take the geometry constant from `frontend/src/utils/badgeBase.ts` (badge geometry is a `CSSProperties` const there, not a CSS class) and confirm the exact export name before importing.

Add to both locale files under a new `integrations` key:

```json
  "integrations": {
    "chipAria": "Open {{label}} in {{repo}}",
    "sectionTitle": "External",
    "empty": "No external references",
    "linkButton": "Link externally",
    "dialogTitle": "Link externally",
    "urlLabel": "GitHub or Jira URL",
    "urlPlaceholder": "https://github.com/owner/repo/issues/142",
    "urlInvalid": "Not a recognised GitHub or Jira URL",
    "unlink": "Remove link",
    "unlinkConfirm": "Remove the link to {{label}}?"
  }
```

German values in `de.json`: `"Öffne {{label}} in {{repo}}"`, `"Extern"`, `"Keine externen Verweise"`, `"Extern verknüpfen"`, `"Extern verknüpfen"`, `"GitHub- oder Jira-URL"`, same placeholder, `"Keine erkennbare GitHub- oder Jira-URL"`, `"Verknüpfung entfernen"`, `"Verknüpfung zu {{label}} entfernen?"`.

Keys must be nested objects — a flat `"integrations.chipAria"` key inside a locale object never resolves, because `keySeparator` is `"."`.

- [ ] **Step 4: Run test to verify it passes**

Run: `$VITEST "npx vitest run src/components/shared/ExternalRefChip.test.tsx --testTimeout=30000"`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/ExternalRefChip.tsx frontend/src/components/shared/ExternalRefChip.test.tsx frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json
git commit -m "feat: add external reference chip component"
```

---

### Task 12: `LinkExternalDialog`

**Files:**
- Create: `frontend/src/components/shared/LinkExternalDialog.tsx`
- Create: `frontend/src/components/shared/LinkExternalDialog.test.tsx`

**Interfaces:**
- Consumes: `integrationsApi.linkExternal` (Task 10), `components/shared/Dialog`
- Produces: `LinkExternalDialog({ artifactId, open, onClose, onCreated })`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/shared/LinkExternalDialog.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LinkExternalDialog } from "./LinkExternalDialog";
import { integrationsApi } from "../../api/integrations";

describe("LinkExternalDialog", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("submits the pasted url and reports the created ref", async () => {
    const created = { id: "1", externalId: "142" };
    const link = vi
      .spyOn(integrationsApi, "linkExternal")
      .mockResolvedValue(created as never);
    const onCreated = vi.fn();
    const onClose = vi.fn();

    render(
      <LinkExternalDialog
        artifactId="a"
        open
        onClose={onClose}
        onCreated={onCreated}
      />,
    );

    await userEvent.type(
      screen.getByTestId("link-external-url"),
      "https://github.com/acme/widgets/issues/142",
    );
    await userEvent.click(screen.getByTestId("link-external-submit"));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created));
    expect(link).toHaveBeenCalledWith(
      "a",
      "https://github.com/acme/widgets/issues/142",
    );
    expect(onClose).toHaveBeenCalled();
  });

  it("keeps the dialog open and shows the error when the server rejects", async () => {
    vi.spyOn(integrationsApi, "linkExternal").mockRejectedValue(
      new Error("nope"),
    );
    const onClose = vi.fn();

    render(
      <LinkExternalDialog
        artifactId="a"
        open
        onClose={onClose}
        onCreated={vi.fn()}
      />,
    );

    await userEvent.type(screen.getByTestId("link-external-url"), "https://x/y");
    await userEvent.click(screen.getByTestId("link-external-submit"));

    await waitFor(() =>
      expect(screen.getByTestId("link-external-error")).toBeInTheDocument(),
    );
    expect(onClose).not.toHaveBeenCalled();
  });

  it("disables submit while the url field is empty", () => {
    render(
      <LinkExternalDialog
        artifactId="a"
        open
        onClose={vi.fn()}
        onCreated={vi.fn()}
      />,
    );
    expect(screen.getByTestId("link-external-submit")).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$VITEST "npx vitest run src/components/shared/LinkExternalDialog.test.tsx --testTimeout=30000"`
Expected: FAIL with `Failed to resolve import "./LinkExternalDialog"`

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/shared/LinkExternalDialog.tsx
/**
 * "Link externally" — paste a GitHub/Jira URL; the backend parses it.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Dialog } from "./Dialog";
import { integrationsApi } from "../../api/integrations";
import type { ExternalRef } from "../../api/integrations";
import type { UUID } from "../../types";

export interface LinkExternalDialogProps {
  artifactId: UUID;
  open: boolean;
  onClose: () => void;
  onCreated: (ref: ExternalRef) => void;
}

export function LinkExternalDialog({
  artifactId,
  open,
  onClose,
  onCreated,
}: LinkExternalDialogProps): JSX.Element | null {
  const { t } = useTranslation();
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  const submit = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const created = await integrationsApi.linkExternal(artifactId, url.trim());
      onCreated(created);
      setUrl("");
      onClose();
    } catch {
      setError(t("integrations.urlInvalid"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      title={t("integrations.dialogTitle")}
      onClose={onClose}
      data-testid="link-external-dialog"
    >
      <label htmlFor="link-external-url">{t("integrations.urlLabel")}</label>
      <input
        id="link-external-url"
        data-testid="link-external-url"
        type="url"
        value={url}
        placeholder={t("integrations.urlPlaceholder")}
        onChange={(event) => setUrl(event.target.value)}
      />
      {error ? (
        <p data-testid="link-external-error" role="alert">
          {error}
        </p>
      ) : null}
      <button
        type="button"
        data-testid="link-external-submit"
        disabled={busy || url.trim().length === 0}
        onClick={() => void submit()}
      >
        {t("integrations.linkButton")}
      </button>
    </Dialog>
  );
}
```

Align the `Dialog` import and props with the actual component in `frontend/src/components/shared/Dialog` (check its exported prop names before wiring), and style the input/button with `tokens.css` custom properties only.

- [ ] **Step 4: Run test to verify it passes**

Run: `$VITEST "npx vitest run src/components/shared/LinkExternalDialog.test.tsx --testTimeout=30000"`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/LinkExternalDialog.tsx frontend/src/components/shared/LinkExternalDialog.test.tsx
git commit -m "feat: add link-external dialog"
```

---

### Task 13: `ExternalPanel` in the artifact inspector

**Files:**
- Create: `frontend/src/components/shared/ArtifactInspector/ExternalPanel.tsx`
- Create: `frontend/src/components/shared/ArtifactInspector/ExternalPanel.module.css`
- Create: `frontend/src/components/shared/ArtifactInspector/ExternalPanel.test.tsx`
- Modify: `frontend/src/components/shared/ArtifactInspector/RightSidebar.tsx:471` (render the panel after `TracePanel`)
- Modify: `frontend/src/components/shared/ArtifactInspector/index.ts` (export it)

**Interfaces:**
- Consumes: `integrationsApi.listExternalRefs`, `.unlinkExternal`, `ExternalRefChip`, `LinkExternalDialog`, `ConfirmDialog`
- Produces: `ExternalPanel({ kind, artifactId }: { kind: ArtifactKind; artifactId: string | number })`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/shared/ArtifactInspector/ExternalPanel.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ExternalPanel } from "./ExternalPanel";
import { integrationsApi } from "../../../api/integrations";

const ref = {
  id: "1",
  artifactId: "a",
  backingArtifactId: "b",
  system: "github" as const,
  repo: "acme/widgets",
  externalId: "142",
  url: "https://github.com/acme/widgets/issues/142",
  kind: "issue" as const,
  lastSeenStatus: "open",
  syncedAt: null,
};

describe("ExternalPanel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders a chip per external reference", async () => {
    vi.spyOn(integrationsApi, "listExternalRefs").mockResolvedValue([ref]);
    render(<ExternalPanel kind="requirement" artifactId="a" />);
    expect(await screen.findByTestId("external-ref-chip-1")).toBeInTheDocument();
  });

  it("shows an empty state when there are none", async () => {
    vi.spyOn(integrationsApi, "listExternalRefs").mockResolvedValue([]);
    render(<ExternalPanel kind="requirement" artifactId="a" />);
    expect(await screen.findByTestId("external-panel-empty")).toBeInTheDocument();
  });

  it("removes a reference through the shared confirm dialog", async () => {
    vi.spyOn(integrationsApi, "listExternalRefs").mockResolvedValue([ref]);
    const unlink = vi
      .spyOn(integrationsApi, "unlinkExternal")
      .mockResolvedValue(undefined);

    render(<ExternalPanel kind="requirement" artifactId="a" />);
    await userEvent.click(await screen.findByTestId("external-ref-unlink-1"));
    await userEvent.click(screen.getByTestId("external-unlink-confirm"));

    await waitFor(() => expect(unlink).toHaveBeenCalledWith("1"));
    await waitFor(() =>
      expect(screen.queryByTestId("external-unlink-confirm")).toBeNull(),
    );
  });

  it("degrades to the empty state when the request fails", async () => {
    vi.spyOn(integrationsApi, "listExternalRefs").mockRejectedValue(
      new Error("boom"),
    );
    render(<ExternalPanel kind="requirement" artifactId="a" />);
    expect(await screen.findByTestId("external-panel-empty")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$VITEST "npx vitest run src/components/shared/ArtifactInspector/ExternalPanel.test.tsx --testTimeout=30000"`
Expected: FAIL with `Failed to resolve import "./ExternalPanel"`

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/shared/ArtifactInspector/ExternalPanel.tsx
/**
 * "External" section of the artifact inspector: chips for every linked
 * GitHub/Jira object, plus link/unlink actions (spec §6).
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import styles from "./ExternalPanel.module.css";
import type { ArtifactKind } from "./types";
import { ConfirmDialog } from "../ConfirmDialog";
import { ExternalRefChip } from "../ExternalRefChip";
import { LinkExternalDialog } from "../LinkExternalDialog";
import { integrationsApi } from "../../../api/integrations";
import type { ExternalRef } from "../../../api/integrations";

export interface ExternalPanelProps {
  kind: ArtifactKind;
  artifactId: string | number;
}

export function ExternalPanel({ artifactId }: ExternalPanelProps): JSX.Element {
  const { t } = useTranslation();
  const [refs, setRefs] = useState<ExternalRef[]>([]);
  const [linkOpen, setLinkOpen] = useState(false);
  const [pendingUnlink, setPendingUnlink] = useState<ExternalRef | null>(null);

  const reload = useCallback(async (): Promise<void> => {
    try {
      setRefs(await integrationsApi.listExternalRefs(String(artifactId)));
    } catch {
      // Read-only enhancement: an unreachable endpoint must not break the
      // inspector, so this degrades to "no references" like TracePanel does.
      setRefs([]);
    }
  }, [artifactId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const confirmUnlink = async (): Promise<void> => {
    if (!pendingUnlink) return;
    await integrationsApi.unlinkExternal(pendingUnlink.id);
    setPendingUnlink(null);
    await reload();
  };

  return (
    <section className={styles.panel} data-testid="external-panel">
      <header className={styles.header}>
        <h3>{t("integrations.sectionTitle")}</h3>
        <button
          type="button"
          data-testid="external-panel-link"
          onClick={() => setLinkOpen(true)}
        >
          {t("integrations.linkButton")}
        </button>
      </header>

      {refs.length === 0 ? (
        <p data-testid="external-panel-empty">{t("integrations.empty")}</p>
      ) : (
        <ul className={styles.chips}>
          {refs.map((ref) => (
            <li key={ref.id}>
              <ExternalRefChip externalRef={ref} />
              <button
                type="button"
                data-testid={`external-ref-unlink-${ref.id}`}
                aria-label={t("integrations.unlink")}
                onClick={() => setPendingUnlink(ref)}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <LinkExternalDialog
        artifactId={String(artifactId)}
        open={linkOpen}
        onClose={() => setLinkOpen(false)}
        onCreated={() => void reload()}
      />

      <ConfirmDialog
        open={pendingUnlink !== null}
        title={t("integrations.unlink")}
        message={t("integrations.unlinkConfirm", {
          label: pendingUnlink?.externalId ?? "",
        })}
        confirmTestId="external-unlink-confirm"
        cancelTestId="external-unlink-cancel"
        onConfirm={() => void confirmUnlink()}
        onCancel={() => setPendingUnlink(null)}
      />
    </section>
  );
}
```

```css
/* frontend/src/components/shared/ArtifactInspector/ExternalPanel.module.css */
.panel {
  padding: var(--space-3);
  border-top: 1px solid var(--color-border);
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: var(--space-2) 0 0;
  padding: 0;
  list-style: none;
}

.chips li {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}
```

Verify the `ConfirmDialog` prop names in `frontend/src/components/shared/ConfirmDialog.tsx` and align them — it is the single delete seam in this codebase; never hand-roll a confirm. Verify the spacing token names exist in `frontend/src/styles/tokens.css`.

In `RightSidebar.tsx`, render it after the `TracePanel` line:

```tsx
            {!hideTraceLinks && <TracePanel kind={kind} artifactId={artifactId} />}
            <ExternalPanel kind={kind} artifactId={artifactId} />
```

In `index.ts`:

```ts
export { ExternalPanel } from "./ExternalPanel";
export type { ExternalPanelProps } from "./ExternalPanel";
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$VITEST "npx vitest run src/components/shared/ArtifactInspector --testTimeout=30000"`
Expected: PASS (4 new tests pass, `RightSidebar.test.tsx` still green)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/ArtifactInspector/ExternalPanel.tsx frontend/src/components/shared/ArtifactInspector/ExternalPanel.module.css frontend/src/components/shared/ArtifactInspector/ExternalPanel.test.tsx frontend/src/components/shared/ArtifactInspector/RightSidebar.tsx frontend/src/components/shared/ArtifactInspector/index.ts
git commit -m "feat: show external references in the artifact inspector"
```

---

# Stage 2 — Inbound Sync

### Task 14: `IntegrationConfig` model

**Files:**
- Modify: `backend/integrations/models.py` (add `IntegrationConfig`)
- Create: `backend/integrations/migrations/0004_integration_config.py` (generated)
- Create: `backend/integrations/migrations/0005_integration_config_rls.py`
- Create: `backend/integrations/tests/test_integration_config_model.py`

**Interfaces:**
- Consumes: `persistence.encryption.encrypt_secret`, `decrypt_secret`
- Produces: `integrations.models.IntegrationConfig` with a `webhook_secret` property (plaintext in, ciphertext at rest)

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_integration_config_model.py
"""IntegrationConfig: per-workspace inbound/outbound configuration."""
from __future__ import annotations

import pytest
from django.db.utils import IntegrityError

from integrations.constants import SYSTEM_GITHUB
from integrations.models import IntegrationConfig
from persistence.encryption import ENCRYPTED_PREFIX


@pytest.mark.django_db
def test_webhook_secret_is_stored_encrypted(workspace):
    config = IntegrationConfig(
        tenant=workspace.tenant, workspace=workspace, system=SYSTEM_GITHUB
    )
    config.webhook_secret = "s3cr3t"
    config.save()

    config.refresh_from_db()
    assert config.webhook_secret_encrypted.startswith(ENCRYPTED_PREFIX)
    assert "s3cr3t" not in config.webhook_secret_encrypted
    assert config.webhook_secret == "s3cr3t"


@pytest.mark.django_db
def test_empty_secret_round_trips_as_empty(workspace):
    config = IntegrationConfig(
        tenant=workspace.tenant, workspace=workspace, system=SYSTEM_GITHUB
    )
    config.webhook_secret = ""
    config.save()
    assert config.webhook_secret_encrypted == ""
    assert config.webhook_secret == ""


@pytest.mark.django_db
def test_one_config_per_workspace_and_system(workspace):
    IntegrationConfig.objects.create(
        tenant=workspace.tenant, workspace=workspace, system=SYSTEM_GITHUB
    )
    with pytest.raises(IntegrityError):
        IntegrationConfig.objects.create(
            tenant=workspace.tenant, workspace=workspace, system=SYSTEM_GITHUB
        )


@pytest.mark.django_db
def test_defaults_are_empty_lists(workspace):
    config = IntegrationConfig.objects.create(
        tenant=workspace.tenant, workspace=workspace, system=SYSTEM_GITHUB
    )
    assert config.repos == []
    assert config.outbound_rules == []
    assert config.enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_integration_config_model.py -q`
Expected: FAIL with `ImportError: cannot import name 'IntegrationConfig' from 'integrations.models'`

- [ ] **Step 3: Write minimal implementation**

```python
# appended to backend/integrations/models.py
from persistence.encryption import decrypt_secret, encrypt_secret


class IntegrationConfig(TenantScopedModel):
    """Per-workspace, per-system integration configuration.

    Holds everything the inbound receiver and the outbound adapters need that
    is not a credential: which repositories/projects this workspace listens
    to, the webhook secret (GitHub HMAC key or Jira query token — both are a
    shared secret, so one column serves both), and the outbound rule list.

    ``webhook_secret`` mirrors the ``LlmSettings.api_key`` /
    ``SystemMemorySettings.honcho_api_key`` property pattern: never read or
    write ``webhook_secret_encrypted`` directly.
    """

    workspace = models.ForeignKey(
        "persistence.Workspace",
        on_delete=models.CASCADE,
        related_name="integration_configs",
    )
    system = models.CharField(max_length=32, choices=SYSTEM_CHOICES)
    repos = models.JSONField(
        default=list,
        blank=True,
        help_text="GitHub 'owner/repo' entries or Jira project keys.",
    )
    webhook_secret_encrypted = models.TextField(blank=True, default="")
    outbound_rules = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "List of {'event_type', 'to_state', 'item_type', 'action'} rules "
            "evaluated by OutboundIntegrationSubscriber."
        ),
    )
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "int_integration_config"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "workspace", "system"],
                name="uq_integration_config_ws_system",
            ),
        ]

    @property
    def webhook_secret(self) -> str:
        """Return the decrypted shared secret ("" when unset)."""
        return decrypt_secret(self.webhook_secret_encrypted)

    @webhook_secret.setter
    def webhook_secret(self, value: str) -> None:
        self.webhook_secret_encrypted = encrypt_secret(value or "")

    def __str__(self) -> str:
        return f"IntegrationConfig:{self.workspace_id}:{self.system}"
```

Extend `__all__` with `"IntegrationConfig"`.

Run: `$MANAGE makemigrations integrations --name integration_config`
Expected: creates `backend/integrations/migrations/0004_integration_config.py`

Then add `backend/integrations/migrations/0005_integration_config_rls.py`, copying the shape of `0002_rls_policies.py` with `_TENANT_TABLES = ["int_integration_config"]` and `dependencies = [("integrations", "0004_integration_config"), ("persistence", "0003_rls_policies")]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_integration_config_model.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations/models.py backend/integrations/migrations backend/integrations/tests/test_integration_config_model.py
git commit -m "feat: add IntegrationConfig with encrypted webhook secret"
```

---

### Task 15: Webhook signature verification

**Files:**
- Create: `backend/integrations/signatures.py`
- Create: `backend/integrations/tests/test_signatures.py`

**Interfaces:**
- Consumes: stdlib `hmac`, `hashlib`
- Produces: `verify_github_signature(body: bytes, header: str | None, secret: str) -> bool`, `verify_jira_token(supplied: str | None, secret: str) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_signatures.py
"""Webhook authentication primitives — the whole trust boundary of stage 2."""
from __future__ import annotations

import hashlib
import hmac

import pytest

from integrations.signatures import verify_github_signature, verify_jira_token

_SECRET = "top-secret"
_BODY = b'{"action":"closed"}'


def _valid_header(body: bytes = _BODY, secret: str = _SECRET) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_valid_signature_is_accepted():
    assert verify_github_signature(_BODY, _valid_header(), _SECRET) is True


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "sha256=deadbeef",
        "sha1=" + hmac.new(b"top-secret", _BODY, hashlib.sha1).hexdigest(),
        hmac.new(b"top-secret", _BODY, hashlib.sha256).hexdigest(),
        "sha256=",
        "sha256=zz",
    ],
)
def test_malformed_or_wrong_signatures_are_rejected(header):
    assert verify_github_signature(_BODY, header, _SECRET) is False


def test_a_different_body_is_rejected():
    assert verify_github_signature(b'{"action":"opened"}', _valid_header(), _SECRET) is False


def test_an_unset_secret_rejects_everything():
    assert verify_github_signature(_BODY, _valid_header(), "") is False
    assert verify_github_signature(_BODY, None, "") is False


def test_jira_token_compare():
    assert verify_jira_token("abc", "abc") is True
    assert verify_jira_token("abd", "abc") is False
    assert verify_jira_token(None, "abc") is False
    assert verify_jira_token("", "abc") is False
    assert verify_jira_token("abc", "") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_signatures.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'integrations.signatures'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/integrations/signatures.py
"""Authentication for the two public webhook receivers.

This is the entire trust boundary of stage 2: nothing else runs before these
functions return True, because the endpoints are unauthenticated by design
(GitHub and Jira hold no ReqogniLoom session).

Both comparisons use ``hmac.compare_digest`` — a short-circuiting ``==`` on a
secret is a timing oracle.
"""
from __future__ import annotations

import hashlib
import hmac

_GITHUB_PREFIX = "sha256="


def verify_github_signature(body: bytes, header: str | None, secret: str) -> bool:
    """Return whether *header* is a valid ``X-Hub-Signature-256`` for *body*.

    Args:
        body: The raw request body, exactly as received. Re-serialising the
            parsed JSON would change the bytes and break every signature.
        header: The ``X-Hub-Signature-256`` value, or None when absent.
        secret: The workspace's configured shared secret.

    Returns:
        True only for a well-formed ``sha256=<hex>`` header that matches. An
        unset secret returns False — an unconfigured integration must never
        accept traffic.
    """
    if not secret or not header:
        return False
    if not header.startswith(_GITHUB_PREFIX):
        return False
    supplied = header[len(_GITHUB_PREFIX) :]
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, expected)


def verify_jira_token(supplied: str | None, secret: str) -> bool:
    """Return whether the ``?token=`` query parameter matches the secret.

    Jira Server/Data-Center webhooks have no HMAC equivalent, so the URL
    itself carries the shared secret (spec §4.1). Weaker than HMAC on purpose
    and documented as such: the value can leak through access logs, so
    deployments must exclude query strings from those logs and rotate on
    suspicion.
    """
    if not secret or not supplied:
        return False
    return hmac.compare_digest(supplied, secret)


__all__ = ["verify_github_signature", "verify_jira_token"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_signatures.py -q`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations/signatures.py backend/integrations/tests/test_signatures.py
git commit -m "feat: add GitHub HMAC and Jira token webhook verification"
```

---

### Task 16: Event normalisation

**Files:**
- Create: `backend/integrations/events.py`
- Create: `backend/integrations/tests/test_events.py`

**Interfaces:**
- Consumes: `integrations.constants.SYSTEM_GITHUB`, `SYSTEM_JIRA`
- Produces: `NormalizedExternalEvent(system, event, repo, external_id, status, url)`; `normalize_github_event(event_name: str, payload: dict) -> NormalizedExternalEvent | None`; `normalize_jira_event(payload: dict) -> NormalizedExternalEvent | None`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_events.py
"""Turn a provider payload into the fields the sync path needs."""
from __future__ import annotations

from integrations.events import normalize_github_event, normalize_jira_event


def _gh_issue(action: str, state: str) -> dict:
    return {
        "action": action,
        "repository": {"full_name": "acme/widgets"},
        "issue": {
            "number": 142,
            "state": state,
            "html_url": "https://github.com/acme/widgets/issues/142",
        },
    }


def test_issue_opened():
    event = normalize_github_event("issues", _gh_issue("opened", "open"))
    assert event.system == "github"
    assert event.event == "issue.opened"
    assert event.repo == "acme/widgets"
    assert event.external_id == "142"
    assert event.status == "open"


def test_issue_closed():
    event = normalize_github_event("issues", _gh_issue("closed", "closed"))
    assert event.event == "issue.closed"
    assert event.status == "closed"


def test_issue_labeled():
    event = normalize_github_event("issues", _gh_issue("labeled", "open"))
    assert event.event == "issue.labeled"


def test_pull_request_merged():
    payload = {
        "action": "closed",
        "repository": {"full_name": "acme/widgets"},
        "pull_request": {
            "number": 7,
            "state": "closed",
            "merged": True,
            "html_url": "https://github.com/acme/widgets/pull/7",
        },
    }
    event = normalize_github_event("pull_request", payload)
    assert event.event == "pull_request.merged"
    assert event.external_id == "7"
    assert event.status == "merged"


def test_pull_request_closed_without_merge_is_ignored():
    payload = {
        "action": "closed",
        "repository": {"full_name": "acme/widgets"},
        "pull_request": {"number": 7, "state": "closed", "merged": False, "html_url": "u"},
    }
    assert normalize_github_event("pull_request", payload) is None


def test_unknown_github_event_is_ignored():
    assert normalize_github_event("star", {"action": "created"}) is None


def test_malformed_github_payload_is_ignored():
    assert normalize_github_event("issues", {"action": "opened"}) is None


def test_jira_issue_updated():
    payload = {
        "webhookEvent": "jira:issue_updated",
        "issue": {
            "key": "PROJ-42",
            "fields": {"project": {"key": "PROJ"}, "status": {"name": "Done"}},
            "self": "https://acme.atlassian.net/rest/api/2/issue/10001",
        },
    }
    event = normalize_jira_event(payload)
    assert event.system == "jira"
    assert event.event == "jira:issue_updated"
    assert event.repo == "PROJ"
    assert event.external_id == "PROJ-42"
    assert event.status == "Done"


def test_jira_event_without_status_is_ignored():
    payload = {
        "webhookEvent": "jira:issue_updated",
        "issue": {"key": "PROJ-42", "fields": {"project": {"key": "PROJ"}}},
    }
    assert normalize_jira_event(payload) is None


def test_other_jira_webhook_events_are_ignored():
    assert normalize_jira_event({"webhookEvent": "jira:worklog_updated"}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_events.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'integrations.events'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/integrations/events.py
"""Provider payload -> the fields the sync path actually uses.

Everything unrecognised returns None rather than raising: a webhook receiver
that 500s on an event type it does not care about teaches GitHub to disable
the hook.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from integrations.constants import SYSTEM_GITHUB, SYSTEM_JIRA

#: Processed GitHub issue actions (spec §4.2).
GITHUB_ISSUE_ACTIONS = {"opened", "closed", "labeled"}


@dataclass(frozen=True)
class NormalizedExternalEvent:
    """One inbound event, provider-independent."""

    system: str
    event: str
    repo: str
    external_id: str
    status: str
    url: str


def normalize_github_event(
    event_name: str, payload: dict[str, Any]
) -> Optional[NormalizedExternalEvent]:
    """Map an ``X-GitHub-Event`` header plus body to a normalized event.

    Args:
        event_name: The ``X-GitHub-Event`` header value ("issues",
            "pull_request", ...).
        payload: The parsed JSON body.

    Returns:
        The normalized event, or None when this is an event the system does
        not process (including a pull request closed without a merge).
    """
    repo = (payload.get("repository") or {}).get("full_name")
    action = payload.get("action")
    if not repo or not action:
        return None

    if event_name == "issues" and action in GITHUB_ISSUE_ACTIONS:
        issue = payload.get("issue") or {}
        number = issue.get("number")
        if number is None:
            return None
        return NormalizedExternalEvent(
            system=SYSTEM_GITHUB,
            event=f"issue.{action}",
            repo=repo,
            external_id=str(number),
            status=str(issue.get("state") or ""),
            url=str(issue.get("html_url") or ""),
        )

    if event_name == "pull_request" and action == "closed":
        pull = payload.get("pull_request") or {}
        if not pull.get("merged"):
            return None
        number = pull.get("number")
        if number is None:
            return None
        return NormalizedExternalEvent(
            system=SYSTEM_GITHUB,
            event="pull_request.merged",
            repo=repo,
            external_id=str(number),
            status="merged",
            url=str(pull.get("html_url") or ""),
        )

    return None


def normalize_jira_event(payload: dict[str, Any]) -> Optional[NormalizedExternalEvent]:
    """Map a Jira webhook body to a normalized event, or None.

    Only ``jira:issue_updated`` carrying a status is processed — the spec
    scopes stage 2 to status changes, and an update without a status field
    tells the sync path nothing.
    """
    if payload.get("webhookEvent") != "jira:issue_updated":
        return None

    issue = payload.get("issue") or {}
    key = issue.get("key")
    fields = issue.get("fields") or {}
    status = (fields.get("status") or {}).get("name")
    project = (fields.get("project") or {}).get("key")
    if not key or not status or not project:
        return None

    return NormalizedExternalEvent(
        system=SYSTEM_JIRA,
        event="jira:issue_updated",
        repo=str(project),
        external_id=str(key),
        status=str(status),
        url=str(issue.get("self") or ""),
    )


__all__ = [
    "GITHUB_ISSUE_ACTIONS",
    "NormalizedExternalEvent",
    "normalize_github_event",
    "normalize_jira_event",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_events.py -q`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations/events.py backend/integrations/tests/test_events.py
git commit -m "feat: normalize GitHub and Jira webhook payloads"
```

---

### Task 17: `system` actor type on audit and workflow history

**Files:**
- Modify: `backend/audit/models.py:106-111` (`ACTOR_TYPE_SYSTEM` + choices)
- Modify: `backend/workflow/models.py:237-266` (`actor_type`, `client_name` on `WorkflowHistoryEntry`)
- Create: `backend/audit/migrations/00NN_actor_type_system.py` (generated)
- Create: `backend/workflow/migrations/00NN_history_actor_columns.py` (generated)
- Create: `backend/integrations/tests/test_system_actor_type.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `AuditEntry.ACTOR_TYPE_SYSTEM == "system"`; `WorkflowHistoryEntry.actor_type` (default `"user"`), `.client_name`

> Check first: `grep -n "actor_type" backend/workflow/models.py`. If spec 4's implementation already added both columns, skip the workflow half of this task and keep only the `AuditEntry` change. See OPEN QUESTION 1.

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_system_actor_type.py
"""'system' is the third actor type, next to 'user' and 'agent' (spec §4.2)."""
from __future__ import annotations

import uuid

import pytest

from audit.models import AuditEntry
from audit.services import log_write


def test_system_is_a_declared_actor_type():
    assert AuditEntry.ACTOR_TYPE_SYSTEM == "system"
    assert ("system", "System") in AuditEntry.ACTOR_TYPE_CHOICES
    assert ("user", "User") in AuditEntry.ACTOR_TYPE_CHOICES
    assert ("agent", "Agent") in AuditEntry.ACTOR_TYPE_CHOICES


@pytest.mark.django_db
def test_a_system_audit_entry_validates_and_persists(armed_tenant):
    entry = log_write(
        actor="github-webhook",
        actor_type=AuditEntry.ACTOR_TYPE_SYSTEM,
        operation=AuditEntry.OP_TRANSITION,
        entity_type="Requirement",
        entity_id=uuid.uuid4(),
        change_reason="pull_request.merged",
    )
    assert entry is not None
    assert entry.actor_type == "system"


@pytest.mark.django_db
def test_workflow_history_carries_actor_columns():
    from workflow.models import WorkflowHistoryEntry

    field_names = {f.name for f in WorkflowHistoryEntry._meta.get_fields()}
    assert {"actor_type", "client_name"} <= field_names
    assert WorkflowHistoryEntry._meta.get_field("actor_type").default == "user"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_system_actor_type.py -q`
Expected: FAIL with `AttributeError: type object 'AuditEntry' has no attribute 'ACTOR_TYPE_SYSTEM'`

- [ ] **Step 3: Write minimal implementation**

In `backend/audit/models.py`:

```python
    ACTOR_TYPE_USER = "user"
    ACTOR_TYPE_AGENT = "agent"
    # GitHub/Jira integration (spec §4.2): an externally triggered workflow
    # transition is neither a person nor an agent — the acting party is the
    # remote system itself. Additive; the two values above are unchanged.
    ACTOR_TYPE_SYSTEM = "system"
    ACTOR_TYPE_CHOICES = [
        (ACTOR_TYPE_USER, "User"),
        (ACTOR_TYPE_AGENT, "Agent"),
        (ACTOR_TYPE_SYSTEM, "System"),
    ]
```

In `backend/workflow/models.py`, on `WorkflowHistoryEntry`:

```python
    #: Who performed the transition: "user", "agent" (spec 4) or "system"
    #: (external trigger, spec 8 §4.2). Mirrors AuditEntry.ACTOR_TYPE_CHOICES
    #: without importing it — workflow (Layer 1) must not depend on audit.
    actor_type = models.CharField(
        max_length=16,
        choices=[("user", "User"), ("agent", "Agent"), ("system", "System")],
        default="user",
    )
    #: Free-text identity of a non-user actor, e.g. "github-webhook" or an
    #: ApiKey's agent_label. Empty for human transitions.
    client_name = models.CharField(max_length=255, blank=True, default="")
```

Run: `$MANAGE makemigrations audit workflow --name actor_type_system`
Expected: an `AlterField` on `audit.AuditEntry.actor_type` and two `AddField`s on `workflow.WorkflowHistoryEntry`

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_system_actor_type.py audit/tests/test_op_vocabulary.py workflow/tests -q`
Expected: PASS (3 new tests pass, audit and workflow suites unchanged)

- [ ] **Step 5: Commit**

```bash
git add backend/audit backend/workflow backend/integrations/tests/test_system_actor_type.py
git commit -m "feat: add system actor type to audit and workflow history"
```

---

### Task 18: `workflow.services.system_transition`

**Files:**
- Modify: `backend/workflow/services.py:194-282` (add `system_transition` after `transition`)
- Modify: `backend/workflow/transition_validator.py:251` (`validate(..., skip_role_check=False)`)
- Modify: `backend/workflow/lifecycle_manager.py` (`perform_transition` accepts `actor_type` / `client_name`)
- Create: `backend/workflow/tests/test_system_transition.py`

**Interfaces:**
- Consumes: `workflow.services._get_lifecycle`, `_get_validator`, `auth_tenancy.context.AuthContext.system(tenant_id=...)`
- Produces: `workflow.services.system_transition(item_id, item_type, workspace_id, target_state, *, tenant_id, client_name, change_reason="") -> TransitionResult | None`

- [ ] **Step 1: Write the failing test**

```python
# backend/workflow/tests/test_system_transition.py
"""Externally triggered transitions bypass allowed_roles but nothing else.

Spec §4.2: "kein allowed_roles-Check (die Aktion kommt nicht von einer Person
oder einem Agenten, sondern vom externen System selbst)". Spec §8 flags the
same path as a new, unguarded automation route — hence the explicit
signature-gate refusal below.
"""
from __future__ import annotations

import pytest

from workflow.models import WorkflowHistoryEntry, WorkflowItemState
from workflow.services import WorkflowTransitionError, system_transition


@pytest.mark.django_db
def test_transition_runs_without_any_role(requirement_with_workflow):
    item, workspace = requirement_with_workflow

    result = system_transition(
        item_id=item.id,
        item_type="Requirement",
        workspace_id=workspace.id,
        target_state="in_review",
        tenant_id=workspace.tenant_id,
        client_name="github-webhook",
        change_reason="pull_request.merged",
    )

    assert result.new_state == "in_review"
    state = WorkflowItemState.objects.get(item_id=item.id, item_type="Requirement")
    assert state.current_state == "in_review"


@pytest.mark.django_db
def test_history_records_the_system_actor(requirement_with_workflow):
    item, workspace = requirement_with_workflow
    system_transition(
        item_id=item.id,
        item_type="Requirement",
        workspace_id=workspace.id,
        target_state="in_review",
        tenant_id=workspace.tenant_id,
        client_name="github-webhook",
        change_reason="pull_request.merged",
    )
    entry = WorkflowHistoryEntry.objects.latest("transitioned_at")
    assert entry.actor_type == "system"
    assert entry.client_name == "github-webhook"
    assert entry.change_reason == "pull_request.merged"


@pytest.mark.django_db
def test_transition_to_the_current_state_is_a_no_op(requirement_with_workflow):
    """Re-delivery safety: the same webhook twice must not double-transition."""
    item, workspace = requirement_with_workflow
    before = WorkflowHistoryEntry.objects.count()

    result = system_transition(
        item_id=item.id,
        item_type="Requirement",
        workspace_id=workspace.id,
        target_state="draft",
        tenant_id=workspace.tenant_id,
        client_name="github-webhook",
    )

    assert result is None
    assert WorkflowHistoryEntry.objects.count() == before


@pytest.mark.django_db
def test_an_undeclared_transition_still_fails(requirement_with_workflow):
    item, workspace = requirement_with_workflow
    with pytest.raises(WorkflowTransitionError):
        system_transition(
            item_id=item.id,
            item_type="Requirement",
            workspace_id=workspace.id,
            target_state="not_a_state",
            tenant_id=workspace.tenant_id,
            client_name="github-webhook",
        )


@pytest.mark.django_db
def test_a_signature_gated_transition_is_refused(requirement_with_signature_gate):
    """A system actor cannot produce a signature seal — fail closed."""
    item, workspace, target = requirement_with_signature_gate
    with pytest.raises(WorkflowTransitionError) as excinfo:
        system_transition(
            item_id=item.id,
            item_type="Requirement",
            workspace_id=workspace.id,
            target_state=target,
            tenant_id=workspace.tenant_id,
            client_name="github-webhook",
        )
    assert excinfo.value.error_code == "SIGNATURE_GATE_NOT_AVAILABLE"
```

Add two fixtures to `backend/workflow/tests/conftest.py`: `requirement_with_workflow` returns `(requirement, workspace)` with an initialised `WorkflowItemState` in `draft` and the default Requirement definition; `requirement_with_signature_gate` additionally sets `signature_gate: true` on one outgoing transition and returns its target state. Build both on the definition-seeding helper the existing workflow tests already use (grep `backend/workflow/tests/conftest.py`) rather than hand-rolling a `workflow_json`.

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST workflow/tests/test_system_transition.py -q`
Expected: FAIL with `ImportError: cannot import name 'system_transition' from 'workflow.services'`

- [ ] **Step 3: Write minimal implementation**

```python
# added to backend/workflow/services.py, directly after transition()
def system_transition(
    item_id: UUID | str,
    item_type: str,
    workspace_id: UUID | str,
    target_state: str,
    *,
    tenant_id: UUID | str,
    client_name: str,
    change_reason: str = "",
) -> Optional[TransitionResult]:
    """Execute a transition triggered by an external system, not a principal.

    Used only by the inbound integration path (GitHub/Jira webhook, spec
    §4.2). Differences from :func:`transition`:

    * **No ``allowed_roles`` check.** The actor is the remote system; there is
      no principal whose roles could be checked, and inventing one would grant
      a webhook whatever that fake principal holds.
    * **Signature-gated transitions are refused.** A system actor cannot
      produce a seal, and silently skipping the gate would turn the strongest
      control in the workflow engine into the weakest.
    * **Same-state requests are a no-op returning None.** GitHub re-delivers
      on any non-2xx, so the handler must be idempotent; this is the guard
      that makes it so (chosen over a delivery-id dedup table).

    Everything else — the transition must exist in the resolved definition,
    ``requires_change_reason``, the atomic state+history write — is unchanged.

    Args:
        item_id: Domain-entity id (``Requirement.id``, ``Adr.id``, ...) — NOT
            the Artifact id; ``WorkflowItemState.item_id`` is written from the
            domain id by every ``create_X`` service.
        item_type: Entity type, e.g. "Requirement".
        workspace_id: Workspace UUID.
        target_state: Requested new state.
        tenant_id: Active tenant; the caller has already armed it.
        client_name: Identity recorded on the history entry, e.g.
            "github-webhook".
        change_reason: Recorded reason, typically the external event name.

    Returns:
        The transition result, or None when the item is already in
        *target_state*.

    Raises:
        WorkflowTransitionError: Unknown transition, missing change reason, or
            a signature-gated target.
        WorkflowStateError: The item has no workflow state record.
    """
    item_id_uuid = UUID(str(item_id))
    workspace_uuid = UUID(str(workspace_id))

    lifecycle = _get_lifecycle()
    item_state = lifecycle.get_item_state(item_id_uuid, item_type, workspace_uuid)
    if item_state is None:
        raise WorkflowStateError(
            f"No workflow state found for item_id={item_id}, item_type={item_type}"
        )

    if item_state.current_state == target_state:
        logger.info(
            "system_transition: %s/%s already in %s — no-op",
            item_type,
            item_id_uuid,
            target_state,
        )
        return None

    ctx = AuthContext.system(tenant_id=UUID(str(tenant_id)))
    req = ValidationRequest(
        item_id=item_id_uuid,
        workspace_id=workspace_uuid,
        item_type=item_type,
        current_state=item_state.current_state,
        target_state=target_state,
        user_id=ctx.user_id,
        user_roles=ctx.active_roles,
        tenant_id=ctx.tenant_id,
        change_reason=change_reason,
        credential="",
    )
    result = _get_validator().validate(req, skip_role_check=True)

    if not result.valid:
        raise WorkflowTransitionError(
            error_code=result.error_code or "UNKNOWN",
            error_message=result.error_message or "Transition rejected",
        )
    if result.requires_signature:
        raise WorkflowTransitionError(
            error_code="SIGNATURE_GATE_NOT_AVAILABLE",
            error_message=(
                "This transition requires an electronic signature and cannot "
                "be executed by an external system trigger."
            ),
        )

    outcome = lifecycle.perform_transition(
        item_id=item_id_uuid,
        item_type=item_type,
        workspace_id=workspace_uuid,
        target_state=target_state,
        transitioned_by=client_name,
        validation_result=result,
        change_reason=change_reason,
        actor_type="system",
        client_name=client_name,
    )

    return TransitionResult(
        item_id=item_id_uuid,
        previous_state=outcome.previous_state,
        new_state=outcome.new_state,
        history_entry_id=outcome.history_entry_id,
        signature_seal=outcome.signature_seal,
    )
```

Two supporting changes:

1. `TransitionValidator.validate` gains a keyword-only `skip_role_check: bool = False` that short-circuits only the `allowed_roles` rule; every other rule runs unchanged. Also confirm `ValidationResult` exposes whether the matched transition is signature-gated — if it does not, add `requires_signature: bool = False` set where the signature rule is evaluated, and align the `result.requires_signature` read above with the real attribute name.
2. `StateLifecycleManager.perform_transition` gains keyword-only `actor_type: str = "user"` and `client_name: str = ""` and writes both onto the `WorkflowHistoryEntry` it creates.

Add `from typing import Optional` if absent and confirm `logger` exists in `workflow/services.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST workflow/tests -q`
Expected: PASS (5 new tests pass, the existing workflow suite unchanged)

- [ ] **Step 5: Commit**

```bash
git add backend/workflow
git commit -m "feat: add system_transition for externally triggered moves"
```

---

### Task 19: `external_trigger` resolution

**Files:**
- Create: `backend/integrations/triggers.py`
- Create: `backend/integrations/tests/test_triggers.py`

**Interfaces:**
- Consumes: nothing (pure function over a `workflow_json` document)
- Produces: `find_external_trigger_target(*, workflow_json: dict, current_state: str, system: str, event: str) -> str | None`, `EXTERNAL_TRIGGER_KEY`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_triggers.py
"""Match an inbound event against the external_trigger field on a transition.

Spec §4.2 puts the rule *on the transition* rather than in a parallel rule
engine, so the workflow definition stays the single source of truth for what
a state machine may do.
"""
from __future__ import annotations

from integrations.triggers import find_external_trigger_target

_JSON = {
    "states": ["draft", "in_review", "approved"],
    "transitions": [
        {
            "from_state": "draft",
            "to_state": "in_review",
            "allowed_roles": ["editor"],
            "external_trigger": {"system": "github", "event": "pull_request.merged"},
        },
        {
            "from_state": "in_review",
            "to_state": "approved",
            "allowed_roles": ["approver"],
            "external_trigger": {"system": "github", "event": "issue.closed"},
        },
        {"from_state": "draft", "to_state": "approved", "allowed_roles": ["admin"]},
    ],
}


def _find(current_state, system, event, workflow_json=_JSON):
    return find_external_trigger_target(
        workflow_json=workflow_json,
        current_state=current_state,
        system=system,
        event=event,
    )


def test_matching_trigger_returns_the_target_state():
    assert _find("draft", "github", "pull_request.merged") == "in_review"


def test_trigger_only_fires_from_its_own_source_state():
    assert _find("in_review", "github", "pull_request.merged") is None


def test_a_different_system_does_not_match():
    assert _find("draft", "jira", "pull_request.merged") is None


def test_a_different_event_does_not_match():
    assert _find("draft", "github", "issue.labeled") is None


def test_transitions_without_a_trigger_are_never_selected():
    assert _find("draft", "github", "") is None


def test_an_empty_workflow_json_is_safe():
    assert _find("draft", "github", "issue.closed", workflow_json={}) is None


def test_a_malformed_trigger_is_ignored():
    broken = {
        "transitions": [
            {"from_state": "draft", "to_state": "x", "external_trigger": "yes"}
        ]
    }
    assert _find("draft", "github", "issue.closed", workflow_json=broken) is None


def test_the_first_matching_transition_wins():
    duplicated = {
        "transitions": [
            {
                "from_state": "draft",
                "to_state": "first",
                "external_trigger": {"system": "github", "event": "issue.closed"},
            },
            {
                "from_state": "draft",
                "to_state": "second",
                "external_trigger": {"system": "github", "event": "issue.closed"},
            },
        ]
    }
    assert _find("draft", "github", "issue.closed", workflow_json=duplicated) == "first"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_triggers.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'integrations.triggers'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/integrations/triggers.py
"""Resolve which workflow transition an inbound external event fires.

The rule lives on the transition itself as an optional ``external_trigger``
object (spec §4.2) — additive to ``workflow_json``, so every existing
definition keeps working untouched.
"""
from __future__ import annotations

from typing import Any, Optional

#: Optional key on a transition in ``WorkflowEngineDefinition.workflow_json``.
EXTERNAL_TRIGGER_KEY = "external_trigger"


def find_external_trigger_target(
    *,
    workflow_json: dict[str, Any],
    current_state: str,
    system: str,
    event: str,
) -> Optional[str]:
    """Return the target state an external event should move the item to.

    Args:
        workflow_json: The resolved definition document for the item's
            workspace and type.
        current_state: The item's current workflow state — a trigger only
            fires from the state its transition declares as ``from_state``.
        system: "github" or "jira".
        event: Normalized event name, e.g. "pull_request.merged".

    Returns:
        The ``to_state`` of the first matching transition, or None when no
        transition declares this (system, event) pair from *current_state*.
        Malformed ``external_trigger`` values are skipped rather than raised
        on — a webhook must never 500 on a misconfigured definition.
    """
    if not event:
        return None

    for transition in workflow_json.get("transitions") or []:
        if not isinstance(transition, dict):
            continue
        trigger = transition.get(EXTERNAL_TRIGGER_KEY)
        if not isinstance(trigger, dict):
            continue
        if transition.get("from_state") != current_state:
            continue
        if trigger.get("system") != system or trigger.get("event") != event:
            continue
        target = transition.get("to_state")
        if isinstance(target, str) and target:
            return target

    return None


__all__ = ["EXTERNAL_TRIGGER_KEY", "find_external_trigger_target"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_triggers.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations/triggers.py backend/integrations/tests/test_triggers.py
git commit -m "feat: resolve external_trigger transitions from workflow json"
```

---

### Task 20: `InboundIntegrationService.apply_event`

**Files:**
- Create: `backend/integrations/inbound.py`
- Modify: `backend/workflow/services.py` (export `get_item_state(item_id, item_type, workspace_id)`)
- Create: `backend/integrations/tests/test_inbound.py`

**Interfaces:**
- Consumes: `integrations.events.NormalizedExternalEvent`, `integrations.triggers.find_external_trigger_target`, `workflow.services.get_workflow_json`, `.get_item_state`, `.system_transition`, `traceability.service.resolve_artifacts`, `audit.services.log_write`
- Produces: `InboundIntegrationService.apply_event(event, *, config) -> InboundResult(refs_updated: int, transitions: int)`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_inbound.py
"""Status mirror + optional workflow transition for one inbound event."""
from __future__ import annotations

import pytest

from integrations.events import NormalizedExternalEvent
from integrations.inbound import InboundIntegrationService
from integrations.models import ExternalRef, IntegrationConfig
from integrations.service import ExternalRefService


@pytest.fixture()
def linked(editor_ctx, requirement, workspace):
    ExternalRefService().link_external(
        editor_ctx,
        artifact_id=requirement.id,
        url="https://github.com/acme/widgets/pull/7",
    )
    config = IntegrationConfig.objects.create(
        tenant=workspace.tenant,
        workspace=workspace,
        system="github",
        repos=["acme/widgets"],
    )
    return requirement, config


def _merged_event() -> NormalizedExternalEvent:
    return NormalizedExternalEvent(
        system="github",
        event="pull_request.merged",
        repo="acme/widgets",
        external_id="7",
        status="merged",
        url="https://github.com/acme/widgets/pull/7",
    )


@pytest.mark.django_db
def test_status_and_synced_at_are_mirrored(linked):
    _, config = linked
    result = InboundIntegrationService().apply_event(_merged_event(), config=config)

    ref = ExternalRef.objects.get(external_id="7")
    assert ref.last_seen_status == "merged"
    assert ref.synced_at is not None
    assert result.refs_updated == 1


@pytest.mark.django_db
def test_an_event_for_an_unlinked_object_is_ignored(linked):
    _, config = linked
    event = NormalizedExternalEvent(
        system="github",
        event="issue.closed",
        repo="acme/widgets",
        external_id="999",
        status="closed",
        url="u",
    )
    result = InboundIntegrationService().apply_event(event, config=config)
    assert result.refs_updated == 0
    assert result.transitions == 0


@pytest.mark.django_db
def test_an_event_for_another_repo_is_ignored(linked):
    _, config = linked
    event = NormalizedExternalEvent(
        system="github",
        event="pull_request.merged",
        repo="acme/other",
        external_id="7",
        status="merged",
        url="u",
    )
    assert (
        InboundIntegrationService().apply_event(event, config=config).refs_updated == 0
    )


@pytest.mark.django_db
def test_a_matching_trigger_moves_the_artifact(linked, workflow_with_external_trigger):
    _, config = linked
    result = InboundIntegrationService().apply_event(_merged_event(), config=config)
    assert result.transitions == 1

    from workflow.models import WorkflowItemState

    state = WorkflowItemState.objects.get(item_type="Requirement")
    assert state.current_state == "in_review"


@pytest.mark.django_db
def test_replaying_the_same_event_changes_nothing(
    linked, workflow_with_external_trigger
):
    _, config = linked
    service = InboundIntegrationService()
    service.apply_event(_merged_event(), config=config)
    second = service.apply_event(_merged_event(), config=config)
    assert second.transitions == 0


@pytest.mark.django_db
def test_a_failing_transition_still_persists_the_status(
    linked, workflow_with_signature_gated_trigger
):
    """A refused transition must not roll back the status mirror."""
    _, config = linked
    result = InboundIntegrationService().apply_event(_merged_event(), config=config)
    assert result.refs_updated == 1
    assert result.transitions == 0
    assert ExternalRef.objects.get(external_id="7").last_seen_status == "merged"
```

Add `workflow_with_external_trigger` and `workflow_with_signature_gated_trigger` to `backend/integrations/tests/conftest.py`: both seed the workspace's Requirement definition with a `draft -> in_review` transition carrying `external_trigger: {"system": "github", "event": "pull_request.merged"}`, the second additionally setting `signature_gate: true`, and both initialise the requirement's `WorkflowItemState` to `draft` via `workflow.services.initialize_workflow_states`.

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_inbound.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'integrations.inbound'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/integrations/inbound.py
"""Apply one normalized external event to the ReqogniLoom side.

Two effects, in this order and deliberately not in one transaction:

1. Mirror ``last_seen_status``/``synced_at`` onto every matching ExternalRef.
2. Fire the workflow transition the matching ``external_trigger`` declares.

Step 2 failing must not undo step 1 — the external object really did change
state, and the dashboard mismatch view (spec §6) is precisely the surface that
shows "external says merged, we still say draft".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from django.utils import timezone

from audit.models import AuditEntry
from audit.services import log_write
from integrations.events import NormalizedExternalEvent
from integrations.models import ExternalRef, IntegrationConfig
from integrations.triggers import find_external_trigger_target

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InboundResult:
    """What one inbound event changed."""

    refs_updated: int
    transitions: int


class InboundIntegrationService:
    """Stage 2: turn an inbound webhook event into local state changes."""

    def apply_event(
        self, event: NormalizedExternalEvent, *, config: IntegrationConfig
    ) -> InboundResult:
        """Mirror the external status and run any triggered transition.

        Args:
            event: The normalized inbound event.
            config: The workspace configuration the request authenticated
                against. Its ``repos`` list is the allowlist: an event for a
                repository this workspace has not configured is ignored, so a
                valid secret cannot be used to reach arbitrary repositories.

        Returns:
            Counts of updated references and executed transitions.
        """
        if config.repos and event.repo not in config.repos:
            logger.info(
                "Inbound %s event for unconfigured repo %s — ignored",
                event.system,
                event.repo,
            )
            return InboundResult(refs_updated=0, transitions=0)

        refs = list(
            ExternalRef.objects.filter(
                artifact__workspace_id=config.workspace_id,
                system=event.system,
                repo=event.repo,
                external_id=event.external_id,
            ).select_related("artifact")
        )
        if not refs:
            return InboundResult(refs_updated=0, transitions=0)

        now = timezone.now()
        for ref in refs:
            ref.last_seen_status = event.status
            ref.synced_at = now
        ExternalRef.objects.bulk_update(refs, ["last_seen_status", "synced_at"])

        transitions = 0
        for ref in refs:
            if self._run_trigger(event, config=config, ref=ref):
                transitions += 1

        return InboundResult(refs_updated=len(refs), transitions=transitions)

    def _run_trigger(
        self,
        event: NormalizedExternalEvent,
        *,
        config: IntegrationConfig,
        ref: ExternalRef,
    ) -> bool:
        """Execute the transition *event* triggers for *ref*, if any.

        Returns True when a transition was actually performed. Never raises: a
        misconfigured rule or a refused transition is logged, not propagated —
        the webhook response must stay 200 so the provider does not disable
        the hook.
        """
        from traceability.service import resolve_artifacts
        from workflow.services import (
            WorkflowStateError,
            WorkflowTransitionError,
            get_item_state,
            get_workflow_json,
            system_transition,
        )

        resolved = resolve_artifacts([ref.artifact_id], config.tenant_id)
        if not resolved or not resolved[0].resolved:
            return False
        item_type = resolved[0].entity_type
        item_id = UUID(resolved[0].entity_id)

        state = get_item_state(item_id, item_type, config.workspace_id)
        if state is None:
            return False

        target = find_external_trigger_target(
            workflow_json=get_workflow_json(config.workspace_id, item_type),
            current_state=state.current_state,
            system=event.system,
            event=event.event,
        )
        if target is None:
            return False

        client_name = f"{event.system}-webhook"
        try:
            result = system_transition(
                item_id=item_id,
                item_type=item_type,
                workspace_id=config.workspace_id,
                target_state=target,
                tenant_id=config.tenant_id,
                client_name=client_name,
                change_reason=event.event,
            )
        except (WorkflowTransitionError, WorkflowStateError) as exc:
            logger.warning(
                "external_trigger refused for %s %s: %s", item_type, item_id, exc
            )
            return False

        if result is None:
            return False

        log_write(
            actor=client_name,
            actor_type=AuditEntry.ACTOR_TYPE_SYSTEM,
            operation=AuditEntry.OP_TRANSITION,
            entity_type=item_type,
            entity_id=result.item_id,
            change_reason=event.event,
            details={
                "system": event.system,
                "external_id": event.external_id,
                "from_state": result.previous_state,
                "to_state": result.new_state,
            },
        )
        return True


__all__ = ["InboundIntegrationService", "InboundResult"]
```

Add the missing read seam to `backend/workflow/services.py` (ADR-01: Layer 1 consumers must not instantiate `StateLifecycleManager` themselves — `workflow/tests/test_services_read_seams.py` guards this):

```python
def get_item_state(
    item_id: UUID | str, item_type: str, workspace_id: UUID | str
) -> Optional[WorkflowItemState]:
    """Return the WorkflowItemState for one item, or None when untracked."""
    return _get_lifecycle().get_item_state(
        UUID(str(item_id)), item_type, UUID(str(workspace_id))
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_inbound.py workflow/tests/test_services_read_seams.py -q`
Expected: PASS (6 passed, read-seam guard still green)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations/inbound.py backend/integrations/tests/test_inbound.py backend/workflow/services.py
git commit -m "feat: apply inbound external events to refs and workflow"
```

---

### Task 21: Public webhook receiver endpoints

**Files:**
- Create: `backend/integrations/throttling.py`
- Create: `backend/integrations/config_service.py` (only `lookup_enabled_config` in this task)
- Create: `backend/integrations/webhook_views.py`
- Modify: `backend/integrations/urls.py` (two routes)
- Modify: `backend/reqogniloom/settings.py` (`WEBHOOK_IN_THROTTLE_RATE` + `DEFAULT_THROTTLE_RATES["webhook_in"]`)
- Create: `backend/integrations/tests/test_webhook_views.py`

**Interfaces:**
- Consumes: `integrations.signatures`, `integrations.events`, `integrations.inbound.InboundIntegrationService`, `persistence.middleware.set_request_tenant`/`clear_request_tenant`, `rest_api.throttling.DynamicRateThrottle`
- Produces: `POST /api/v1/integrations/github/webhook/<uuid:config_id>/`, `POST /api/v1/integrations/jira/webhook/<uuid:config_id>/`, `integrations.config_service.lookup_enabled_config(*, config_id, system)`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_webhook_views.py
"""The two unauthenticated receivers — the only public write path we ship."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest
from django.test import Client

from integrations.models import ExternalRef, IntegrationConfig
from integrations.service import ExternalRefService

_SECRET = "hook-secret"


@pytest.fixture()
def github_config(editor_ctx, requirement, workspace):
    ExternalRefService().link_external(
        editor_ctx,
        artifact_id=requirement.id,
        url="https://github.com/acme/widgets/issues/142",
    )
    config = IntegrationConfig(
        tenant=workspace.tenant,
        workspace=workspace,
        system="github",
        repos=["acme/widgets"],
    )
    config.webhook_secret = _SECRET
    config.save()
    return config


def _github_body(action: str = "closed", state: str = "closed") -> bytes:
    return json.dumps(
        {
            "action": action,
            "repository": {"full_name": "acme/widgets"},
            "issue": {
                "number": 142,
                "state": state,
                "html_url": "https://github.com/acme/widgets/issues/142",
            },
        }
    ).encode("utf-8")


def _sign(body: bytes, secret: str = _SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _post(config_id, body, **headers):
    return Client().post(
        f"/api/v1/integrations/github/webhook/{config_id}/",
        data=body,
        content_type="application/json",
        **headers,
    )


@pytest.mark.django_db(transaction=True)
def test_a_signed_event_updates_the_reference(github_config):
    body = _github_body()
    response = _post(
        github_config.id,
        body,
        HTTP_X_HUB_SIGNATURE_256=_sign(body),
        HTTP_X_GITHUB_EVENT="issues",
    )
    assert response.status_code == 200, response.content
    assert ExternalRef.objects.get(external_id="142").last_seen_status == "closed"


@pytest.mark.django_db(transaction=True)
def test_a_wrong_signature_is_401_and_changes_nothing(github_config):
    body = _github_body()
    response = _post(
        github_config.id,
        body,
        HTTP_X_HUB_SIGNATURE_256=_sign(body, "wrong"),
        HTTP_X_GITHUB_EVENT="issues",
    )
    assert response.status_code == 401
    assert ExternalRef.objects.get(external_id="142").last_seen_status == ""


@pytest.mark.django_db(transaction=True)
def test_a_missing_signature_is_401(github_config):
    assert (
        _post(github_config.id, _github_body(), HTTP_X_GITHUB_EVENT="issues").status_code
        == 401
    )


@pytest.mark.django_db(transaction=True)
def test_an_unknown_config_id_is_404(github_config):
    body = _github_body()
    response = _post(
        uuid.uuid4(),
        body,
        HTTP_X_HUB_SIGNATURE_256=_sign(body),
        HTTP_X_GITHUB_EVENT="issues",
    )
    assert response.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_a_disabled_config_is_404(github_config):
    github_config.enabled = False
    github_config.save(update_fields=["enabled"])
    body = _github_body()
    assert (
        _post(
            github_config.id,
            body,
            HTTP_X_HUB_SIGNATURE_256=_sign(body),
            HTTP_X_GITHUB_EVENT="issues",
        ).status_code
        == 404
    )


@pytest.mark.django_db(transaction=True)
def test_an_ignored_event_type_is_200_and_a_no_op(github_config):
    body = json.dumps(
        {"action": "created", "repository": {"full_name": "acme/widgets"}}
    ).encode()
    response = _post(
        github_config.id,
        body,
        HTTP_X_HUB_SIGNATURE_256=_sign(body),
        HTTP_X_GITHUB_EVENT="star",
    )
    assert response.status_code == 200
    assert response.json()["processed"] is False


@pytest.mark.django_db(transaction=True)
def test_malformed_json_with_a_valid_signature_is_400(github_config):
    body = b"{not json"
    response = _post(
        github_config.id,
        body,
        HTTP_X_HUB_SIGNATURE_256=_sign(body),
        HTTP_X_GITHUB_EVENT="issues",
    )
    assert response.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_an_ambient_cookie_grants_nothing(github_config):
    """SA-36 shape: this endpoint must never honour a browser cookie."""
    client = Client()
    client.cookies["reqogniloom_access"] = "some-jwt"
    response = client.post(
        f"/api/v1/integrations/github/webhook/{github_config.id}/",
        data=_github_body(),
        content_type="application/json",
        HTTP_X_GITHUB_EVENT="issues",
    )
    assert response.status_code == 401


@pytest.mark.django_db(transaction=True)
def test_the_tenant_context_is_cleared_afterwards(github_config):
    from persistence.tenancy import TenantContext

    body = _github_body()
    _post(
        github_config.id,
        body,
        HTTP_X_HUB_SIGNATURE_256=_sign(body),
        HTTP_X_GITHUB_EVENT="issues",
    )
    assert TenantContext.is_set() is False


@pytest.mark.django_db(transaction=True)
def test_jira_requires_the_query_token(editor_ctx, requirement, workspace):
    ExternalRefService().link_external(
        editor_ctx,
        artifact_id=requirement.id,
        url="https://acme.atlassian.net/browse/PROJ-42",
    )
    config = IntegrationConfig(
        tenant=workspace.tenant, workspace=workspace, system="jira", repos=["PROJ"]
    )
    config.webhook_secret = _SECRET
    config.save()

    body = json.dumps(
        {
            "webhookEvent": "jira:issue_updated",
            "issue": {
                "key": "PROJ-42",
                "fields": {"project": {"key": "PROJ"}, "status": {"name": "Done"}},
                "self": "https://acme.atlassian.net/rest/api/2/issue/1",
            },
        }
    ).encode()
    url = f"/api/v1/integrations/jira/webhook/{config.id}/"

    assert Client().post(url, data=body, content_type="application/json").status_code == 401
    ok = Client().post(
        f"{url}?token={_SECRET}", data=body, content_type="application/json"
    )
    assert ok.status_code == 200
    assert ExternalRef.objects.get(external_id="PROJ-42").last_seen_status == "Done"


@pytest.mark.django_db(transaction=True)
def test_a_config_of_another_tenant_is_not_readable_while_one_is_armed(github_config):
    """The unscoped config lookup must not become a cross-tenant read path."""
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import Tenant

    other = Tenant.objects.create(name="rls-other")
    set_request_tenant(other.id)
    try:
        from integrations.config_service import lookup_enabled_config

        assert lookup_enabled_config(config_id=github_config.id, system="github") is None
    finally:
        clear_request_tenant()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_webhook_views.py -q`
Expected: FAIL — every HTTP test 404s (routes not registered) and the last one fails on `ModuleNotFoundError: No module named 'integrations.config_service'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/integrations/config_service.py
"""Reads and writes of IntegrationConfig / ExternalSystemCredential."""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from django.db import connection

logger = logging.getLogger(__name__)


def lookup_enabled_config(*, config_id: UUID, system: str):
    """Return the enabled IntegrationConfig for this id and system, or None.

    The one deliberately tenant-less read in this codebase's request path: the
    caller is an unauthenticated webhook, and this row IS the tenant
    resolution. Two layers have to be crossed for that:

    * ``unscoped`` skips the ORM-level TenantManager filter.
    * RLS on ``int_integration_config`` is bypassed for the duration of this
      single primary-key lookup by arming ``app.current_tenant`` to nothing
      and re-arming it afterwards — see the SET/RESET below. Nothing else
      runs inside that window, and the caller arms the real tenant from the
      returned row before touching any other table.

    A disabled config returns None, so switching an integration off in the UI
    takes effect immediately without rotating secrets.
    """
    from integrations.models import IntegrationConfig

    with connection.cursor() as cur:
        cur.execute("SELECT current_setting('app.current_tenant', true)")
        previous = cur.fetchone()[0]

    try:
        with connection.cursor() as cur:
            cur.execute("SET app.current_tenant = ''")
        return IntegrationConfig.unscoped.filter(
            id=config_id, system=system, enabled=True
        ).first()
    finally:
        with connection.cursor() as cur:
            if previous:
                cur.execute("SET app.current_tenant = %s", [previous])
            else:
                cur.execute("RESET app.current_tenant")
```

That empty-tenant read matches no rows under the standard policy, so the RLS migration for `int_integration_config` (Task 14) must add a second, read-only policy that permits a primary-key lookup with an unset tenant. Write it as a named policy `int_integration_config_webhook_lookup` with `FOR SELECT USING (NULLIF(current_setting('app.current_tenant', true), '') IS NULL)` and cover it with `test_a_config_of_another_tenant_is_not_readable_while_one_is_armed` — the point of that test is that the exemption applies only when *no* tenant is armed, never as a cross-tenant read for an armed one.

```python
# backend/integrations/throttling.py
"""Dedicated throttle scope for the public webhook receivers.

The generic ``anon`` scope (120/min in production) is shared with every other
unauthenticated request and is keyed by IP — GitHub delivers from a rotating
range, so the receivers get their own scope keyed by config id instead of
competing with (and being starved by) login traffic.
"""
from __future__ import annotations

from typing import Any

from rest_framework.request import Request

from rest_api.throttling import DynamicRateThrottle


class WebhookInRateThrottle(DynamicRateThrottle):
    """Per-config-id cap on inbound webhook deliveries."""

    scope = "webhook_in"

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        """Key on the config id from the URL, not on the source IP."""
        config_id = getattr(view, "kwargs", {}).get("config_id")
        return self.cache_format % {
            "scope": self.scope,
            "ident": str(config_id or self.get_ident(request)),
        }


__all__ = ["WebhookInRateThrottle"]
```

```python
# backend/integrations/webhook_views.py
"""Public webhook receivers for GitHub and Jira (spec §4.1).

Unauthenticated by design: GitHub and Jira hold no ReqogniLoom session. The
config id in the path selects *which* secret to verify against — it is not
itself a credential. Nothing but the shared secret authorises the request.

Two things this module must get right, both invisible from the call site:

* **Tenant context.** No authentication class runs, so nothing arms the ORM
  filter or the ``app.current_tenant`` RLS variable. Both are armed here from
  the config's tenant and cleared in a ``finally``.
* **Raw body.** HMAC is computed over the exact bytes received; re-serialising
  ``request.data`` would break every signature.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.config_service import lookup_enabled_config
from integrations.constants import SYSTEM_GITHUB, SYSTEM_JIRA
from integrations.events import normalize_github_event, normalize_jira_event
from integrations.inbound import InboundIntegrationService
from integrations.signatures import verify_github_signature, verify_jira_token
from integrations.throttling import WebhookInRateThrottle
from persistence.middleware import clear_request_tenant, set_request_tenant

logger = logging.getLogger(__name__)


class _BaseWebhookView(APIView):
    """Shared plumbing: no auth, own throttle scope, tenant armed by hand."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [WebhookInRateThrottle]
    system = ""

    @staticmethod
    def _parse(request: Request) -> Optional[dict[str, Any]]:
        try:
            return json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None

    @staticmethod
    def _invalid_payload() -> Response:
        return Response(
            {"error": {"code": "invalid_payload", "message": "Body is not JSON"}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _apply(self, event, config) -> Response:
        set_request_tenant(config.tenant_id)
        try:
            result = InboundIntegrationService().apply_event(event, config=config)
        finally:
            clear_request_tenant()
        return Response(
            {
                "processed": True,
                "refs_updated": result.refs_updated,
                "transitions": result.transitions,
            }
        )


class GitHubWebhookView(_BaseWebhookView):
    """``POST /api/v1/integrations/github/webhook/<config_id>/``."""

    system = SYSTEM_GITHUB

    def post(self, request: Request, config_id: UUID, **kwargs: Any) -> Response:
        """Verify ``X-Hub-Signature-256`` and apply the event."""
        config = lookup_enabled_config(config_id=config_id, system=self.system)
        if config is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not verify_github_signature(
            request.body,
            request.headers.get("X-Hub-Signature-256"),
            config.webhook_secret,
        ):
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        payload = self._parse(request)
        if payload is None:
            return self._invalid_payload()

        event = normalize_github_event(
            request.headers.get("X-GitHub-Event", ""), payload
        )
        if event is None:
            return Response({"processed": False})

        return self._apply(event, config)


class JiraWebhookView(_BaseWebhookView):
    """``POST /api/v1/integrations/jira/webhook/<config_id>/?token=...``.

    Jira Server/Data-Center webhooks have no HMAC option; the shared secret
    travels in the URL (spec §4.1, §8). Deployments must keep query strings
    out of access logs — this module never logs the request URL.
    """

    system = SYSTEM_JIRA

    def post(self, request: Request, config_id: UUID, **kwargs: Any) -> Response:
        """Verify the ``token`` query parameter and apply the event."""
        config = lookup_enabled_config(config_id=config_id, system=self.system)
        if config is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not verify_jira_token(
            request.query_params.get("token"), config.webhook_secret
        ):
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        payload = self._parse(request)
        if payload is None:
            return self._invalid_payload()

        event = normalize_jira_event(payload)
        if event is None:
            return Response({"processed": False})

        return self._apply(event, config)


__all__ = ["GitHubWebhookView", "JiraWebhookView"]
```

In `backend/integrations/urls.py`, add the import and the two routes:

```python
from integrations.webhook_views import GitHubWebhookView, JiraWebhookView
```

```python
    path(
        "integrations/github/webhook/<uuid:config_id>/",
        GitHubWebhookView.as_view(),
        name="api-v1-github-webhook",
    ),
    path(
        "integrations/jira/webhook/<uuid:config_id>/",
        JiraWebhookView.as_view(),
        name="api-v1-jira-webhook",
    ),
```

In `backend/reqogniloom/settings.py`, next to the other rates:

```python
# Inbound webhook deliveries are keyed per integration config, not per IP —
# GitHub delivers from a rotating range and must not compete with the shared
# anon bucket.
WEBHOOK_IN_THROTTLE_RATE: str = _throttle_rate(
    "WEBHOOK_IN_THROTTLE_RATE", prod="600/min", non_prod="20000/min"
)
```

and in `DEFAULT_THROTTLE_RATES`: `"webhook_in": WEBHOOK_IN_THROTTLE_RATE or None,`.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_webhook_views.py -q`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations backend/reqogniloom/settings.py
git commit -m "feat: add GitHub and Jira webhook receivers"
```

---

### Task 22: REST CRUD for integration configuration

**Files:**
- Modify: `backend/integrations/config_service.py` (add `IntegrationConfigService`)
- Modify: `backend/integrations/serializers.py` (add `IntegrationConfigSerializer`)
- Modify: `backend/integrations/rest.py` (add `WorkspaceIntegrationConfigView`)
- Modify: `backend/integrations/urls.py` (one route)
- Create: `backend/integrations/tests/test_config_rest.py`

**Interfaces:**
- Consumes: `application.base.ServiceBase`, `integrations.models.IntegrationConfig`
- Produces: `IntegrationConfigService.list_configs(ctx, *, workspace_id)`, `.upsert_config(ctx, *, workspace_id, system, repos, webhook_secret, outbound_rules, enabled)`; `GET/PUT /api/v1/workspaces/<uuid:workspace_id>/integrations/`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_config_rest.py
"""Admin-only configuration surface for the Integrations settings tab."""
from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_get_returns_an_entry_per_system_even_when_unconfigured(
    api_client_admin, workspace
):
    response = api_client_admin.get(
        f"/api/v1/workspaces/{workspace.id}/integrations/"
    )
    assert response.status_code == 200
    assert {row["system"] for row in response.data} == {"github", "jira"}
    assert all(row["has_webhook_secret"] is False for row in response.data)


@pytest.mark.django_db
def test_put_creates_and_updates_a_config(api_client_admin, workspace):
    response = api_client_admin.put(
        f"/api/v1/workspaces/{workspace.id}/integrations/",
        {
            "system": "github",
            "repos": ["acme/widgets"],
            "webhook_secret": "hook-secret",
            "enabled": True,
            "outbound_rules": [],
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.data["repos"] == ["acme/widgets"]
    assert response.data["has_webhook_secret"] is True
    assert response.data["webhook_url"].endswith(
        f"/api/v1/integrations/github/webhook/{response.data['id']}/"
    )


@pytest.mark.django_db
def test_the_secret_is_never_returned(api_client_admin, workspace):
    api_client_admin.put(
        f"/api/v1/workspaces/{workspace.id}/integrations/",
        {"system": "github", "repos": [], "webhook_secret": "hook-secret"},
        format="json",
    )
    response = api_client_admin.get(
        f"/api/v1/workspaces/{workspace.id}/integrations/"
    )
    body = str(response.data)
    assert "hook-secret" not in body
    assert "webhook_secret_encrypted" not in body


@pytest.mark.django_db
def test_an_omitted_secret_keeps_the_stored_one(api_client_admin, workspace):
    url = f"/api/v1/workspaces/{workspace.id}/integrations/"
    api_client_admin.put(
        url,
        {"system": "github", "repos": [], "webhook_secret": "hook-secret"},
        format="json",
    )
    api_client_admin.put(url, {"system": "github", "repos": ["a/b"]}, format="json")

    from integrations.models import IntegrationConfig

    assert IntegrationConfig.objects.get(system="github").webhook_secret == "hook-secret"


@pytest.mark.django_db
def test_an_editor_cannot_configure_integrations(api_client_editor, workspace):
    response = api_client_editor.put(
        f"/api/v1/workspaces/{workspace.id}/integrations/",
        {"system": "github", "repos": []},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_an_unknown_system_is_400(api_client_admin, workspace):
    response = api_client_admin.put(
        f"/api/v1/workspaces/{workspace.id}/integrations/",
        {"system": "gitlab", "repos": []},
        format="json",
    )
    assert response.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_config_rest.py -q`
Expected: FAIL — all six 404 (route not registered)

- [ ] **Step 3: Write minimal implementation**

```python
# appended to backend/integrations/config_service.py
from application.base import ServiceBase
from auth_tenancy.models import ROLE_ADMIN


class IntegrationConfigService(ServiceBase):
    """Workspace-admin CRUD over IntegrationConfig.

    ``webhook_secret`` is write-only end to end: it enters through
    :meth:`upsert_config` and is never part of any read shape — the UI shows
    ``has_webhook_secret`` instead, exactly like the LLM and Honcho settings
    surfaces do for their keys.
    """

    def list_configs(self, ctx, *, workspace_id: UUID) -> list[dict]:
        """Return one entry per supported system, configured or not.

        A never-configured system yields a placeholder row so the settings tab
        can render both systems without a separate "supported systems"
        endpoint.
        """
        from integrations.constants import SYSTEM_CHOICES
        from integrations.models import IntegrationConfig

        self._set_tenant_context(ctx)
        self._assert_permission(ctx, ROLE_ADMIN)

        existing = {
            row.system: row
            for row in IntegrationConfig.objects.filter(workspace_id=workspace_id)
        }
        result = []
        for system, _label in SYSTEM_CHOICES:
            row = existing.get(system)
            result.append(
                {
                    "id": str(row.id) if row else None,
                    "system": system,
                    "repos": row.repos if row else [],
                    "outbound_rules": row.outbound_rules if row else [],
                    "enabled": row.enabled if row else False,
                    "has_webhook_secret": bool(row and row.webhook_secret_encrypted),
                }
            )
        return result

    def upsert_config(
        self,
        ctx,
        *,
        workspace_id: UUID,
        system: str,
        repos: list[str],
        webhook_secret: Optional[str] = None,
        outbound_rules: Optional[list] = None,
        enabled: bool = True,
    ) -> dict:
        """Create or update the config for one system in one workspace.

        ``webhook_secret=None`` means "leave the stored secret untouched" —
        the UI cannot re-send a value it never received. An explicit empty
        string clears it.
        """
        from integrations.models import IntegrationConfig

        self._set_tenant_context(ctx)
        self._assert_permission(ctx, ROLE_ADMIN)

        config, _created = IntegrationConfig.objects.get_or_create(
            tenant_id=ctx.tenant_id, workspace_id=workspace_id, system=system
        )
        config.repos = list(repos or [])
        config.enabled = bool(enabled)
        if outbound_rules is not None:
            config.outbound_rules = list(outbound_rules)
        if webhook_secret is not None:
            config.webhook_secret = webhook_secret
        config.save()

        self._audit(
            ctx,
            "update",
            "IntegrationConfig",
            config.id,
            details={"system": system, "repos": config.repos},
        )
        return {
            "id": str(config.id),
            "system": config.system,
            "repos": config.repos,
            "outbound_rules": config.outbound_rules,
            "enabled": config.enabled,
            "has_webhook_secret": bool(config.webhook_secret_encrypted),
        }
```

```python
# appended to backend/integrations/serializers.py
from integrations.constants import SYSTEM_CHOICES


class IntegrationConfigSerializer(serializers.Serializer):
    """Read shape. The secret is deliberately absent — only its presence."""

    id = serializers.CharField(read_only=True, allow_null=True)
    system = serializers.CharField(read_only=True)
    repos = serializers.ListField(child=serializers.CharField(), read_only=True)
    outbound_rules = serializers.ListField(read_only=True)
    enabled = serializers.BooleanField(read_only=True)
    has_webhook_secret = serializers.BooleanField(read_only=True)
    webhook_url = serializers.CharField(read_only=True, allow_null=True)


class IntegrationConfigWriteSerializer(serializers.Serializer):
    """Write shape. ``webhook_secret`` omitted = keep the stored value."""

    system = serializers.ChoiceField(choices=[c[0] for c in SYSTEM_CHOICES])
    repos = serializers.ListField(child=serializers.CharField(max_length=255))
    webhook_secret = serializers.CharField(
        required=False, allow_blank=True, write_only=True, max_length=512
    )
    outbound_rules = serializers.ListField(required=False)
    enabled = serializers.BooleanField(required=False, default=True)
```

```python
# appended to backend/integrations/rest.py
class WorkspaceIntegrationConfigView(APIView):
    """``/api/v1/workspaces/<workspace_id>/integrations/`` — list and upsert."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = IntegrationConfigService()

    @staticmethod
    def _with_url(request: Request, row: dict) -> dict:
        """Attach the ready-to-paste webhook URL for a configured system."""
        if not row.get("id"):
            return {**row, "webhook_url": None}
        path = f"/api/v1/integrations/{row['system']}/webhook/{row['id']}/"
        return {**row, "webhook_url": request.build_absolute_uri(path)}

    def get(self, request: Request, workspace_id: UUID, **kwargs: Any) -> Response:
        """Return one entry per supported system."""
        rows = self._service.list_configs(
            request.auth_context, workspace_id=workspace_id
        )
        return Response(
            IntegrationConfigSerializer(
                [self._with_url(request, row) for row in rows], many=True
            ).data
        )

    def put(self, request: Request, workspace_id: UUID, **kwargs: Any) -> Response:
        """Create or update the configuration for one system."""
        payload = IntegrationConfigWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        row = self._service.upsert_config(
            request.auth_context,
            workspace_id=workspace_id,
            system=data["system"],
            repos=data["repos"],
            webhook_secret=data.get("webhook_secret"),
            outbound_rules=data.get("outbound_rules"),
            enabled=data.get("enabled", True),
        )
        return Response(IntegrationConfigSerializer(self._with_url(request, row)).data)
```

In `backend/integrations/urls.py`:

```python
    path(
        "workspaces/<uuid:workspace_id>/integrations/",
        WorkspaceIntegrationConfigView.as_view(),
        name="api-v1-workspace-integrations",
    ),
```

Confirm `ROLE_ADMIN`'s exact import path in `backend/auth_tenancy/models.py` and that `_assert_permission` is the right admin gate for a workspace-scoped setting (compare with how `WorkspaceMembersView` gates); use whichever check that surface uses so the 403 test matches production behaviour.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_config_rest.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations
git commit -m "feat: add REST CRUD for workspace integration config"
```

---

### Task 23: Integrations settings tab

**Files:**
- Modify: `frontend/src/api/integrations.ts` (config functions)
- Create: `frontend/src/components/SystemSettings/IntegrationsTab.tsx`
- Create: `frontend/src/components/SystemSettings/IntegrationsTab.test.tsx`
- Modify: `frontend/src/components/SystemSettings/SystemSettings.tsx:33-80` (new tab id + label + panel)
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`

**Interfaces:**
- Consumes: `apiClient`
- Produces: `IntegrationConfig` type; `integrationsApi.listConfigs(workspaceId)`, `.saveConfig(workspaceId, payload)`; `IntegrationsTab({ workspaceId })`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/SystemSettings/IntegrationsTab.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { IntegrationsTab } from "./IntegrationsTab";
import { integrationsApi } from "../../api/integrations";

const configs = [
  {
    id: "cfg-1",
    system: "github" as const,
    repos: ["acme/widgets"],
    outboundRules: [],
    enabled: true,
    hasWebhookSecret: true,
    webhookUrl: "https://app.example/api/v1/integrations/github/webhook/cfg-1/",
  },
  {
    id: null,
    system: "jira" as const,
    repos: [],
    outboundRules: [],
    enabled: false,
    hasWebhookSecret: false,
    webhookUrl: null,
  },
];

describe("IntegrationsTab", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(integrationsApi, "listConfigs").mockResolvedValue(configs);
  });

  it("renders a card per system", async () => {
    render(<IntegrationsTab workspaceId="ws" />);
    expect(await screen.findByTestId("integration-card-github")).toBeInTheDocument();
    expect(screen.getByTestId("integration-card-jira")).toBeInTheDocument();
  });

  it("shows the webhook url only for a configured system", async () => {
    render(<IntegrationsTab workspaceId="ws" />);
    expect(await screen.findByTestId("integration-webhook-url-github")).toHaveTextContent(
      "/api/v1/integrations/github/webhook/cfg-1/",
    );
    expect(screen.queryByTestId("integration-webhook-url-jira")).toBeNull();
  });

  it("never renders the stored secret, only its presence", async () => {
    render(<IntegrationsTab workspaceId="ws" />);
    expect(await screen.findByTestId("integration-secret-set-github")).toBeInTheDocument();
    expect(
      (screen.getByTestId("integration-secret-github") as HTMLInputElement).value,
    ).toBe("");
  });

  it("saves repos and secret together", async () => {
    const save = vi.spyOn(integrationsApi, "saveConfig").mockResolvedValue(configs[0]);
    render(<IntegrationsTab workspaceId="ws" />);

    await userEvent.clear(await screen.findByTestId("integration-repos-github"));
    await userEvent.type(
      screen.getByTestId("integration-repos-github"),
      "acme/widgets, acme/gadgets",
    );
    await userEvent.type(screen.getByTestId("integration-secret-github"), "new-secret");
    await userEvent.click(screen.getByTestId("integration-save-github"));

    await waitFor(() =>
      expect(save).toHaveBeenCalledWith("ws", {
        system: "github",
        repos: ["acme/widgets", "acme/gadgets"],
        webhookSecret: "new-secret",
        enabled: true,
      }),
    );
  });

  it("omits the secret when the field was left empty", async () => {
    const save = vi.spyOn(integrationsApi, "saveConfig").mockResolvedValue(configs[0]);
    render(<IntegrationsTab workspaceId="ws" />);
    await userEvent.click(await screen.findByTestId("integration-save-github"));

    await waitFor(() =>
      expect(save).toHaveBeenCalledWith("ws", {
        system: "github",
        repos: ["acme/widgets"],
        enabled: true,
      }),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$VITEST "npx vitest run src/components/SystemSettings/IntegrationsTab.test.tsx --testTimeout=30000"`
Expected: FAIL with `Failed to resolve import "./IntegrationsTab"`

- [ ] **Step 3: Write minimal implementation**

Add to `frontend/src/api/integrations.ts`:

```ts
export interface IntegrationConfig {
  id: string | null;
  system: ExternalSystem;
  repos: string[];
  outboundRules: unknown[];
  enabled: boolean;
  hasWebhookSecret: boolean;
  webhookUrl: string | null;
}

export interface IntegrationConfigInput {
  system: ExternalSystem;
  repos: string[];
  webhookSecret?: string;
  enabled: boolean;
}

interface IntegrationConfigWire {
  id: string | null;
  system: ExternalSystem;
  repos: string[];
  outbound_rules: unknown[];
  enabled: boolean;
  has_webhook_secret: boolean;
  webhook_url: string | null;
}

function toConfig(wire: IntegrationConfigWire): IntegrationConfig {
  return {
    id: wire.id,
    system: wire.system,
    repos: wire.repos,
    outboundRules: wire.outbound_rules,
    enabled: wire.enabled,
    hasWebhookSecret: wire.has_webhook_secret,
    webhookUrl: wire.webhook_url,
  };
}
```

and two functions on `integrationsApi`:

```ts
  async listConfigs(workspaceId: UUID): Promise<IntegrationConfig[]> {
    const response = await apiClient.get<IntegrationConfigWire[]>(
      `/workspaces/${workspaceId}/integrations/`,
    );
    return response.data.map(toConfig);
  },

  async saveConfig(
    workspaceId: UUID,
    input: IntegrationConfigInput,
  ): Promise<IntegrationConfig> {
    const body: Record<string, unknown> = {
      system: input.system,
      repos: input.repos,
      enabled: input.enabled,
    };
    // Omitted, not empty: an empty string clears the stored secret server-side.
    if (input.webhookSecret) body.webhook_secret = input.webhookSecret;
    const response = await apiClient.put<IntegrationConfigWire>(
      `/workspaces/${workspaceId}/integrations/`,
      body,
    );
    return toConfig(response.data);
  },
```

```tsx
// frontend/src/components/SystemSettings/IntegrationsTab.tsx
/**
 * System settings > Integrations: one card per external system with its
 * repository list, webhook secret and ready-to-paste webhook URL (spec §4.2).
 *
 * A flat list, not a canvas — there is no graph structure to draw here.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { integrationsApi } from "../../api/integrations";
import type { IntegrationConfig } from "../../api/integrations";
import type { UUID } from "../../types";

export interface IntegrationsTabProps {
  workspaceId: UUID;
}

function parseRepos(raw: string): string[] {
  return raw
    .split(",")
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
}

export function IntegrationsTab({ workspaceId }: IntegrationsTabProps): JSX.Element {
  const { t } = useTranslation();
  const [configs, setConfigs] = useState<IntegrationConfig[]>([]);
  const [repoDraft, setRepoDraft] = useState<Record<string, string>>({});
  const [secretDraft, setSecretDraft] = useState<Record<string, string>>({});

  const reload = useCallback(async (): Promise<void> => {
    const rows = await integrationsApi.listConfigs(workspaceId);
    setConfigs(rows);
    setRepoDraft(
      Object.fromEntries(rows.map((row) => [row.system, row.repos.join(", ")])),
    );
  }, [workspaceId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const save = async (config: IntegrationConfig): Promise<void> => {
    const secret = secretDraft[config.system] ?? "";
    await integrationsApi.saveConfig(workspaceId, {
      system: config.system,
      repos: parseRepos(repoDraft[config.system] ?? ""),
      enabled: config.enabled,
      ...(secret ? { webhookSecret: secret } : {}),
    });
    setSecretDraft((prev) => ({ ...prev, [config.system]: "" }));
    await reload();
  };

  return (
    <div data-testid="integrations-tab">
      {configs.map((config) => (
        <section
          key={config.system}
          data-testid={`integration-card-${config.system}`}
        >
          <h3>{t(`integrations.system.${config.system}`)}</h3>

          <label htmlFor={`integration-repos-${config.system}`}>
            {t("integrations.reposLabel")}
          </label>
          <input
            id={`integration-repos-${config.system}`}
            data-testid={`integration-repos-${config.system}`}
            value={repoDraft[config.system] ?? ""}
            onChange={(event) =>
              setRepoDraft((prev) => ({
                ...prev,
                [config.system]: event.target.value,
              }))
            }
          />

          <label htmlFor={`integration-secret-${config.system}`}>
            {t("integrations.secretLabel")}
          </label>
          <input
            id={`integration-secret-${config.system}`}
            data-testid={`integration-secret-${config.system}`}
            type="password"
            autoComplete="off"
            value={secretDraft[config.system] ?? ""}
            placeholder={t("integrations.secretPlaceholder")}
            onChange={(event) =>
              setSecretDraft((prev) => ({
                ...prev,
                [config.system]: event.target.value,
              }))
            }
          />
          {config.hasWebhookSecret ? (
            <span data-testid={`integration-secret-set-${config.system}`}>
              {t("integrations.secretSet")}
            </span>
          ) : null}

          {config.webhookUrl ? (
            <code data-testid={`integration-webhook-url-${config.system}`}>
              {config.webhookUrl}
            </code>
          ) : null}

          <button
            type="button"
            data-testid={`integration-save-${config.system}`}
            onClick={() => void save(config)}
          >
            {t("integrations.save")}
          </button>
        </section>
      ))}
    </div>
  );
}
```

In `SystemSettings.tsx`: extend `SystemTabId` with `"integrations"`, add it to `TAB_IDS`, add `{ id: "integrations", label: t("systemSettings.tabs.integrations", "Integrations") }` to `TABS`, and render `<IntegrationsTab workspaceId={...} />` in the panel switch, taking the workspace id from the same context the sibling tabs use.

New locale keys under `integrations`: `system.github` ("GitHub"), `system.jira` ("Jira"), `reposLabel` (EN "Repositories / projects (comma separated)", DE "Repositories / Projekte (kommagetrennt)"), `secretLabel` (EN "Webhook secret", DE "Webhook-Secret"), `secretPlaceholder` (EN "Leave empty to keep the stored secret", DE "Leer lassen, um das gespeicherte Secret zu behalten"), `secretSet` (EN "A secret is stored", DE "Ein Secret ist hinterlegt"), `save` (EN "Save", DE "Speichern"); plus `systemSettings.tabs.integrations` (EN "Integrations", DE "Integrationen").

- [ ] **Step 4: Run test to verify it passes**

Run: `$VITEST "npx vitest run src/components/SystemSettings src/api/integrations.test.ts --testTimeout=30000"`
Expected: PASS (5 new tests pass, the existing SystemSettings suite unchanged)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/integrations.ts frontend/src/components/SystemSettings frontend/src/i18n/locales
git commit -m "feat: add integrations tab to system settings"
```

---

# Stage 3 — Outbound and Agent

### Task 24: `ExternalSystemCredential`

**Files:**
- Modify: `backend/integrations/models.py` (add `ExternalSystemCredential`)
- Create: `backend/integrations/migrations/0006_external_credential.py` (generated)
- Create: `backend/integrations/migrations/0007_external_credential_rls.py`
- Modify: `backend/integrations/config_service.py` (add `CredentialService`)
- Modify: `backend/integrations/serializers.py`, `rest.py`, `urls.py`
- Create: `backend/integrations/tests/test_credentials.py`

**Interfaces:**
- Consumes: `persistence.encryption.encrypt_secret`, `decrypt_secret`
- Produces: `integrations.models.ExternalSystemCredential` with a `token` property; `CredentialService.upsert(ctx, *, workspace_id, system, token, api_base_url, account_email)`, `.get_for(workspace_id, system)`; `PUT /api/v1/workspaces/<uuid:workspace_id>/integration-credentials/`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_credentials.py
"""Per-workspace PAT storage, same encryption seam as the LLM/Honcho keys."""
from __future__ import annotations

import pytest

from integrations.config_service import CredentialService
from integrations.models import ExternalSystemCredential
from persistence.encryption import ENCRYPTED_PREFIX


@pytest.mark.django_db
def test_token_is_encrypted_at_rest(admin_ctx, workspace):
    CredentialService().upsert(
        admin_ctx,
        workspace_id=workspace.id,
        system="github",
        token="ghp_example",
        api_base_url="https://api.github.com",
        account_email="",
    )
    row = ExternalSystemCredential.objects.get(system="github")
    assert row.token_encrypted.startswith(ENCRYPTED_PREFIX)
    assert "ghp_example" not in row.token_encrypted
    assert row.token == "ghp_example"


@pytest.mark.django_db
def test_upsert_replaces_the_existing_row(admin_ctx, workspace):
    service = CredentialService()
    for token in ("first", "second"):
        service.upsert(
            admin_ctx,
            workspace_id=workspace.id,
            system="github",
            token=token,
            api_base_url="https://api.github.com",
            account_email="",
        )
    assert ExternalSystemCredential.objects.filter(system="github").count() == 1
    assert ExternalSystemCredential.objects.get(system="github").token == "second"


@pytest.mark.django_db
def test_get_for_returns_none_when_unconfigured(workspace):
    assert CredentialService().get_for(workspace.id, "jira") is None


@pytest.mark.django_db
def test_an_editor_cannot_store_a_token(editor_ctx, workspace):
    from application.base import PermissionDeniedError

    with pytest.raises(PermissionDeniedError):
        CredentialService().upsert(
            editor_ctx,
            workspace_id=workspace.id,
            system="github",
            token="ghp_example",
            api_base_url="",
            account_email="",
        )


@pytest.mark.django_db
def test_rest_never_returns_the_token(api_client_admin, workspace):
    url = f"/api/v1/workspaces/{workspace.id}/integration-credentials/"
    response = api_client_admin.put(
        url,
        {
            "system": "github",
            "token": "ghp_example",
            "api_base_url": "https://api.github.com",
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.data["has_token"] is True
    assert "ghp_example" not in str(response.data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_credentials.py -q`
Expected: FAIL with `ImportError: cannot import name 'CredentialService' from 'integrations.config_service'`

- [ ] **Step 3: Write minimal implementation**

```python
# appended to backend/integrations/models.py
class ExternalSystemCredential(TenantScopedModel):
    """One personal access token per workspace and system.

    Beyond the design sketch's four fields:

    * ``api_base_url`` — Jira lives on a per-tenant host and GitHub Enterprise
      on a customer host; without it the adapters have no address to call.
    * ``account_email`` — Jira Cloud authenticates with ``email:token`` Basic
      auth, so the token alone is not a credential there.

    Spec §8: a PAT is a single broad grant with no fine-grained scoping. The
    settings UI must tell the admin to mint a token with minimal repository
    scopes; that cannot be enforced technically without a GitHub App.
    """

    workspace = models.ForeignKey(
        "persistence.Workspace",
        on_delete=models.CASCADE,
        related_name="external_credentials",
    )
    system = models.CharField(max_length=32, choices=SYSTEM_CHOICES)
    api_base_url = models.URLField(max_length=2048, blank=True, default="")
    account_email = models.CharField(max_length=255, blank=True, default="")
    token_encrypted = models.TextField(blank=True, default="")
    created_by = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "int_external_credential"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "workspace", "system"],
                name="uq_external_credential_ws_system",
            ),
        ]

    @property
    def token(self) -> str:
        """Return the decrypted token ("" when unset)."""
        return decrypt_secret(self.token_encrypted)

    @token.setter
    def token(self, value: str) -> None:
        self.token_encrypted = encrypt_secret(value or "")

    def __str__(self) -> str:
        return f"ExternalSystemCredential:{self.workspace_id}:{self.system}"
```

```python
# appended to backend/integrations/config_service.py
class CredentialService(ServiceBase):
    """Workspace-admin storage and internal retrieval of external PATs."""

    def upsert(
        self,
        ctx,
        *,
        workspace_id: UUID,
        system: str,
        token: str,
        api_base_url: str,
        account_email: str,
    ) -> dict:
        """Store or replace the credential for one system in one workspace."""
        from integrations.models import ExternalSystemCredential

        self._set_tenant_context(ctx)
        self._assert_permission(ctx, ROLE_ADMIN)

        row, _created = ExternalSystemCredential.objects.get_or_create(
            tenant_id=ctx.tenant_id, workspace_id=workspace_id, system=system
        )
        row.api_base_url = api_base_url or ""
        row.account_email = account_email or ""
        row.created_by = ctx.user_id
        if token:
            row.token = token
        row.save()

        self._audit(
            ctx,
            "update",
            "ExternalSystemCredential",
            row.id,
            details={"system": system},
        )
        return {
            "id": str(row.id),
            "system": row.system,
            "api_base_url": row.api_base_url,
            "account_email": row.account_email,
            "has_token": bool(row.token_encrypted),
        }

    @staticmethod
    def get_for(workspace_id: UUID, system: str):
        """Return the credential row for internal adapter use, or None.

        No ctx: the outbound adapters run off the event bus, where the caller
        has already armed the tenant context from the outbox record. This
        method deliberately performs no permission check — it is not reachable
        from any transport.
        """
        from integrations.models import ExternalSystemCredential

        return ExternalSystemCredential.objects.filter(
            workspace_id=workspace_id, system=system
        ).first()
```

Serializer (`ExternalCredentialSerializer` with `id`, `system`, `api_base_url`, `account_email`, `has_token`; write serializer with `system` choice, `token` write-only, `api_base_url`, `account_email`), a `WorkspaceIntegrationCredentialView` in `rest.py` shaped exactly like `WorkspaceIntegrationConfigView`, and the route:

```python
    path(
        "workspaces/<uuid:workspace_id>/integration-credentials/",
        WorkspaceIntegrationCredentialView.as_view(),
        name="api-v1-workspace-integration-credentials",
    ),
```

Generate `0006_external_credential.py` with `$MANAGE makemigrations integrations --name external_credential`, then write `0007_external_credential_rls.py` from the `0002` template with `_TENANT_TABLES = ["int_external_credential"]`. This table gets **no** webhook-lookup exemption policy — nothing unauthenticated ever reads a credential.

Add an `admin_ctx` fixture to `backend/integrations/tests/conftest.py`, identical to `editor_ctx` but with `active_roles=("admin",)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_credentials.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations
git commit -m "feat: add encrypted external system credentials"
```

---

### Task 25: GitHub and Jira issue adapters

**Files:**
- Create: `backend/integrations/adapters.py`
- Create: `backend/integrations/tests/test_adapters.py`

**Interfaces:**
- Consumes: `requests` (already pinned), `integrations.config_service.CredentialService.get_for`, `integrations.service.ExternalRefService`
- Produces: `IssueAdapter` protocol with `create_issue(*, workspace_id, tenant_id, repo, title, body) -> ParsedExternalUrl`; `GitHubIssueAdapter`, `JiraIssueAdapter`, `ADAPTERS: dict[str, IssueAdapter]`, `AdapterError`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_adapters.py
"""Outbound adapters: one event, one adapter per target system.

The HTTP call is the only thing mocked — the request shape it produces is
exactly what these tests pin.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from integrations.adapters import ADAPTERS, AdapterError, GitHubIssueAdapter, JiraIssueAdapter
from integrations.config_service import CredentialService


@pytest.fixture()
def github_credential(admin_ctx, workspace):
    CredentialService().upsert(
        admin_ctx,
        workspace_id=workspace.id,
        system="github",
        token="ghp_example",
        api_base_url="https://api.github.com",
        account_email="",
    )
    return workspace


def test_both_systems_have_an_adapter():
    assert set(ADAPTERS) == {"github", "jira"}


@pytest.mark.django_db
def test_github_adapter_posts_to_the_repo_issue_endpoint(github_credential):
    workspace = github_credential
    with patch("integrations.adapters.requests.post") as post:
        post.return_value.status_code = 201
        post.return_value.json.return_value = {
            "number": 512,
            "html_url": "https://github.com/acme/widgets/issues/512",
        }

        parsed = GitHubIssueAdapter().create_issue(
            workspace_id=workspace.id,
            tenant_id=workspace.tenant_id,
            repo="acme/widgets",
            title="Requirement REQ-1 approved",
            body="See ReqogniLoom",
        )

    url, kwargs = post.call_args[0][0], post.call_args[1]
    assert url == "https://api.github.com/repos/acme/widgets/issues"
    assert kwargs["headers"]["Authorization"] == "Bearer ghp_example"
    assert kwargs["json"] == {"title": "Requirement REQ-1 approved", "body": "See ReqogniLoom"}
    assert kwargs["timeout"] > 0
    assert parsed.external_id == "512"
    assert parsed.system == "github"
    assert parsed.kind == "issue"


@pytest.mark.django_db
def test_github_adapter_raises_without_a_credential(workspace):
    with pytest.raises(AdapterError):
        GitHubIssueAdapter().create_issue(
            workspace_id=workspace.id,
            tenant_id=workspace.tenant_id,
            repo="acme/widgets",
            title="t",
            body="b",
        )


@pytest.mark.django_db
def test_github_adapter_raises_on_a_non_2xx(github_credential):
    workspace = github_credential
    with patch("integrations.adapters.requests.post") as post:
        post.return_value.status_code = 403
        post.return_value.text = "ghp_example is not authorised"
        with pytest.raises(AdapterError) as excinfo:
            GitHubIssueAdapter().create_issue(
                workspace_id=workspace.id,
                tenant_id=workspace.tenant_id,
                repo="acme/widgets",
                title="t",
                body="b",
            )
    assert "ghp_example" not in str(excinfo.value), "the token must never reach an error message"


@pytest.mark.django_db
def test_jira_adapter_posts_to_the_issue_endpoint(admin_ctx, workspace):
    CredentialService().upsert(
        admin_ctx,
        workspace_id=workspace.id,
        system="jira",
        token="jira-token",
        api_base_url="https://acme.atlassian.net",
        account_email="bot@acme.example",
    )
    with patch("integrations.adapters.requests.post") as post:
        post.return_value.status_code = 201
        post.return_value.json.return_value = {"key": "PROJ-77"}

        parsed = JiraIssueAdapter().create_issue(
            workspace_id=workspace.id,
            tenant_id=workspace.tenant_id,
            repo="PROJ",
            title="Bug from failed test",
            body="details",
        )

    url, kwargs = post.call_args[0][0], post.call_args[1]
    assert url == "https://acme.atlassian.net/rest/api/3/issue"
    assert kwargs["auth"] == ("bot@acme.example", "jira-token")
    assert kwargs["json"]["fields"]["project"]["key"] == "PROJ"
    assert parsed.external_id == "PROJ-77"
    assert parsed.url == "https://acme.atlassian.net/browse/PROJ-77"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_adapters.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'integrations.adapters'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/integrations/adapters.py
"""Outbound adapters: one domain event -> one API call per target system.

Same shape as ``ARTIFACT_CREATION_ADAPTERS`` in the interview engine — the
caller looks the adapter up by key and never branches on the system itself.

``requests`` is used because it is already a pinned dependency; the timeout is
mandatory (a hung POST inside an event-bus subscriber blocks the outbox
poller, whose Celery hard limit is 180s).
"""
from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

import requests

from integrations.config_service import CredentialService
from integrations.constants import KIND_ISSUE, SYSTEM_GITHUB, SYSTEM_JIRA
from integrations.url_parser import ParsedExternalUrl

logger = logging.getLogger(__name__)

#: Well below the outbox poller's Celery hard limit (180s).
HTTP_TIMEOUT_SECONDS = 15


class AdapterError(RuntimeError):
    """An outbound call could not be made or was rejected.

    The message never contains the token: an adapter error is logged and
    audited, and a credential in a log line is a credential leak.
    """


class IssueAdapter(Protocol):
    """Create one issue in an external system and return its reference."""

    def create_issue(
        self,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        repo: str,
        title: str,
        body: str,
    ) -> ParsedExternalUrl: ...


def _credential(workspace_id: UUID, system: str):
    credential = CredentialService.get_for(workspace_id, system)
    if credential is None or not credential.token:
        raise AdapterError(f"No {system} credential configured for this workspace")
    return credential


class GitHubIssueAdapter:
    """Create a GitHub issue via the REST API."""

    def create_issue(
        self,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        repo: str,
        title: str,
        body: str,
    ) -> ParsedExternalUrl:
        """POST /repos/{repo}/issues and return the created reference."""
        credential = _credential(workspace_id, SYSTEM_GITHUB)
        base = (credential.api_base_url or "https://api.github.com").rstrip("/")

        response = requests.post(
            f"{base}/repos/{repo}/issues",
            headers={
                "Authorization": f"Bearer {credential.token}",
                "Accept": "application/vnd.github+json",
            },
            json={"title": title, "body": body},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if not 200 <= response.status_code < 300:
            raise AdapterError(
                f"GitHub rejected the issue creation with HTTP {response.status_code}"
            )

        payload = response.json()
        number = str(payload["number"])
        return ParsedExternalUrl(
            system=SYSTEM_GITHUB,
            repo=repo,
            external_id=number,
            kind=KIND_ISSUE,
            url=payload.get("html_url") or f"https://github.com/{repo}/issues/{number}",
        )


class JiraIssueAdapter:
    """Create a Jira issue via the Cloud REST API (v3)."""

    def create_issue(
        self,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        repo: str,
        title: str,
        body: str,
    ) -> ParsedExternalUrl:
        """POST /rest/api/3/issue and return the created reference."""
        credential = _credential(workspace_id, SYSTEM_JIRA)
        base = (credential.api_base_url or "").rstrip("/")
        if not base:
            raise AdapterError("No Jira base URL configured for this workspace")

        response = requests.post(
            f"{base}/rest/api/3/issue",
            auth=(credential.account_email, credential.token),
            json={
                "fields": {
                    "project": {"key": repo},
                    "summary": title,
                    "description": body,
                    "issuetype": {"name": "Task"},
                }
            },
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if not 200 <= response.status_code < 300:
            raise AdapterError(
                f"Jira rejected the issue creation with HTTP {response.status_code}"
            )

        key = str(response.json()["key"])
        return ParsedExternalUrl(
            system=SYSTEM_JIRA,
            repo=repo,
            external_id=key,
            kind=KIND_ISSUE,
            url=f"{base}/browse/{key}",
        )


ADAPTERS: dict[str, IssueAdapter] = {
    SYSTEM_GITHUB: GitHubIssueAdapter(),
    SYSTEM_JIRA: JiraIssueAdapter(),
}

__all__ = [
    "ADAPTERS",
    "AdapterError",
    "GitHubIssueAdapter",
    "HTTP_TIMEOUT_SECONDS",
    "IssueAdapter",
    "JiraIssueAdapter",
]
```

Note the Jira description field: API v3 expects Atlassian Document Format, not a plain string. Verify against a live instance during implementation; if plain text is rejected, wrap it as `{"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": body}]}]}` and update `test_jira_adapter_posts_to_the_issue_endpoint` to assert that shape.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_adapters.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations/adapters.py backend/integrations/tests/test_adapters.py
git commit -m "feat: add GitHub and Jira issue creation adapters"
```

---

### Task 26: Outbound event-bus subscriber

**Files:**
- Create: `backend/integrations/outbound.py`
- Modify: `backend/integrations/apps.py` (`ready()` registers the subscriber)
- Modify: `backend/audit/models.py` (`OP_INTEGRATION_CREATE_ISSUE`)
- Create: `backend/integrations/tests/test_outbound.py`

**Interfaces:**
- Consumes: `application.event_bus.get_event_bus().register_subscriber(event_type, callback)`, `DomainEvent`, `integrations.adapters.ADAPTERS`, `integrations.service.ExternalRefService`
- Produces: `OutboundIntegrationSubscriber.process_event(event)`, `.subscribe_to_events()`, `SUBSCRIBED_EVENT_TYPES`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_outbound.py
"""Rule-driven outbound issue creation off the existing outbox subscriber path."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from application.event_bus import DomainEvent
from integrations.models import ExternalRef, IntegrationConfig
from integrations.outbound import OutboundIntegrationSubscriber
from integrations.url_parser import ParsedExternalUrl


@pytest.fixture()
def configured(admin_ctx, workspace, requirement):
    from integrations.config_service import CredentialService

    CredentialService().upsert(
        admin_ctx,
        workspace_id=workspace.id,
        system="github",
        token="ghp_example",
        api_base_url="https://api.github.com",
        account_email="",
    )
    IntegrationConfig.objects.create(
        tenant=workspace.tenant,
        workspace=workspace,
        system="github",
        repos=["acme/widgets"],
        outbound_rules=[
            {
                "event_type": "WorkflowTransitioned",
                "item_type": "Requirement",
                "to_state": "approved",
                "action": "github.create_issue",
            }
        ],
    )
    return workspace, requirement


def _event(workspace, requirement, to_state="approved", item_type="Requirement"):
    return DomainEvent(
        event_type="WorkflowTransitioned",
        entity_id=requirement.id,
        workspace_id=workspace.id,
        payload={"item_type": item_type, "to_state": to_state},
    )


_CREATED = ParsedExternalUrl(
    system="github",
    repo="acme/widgets",
    external_id="512",
    kind="issue",
    url="https://github.com/acme/widgets/issues/512",
)


@pytest.mark.django_db
def test_a_matching_rule_creates_an_issue_and_links_it_back(configured):
    workspace, requirement = configured
    with patch("integrations.adapters.GitHubIssueAdapter.create_issue", return_value=_CREATED):
        OutboundIntegrationSubscriber().process_event(_event(workspace, requirement))

    ref = ExternalRef.objects.get(external_id="512")
    assert ref.artifact_id == requirement.artifact_id
    assert ref.repo == "acme/widgets"


@pytest.mark.django_db
def test_a_non_matching_state_creates_nothing(configured):
    workspace, requirement = configured
    with patch("integrations.adapters.GitHubIssueAdapter.create_issue") as create:
        OutboundIntegrationSubscriber().process_event(
            _event(workspace, requirement, to_state="draft")
        )
    create.assert_not_called()
    assert not ExternalRef.objects.exists()


@pytest.mark.django_db
def test_a_non_matching_item_type_creates_nothing(configured):
    workspace, requirement = configured
    with patch("integrations.adapters.GitHubIssueAdapter.create_issue") as create:
        OutboundIntegrationSubscriber().process_event(
            _event(workspace, requirement, item_type="Adr")
        )
    create.assert_not_called()


@pytest.mark.django_db
def test_an_event_for_an_unconfigured_workspace_is_ignored(requirement):
    event = DomainEvent(
        event_type="WorkflowTransitioned",
        entity_id=requirement.id,
        workspace_id=uuid.uuid4(),
        payload={"item_type": "Requirement", "to_state": "approved"},
    )
    with patch("integrations.adapters.GitHubIssueAdapter.create_issue") as create:
        OutboundIntegrationSubscriber().process_event(event)
    create.assert_not_called()


@pytest.mark.django_db
def test_an_adapter_failure_is_swallowed(configured):
    """Subscribers run unwrapped off the outbox — raising would fail the poll."""
    from integrations.adapters import AdapterError

    workspace, requirement = configured
    with patch(
        "integrations.adapters.GitHubIssueAdapter.create_issue",
        side_effect=AdapterError("boom"),
    ):
        OutboundIntegrationSubscriber().process_event(_event(workspace, requirement))
    assert not ExternalRef.objects.exists()


def test_the_subscriber_is_registered_at_startup():
    from application.event_bus import get_event_bus

    registry = get_event_bus().get_subscriber_registry()
    callbacks = registry.get("WorkflowTransitioned", [])
    assert any(
        getattr(cb, "__self__", None).__class__.__name__ == "OutboundIntegrationSubscriber"
        for cb in callbacks
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_outbound.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'integrations.outbound'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/integrations/outbound.py
"""Stage 3: create an external issue when a configured rule matches.

Runs as a DomainEventBus subscriber, the same seam WebhookDispatcher uses —
registered from ``IntegrationsConfig.ready()`` (the registration path that
SYSTEMAUDIT_2026-08-27 P0-3c already proved end to end for WebhookDispatcher).

Subscribers run *unwrapped* by ``dispatch_to_subscribers``: no transaction is
open around them and an exception would surface in the poller. This class
therefore owns its own error handling and never raises.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from application.event_bus import DomainEvent, get_event_bus
from audit.models import AuditEntry
from audit.services import log_write
from persistence.middleware import clear_request_tenant, set_request_tenant

logger = logging.getLogger(__name__)

#: The only event this subscriber reacts to today. Adding more means adding
#: them here AND to DomainEventOutbox.EventType (an undeclared string is
#: invisible to anything iterating EventType.choices).
SUBSCRIBED_EVENT_TYPES = ("WorkflowTransitioned",)

_CREATE_ISSUE_ACTIONS = {"github.create_issue": "github", "jira.create_issue": "jira"}


class OutboundIntegrationSubscriber:
    """Turn a matching domain event into an external issue plus an ExternalRef."""

    def subscribe_to_events(self) -> None:
        """Register on the application DomainEventBus. Idempotent."""
        bus = get_event_bus()
        for event_type in SUBSCRIBED_EVENT_TYPES:
            bus.register_subscriber(event_type, self.process_event)

    def process_event(self, event: DomainEvent) -> None:
        """Evaluate every configured rule for this event. Never raises."""
        try:
            self._process(event)
        except Exception:  # noqa: BLE001 -- see module docstring
            logger.exception(
                "OutboundIntegrationSubscriber failed for event %s/%s",
                event.event_type,
                event.entity_id,
            )

    def _process(self, event: DomainEvent) -> None:
        from integrations.models import IntegrationConfig

        tenant_id = self._resolve_tenant(event.workspace_id)
        if tenant_id is None:
            return

        set_request_tenant(tenant_id)
        try:
            configs = list(
                IntegrationConfig.objects.filter(
                    workspace_id=event.workspace_id, enabled=True
                )
            )
            for config in configs:
                for rule in config.outbound_rules or []:
                    if self._matches(rule, event):
                        self._execute(rule, event, config, tenant_id)
        finally:
            clear_request_tenant()

    @staticmethod
    def _resolve_tenant(workspace_id: UUID) -> Optional[UUID]:
        """Map a workspace to its tenant.

        The event bus carries no tenant, so this is the one lookup that must
        run before a context exists — hence ``unscoped``, and hence nothing
        else happens before ``set_request_tenant``.
        """
        from persistence.models import Workspace

        return (
            Workspace.unscoped.filter(id=workspace_id)
            .values_list("tenant_id", flat=True)
            .first()
        )

    @staticmethod
    def _matches(rule: dict[str, Any], event: DomainEvent) -> bool:
        """Return whether *rule* selects *event*.

        An absent key in the rule means "any value" — a rule that only names
        ``event_type`` and ``action`` fires for every transition of every type.
        """
        if not isinstance(rule, dict):
            return False
        if rule.get("action") not in _CREATE_ISSUE_ACTIONS:
            return False
        if rule.get("event_type") not in (None, event.event_type):
            return False
        payload = event.payload or {}
        if rule.get("item_type") not in (None, payload.get("item_type")):
            return False
        if rule.get("to_state") not in (None, payload.get("to_state")):
            return False
        return True

    def _execute(
        self,
        rule: dict[str, Any],
        event: DomainEvent,
        config: Any,
        tenant_id: UUID,
    ) -> None:
        """Create the external issue and link it back to the artifact."""
        from auth_tenancy.context import AuthContext
        from integrations.adapters import ADAPTERS, AdapterError
        from integrations.service import ExternalRefService

        system = _CREATE_ISSUE_ACTIONS[rule["action"]]
        if system != config.system or not config.repos:
            return
        repo = config.repos[0]

        payload = event.payload or {}
        title = payload.get("title") or (
            f"{payload.get('item_type', 'Artifact')} moved to "
            f"{payload.get('to_state', 'a new state')}"
        )
        body = payload.get("body") or (
            f"Created automatically by ReqogniLoom for "
            f"{payload.get('item_type', 'artifact')} {event.entity_id}."
        )

        try:
            created = ADAPTERS[system].create_issue(
                workspace_id=config.workspace_id,
                tenant_id=tenant_id,
                repo=repo,
                title=title,
                body=body,
            )
        except AdapterError as exc:
            logger.warning("Outbound %s issue creation failed: %s", system, exc)
            return

        ctx = AuthContext.system(tenant_id=tenant_id)
        ref = ExternalRefService().link_external_unchecked(
            ctx, artifact_id=event.entity_id, parsed=created
        )

        log_write(
            actor=f"{system}-outbound",
            actor_type=AuditEntry.ACTOR_TYPE_SYSTEM,
            operation=AuditEntry.OP_INTEGRATION_CREATE_ISSUE,
            entity_type="ExternalRef",
            entity_id=ref.id,
            details={"system": system, "repo": repo, "external_id": created.external_id},
        )


__all__ = ["OutboundIntegrationSubscriber", "SUBSCRIBED_EVENT_TYPES"]
```

Three supporting changes:

1. `ExternalRefService` gains `link_external_unchecked(ctx, *, artifact_id, parsed: ParsedExternalUrl) -> ExternalRefDTO` — the same body as `link_external` minus URL parsing and minus `_assert_write_permission` (the caller is `AuthContext.system`, which has no roles by construction). Refactor `link_external` to parse and then delegate, so there is one creation path, not two.
2. `backend/audit/models.py`: `OP_INTEGRATION_CREATE_ISSUE = "integration.create_issue"` plus its `OP_CHOICES` entry — no REST pendant exists, so it needs its own value, same reasoning as the `ai.*` and `events.replay` families.
3. `backend/integrations/apps.py::ready()`:

```python
    def ready(self) -> None:
        """Register the outbound subscriber on the application DomainEventBus."""
        from integrations.outbound import OutboundIntegrationSubscriber

        OutboundIntegrationSubscriber().subscribe_to_events()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_outbound.py audit/tests/test_op_vocabulary.py -q`
Expected: PASS (6 passed, op vocabulary guard green)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations backend/audit/models.py
git commit -m "feat: create external issues from workflow transitions"
```

---

### Task 27: `integration.*` MCP tools

**Files:**
- Modify: `backend/mcp_server/tools/integration.py` (two more tools)
- Modify: `backend/mcp_server/workspace_scope.py` (`_TOOL_TARGETS`)
- Create: `backend/integrations/tests/test_mcp_integration_tools.py`

**Interfaces:**
- Consumes: `integrations.adapters.ADAPTERS`, `integrations.config_service`, `integrations.service.ExternalRefService`
- Produces: `integration.github.create_issue(artifact_id, title?, body?)`, `integration.jira.sync(artifact_id)`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_mcp_integration_tools.py
"""Agent-facing outbound tools (spec §5.2)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from integrations.url_parser import ParsedExternalUrl
from mcp_server.tools.integration import IntegrationToolGroup
from mcp_server.workspace_scope import _TOOL_TARGETS

_CREATED = ParsedExternalUrl(
    system="github",
    repo="acme/widgets",
    external_id="900",
    kind="issue",
    url="https://github.com/acme/widgets/issues/900",
)


def test_both_tools_are_workspace_scoped():
    assert "integration.github.create_issue" in _TOOL_TARGETS
    assert "integration.jira.sync" in _TOOL_TARGETS


def test_neither_tool_is_read_only():
    from mcp_server.tool_registry import _READ_ONLY_TOOL_NAMES

    assert "integration.github.create_issue" not in _READ_ONLY_TOOL_NAMES
    assert "integration.jira.sync" not in _READ_ONLY_TOOL_NAMES


@pytest.mark.django_db
def test_create_issue_links_the_result_back(configured_github, requirement, editor_ctx):
    with patch(
        "integrations.adapters.GitHubIssueAdapter.create_issue", return_value=_CREATED
    ):
        result = IntegrationToolGroup().execute_tool(
            "integration.github.create_issue",
            {"artifact_id": str(requirement.id), "title": "From an agent"},
            editor_ctx,
        )

    assert result.is_error is False
    assert result.data["external_ref"]["external_id"] == "900"

    from integrations.models import ExternalRef

    assert ExternalRef.objects.filter(external_id="900").exists()


@pytest.mark.django_db
def test_a_read_scoped_agent_key_is_denied(configured_github, requirement, agent_read_ctx):
    """Spec §5.2: an agent needs scope='write' for this, like any other write."""
    from application.base import PermissionDeniedError

    with pytest.raises(PermissionDeniedError):
        IntegrationToolGroup().execute_tool(
            "integration.github.create_issue",
            {"artifact_id": str(requirement.id)},
            agent_read_ctx,
        )


@pytest.mark.django_db
def test_jira_sync_refreshes_last_seen_status(
    configured_jira, requirement, editor_ctx
):
    from integrations.models import ExternalRef
    from integrations.service import ExternalRefService

    ExternalRefService().link_external(
        editor_ctx,
        artifact_id=requirement.id,
        url="https://acme.atlassian.net/browse/PROJ-42",
    )
    with patch("integrations.adapters.requests.get") as get:
        get.return_value.status_code = 200
        get.return_value.json.return_value = {"fields": {"status": {"name": "Done"}}}

        result = IntegrationToolGroup().execute_tool(
            "integration.jira.sync", {"artifact_id": str(requirement.id)}, editor_ctx
        )

    assert result.data["synced"] == 1
    assert ExternalRef.objects.get(external_id="PROJ-42").last_seen_status == "Done"


@pytest.mark.django_db
def test_jira_sync_on_an_artifact_without_refs_reports_zero(
    configured_jira, requirement, editor_ctx
):
    result = IntegrationToolGroup().execute_tool(
        "integration.jira.sync", {"artifact_id": str(requirement.id)}, editor_ctx
    )
    assert result.data["synced"] == 0
```

Add `configured_github` / `configured_jira` fixtures (credential + `IntegrationConfig` for the workspace, mirroring the Task 26 fixture) and `agent_read_ctx` (an `AuthContext` with `actor_type="agent"` and the API key's `scope="read"`) to `backend/integrations/tests/conftest.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_mcp_integration_tools.py -q`
Expected: FAIL with `assert 'integration.github.create_issue' in {...}`

- [ ] **Step 3: Write minimal implementation**

Extend `IntegrationToolGroup._TOOL_MAP` and `_TOOL_SCHEMAS`:

```python
        "integration.github.create_issue": "_handle_create_github_issue",
        "integration.jira.sync": "_handle_jira_sync",
```

```python
        {
            "name": "integration.github.create_issue",
            "description": (
                "Create a GitHub issue for an artifact using the workspace's "
                "configured repository and credential, and link it back."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "artifact_id": {"type": "string", "format": "uuid"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["artifact_id"],
            },
        },
        {
            "name": "integration.jira.sync",
            "description": (
                "Refresh last_seen_status for every Jira reference of an "
                "artifact by reading the current status from Jira."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"artifact_id": {"type": "string", "format": "uuid"}},
                "required": ["artifact_id"],
            },
        },
```

```python
    def _handle_create_github_issue(
        self, params: Dict[str, Any], auth_context: AuthContext
    ) -> ToolResult:
        """Create a GitHub issue and link it to the artifact.

        The created ticket itself does NOT enter the ``proposed`` workflow
        state — it is an external side effect, not an internal artifact
        (spec §5.2). The resulting ExternalRef *link* does, via
        ``TraceLinkService``'s own agent handling.
        """
        from integrations.outbound_tools import create_issue_for_artifact

        artifact_id = require_uuid(params, "artifact_id")
        dto = create_issue_for_artifact(
            auth_context,
            artifact_id=artifact_id,
            system="github",
            title=params.get("title"),
            body=params.get("body"),
        )
        return ToolResult(data={"external_ref": dto.to_dict()})

    def _handle_jira_sync(
        self, params: Dict[str, Any], auth_context: AuthContext
    ) -> ToolResult:
        """Pull the current Jira status for every Jira reference of an artifact."""
        from integrations.outbound_tools import sync_jira_refs

        artifact_id = require_uuid(params, "artifact_id")
        synced = sync_jira_refs(auth_context, artifact_id=artifact_id)
        return ToolResult(data={"synced": synced})
```

Create `backend/integrations/outbound_tools.py` holding the two service functions (`create_issue_for_artifact`, `sync_jira_refs`), so the tool module keeps zero ORM lines. `create_issue_for_artifact` asserts write permission, reads the workspace's `IntegrationConfig` for the repo, calls `ADAPTERS[system].create_issue`, then `ExternalRefService.link_external_unchecked`. `sync_jira_refs` asserts write permission, lists the artifact's Jira refs, GETs `{base}/rest/api/3/issue/{key}?fields=status` per ref with the stored credential, writes `last_seen_status`/`synced_at`, and returns the count.

Add both tools to `_TOOL_TARGETS`:

```python
    "integration.github.create_issue": _artifact_or_domain("artifact_id"),
    "integration.jira.sync": _artifact_or_domain("artifact_id"),
```

Both are absent from `_READ_ONLY_TOOL_NAMES`, so the fail-closed default already write-gates them; `ApiKey.scope="read"` denial comes from spec 4's scope check in the dispatcher, which the `agent_read_ctx` test pins.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_mcp_integration_tools.py mcp_server/tests/test_mcp_workspace_scope.py -q`
Expected: PASS (6 passed, workspace-scope ratchet green)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations backend/mcp_server
git commit -m "feat: add integration MCP tools for issue creation and sync"
```

---

### Task 28: External references in interview grounding

**Files:**
- Modify: `backend/memory/context_builder.py:45-82` (optional `artifact_id`)
- Modify: `backend/application/interview_service.py:1193` (pass `session.artifact_id`)
- Create: `backend/integrations/tests/test_grounding.py`

**Interfaces:**
- Consumes: `integrations.service.ExternalRefService`
- Produces: `build_memory_context(tenant_id, workspace_id, user_id, query_text, *, artifact_id: UUID | None = None) -> str`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_grounding.py
"""Spec §5.3: an artifact's external refs join the interview grounding block."""
from __future__ import annotations

import pytest

from integrations.service import ExternalRefService
from memory.context_builder import build_memory_context


@pytest.mark.django_db
def test_external_refs_appear_in_the_context(editor_ctx, requirement, workspace):
    ExternalRefService().link_external(
        editor_ctx,
        artifact_id=requirement.id,
        url="https://github.com/acme/widgets/pull/142",
    )
    context = build_memory_context(
        workspace.tenant_id,
        workspace.id,
        editor_ctx.user_id,
        "anything",
        artifact_id=requirement.artifact_id,
    )
    assert "acme/widgets" in context
    assert "142" in context


@pytest.mark.django_db
def test_no_artifact_id_keeps_the_old_behaviour(editor_ctx, requirement, workspace):
    ExternalRefService().link_external(
        editor_ctx,
        artifact_id=requirement.id,
        url="https://github.com/acme/widgets/pull/143",
    )
    context = build_memory_context(
        workspace.tenant_id, workspace.id, editor_ctx.user_id, "anything"
    )
    assert "acme/widgets" not in context


@pytest.mark.django_db
def test_an_artifact_without_refs_adds_nothing(editor_ctx, requirement, workspace):
    context = build_memory_context(
        workspace.tenant_id,
        workspace.id,
        editor_ctx.user_id,
        "anything",
        artifact_id=requirement.artifact_id,
    )
    assert "External references" not in context


@pytest.mark.django_db
def test_a_failing_lookup_degrades_to_the_rest_of_the_context(
    editor_ctx, requirement, workspace, monkeypatch
):
    """Grounding is best-effort — a broken lookup must not break the chat turn."""
    import memory.context_builder as module

    monkeypatch.setattr(
        module, "_external_refs_block", lambda *a, **k: (_ for _ in ()).throw(RuntimeError())
    )
    context = build_memory_context(
        workspace.tenant_id,
        workspace.id,
        editor_ctx.user_id,
        "anything",
        artifact_id=requirement.artifact_id,
    )
    assert isinstance(context, str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_grounding.py -q`
Expected: FAIL with `TypeError: build_memory_context() got an unexpected keyword argument 'artifact_id'`

- [ ] **Step 3: Write minimal implementation**

In `backend/memory/context_builder.py`:

```python
def _external_refs_block(artifact_id: UUID) -> list[str]:
    """Return one line per external reference of *artifact_id*.

    Read-only use of stage-1/2 data (GitHub/Jira spec §5.3) — no new
    mechanism, and no tenant context of its own: the caller
    (``InterviewService.generate_chat_turn``) already has one armed.
    """
    from integrations.models import ExternalRef

    rows = ExternalRef.objects.filter(artifact_id=artifact_id).order_by(
        "system", "external_id"
    )
    lines = []
    for row in rows:
        status = f", status {row.last_seen_status}" if row.last_seen_status else ""
        lines.append(f"- {row.system} {row.repo} {row.kind} {row.external_id}{status}")
    return lines
```

and, at the end of `build_memory_context`, before the return, with `artifact_id: UUID | None = None` added as a keyword-only parameter:

```python
    if artifact_id is not None:
        try:
            external = _external_refs_block(artifact_id)
        except Exception as exc:  # noqa: BLE001 -- best-effort, see docstring
            logger.warning("external ref grounding failed: %s", exc)
            external = []
        if external:
            lines.append("External references:")
            lines.extend(external)
```

Move the early `if not workspace_hits and not user_hits: return ""` guard *after* the external block is built, otherwise an artifact with references but no memory hits still returns `""`.

In `backend/application/interview_service.py:1193`:

```python
        memory_context = build_memory_context(
            ctx.tenant_id,
            session.workspace_id,
            ctx.user_id,
            user_message,
            artifact_id=session.artifact_id,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_grounding.py memory/tests -q`
Expected: PASS (4 passed, memory suite unchanged)

- [ ] **Step 5: Commit**

```bash
git add backend/memory/context_builder.py backend/application/interview_service.py backend/integrations/tests/test_grounding.py
git commit -m "feat: ground interviews with an artifact's external references"
```

---

### Task 29: Dashboard mismatch card

**Files:**
- Modify: `backend/integrations/service.py` (add `list_status_mismatches`)
- Modify: `backend/integrations/rest.py`, `urls.py`, `serializers.py`
- Modify: `frontend/src/api/integrations.ts` (`listMismatches`)
- Create: `frontend/src/components/DashboardViews/ExternalMismatchCard.tsx`
- Create: `frontend/src/components/DashboardViews/ExternalMismatchCard.test.tsx`
- Create: `backend/integrations/tests/test_mismatches.py`

**Interfaces:**
- Consumes: `workflow.services.list_item_states`, `traceability.service.resolve_artifacts`
- Produces: `ExternalRefService.list_status_mismatches(ctx, *, workspace_id) -> list[dict]`; `GET /api/v1/workspaces/<uuid:workspace_id>/external-mismatches/`; `ExternalMismatchCard({ workspaceId })`

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_mismatches.py
"""Spec §6: "3 requirements have merged PRs but are still in draft"."""
from __future__ import annotations

import pytest

from integrations.models import ExternalRef
from integrations.service import ExternalRefService


@pytest.fixture()
def merged_but_draft(editor_ctx, requirement, workspace, requirement_in_draft):
    dto = ExternalRefService().link_external(
        editor_ctx,
        artifact_id=requirement.id,
        url="https://github.com/acme/widgets/pull/7",
    )
    ExternalRef.objects.filter(id=dto.id).update(last_seen_status="merged")
    return requirement


@pytest.mark.django_db
def test_a_merged_pr_on_a_draft_artifact_is_reported(
    editor_ctx, workspace, merged_but_draft
):
    rows = ExternalRefService().list_status_mismatches(
        editor_ctx, workspace_id=workspace.id
    )
    assert len(rows) == 1
    assert rows[0]["entity_type"] == "Requirement"
    assert rows[0]["current_state"] == "draft"
    assert rows[0]["last_seen_status"] == "merged"
    assert rows[0]["external_id"] == "7"


@pytest.mark.django_db
def test_a_ref_without_a_seen_status_is_not_a_mismatch(
    editor_ctx, requirement, workspace, requirement_in_draft
):
    ExternalRefService().link_external(
        editor_ctx,
        artifact_id=requirement.id,
        url="https://github.com/acme/widgets/pull/8",
    )
    assert (
        ExternalRefService().list_status_mismatches(editor_ctx, workspace_id=workspace.id)
        == []
    )


@pytest.mark.django_db
def test_an_open_pr_on_a_draft_artifact_is_not_a_mismatch(
    editor_ctx, requirement, workspace, requirement_in_draft
):
    dto = ExternalRefService().link_external(
        editor_ctx,
        artifact_id=requirement.id,
        url="https://github.com/acme/widgets/pull/9",
    )
    ExternalRef.objects.filter(id=dto.id).update(last_seen_status="open")
    assert (
        ExternalRefService().list_status_mismatches(editor_ctx, workspace_id=workspace.id)
        == []
    )


@pytest.mark.django_db
def test_rest_exposes_the_same_rows(api_client_editor, workspace, merged_but_draft):
    response = api_client_editor.get(
        f"/api/v1/workspaces/{workspace.id}/external-mismatches/"
    )
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["last_seen_status"] == "merged"
```

```tsx
// frontend/src/components/DashboardViews/ExternalMismatchCard.test.tsx
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ExternalMismatchCard } from "./ExternalMismatchCard";
import { integrationsApi } from "../../api/integrations";

describe("ExternalMismatchCard", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("summarises the mismatch count", async () => {
    vi.spyOn(integrationsApi, "listMismatches").mockResolvedValue([
      {
        artifactId: "a1",
        entityType: "Requirement",
        entityId: "r1",
        title: "Login",
        currentState: "draft",
        system: "github",
        externalId: "7",
        lastSeenStatus: "merged",
        url: "https://github.com/acme/widgets/pull/7",
      },
    ]);
    render(<ExternalMismatchCard workspaceId="ws" />);
    expect(await screen.findByTestId("external-mismatch-count")).toHaveTextContent("1");
  });

  it("renders nothing when there is no mismatch", async () => {
    vi.spyOn(integrationsApi, "listMismatches").mockResolvedValue([]);
    const { container } = render(<ExternalMismatchCard workspaceId="ws" />);
    await Promise.resolve();
    expect(container.querySelector("[data-testid='external-mismatch-card']")).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_mismatches.py -q`
Expected: FAIL with `AttributeError: 'ExternalRefService' object has no attribute 'list_status_mismatches'`

- [ ] **Step 3: Write minimal implementation**

```python
# appended to the ExternalRefService class in backend/integrations/service.py
#: External statuses that mean "the work is done over there".
TERMINAL_EXTERNAL_STATUSES = frozenset({"merged", "closed", "done", "resolved"})

#: Local states that mean "we have not acted on it yet".
OPEN_LOCAL_STATES = frozenset({"proposed", "draft", "in_review"})
```

```python
    def list_status_mismatches(self, ctx, *, workspace_id: UUID) -> list[dict]:
        """Return artifacts whose external object is done but whose state is not.

        Spec §6's dashboard line ("3 requirements have merged PRs but are
        still in draft"). Deliberately a comparison of two flat sets rather
        than a per-workspace mapping table: the sets are small, and a
        configurable mapping is a second state machine nobody asked for yet.
        """
        from workflow.services import list_item_states
        from traceability.service import resolve_artifacts

        self._set_tenant_context(ctx)

        refs = list(
            ExternalRef.objects.filter(
                artifact__workspace_id=workspace_id,
                last_seen_status__in=TERMINAL_EXTERNAL_STATUSES,
            )
        )
        if not refs:
            return []

        resolved = {
            item.artifact_id: item
            for item in resolve_artifacts([r.artifact_id for r in refs], ctx.tenant_id)
            if item.resolved
        }
        states = {
            (state.item_type, str(state.item_id)): state.current_state
            for state in list_item_states(workspace_id, tenant_id=ctx.tenant_id)
        }

        rows = []
        for ref in refs:
            item = resolved.get(str(ref.artifact_id))
            if item is None:
                continue
            current = states.get((item.entity_type, item.entity_id))
            if current is None or current not in OPEN_LOCAL_STATES:
                continue
            rows.append(
                {
                    "artifact_id": str(ref.artifact_id),
                    "entity_type": item.entity_type,
                    "entity_id": item.entity_id,
                    "current_state": current,
                    "system": ref.system,
                    "external_id": ref.external_id,
                    "last_seen_status": ref.last_seen_status,
                    "url": ref.url,
                }
            )
        return rows
```

`resolve_artifacts` keys its results by the string form of the artifact id — check whether `ResolvedArtifact.artifact_id` is `str` (it is) and key the dict consistently; the snippet above already uses `str(...)` on both sides.

Add `MismatchSerializer` (all eight fields read-only), a `WorkspaceExternalMismatchView` in `rest.py` calling the service, the route `workspaces/<uuid:workspace_id>/external-mismatches/`, and `integrationsApi.listMismatches(workspaceId)` in `frontend/src/api/integrations.ts` mapping snake_case to camelCase like the other wrappers.

```tsx
// frontend/src/components/DashboardViews/ExternalMismatchCard.tsx
/**
 * Dashboard card: artifacts whose linked GitHub/Jira object is already done
 * while the artifact itself is still open (spec §6). Renders nothing when
 * there is no mismatch — an always-visible empty card is noise.
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { integrationsApi } from "../../api/integrations";
import type { ExternalMismatch } from "../../api/integrations";
import type { UUID } from "../../types";

export interface ExternalMismatchCardProps {
  workspaceId: UUID;
}

export function ExternalMismatchCard({
  workspaceId,
}: ExternalMismatchCardProps): JSX.Element | null {
  const { t } = useTranslation();
  const [rows, setRows] = useState<ExternalMismatch[]>([]);

  useEffect(() => {
    let cancelled = false;
    void integrationsApi
      .listMismatches(workspaceId)
      .then((result) => {
        if (!cancelled) setRows(result);
      })
      .catch(() => {
        if (!cancelled) setRows([]);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  if (rows.length === 0) return null;

  return (
    <section data-testid="external-mismatch-card">
      <h3>
        <span data-testid="external-mismatch-count">{rows.length}</span>{" "}
        {t("integrations.mismatchTitle")}
      </h3>
      <ul>
        {rows.map((row) => (
          <li key={`${row.artifactId}-${row.externalId}`}>
            <a href={row.url} target="_blank" rel="noopener noreferrer">
              {row.system} {row.externalId} · {row.lastSeenStatus}
            </a>{" "}
            — {row.title || row.entityType} ({row.currentState})
          </li>
        ))}
      </ul>
    </section>
  );
}
```

New locale keys under `integrations`: `mismatchTitle` (EN "artifacts are done externally but still open here", DE "Artefakte sind extern erledigt, hier aber noch offen").

Mount the card in the dashboard alongside the existing cards in `frontend/src/components/DashboardViews/`; find the container component that renders the other summary cards and add it there.

Add `requirement_in_draft` to `backend/integrations/tests/conftest.py`: initialises the requirement's `WorkflowItemState` to `draft` via `workflow.services.initialize_workflow_states`.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/tests/test_mismatches.py -q` then `$VITEST "npx vitest run src/components/DashboardViews/ExternalMismatchCard.test.tsx --testTimeout=30000"`
Expected: PASS (4 backend, 2 frontend)

- [ ] **Step 5: Commit**

```bash
git add backend/integrations frontend/src/api/integrations.ts frontend/src/components/DashboardViews frontend/src/i18n/locales
git commit -m "feat: surface external status mismatches on the dashboard"
```

---

### Task 30: Full-surface verification

**Files:**
- Modify: `docs/superpowers/specs/2026-09-03-traceability-semantik-design.md` (mark the `references`/`ExternalRef` amendment as implemented)
- Create: `backend/integrations/tests/test_smoke_stage_coverage.py`

**Interfaces:**
- Consumes: everything above
- Produces: nothing new — this task only proves the surface is wired

- [ ] **Step 1: Write the failing test**

```python
# backend/integrations/tests/test_smoke_stage_coverage.py
"""One assertion per externally visible promise of the spec."""
from __future__ import annotations

import pytest
from django.urls import reverse


@pytest.mark.parametrize(
    "name",
    [
        "api-v1-artifact-external-refs",
        "api-v1-external-ref-detail",
        "api-v1-github-webhook",
        "api-v1-jira-webhook",
        "api-v1-workspace-integrations",
        "api-v1-workspace-integration-credentials",
        "api-v1-workspace-external-mismatches",
    ],
)
def test_every_route_is_registered(name):
    assert reverse(name, args=["00000000-0000-0000-0000-000000000000"])


def test_every_promised_mcp_tool_exists():
    from mcp_server.tool_registry import TenantToolRegistry

    names = {schema["name"] for schema in TenantToolRegistry().all_tool_schemas()}
    assert {
        "artifact.link_external",
        "artifact.list_external",
        "integration.github.create_issue",
        "integration.jira.sync",
    } <= names


def test_the_openapi_schema_generates_without_errors():
    from drf_spectacular.generators import SchemaGenerator

    schema = SchemaGenerator().get_schema(request=None, public=True)
    paths = schema["paths"]
    assert any("external-refs" in path for path in paths)
    assert any("integrations/github/webhook" in path for path in paths)
```

`reverse` needs the right argument count per route — split the parametrisation into two lists (single-arg and no-arg routes) if a route's signature differs, rather than forcing one shape.

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST integrations/tests/test_smoke_stage_coverage.py -q`
Expected: FAIL on the first route whose `name=` differs from the plan (fix the URLconf name, not the test)

- [ ] **Step 3: Write minimal implementation**

Reconcile the route names in `backend/integrations/urls.py` with the test, and append to §3.2 of `docs/superpowers/specs/2026-09-03-traceability-semantik-design.md`, right under the existing amendment paragraph:

```markdown
**Implementiert:** die `references`-Zielliste enthält `ExternalRef` seit
`link_types/seed_data.py` + `integrations/migrations/0003_references_external_ref_pair.py`
(Plan `docs/superpowers/plans/2026-09-03-github-jira-integration.md`, Task 4).
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST integrations/ workflow/tests mcp_server/tests/test_mcp_workspace_scope.py rest_api/tests/test_architecture.py audit/tests/test_op_vocabulary.py -q`
Expected: PASS — the full integration suite plus every ratchet this plan touches

- [ ] **Step 5: Commit**

```bash
git add backend/integrations docs/superpowers/specs/2026-09-03-traceability-semantik-design.md
git commit -m "test: pin the integration route and tool surface"
```

---

## Self-Review

**1. Spec coverage**

| Spec section | Tasks |
|---|---|
| §3.1 `ExternalRef` as Artifact-backed entity | 1, 2, 5 |
| §3.1 `references` amendment (consumed from the traceability spec) | 4, 30 |
| §3.2 REST `artifacts/<id>/external-refs/`, `external-refs/<id>/` | 8 |
| §3.2 MCP `artifact.link_external` / `artifact.list_external` | 9 |
| §3.2 UI chip, "Extern verknüpfen" dialog, open externally | 10, 11, 12, 13 |
| §4.1 GitHub webhook receiver, HMAC `X-Hub-Signature-256` | 15, 21 |
| §4.1 Jira webhook receiver, `?token=` shared secret | 15, 21 |
| §4.2 events `issue.opened/closed/labeled`, `pull_request.merged`, `jira:issue_updated` | 16 |
| §4.2 `last_seen_status` / `synced_at` mirror | 20 |
| §4.2 `external_trigger` on a transition, no `allowed_roles` check | 18, 19, 20 |
| §4.2 `actor_type="system"` + `client_name` | 17, 18, 20 |
| §4.2 System-settings tab "Integrationen" (repos, secret, rule table) | 22, 23 |
| §5.1 `ExternalSystemCredential`, encrypted like `honcho_api_key` | 24 |
| §5.2 `GitHubIssueAdapter` / `JiraIssueAdapter` on the outbox mechanism | 25, 26 |
| §5.2 MCP `integration.github.create_issue`, `integration.jira.sync`, agent `scope="write"` | 27 |
| §5.2 external ticket bypasses `proposed`; the ExternalRef link does not | 5 (test), 27 (docstring) |
| §5.3 interview grounding with `ExternalRef`s | 28 |
| §6 UI: artifact section, links group, dashboard mismatch | 13, 29 |
| §6 list column "Extern" | **not covered — see below** |
| §7 migrations 1–4 | 1, 2, 4, 14, 17, 24 |
| §8 risks: Jira query secret, PAT breadth, unguarded trigger path | 15, 21, 24, 18 (signature-gate refusal) |

Two deliberate gaps, both named rather than silently dropped:

- **§6 "In der Liste: Spalte 'Extern' mit System-Icon"** is not a task. It lands in the table view that spec 9 (Tabellenansicht, next in the implementation order) rebuilds column by column; adding a column to the current list and then again to its replacement is work done twice. The data it needs (`integrationsApi.listExternalRefs`) ships in Task 10. Add it as one column definition in that plan.
- **§4.2's rule table as an editor UI** is served in Task 23 by the repos/secret form plus the existing workflow editor, where `external_trigger` lives. A dedicated rule-table widget over `workflow_json.transitions[].external_trigger` is an editor for a field that already has one; if the workflow editor turns out not to surface unknown transition keys, add a single task there rather than a second editing surface here.

**2. Placeholder scan**

No "TBD"/"TODO"/"Similar to Task N" remains. Every step names a file, a command and either literal code or a specific, named reconciliation ("align `ConfirmDialog` prop names with `frontend/src/components/shared/ConfirmDialog.tsx`"). The reconciliation notes are deliberate: they point at a file that exists today and state what to check, rather than inventing a signature this plan cannot verify.

**3. Type consistency**

Checked and fixed inline while writing:

- `ExternalRefDTO.to_dict()` stringifies UUIDs and datetimes — MCP's transport uses stdlib `json.dumps`, which raises on both.
- `system_transition` takes the **domain-entity** id, not the Artifact id; `WorkflowItemState.item_id` is written from `requirement.id` / `adr.id` by every `create_X` service. Task 20 goes `ExternalRef.artifact_id -> resolve_artifacts -> (entity_type, entity_id)` before calling it.
- `_audit(..., details=...)` takes a dict, not a string — corrected in Task 5.
- `ServiceBase._audit` hardcodes `actor_type="user"`, so every system-actor entry calls `audit.services.log_write` directly (Tasks 20, 26).
- `resolve_artifacts` returns `entity_type` labels that match workflow `item_type` strings exactly ("Requirement", "Adr", ...), which is what makes Task 20's handoff work without a mapping table.
- `parse_external_url` returns `ParsedExternalUrl`, which is also the adapters' return type (Task 25) — one shape flows into `link_external_unchecked` from both the paste path and the outbound path.
- `ExternalRef.artifact` uses `related_name="external_refs"` (the spec sketch says `"+"`, which would make `subject.external_refs` impossible).

**4. Verification notes on the spec's own claims**

- `DomainEventOutbox` is at `backend/application/models.py:27` and `WebhookSubscription` at `:147` — both exactly as the spec states. `EventType` has 33 values, also as stated.
- `WebhookDispatcher.subscribe_to_events()` **is** wired from `ApplicationConfig.ready()` (added for SYSTEMAUDIT_2026-08-27 P0-3c). The subscriber path is proven, so Task 26 is not the first consumer.
- `/api/v1/integrations/...` routes cleanly under the existing `path("api/v1/", include("rest_api.urls"))`; the `re_path(r"^api/v1/", api_not_found)` catch-all stays last and is unaffected. The one ordering constraint is that `integrations.urls` must be included **before** `router.urls`, or `ArtifactViewSet`'s detail route swallows `artifacts/<id>/external-refs/`.
- DRF `APIView.as_view()` is `csrf_exempt`, so the receivers need no extra decorator; with `authentication_classes = []` they cannot be reached by an ambient cookie, which is what Task 21's SA-36-shaped test pins.
