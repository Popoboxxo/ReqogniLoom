"""CR-17 exit evidence — RLS on plain (non-``TenantScopedModel``) child tables.

``test_rls_coverage.py`` closes the gap for every ``TenantScopedModel``: it
diffs ``db_table`` against the ``CREATE POLICY`` statements in the migration
graph. A plain ``models.Model`` with no ``tenant_id`` column is invisible to
that check by construction, which is the class of table this module covers:

* ``bl_delta_index_entry`` — ``baseline.models.BaselineDeltaIndexEntry``,
  tenant identity inherited through the ``baseline_id`` FK
  (``baseline/migrations/0006_baseline_snapshot_rls.py`` documented the
  deferral; ``0010_baseline_delta_index_entry_rls.py`` closes it).
* ``as_domain_event_outbox``, ``as_domain_event_dlq``,
  ``as_webhook_subscription``, ``as_webhook_delivery_log`` —
  ``application/models.py``, keyed by a bare ``workspace_id`` UUID field.

OPEN RESIDUAL RISK (audit track CR-17, system-audit-2026-09) — the four
worker-owned tables in the second group are NOT closed. Each of them is
confirmed readable across tenants by the least-privilege application role with
``app.current_tenant`` unset, and each is *declared* in
``RLS_EXEMPT_TABLES`` in ``test_rls_coverage.py`` as the reviewed exemption for
exactly that fact. A GUC-keyed policy is not merely unimplemented on them, it
is inexpressible: they carry no ``tenant_id`` column, so there is nothing to
compare. Turning RLS on requires stamping ``tenant_id`` onto the outbox payload
at emission time — the fix shape already used for ``memory.projector`` — which
is an architecture change, not a test change. Until that lands, what the
database guarantees on those four tables is *nothing*; the compensating controls
asserted here are service-layer and code-path arguments, and the tests that
assert them say so explicitly.

The admin is part of that exposure, and the exemption justifications now say so
per table rather than in general terms (see :data:`CR17_JUSTIFICATION_CLAIMS`):
``/admin/`` is mounted at ``reqogniloom/urls.py:33`` and every one of the four
tables is registered in ``application/admin.py``, so a staff superuser reaches
their rows outside any tenant-scoped code path — on ``as_webhook_subscription``
down to the plaintext HMAC ``secret`` and an admin-writable foreign
``workspace_id``, and on the outbox/DLQ down to the rendered event ``payload``.
That is a human-reachable path, not a database-enforced one, and no test here
can close it.

Every assertion runs against the least-privilege, NOSUPERUSER application role
(``persistence.db_roles.APP_DB_ROLE``, REQ-L2-PL-010) with
``app.current_tenant`` deliberately UNSET, via raw ``cursor.execute`` — the
default test connection is a superuser and bypasses RLS unconditionally, even
with FORCE ROW LEVEL SECURITY. Setup rows are written on that owner
connection; the role is switched only for the read under test.
"""
from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest
from django.db import connection

from persistence.db_roles import APP_DB_ROLE
from persistence.tests.test_rls_coverage import (
    RLS_EXEMPT_PLAIN_TABLES,
    RLS_EXEMPT_TABLES,
)

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")

#: Every plain child table CR-17 names, with the model that owns it.
PLAIN_CHILD_TABLES = {
    "bl_delta_index_entry": "baseline.models.BaselineDeltaIndexEntry",
    "as_domain_event_outbox": "application.models.DomainEventOutbox",
    "as_domain_event_dlq": "application.models.DomainEventDLQ",
    "as_webhook_subscription": "application.models.WebhookSubscription",
    "as_webhook_delivery_log": "application.models.WebhookDeliveryLog",
}

#: Tables whose *primary* production access path is the Celery outbox poller,
#: which by design runs with no tenant context armed
#: (``application.event_bus`` ``poll_and_dispatch`` never calls
#: ``set_request_tenant``). A GUC-keyed RLS policy is inexpressible on them — no
#: ``tenant_id`` column — and a policy on the workspace id would make the worker
#: blind and blind the poller to writes. They are declared in
#: ``RLS_EXEMPT_TABLES`` and covered below by the declaration, the no-tenant-
#: column and the compensating-control assertions instead of by a "must be
#: empty without GUC" assertion they could never pass.
#:
#: "Primary", not "only": the Django admin is a second production access path on
#: all four (``application/admin.py`` registers each of them) and it is not
#: tenant-scoped, which is why every justification below has to name its admin
#: exposure instead of claiming a closed set of readers.
WORKER_OWNED_TABLES = frozenset(
    {
        "as_domain_event_outbox",
        "as_domain_event_dlq",
        "as_webhook_subscription",
        "as_webhook_delivery_log",
    }
)

#: The subset of :data:`WORKER_OWNED_TABLES` holding outbound-webhook
#: configuration and its attempt log, i.e. the two tables whose compensating
#: control is purely a "no user-reachable reader exists" code-path argument.
WEBHOOK_TABLES = frozenset(
    {"as_webhook_subscription", "as_webhook_delivery_log"}
)

#: The plain child tables that DO carry a policy, i.e. the ones for which
#: "empty without the GUC" is a property the project actually guarantees.
RLS_GUARDED_TABLES = frozenset(PLAIN_CHILD_TABLES) - set(RLS_EXEMPT_TABLES)

