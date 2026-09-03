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

1. **`WorkflowHistoryEntry` has no actor columns.** `backend/workflow/models.py:237` declares only `transitioned_by: CharField`. Spec 8 §4.2 requires `actor_type="system"` + `client_name` there, and spec 4 (KI-Vorschlag) §4.2 assumes the same two columns exist — but spec 4's own migration list (§7) never adds them. Ownership is therefore undefined across the two specs. **Default taken here (non-blocking):** Task 16 of this plan adds `actor_type` + `client_name` to `WorkflowHistoryEntry`. If spec 4's implementation already added them, Task 16 collapses to only the `AuditEntry.ACTOR_TYPE_SYSTEM` half — verify with `grep -n "actor_type" backend/workflow/models.py` before starting the task.

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
  adapters.py                  # GitHubIssueAdapter, JiraIssueAdapter
  outbound.py                  # OutboundIntegrationSubscriber
  serializers.py               # DRF serializers for the three models
  rest.py                      # authenticated REST views
  webhook_views.py             # the two public receivers
  throttling.py                # WebhookInRateThrottle
  urls.py                      # url patterns, included from rest_api/urls.py
  migrations/0001_initial.py
  migrations/0002_rls_policies.py
  migrations/0003_references_external_ref_pair.py
  tests/__init__.py
  tests/test_url_parser.py
  tests/test_external_ref_service.py
  tests/test_rest_external_refs.py
  tests/test_signatures.py
  tests/test_events.py
  tests/test_triggers.py
  tests/test_inbound.py
  tests/test_webhook_views.py
  tests/test_config_rest.py
  tests/test_adapters.py
  tests/test_outbound.py
  tests/test_rls_policies.py

frontend/src/api/integrations.ts
frontend/src/components/shared/ArtifactInspector/ExternalPanel.tsx
frontend/src/components/shared/ArtifactInspector/ExternalPanel.module.css
frontend/src/components/shared/LinkExternalDialog.tsx
frontend/src/components/shared/ExternalRefChip.tsx
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