#: Production modules allowed to reference a webhook model, and why. A reader
#: outside this set would make the compensating control below untrue, because
#: nothing at the database layer stops it reading another tenant's rows.
WEBHOOK_READER_ALLOWLIST = {
    "application/models.py": "the model definitions themselves",
    "application/admin.py": (
        "Django admin change lists (reqogniloom/urls.py mounts /admin/) - a "
        "staff-superuser operator surface, not a tenant-scoped one"
    ),
    "application/webhook_dispatcher.py": (
        "the poller-driven subscriber: process_event / _load_webhook_configs "
        "/ _already_delivered / _dispatch_with_retry"
    ),
}

# ---------------------------------------------------------------------------
# CR-17 exemption-record contract
# ---------------------------------------------------------------------------
# The claims each ``RLS_EXEMPT_TABLES`` justification must carry *verbatim*, as
# ``(marker, what the marker stands for)`` pairs, plus the ones every one of
# the four entries has to state. This exists because a length check is not a
# record: an earlier revision only required > 200 characters, so the
# admin-exposure sentences could be deleted and the suite would stay green.
# A marker is a phrase, not a length, so shortening or dropping the sentence
# that carries it fails the test.
#
# The admin markers are attributed per table, deliberately. Verified against
# ``application/admin.py`` and ``application/models.py``: the secret and the
# writable foreign ``workspace_id`` belong to ``as_webhook_subscription``
# alone, the rendered ``payload`` to the outbox and the DLQ, and the two
# read-only admins are called out as such — including the three tables for
# which the "admin can mint or retarget a foreign workspace_id" claim does NOT
# hold.
_ADMIN_DETAIL_PAYLOAD_CLAIM = (
    "the admin change page renders payload and workspace_id",
    "the admin detail page shows another tenant's row payload to a staff "
    "superuser (verified: both fields are in readonly_fields, which Django "
    "renders rather than edits)",
)
_ADMIN_NO_MINT_CLAIM = (
    "no admin add/edit form can mint or retarget a foreign workspace_id",
    "the claim that a superuser can mint or retarget a row into another tenant "
    "through the admin form is explicitly REFUTED for this table (verified "
    "form fields / permissions in application/admin.py)",
)
_ADMIN_READ_ONLY_CLAIM = (
    "has_add_permission, has_change_permission and has_delete_permission all "
    "return False",
    "the registered admin for this table is read-only, which is what makes the "
    "refuted mint/retarget claim refuted rather than merely unverified",
)
_ADMIN_CHANGEABLE_OUTBOX_CLAIM = (
    "an editable claimed_at",
    "the real admin write path on the outbox (default add/delete permissions "
    "plus an editable claimed_at) instead of the mint/retarget claim",
)

#: Shared by all four entries: the fix shape and the status markers, plus the
#: compensating-control statement. Every one of these four tables has a control
#: that is service-layer and code-path only, and a staff superuser with
#: Django-admin access, so none of the four may be documented as if the
#: database backed it up.
_CR17_SHARED_CLAIMS = (
    (
        "app.current_tenant",
        "the session variable the standard policy is keyed on, and therefore why "
        "it cannot simply be applied to this table",
    ),
    (
        "stamp tenant_id onto the outbox payload at emission time",
        "the required fix shape (the one memory.projector already uses) — the "
        "entry is not complete without naming it",
    ),
    (
        "service-layer and code-path only",
        "the compensating control is a service-layer / code-path argument, NOT a "
        "database-enforced guarantee",
    ),
    (
        "human-reachable cross-tenant",
        "a staff superuser with Django-admin access remains a human-reachable "
        "cross-tenant path on this table",
    ),
    (
        "still OPEN",
        "the residual risk is still open, i.e. not closed by this entry",
    ),
)

CR17_JUSTIFICATION_CLAIMS: dict[str, tuple[tuple[str, str], ...]] = {
    "as_domain_event_outbox": (
        _ADMIN_DETAIL_PAYLOAD_CLAIM,
        _ADMIN_NO_MINT_CLAIM,
        _ADMIN_CHANGEABLE_OUTBOX_CLAIM,
    ),
    "as_domain_event_dlq": (
        _ADMIN_DETAIL_PAYLOAD_CLAIM,
        _ADMIN_NO_MINT_CLAIM,
        _ADMIN_READ_ONLY_CLAIM,
    ),
    "as_webhook_subscription": (
        (
            "editable field on both the admin add form and the admin change form",
            "the HMAC secret is stored in the clear and is rendered/rewritable "
            "on the admin pages, so a staff superuser sees secret material "
            "(verified: secret is a plain CharField and is absent only from "
            "list_display)",
        ),
        (
            "both accept a foreign workspace_id",
            "the admin add/edit path for this table has no tenant-ownership "
            "validation, so a superuser can mint or retarget a subscription into "
            "another tenant",
        ),
        (
            "cross-secret",
            "the admin is a cross-secret path, not only a cross-tenant one",
        ),
    ),
    "as_webhook_delivery_log": (
        _ADMIN_READ_ONLY_CLAIM,
        (
            "the table has no workspace_id column at all",
            "this table has nothing an admin form could set even if the form "
            "were writable, which is part of why the mint/retarget claim is "
            "refuted rather than merely unverified here",
        ),
        (
            "WebhookSubscription.__str__",
            "the admin change page renders the owning subscription, whose "
            "__str__ prints the owning workspace_id and endpoint URL — how tenant "
            "data reaches the admin on a table with no workspace_id of its own",
        ),
    ),
}

#: Every entry's full claim list: the shared markers plus the table-specific
#: ones. Built once so the test and the failure message cannot drift apart.
CR17_ALL_CLAIMS: dict[str, tuple[tuple[str, str], ...]] = {
    table: _CR17_SHARED_CLAIMS + specific
    for table, specific in CR17_JUSTIFICATION_CLAIMS.items()
}

# ---------------------------------------------------------------------------
# as_domain_event_outbox reader / writer allowlist
# ---------------------------------------------------------------------------
#: Production modules allowed to READ ``as_domain_event_outbox`` rows, and why.
#: A reader outside this set would falsify the compensating control: nothing at
#: the database layer stops it reading another tenant's outbox row.
#:
#: Only two, and both are declared rather than assumed:
#:
#: * ``application/event_bus.py`` — the Celery poller. It has to read: the
#:   candidate query (:490-496) is what tells it *which* tenant a row belongs to
#:   (chicken-and-egg, see the exemption), ``_claim_event`` takes the row under
#:   SELECT FOR UPDATE, ``_finalize_success`` / ``_finalize_failure`` write the
#:   outcome back and the backlog count at :551 aggregates across tenants.
#: * ``application/admin.py`` — the Django admin (registered at
#:   ``application/admin.py:44``). Its reads happen inside Django, not in this
#:   repository's source, so no AST can see them; the registration itself is
#:   the detectable marker, and the change list renders ``workspace_id`` of
#:   every tenant.
OUTBOX_READER_MODULES = {
    "application/event_bus.py": (
        "the Celery OutboxPoller - candidate listing, SELECT FOR UPDATE claim, "
        "write-back and the cross-tenant backlog count; it must read before it "
        "can know the tenant"
    ),
    "application/admin.py": (
        "Django admin change list and change page (registered at "
        "application/admin.py:44) - a staff-superuser operator surface, not a "
        "tenant-scoped one"
    ),
}

#: Production modules allowed to WRITE ``as_domain_event_outbox`` rows *without*
#: reading them. Writers are legitimate and numerous on this table (every
#: emitter service publishes through ``DomainEventBus.publish``), which is why
#: the guard polices readers and not writers: a new legitimate write must not
#: have to fight this test. The set is still declared and still machine-checked,
#: in the two directions that matter — every module listed here must really
#: write, and none of them may read (otherwise it is a reader wearing a writer's
#: label and would slip past the reader allowlist).
OUTBOX_WRITER_MODULES = {
    "application/dlq_service.py": (
        "DlqService.replay_dlq_event re-queues a dead-lettered event "
        "(application/dlq_service.py:184); it inserts a row whose workspace_id "
        "it has already resolved through the tenant-scoped Workspace.objects, so "
        "it writes without reading the outbox"
    ),
}

#: The model module itself, and the emitter services, are neither: they name
#: ``DomainEventOutbox.EventType`` (an enum of choice strings) or nothing more.
#: Counting those as readers would flag every future event emitter, so the
#: classifier below separates "names the model" from "queries the table", and
#: the test pins that separation with a non-vacuity assertion.
OUTBOX_NON_QUERYING_REFERENCE_SAMPLE = {
    "application/requirement_service.py": (
        "publishes through DomainEventBus.publish and only names "
        "DomainEventOutbox.EventType.* as a kwarg"
    ),
    "application/models.py": "defines the model and its EventType enum",
}


def _arm_app_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')


def _disarm_app_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")
        cursor.execute("RESET ROLE")


def _count_as_app_role(sql: str, params=None) -> int:
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return cursor.fetchone()[0]


def _column_names(table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s",
            [table],
        )
        return {row[0] for row in cursor.fetchall()}


def _foreign_key_targets(table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ccu.table_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON kcu.constraint_name = tc.constraint_name "
            " AND kcu.constraint_schema = tc.constraint_schema "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON ccu.constraint_name = tc.constraint_name "
            " AND ccu.constraint_schema = tc.constraint_schema "
            "WHERE tc.constraint_type = 'FOREIGN KEY' "
            "  AND tc.table_schema = current_schema() "
            "  AND tc.table_name = %s",
            [table],
        )
        return {row[0] for row in cursor.fetchall()}


def _references(tree: ast.AST, name: str) -> bool:
    """True if *name* appears in the module as a class, identifier or import."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return True
        if isinstance(node, ast.Name) and node.id == name:
            return True
        if isinstance(node, ast.Attribute) and node.attr == name:
            return True
        if isinstance(node, ast.ImportFrom) and any(
            alias.name == name for alias in node.names
        ):
            return True
    return False


def _production_python_files() -> list[tuple[str, ast.AST]]:
    """``(repo-relative posix path, parsed tree)`` for every production module.

    Tests and migrations are skipped, because a code-path argument is about
    production code only: a reference from a test, or from a migration that
    merely names a table, is not a reachable reader.
    """
    from django.conf import settings

    root = Path(settings.BASE_DIR)
    files: list[tuple[str, ast.AST]] = []
    for path in root.rglob("*.py"):
        parts = path.relative_to(root).parts
        if "migrations" in parts or "tests" in parts:
            continue
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        files.append((Path(*parts).as_posix(), tree))
    return files


def _production_modules_referencing(model_name: str) -> set[str]:
    """Every production module whose source names *model_name*, repo-relative.

    A code-path argument rendered as an executable check. Static ``ast`` scan of
    the backend tree, skipping tests and migrations: a reference from a
    ``rest_api`` view, a serializer or an MCP tool would show up here and fail
    the allowlist comparison in the caller.

    Deliberately name-level and therefore deliberately blunt: it answers "which
    modules mention this model", not "which modules read its rows". For the
    webhook tables that is good enough (few modules mention them), but for
    ``as_domain_event_outbox`` it would return every emitter service, so the
    table-level classifier below is used there instead.
    """
    return {
        relpath
        for relpath, tree in _production_python_files()
        if _references(tree, model_name)
    }


#: Manager attributes that root a queryset, i.e. the segment right below the
#: model name in a chain like ``DomainEventOutbox.objects.filter(...)``.
_MANAGER_ATTRS = frozenset({"objects", "_default_manager", "_base_manager", "unscoped"})

#: QuerySet/Manager methods that mutate rows. Everything else that reaches a
#: table is a read, including methods this map has never heard of.
_WRITE_METHODS = frozenset(
    {
        "create",
        "bulk_create",
        "bulk_update",
        "update",
        "update_or_create",
        "delete",
        "save",
        "remove",
        "clear",
        "set",
        "add",
    }
)


def _attribute_chain(node: ast.AST) -> list[str] | None:
    """``a.b.c`` -> ``['a', 'b', 'c']``; ``None`` when the root is not a Name.

    Only the plain ``Name -> Attribute*`` shape is recognised, so a manager
    passed around as a local variable is not attributed to the model. That is a
    real limit of the technique, stated in the test that relies on it.
    """
    segments: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        segments.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        segments.append(current.id)
        return list(reversed(segments))
    return None


def _table_touch_kind(chain: list[str]) -> str | None:
    """``"read"`` / ``"write"`` for a manager call chain, else ``None``.

    ``None`` means "names the model without querying the table" — the
    ``DomainEventOutbox.EventType.REQUIREMENT_CREATED`` shape every emitter
    service uses, and the model class definition itself. Unknown manager
    methods are counted as reads on purpose: this guard exists to notice a
    reader, so an unrecognised access shape must fail the allowlist rather than
    slip through it.
    """
    if len(chain) < 2 or chain[1] not in _MANAGER_ATTRS:
        return None
    terminal = chain[-1]
    if terminal in _WRITE_METHODS:
        return "write"
    return "read"


def _admin_registration_sites(tree: ast.AST, model_name: str) -> list[str]:
    """``admin.register(Model)`` call sites, as display strings.

    The Django admin reads and writes through its own machinery, not through
    this repository's source, so no query chain exists to find. Registering the
    model is the one marker that is in the source, and it is exactly the
    surface a staff superuser reaches.
    """
    sites: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        chain = _attribute_chain(node.func)
        if not chain or chain[-1] != "register":
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            arg_chain = _attribute_chain(arg)
            if arg_chain and arg_chain[0] == model_name:
                sites.append(f"admin.register({model_name}) @L{node.lineno}")
    return sites


def _production_table_access(model_name: str) -> dict[str, dict[str, list[str]]]:
    """Per production module, the reads and writes it performs on *model_name*.

    ``{module: {"read": [site, ...], "write": [site, ...]}}`` where a site is
    ``"<call chain> @L<lineno>"``. Modules that only name the model (an
    ``EventType`` constant, a type annotation, the class definition) are absent
    from the mapping, which is the whole point: the compensating control is a
    "no unexpected reader" argument, and an emitter that publishes through
    ``DomainEventBus.publish`` is not one.
    """
    access: dict[str, dict[str, list[str]]] = {}
    for relpath, tree in _production_python_files():
        reads: list[str] = []
        writes: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            chain = _attribute_chain(node.func)
            if not chain or chain[0] != model_name:
                continue
            kind = _table_touch_kind(chain)
            if kind == "read":
                reads.append(f"{'.'.join(chain)} @L{node.lineno}")
            elif kind == "write":
                writes.append(f"{'.'.join(chain)} @L{node.lineno}")
        reads.extend(_admin_registration_sites(tree, model_name))
        if reads or writes:
            access[relpath] = {"read": sorted(reads), "write": sorted(writes)}
    return access



def _seed_two_tenants(label: str = "cr17") -> dict:
    """One baseline + delta entries + outbox + DLQ + webhook rows per tenant.

    Returns ``{"tenant_a": ..., "tenant_b": ..., "workspace_a": ...,
    "workspace_b": ..., "item_ids": {tenant: [item_id, ...]}}``; the tenants are
    built with ``unscoped`` writes so no tenant context has to be armed here.
    """
    from application.models import (
        DomainEventDLQ,
        DomainEventOutbox,
        WebhookDeliveryLog,
        WebhookSubscription,
    )
    from baseline.models import BaselineDeltaIndexEntry, BaselineSnapshot
    from persistence.models import Artifact, Tenant, Workspace

    seeded: dict = {"tenants": [], "workspaces": [], "item_ids": {}}
    for slot in ("a", "b"):
        tenant = Tenant.objects.create(
            name=f"{label}-{slot}-{uuid.uuid4().hex[:6]}",
            slug=f"{label}-{slot}-{uuid.uuid4().hex[:10]}",
        )
        workspace = Workspace.unscoped.create(
            tenant=tenant, name=f"{label}-{slot}-{uuid.uuid4().hex[:6]}"
        )
        artifact = Artifact.unscoped.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        baseline = BaselineSnapshot.unscoped.create(
            tenant=tenant, workspace_id=workspace.id, name=f"{label}-{slot}"
        )
        item_ids = []
        for index in (1, 2):
            item_id = str(uuid.uuid4())
            item_ids.append(item_id)
            BaselineDeltaIndexEntry.objects.create(
                baseline=baseline,
                item_id=item_id,
                version=index,
                entity_type="item",
                state={"title": f"{label}-{slot}-{index}"},
            )
        outbox_row = DomainEventOutbox.objects.create(
            event_type=DomainEventOutbox.EventType.REQUIREMENT_CREATED,
            workspace_id=workspace.id,
            entity_id=artifact.id,
            payload={"artifact_id": str(artifact.id)},
        )
        DomainEventDLQ.objects.create(
            event_id=outbox_row.event_id,
            event_type=outbox_row.event_type,
            workspace_id=workspace.id,
            entity_id=artifact.id,
            payload={"artifact_id": str(artifact.id)},
            error_message="boom",
        )
        subscription = WebhookSubscription.objects.create(
            workspace_id=workspace.id,
            event_types="RequirementCreated",
            url=f"https://example.invalid/{label}-{slot}",
            secret=f"secret-{label}-{slot}",
        )
        WebhookDeliveryLog.objects.create(
            subscription=subscription,
            event_id=outbox_row.event_id,
            event_type=outbox_row.event_type,
            status_code=500,
            success=False,
            error_message="boom",
        )
        seeded["tenants"].append(tenant)
        seeded["workspaces"].append(workspace)
        seeded["item_ids"][tenant.id] = item_ids
    return seeded


@_pg_only
def test_app_role_is_the_least_privilege_non_superuser_role():
    """Precondition: the role the negatives below rely on actually exists, is
    NOT the session user, and is not a superuser — otherwise "RLS hid the row"
    and "the superuser bypassed everything" would be indistinguishable."""
    _arm_app_role()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_user, session_user, rolsuper FROM pg_roles "
                "WHERE rolname = current_user"
            )
            app_user, session_user, is_superuser = cursor.fetchone()
    finally:
        _disarm_app_role()

    assert app_user == APP_DB_ROLE, f"expected SET ROLE to land on {APP_DB_ROLE}, got {app_user}"
    assert app_user != session_user, (
        f"the test session user is already {APP_DB_ROLE}; the RLS negatives "
        "below would prove nothing"
    )
    assert is_superuser is False, (
        f"{APP_DB_ROLE} is a superuser and bypasses RLS unconditionally — "
        "persistence/migrations/0048_app_role.py creates it NOSUPERUSER"
    )


@_pg_only
class TestPlainChildTablesUnderAppRole:
    @pytest.mark.parametrize("table", sorted(RLS_GUARDED_TABLES))
    def test_empty_without_tenant_guc(self, table):
        """The CR-17 requirement: two tenants with rows, direct child-table
        query as the app role with no tenant context -> empty/policy-filtered.

        Scoped to :data:`RLS_GUARDED_TABLES` — the four worker-owned tables have
        no ``tenant_id`` column to key a policy on, so this assertion is
        unreachable for them by construction rather than unmet. Their state is
        asserted further down: exempt declaration, no tenant column, and the
        compensating controls that are what actually keeps the cross-tenant
        readability in them unreachable today.
        """
        _seed_two_tenants("cr17-unarmed")

        _arm_app_role()
        try:
            visible = _count_as_app_role(f"SELECT count(*) FROM {table}")
        finally:
            _disarm_app_role()

        assert visible == 0, (
            f"{table} ({PLAIN_CHILD_TABLES[table]}) returned {visible} row(s) "
            "to the least-privilege application role with app.current_tenant "
            "unset — a plain child model with no RLS policy is a cross-tenant "
            "read for any code path that queries it directly"
        )

    def test_delta_index_entry_filters_to_the_owning_tenant(self):
        """``bl_delta_index_entry`` must not only hide rows when unarmed — it
        must filter them by the parent snapshot's tenant once one is armed,
        otherwise the policy would be a blanket deny rather than isolation.
        """
        seeded = _seed_two_tenants("cr17-filter")
        tenant_a, tenant_b = seeded["tenants"]
        own_item_ids = set(seeded["item_ids"][tenant_a.id])
        foreign_item_ids = set(seeded["item_ids"][tenant_b.id])
        unknown_tenant = uuid.uuid4()

        _arm_app_role()
        try:
            visible_unarmed = _count_as_app_role("SELECT count(*) FROM bl_delta_index_entry")

            with connection.cursor() as cursor:
                cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
                cursor.execute("SELECT item_id FROM bl_delta_index_entry")
                own_rows = {row[0] for row in cursor.fetchall()}

                cursor.execute("SET app.current_tenant = %s", [str(unknown_tenant)])
                cursor.execute("SELECT count(*) FROM bl_delta_index_entry")
                unknown_rows = cursor.fetchone()[0]
        finally:
            _disarm_app_role()

        assert visible_unarmed == 0
        assert own_rows == own_item_ids, (
            "arming the owning tenant must expose exactly that tenant's delta "
            "entries — got a different set, so the policy is either keyed on "
            "the wrong relation or not filtering at all"
        )
        assert own_rows.isdisjoint(foreign_item_ids)
        assert unknown_rows == 0

    def test_delta_index_entry_rejects_a_foreign_tenant_write(self):
        """WITH CHECK half: a tenant may not append an entry to a baseline
        owned by somebody else, not merely read its own rows."""
        from baseline.models import BaselineSnapshot

        seeded = _seed_two_tenants("cr17-write")
        tenant_a = seeded["tenants"][0]
        foreign_baseline_id = BaselineSnapshot.unscoped.get(
            workspace_id=seeded["workspaces"][1].id
        ).id

        _arm_app_role()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
                with pytest.raises(Exception) as excinfo:
                    cursor.execute(
                        "INSERT INTO bl_delta_index_entry "
                        "(id, baseline_id, item_id, version, entity_type, state) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        [
                            str(uuid.uuid4()),
                            str(foreign_baseline_id),
                            str(uuid.uuid4()),
                            1,
                            "item",
                            None,
                        ],
                    )
        finally:
            _disarm_app_role()

        assert "row-level security" in str(excinfo.value).lower(), (
            "inserting a delta entry into another tenant's baseline was not "
            f"rejected by the policy: {excinfo.value}"
        )


@_pg_only
def test_dlq_service_denies_a_foreign_workspace_id():
    """The compensating control for ``as_domain_event_dlq``: both user-facing
    entry points resolve ``workspace_id`` through the tenant-scoped
    ``Workspace.objects`` before touching the row, so a cross-tenant
    ``workspace_id`` is indistinguishable from an unknown one
    (``application/dlq_service.py:112`` and ``:160``). Replay is covered too,
    because it is the write half of the same control: naming somebody else's
    ``event_id`` must not move their DLQ row back into the outbox, neither with
    that tenant's ``workspace_id`` nor with the caller's own.

    This is what keeps the DB-level gap on that table unreachable over the
    API today, and it is asserted here so the gap is reported with its actual
    exposure rather than as an open hole. It is a service-layer control, not a
    database one: the row itself stays readable by any code path that queries
    ``DomainEventDLQ`` directly, which is why ``as_domain_event_dlq`` stays in
    ``RLS_EXEMPT_TABLES`` as named CR-17 residual risk until the tenant stamp
    exists.
    """
    from application.base import NotFoundError
    from application.dlq_service import DlqService
    from application.models import DomainEventDLQ, DomainEventOutbox
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.tenancy import TenantContext

    seeded = _seed_two_tenants("cr17-dlq")
    tenant_b = seeded["tenants"][1]
    foreign_workspace_id = seeded["workspaces"][0].id
    own_workspace_id = seeded["workspaces"][1].id
    foreign_dlq = DomainEventDLQ.objects.get(workspace_id=foreign_workspace_id)
    outbox_before = DomainEventOutbox.objects.count()

    ctx = AuthContext(
        user_id=None,
        tenant_id=tenant_b.id,
        active_roles=("admin",),
        auth_method=AuthMethod.API_KEY,
    )
    try:
        with pytest.raises(NotFoundError):
            DlqService().list_dlq(ctx, workspace_id=foreign_workspace_id)

        with pytest.raises(NotFoundError):
            DlqService().replay_dlq_event(
                ctx, foreign_dlq.event_id, workspace_id=foreign_workspace_id
            )
        with pytest.raises(NotFoundError):
            DlqService().replay_dlq_event(
                ctx, foreign_dlq.event_id, workspace_id=own_workspace_id
            )

        assert DomainEventDLQ.objects.filter(pk=foreign_dlq.pk).exists(), (
            "a rejected cross-tenant DLQ replay still removed the foreign row"
        )
        assert DomainEventOutbox.objects.count() == outbox_before, (
            "a rejected cross-tenant DLQ replay still re-queued the foreign "
            "event into the outbox"
        )
    finally:
        TenantContext.clear_tenant()
        with connection.cursor() as cursor:
            cursor.execute("RESET app.current_tenant")


# ---------------------------------------------------------------------------
# Worker-owned tables: documented residual risk instead of unreachable asserts
# ---------------------------------------------------------------------------
#
# ``test_empty_without_tenant_guc`` asks for database enforcement these four
# tables cannot carry. The tests below assert what the project does guarantee,
# which is narrower but true and enforceable, so the cross-tenant readability
# stays visible in the suite instead of being deleted from it.


def test_module_inventory_matches_the_rls_exemption_registry():
    """:data:`WORKER_OWNED_TABLES` and the CR-17 registry must name one set.

    Without this, either list could drift: a table could be added here and
    quietly left out of ``RLS_EXEMPT_TABLES`` (an unreported gap again), or
    exempted there while this module still claims it is unguarded.
    """
    assert WORKER_OWNED_TABLES == set(RLS_EXEMPT_PLAIN_TABLES), (
        "this module's CR-17 inventory and persistence.tests.test_rls_coverage's "
        "plain-table exemptions have diverged: "
        f"{sorted(WORKER_OWNED_TABLES ^ set(RLS_EXEMPT_PLAIN_TABLES))}"
    )
    assert WORKER_OWNED_TABLES <= set(PLAIN_CHILD_TABLES), (
        "WORKER_OWNED_TABLES names a table that CR-17 does not inventory"
    )
    assert RLS_GUARDED_TABLES == {"bl_delta_index_entry"}, (
        "the guarded plain-child set moved: "
        f"{sorted(RLS_GUARDED_TABLES)}. A newly guarded table belongs back in "
        "test_empty_without_tenant_guc; a newly exempted one needs the "
        "compensating-control assertions instead."
    )
    assert set(CR17_ALL_CLAIMS) == set(WORKER_OWNED_TABLES), (
        "the CR-17 claim contract and the worker-owned inventory have drifted: "
        f"{sorted(set(CR17_ALL_CLAIMS) ^ set(WORKER_OWNED_TABLES))}. A newly "
        "exempted table has no required claims yet, so its justification could "
        "be shortened back to a generic paragraph without any test noticing"
    )


@pytest.mark.parametrize("table", sorted(WORKER_OWNED_TABLES))
def test_worker_owned_table_is_declared_rls_exempt_with_a_justification(table):
    """The four tables must stay *declared* as cross-tenant-readable, in
    writing, and the declaration must still carry every specific claim CR-17
    records for that table.

    This is the replacement for asserting they return zero rows, which they
    provably do not. The exemption is what makes the gap a reviewed decision
    rather than a hole: delete the entry, empty the justification, replace it
    with a bare "TODO" or shorten it back to a generic paragraph, and this test
    fails.

    Precisely what the contract is, because the previous wording overstated it.
    Equivalence that IS established: the RLS-guarded plain child
    (``bl_delta_index_entry``) is held to the same database-enforced bar as the
    other guarded tables — empty without the GUC, filtering to the owning tenant
    once one is armed, and a WITH CHECK that rejects a foreign-tenant INSERT
    (``TestPlainChildTablesUnderAppRole``). Equivalence that is NOT established
    and must not be implied: the four worker-owned tables are *not* equivalent to
    those tables and are not treated as if they were — they carry no policy, are
    exempted, and are held only to the declaration, the no-tenant-column check
    and the compensating-control checks below. The text contract asserted here
    is imposed by THIS module and only on these four; ``test_rls_coverage``
    imposes no text contract at all on its own ``TenantScopedModel`` exemptions
    (``at_api_key``, ``at_refresh_token``, ``at_user_role``, ``audit_entry`` —
    four, not three), only the staleness check that their model still exists,
    is still of the same kind, and still has no policy.
    """
    assert table in RLS_EXEMPT_TABLES, (
        f"{table} ({PLAIN_CHILD_TABLES[table]}) is readable across tenants by "
        f"{APP_DB_ROLE} with app.current_tenant unset and is not declared in "
        "RLS_EXEMPT_TABLES — CR-17 residual risk is unreported again"
    )

    justification = RLS_EXEMPT_TABLES[table].strip()
    assert len(justification) > 200, (
        f"the RLS_EXEMPT_TABLES entry for {table} is {len(justification)} "
        "characters long; the convention is a justification that names the "
        "blocking code path, not a placeholder"
    )

    claims = CR17_ALL_CLAIMS[table]
    missing = [claim for marker, claim in claims if marker not in justification]
    assert not missing, (
        f"the RLS_EXEMPT_TABLES entry for {table} no longer states "
        + "; ".join(f"({i + 1}) {claim}" for i, claim in enumerate(missing))
        + ". The exemption record is the only place CR-17's exposure for this "
        "table is written down, so shortening it back to a generic paragraph "
        "is a silent deletion of the finding: re-derive the claim against "
        "application/admin.py and application/models.py and restore the exact "
        "wording, or amend CR17_JUSTIFICATION_CLAIMS in this module if the "
        "claim itself is no longer true."
    )


@_pg_only
@pytest.mark.parametrize("table", sorted(WORKER_OWNED_TABLES))
def test_worker_owned_table_cannot_carry_a_tenant_keyed_policy(table):
    """Machine-checks the *reason* the exemption exists, on the live schema.

    A policy is a predicate over columns. These tables have no ``tenant_id``
    column, and no foreign key that could join one in, and their
    ``workspace_id`` is a bare UUID rather than a reference to a tenant-scoped
    row — so ``USING (tenant_id = current_setting('app.current_tenant'))``
    cannot be written for them at all. The poller cannot be the thing that
    supplies the tenant either: it must read a row to learn which tenant the
    row belongs to.

    So this is where the four tables' exposure actually comes from, asserted
    against the database rather than asserted in prose. The day someone adds
    ``tenant_id`` (the CR-17 fix: stamp it onto the outbox payload at emission
    time, the shape already used for ``memory.projector``) this test fails and
    forces the exemption to be re-litigated instead of quietly outliving the
    fix.
    """
    columns = _column_names(table)
    targets = _foreign_key_targets(table)

    assert "tenant_id" not in columns, (
        f"{table} now carries a tenant_id column ({sorted(columns)}), so the "
        "standard policy is expressible — drop the RLS_EXEMPT_TABLES entry and "
        "ship the policy"
    )
    assert "workspace_id" in columns or targets, (
        f"{table} no longer carries the workspace anchor CR-17 described — it "
        f"has neither a workspace_id column nor a foreign key: {sorted(columns)}"
    )
    if "workspace_id" in columns:
        assert "workspace" not in targets, (
            f"{table}.workspace_id is now a foreign key, so a policy can resolve "
            "the owning tenant through it — re-litigate the exemption"
        )
    for target in sorted(targets):
        assert "tenant_id" not in _column_names(target), (
            f"{table} reaches a tenant_id column through a foreign key to "
            f"{target}, so a policy can join the tenant in — re-litigate the "
            "exemption"
        )


@pytest.mark.parametrize("table", sorted(WEBHOOK_TABLES))
def test_webhook_table_has_no_reader_outside_the_worker_and_the_admin(table):
    """COMPENSATING CONTROL, AND IT IS NOT A DATABASE GUARANTEE.

    For the two webhook tables the only non-test references in the backend tree
    are the model definitions, the Django admin (a staff-superuser operator
    surface, not a tenant-scoped one) and the poller-driven subscriber — and
    the subscriber filters on the ``workspace_id`` carried by the event it was
    handed, not on a tenant identity the database vouched for. No REST view, no
    serializer and no MCP tool reads either table, so the cross-tenant
    readability that CR-17 confirmed is not reachable by any tenant-scoped API
    today.

    That is a CODE-PATH argument, checked here as one: this scans the sources,
    and it fails the moment a reader appears outside
    :data:`WEBHOOK_READER_ALLOWLIST`. It is not RLS, and it would not survive a
    raw query, a management command, a new endpoint or a second service. Raw
    Row-Level-Security enforcement on both tables remains OPEN, pending the
    ``tenant_id`` outbox-payload stamp named in
    ``RLS_EXEMPT_TABLES``.
    """
    referencing = _production_modules_referencing(PLAIN_CHILD_TABLES[table].split(".")[-1])

    unvetted = sorted(referencing - set(WEBHOOK_READER_ALLOWLIST))
    assert not unvetted, (
        f"{table} is now referenced from {unvetted}. This test's compensating "
        "control is 'no user-reachable reader exists' — a new reader has to be "
        "tenant-scoped, and CR-17's webhook exemption justification updated with "
        "it, rather than inherited from this allowlist"
    )

    vanished = sorted(set(WEBHOOK_READER_ALLOWLIST) - referencing)
    assert not vanished, (
        f"{table} is no longer referenced from {vanished}. The allowlist above "
        "is a re-audit snapshot: the compensating-control argument has to be "
        "re-derived, not carried over unchanged"
    )


def test_outbox_table_has_no_reader_outside_the_poller_and_the_admin():
    """COMPENSATING CONTROL, AND IT IS NOT A DATABASE GUARANTEE.

    The same shape as the webhook guard above, but the outbox needs a
    read/write split to be usable at all: a name-level scan of
    ``DomainEventOutbox`` returns every emitter service as well (fifteen
    production modules today), because each of them names
    ``DomainEventOutbox.EventType.*`` when it publishes. A dozen of those are
    not readers, and a reader allowlist that flagged them would block every
    future event emitter — i.e. it would punish exactly the legitimate writers
    this table is full of.

    So the guard classifies each reference site first and polices readers only:

    * declared READERS (:data:`OUTBOX_READER_MODULES`) — the Celery poller,
      which must read the row before it can know which tenant the row belongs
      to, and the Django admin, whose reads happen inside Django rather than in
      this repository's source (the ``admin.register`` call is the detectable
      marker).
    * declared WRITERS (:data:`OUTBOX_WRITER_MODULES`) — modules that write
      without reading. Writing is legitimate and common here, so the guard does
      NOT fail on an undeclared write: a new emitter that publishes into the
      outbox must not have to pass a test to be allowed to. What *is* asserted
      about writers is soundness: every declared writer really does write, and no
      declared writer also reads (a reader wearing a writer's label would walk
      straight past the reader allowlist).
    * everything else that only *names* the model — the ``EventType`` enum, a
      type annotation, the class definition — is not a table touch at all.

    What the AST can and cannot do, stated plainly. It separates read from write
    reliably for the ORM call shapes actually used on this table, by method name
    on a ``Model.objects.<method>(...)`` chain; an unrecognised manager method
    is counted as a READ, so an unknown access shape fails the allowlist instead
    of passing it. It cannot see a queryset or manager passed around as a local
    variable, an instance saved that way (``record.save(...)`` in
    ``_claim_event``), a ``getattr``-built chain, or raw SQL — those would be
    invisible here and are the reason this argument is code-path-only. Note the
    direction of the residual error: a shape it cannot classify is treated as a
    reader (fails loudly, must be declared), never as a writer (would slip
    through).

    The claim being made is therefore narrow and is stated as a code-path
    argument, not a database guarantee: no REST view, serializer, MCP tool or
    management command reads ``as_domain_event_outbox`` outside the declared
    set today, so the cross-tenant readability CR-17 confirmed is not reachable
    by any tenant-scoped API. It would not survive a raw query, a second service
    or a new poller written against a different table. Raw Row-Level-Security
    enforcement on the outbox remains OPEN, pending the ``tenant_id``
    outbox-payload stamp named in ``RLS_EXEMPT_TABLES``.
    """
    model = PLAIN_CHILD_TABLES["as_domain_event_outbox"].split(".")[-1]
    access = _production_table_access(model)
    readers = {module for module, sites in access.items() if sites["read"]}
    writers = {
        module
        for module, sites in access.items()
        if sites["write"] and not sites["read"]
    }

    unvetted = sorted(readers - set(OUTBOX_READER_MODULES))
    assert not unvetted, (
        f"{model} is now READ from {unvetted}. This test's compensating control "
        "is 'no undeclared reader exists' — a new reader sees every tenant's "
        "outbox row, because nothing at the database layer stops it, so it has "
        "to be tenant-scoped and CR-17's outbox exemption justification updated "
        f"with it rather than inherited from this allowlist. Details: "
        + "; ".join(f"{module}: {access[module]['read']}" for module in unvetted)
    )

    vanished = sorted(set(OUTBOX_READER_MODULES) - readers)
    assert not vanished, (
        f"{model} is no longer read from {vanished}. OUTBOX_READER_MODULES is a "
        "re-audit snapshot: the compensating-control argument has to be "
        "re-derived from what the poller and the admin actually do, not carried "
        "over unchanged"
    )

    laundered = sorted(set(OUTBOX_WRITER_MODULES) & readers)
    assert not laundered, (
        f"{laundered} are declared write-only but also READ {model}. A module "
        "that reads must be in OUTBOX_READER_MODULES with its read justified; "
        "declaring it a writer is how a reader would be hidden from the "
        "allowlist above"
    )

    phantom_writers = sorted(set(OUTBOX_WRITER_MODULES) - writers)
    assert not phantom_writers, (
        f"{phantom_writers} are declared writers of {model} but no longer write "
        "it without reading it. The declaration is a re-audit snapshot too: "
        "re-derive it, or move the module to OUTBOX_READER_MODULES if it reads"
    )

    # Non-vacuity: the classifier has to be able to tell "names the model" from
    # "queries the table", otherwise the guard above would be satisfied by any
    # emitter service and would mean nothing.
    wrongly_counted = sorted(
        module
        for module in OUTBOX_NON_QUERYING_REFERENCE_SAMPLE
        if module in readers or module in writers
    )
    assert not wrongly_counted, (
        f"{wrongly_counted} only name {model} (the class definition / the "
        "EventType enum) and must not be classified as touching the table. If "
        "this fails, the read/write classifier has stopped distinguishing ORM "
        "calls from enum access, and the allowlists above no longer prove "
        "anything"
    )
