"""CR-17 exit evidence — RLS on plain (non-``TenantScopedModel``) child tables.

``test_rls_coverage.py`` closes the gap for every ``TenantScopedModel``: it
diffs ``db_table`` against the ``CREATE POLICY`` statements in the migration
graph. A plain ``models.Model`` is invisible to that check by construction,
which is the class of table this module covers:

* ``bl_delta_index_entry`` — ``baseline.models.BaselineDeltaIndexEntry``,
  tenant identity inherited through the ``baseline_id`` FK
  (``baseline/migrations/0006_baseline_snapshot_rls.py`` documented the
  deferral; ``0010_baseline_delta_index_entry_rls.py`` closes it).
* ``as_domain_event_outbox``, ``as_domain_event_dlq``,
  ``as_webhook_subscription``, ``as_webhook_delivery_log`` —
  ``application/models.py``.

STAGED, ENFORCEMENT OFF BY DEFAULT (issue #1136): the four ``as_*`` tables
used to be an open CR-17 residual with no policy at all. They now carry a
nullable ``tenant_id`` (backfilled from ``pl_workspace.tenant_id``) and a
GUC-guarded policy (``application/0030``-``0032``). The policy predicate is
permissive while ``app.rls_as_enforced`` is unset — the production default —
so the Celery outbox poller and every existing path are unchanged; enforcement
turns on only when ``RLS_AS_ENFORCED=true`` arms the GUC. The tests below
therefore arm the GUC explicitly to assert the *armed* state, and pin the
declaration that the tables are staged (not exempt).

The compensating controls asserted here remain service-layer and code-path
arguments, not database guarantees: while the flag is OFF, a direct raw query
still reads across tenants. The Django admin no longer does: all four admins
inherit ``TenantScopedAdminMixin`` (``application/admin.py``), whose
``get_queryset``/``has_*_permission`` narrow to ``request.user.tenant_id``
(fail-closed), so a staff user of tenant A reaches neither list nor change of
tenant B's rows — as application code, not as a database guarantee. A future
registration that drops the mixin would reopen that path; the tests below say
so explicitly rather than claiming a closed set of readers.

Every DB assertion runs against the least-privilege, NOSUPERUSER application
role (``persistence.db_roles.APP_DB_ROLE``, REQ-L2-PL-010), via raw
``cursor.execute`` — the default test connection is a superuser and bypasses
RLS unconditionally, even with FORCE ROW LEVEL SECURITY. Setup rows are written
on that owner connection; the role (and the enforcement GUCs) are switched only
for the read under test.

``tenant_id`` is stamped in :func:`_seed_two_tenants` so positive filtering
(tenant X sees exactly X's rows) is testable, not just the empty-without-GUC
negatives.
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
    RLS_STAGED_TABLES,
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

#: The four plain ``as_*`` tables now in staged RLS scope (issue #1136). They
#: are the subset of :data:`PLAIN_CHILD_TABLES` that carry a GUC-guarded policy
#: behind ``RLS_AS_ENFORCED`` instead of an exemption. Their primary production
#: access path is still the Celery outbox poller, which runs with no tenant
#: context armed (``application.event_bus`` ``poll_and_dispatch``), but the
#: policy predicate is permissive while the GUC is unset, so the poller is
#: untouched in the default state. The declaration is asserted below against
#: ``RLS_STAGED_TABLES`` instead of ``RLS_EXEMPT_TABLES``.
STAGED_PLAIN_CHILD_TABLES = frozenset(
    {
        "as_domain_event_outbox",
        "as_domain_event_dlq",
        "as_webhook_subscription",
        "as_webhook_delivery_log",
    }
)

#: The subset of :data:`STAGED_PLAIN_CHILD_TABLES` holding outbound-webhook
#: configuration and its attempt log, i.e. the two tables whose compensating
#: control is purely a "no user-reachable reader exists" code-path argument.
WEBHOOK_TABLES = frozenset(
    {"as_webhook_subscription", "as_webhook_delivery_log"}
)

#: The plain child tables that carry a policy, i.e. the ones for which
#: "empty without the GUC" is a property the project actually guarantees. Since
#: issue #1136 the four ``as_*`` tables are covered too (staged), so this is all
#: five plain child tables.
RLS_GUARDED_TABLES = frozenset(PLAIN_CHILD_TABLES) - set(RLS_EXEMPT_TABLES)

#: Production modules allowed to reference a webhook model, and why. A reader
#: outside this set would make the compensating control below untrue, because
#: nothing at the database layer stops it reading another tenant's rows.
WEBHOOK_READER_ALLOWLIST = {
    "application/models.py": "the model definitions themselves",
    "application/admin.py": (
        "Django admin change lists/change pages (reqogniloom/urls.py mounts "
        "/admin/) - tenant-scoped per request.user.tenant_id by "
        "TenantScopedAdminMixin, i.e. application code, not a database "
        "guarantee; a future registration without the mixin would reopen the "
        "cross-tenant path"
    ),
    "application/webhook_dispatcher.py": (
        "the poller-driven subscriber: process_event / _load_webhook_configs "
        "/ _already_delivered / _dispatch_with_retry"
    ),
}

# ---------------------------------------------------------------------------
# Staged-record contract (issue #1136; was the CR-17 exemption contract)
# ---------------------------------------------------------------------------
# The claims each ``RLS_STAGED_TABLES`` entry must carry *verbatim*, as
# ``(marker, what the marker stands for)`` pairs. This exists because a length
# check is not a record: an earlier revision only required > 200 characters, so
# the load-bearing sentences could be deleted and the suite would stay green.
# A marker is a phrase, not a length, so shortening or dropping the sentence
# that carries it fails the test.
#
# The texts are re-derived against ``application/admin.py`` as it stands now:
# all four admins inherit ``TenantScopedAdminMixin``, so the old "a staff
# superuser reaches another tenant's rows" claim is STALE and must not appear.
# The staged entries state the opposite — the admin is tenant-scoped by app
# code — while being explicit that this is NOT a database guarantee.
_STAGED_SHARED_CLAIMS: tuple[tuple[str, str], ...] = (
    (
        "app.rls_as_enforced",
        "the GUC that gates the staged policy (off by default)",
    ),
    (
        "RLS_AS_ENFORCED",
        "the flag that arms the GUC, so the entry cannot be read as already "
        "enforced",
    ),
    (
        "pl_workspace.tenant_id",
        "where the nullable tenant_id is backfilled from",
    ),
    (
        "NULL by design",
        "an unresolvable workspace anchor stays NULL (O-2: no delete)",
    ),
    (
        "counted and logged, never deleted",
        "the orphan policy: counted + WARNING, never a destructive cleanup",
    ),
    (
        "fail-closed once enforced",
        "a NULL tenant_id matches nothing when the flag is flipped",
    ),
    (
        "enforcement behind flag",
        "the policy is inert until the flag is flipped (DEFAULT OFF)",
    ),
    (
        "still not enforced in production default",
        "the DEFAULT-OFF status is stated, not implied",
    ),
    (
        "service-layer and code-path only",
        "the compensating control is an app-level argument, NOT a database "
        "guarantee",
    ),
    (
        "NOT a database guarantee",
        "the admin's tenant-scoping is application code, not enforcement",
    ),
    (
        "TenantScopedAdminMixin",
        "the mechanism that tenant-scopes the admin today (app code)",
    ),
    (
        "A4",
        "the flag flip is gated on the poller tenant-arming work (A4/R-2)",
    ),
    (
        "R-7",
        "the fail-open, app-role-settable GUC residual is named",
    ),
    (
        "R-8",
        "the superuser-owned DEFINER residual is named",
    ),
    (
        "CR-17 residual risk, now staged rather than open",
        "the status moved from open residual to staged coverage",
    ),
)

#: Table-specific marker per staged plain child table, so the staged entry
#: names its own model/admin instead of copying one paragraph across all four.
STAGED_JUSTIFICATION_CLAIMS: dict[str, tuple[tuple[str, str], ...]] = {
    "as_domain_event_outbox": (
        (
            "DomainEventOutbox",
            "the outbox admin is named (tenant-scoped by the mixin, app code)",
        ),
    ),
    "as_domain_event_dlq": (
        (
            "DomainEventDLQAdmin",
            "the DLQ admin is named (tenant-scoped by the mixin, app code)",
        ),
    ),
    "as_webhook_subscription": (
        (
            "secret-bearing table",
            "the HMAC-secret exposure of this specific table is named",
        ),
    ),
    "as_webhook_delivery_log": (
        (
            "WebhookDeliveryLogAdmin",
            "the delivery-log admin is named (tenant-scoped through the "
            "subscription's workspace, app code)",
        ),
    ),
}

#: Every entry's full claim list: the shared markers plus the table-specific
#: ones. Built once so the test and the failure message cannot drift apart.
STAGED_ALL_CLAIMS: dict[str, tuple[tuple[str, str], ...]] = {
    table: _STAGED_SHARED_CLAIMS + specific
    for table, specific in STAGED_JUSTIFICATION_CLAIMS.items()
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
#:   ``application/admin.py:55``). Its reads happen inside Django, not in this
#:   repository's source, so no AST can see them; the registration itself is
#:   the detectable marker. ``DomainEventOutboxAdmin`` inherits
#:   ``TenantScopedAdminMixin``, so it narrows to the operator's tenant — but
#:   that is application code, not a database guarantee.
OUTBOX_READER_MODULES = {
    "application/event_bus.py": (
        "the Celery OutboxPoller - candidate listing, SELECT FOR UPDATE claim, "
        "write-back and the cross-tenant backlog count; it must read before it "
        "can know the tenant"
    ),
    "application/admin.py": (
        "Django admin change list and change page (registered at "
        "application/admin.py:55) - tenant-scoped per request.user.tenant_id "
        "by TenantScopedAdminMixin (application code, not a database guarantee)"
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
    """Switch to the app role AND arm both staged-RLS enforcement GUCs.

    Arming the GUCs is what makes ``test_empty_without_tenant_guc`` assert the
    *sharp* state for the staged tables: without it the policy would be
    permissive and the negative would prove nothing. ``app.current_tenant`` is
    deliberately left unset for that assertion.
    """
    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        cursor.execute("SET app.rls_as_enforced = 'on'")
        cursor.execute("SET app.rls_preauth_enforced = 'on'")


def _disarm_app_role() -> None:
    """Reset both enforcement GUCs and the role.

    Resetting the GUCs matters: they are session-scoped, so a value left armed
    here would leak into later tests and silently change their meaning (F-07 /
    AC-23).
    """
    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")
        cursor.execute("RESET app.rls_as_enforced")
        cursor.execute("RESET app.rls_preauth_enforced")
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
            tenant_id=tenant.id,
            entity_id=artifact.id,
            payload={"artifact_id": str(artifact.id)},
        )
        DomainEventDLQ.objects.create(
            event_id=outbox_row.event_id,
            event_type=outbox_row.event_type,
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            entity_id=artifact.id,
            payload={"artifact_id": str(artifact.id)},
            error_message="boom",
        )
        subscription = WebhookSubscription.objects.create(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            event_types="RequirementCreated",
            url=f"https://example.invalid/{label}-{slot}",
            secret=f"secret-{label}-{slot}",
        )
        WebhookDeliveryLog.objects.create(
            subscription=subscription,
            # Stamped from the owning subscription's tenant (F-03): without it
            # the positive filter assertion below would be untestable.
            tenant_id=tenant.id,
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
        """Two tenants with rows, direct child-table query as the app role with
        the enforcement GUC armed but no tenant context -> empty.

        ``_arm_app_role`` arms ``app.rls_as_enforced`` / ``app.rls_preauth_enforced``,
        so this asserts the *sharp* state for all five guarded plain child
        tables (``bl_delta_index_entry`` plus the four staged ``as_*`` tables).
        Without the arm the staged policies would be permissive and the
        negative would prove nothing.
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
            "unset and the enforcement GUC armed — a guarded table that leaks "
            "rows is a cross-tenant read for any code path that queries it "
            "directly"
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
@pytest.mark.parametrize("table", sorted(STAGED_PLAIN_CHILD_TABLES))
def test_staged_plain_child_table_filters_to_the_owning_tenant(table):
    """AC-9: with the enforcement GUC armed and ``app.current_tenant=X`` the
    staged table exposes exactly X's rows and none of the other tenant's.

    The seed stamps ``tenant_id`` (F-03), so this is a real positive filter
    assertion, not just the empty-without-GUC negative.
    """
    seeded = _seed_two_tenants("cr17-staged-filter")
    tenant_a, tenant_b = seeded["tenants"]

    _arm_app_role()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
            cursor.execute(
                f"SELECT count(*) FROM {table} WHERE tenant_id = %s",
                [str(tenant_a.id)],
            )
            own = cursor.fetchone()[0]
            cursor.execute(
                f"SELECT count(*) FROM {table} WHERE tenant_id = %s",
                [str(tenant_b.id)],
            )
            foreign = cursor.fetchone()[0]
    finally:
        _disarm_app_role()

    assert own == 1, (
        f"{table} exposed {own} of tenant A's own rows to tenant A under "
        "enforcement (expected exactly 1)"
    )
    assert foreign == 0, (
        f"{table} exposed {foreign} of tenant B's rows to tenant A under "
        "enforcement"
    )


@_pg_only
def test_staged_plain_child_table_rejects_a_foreign_tenant_write():
    """AC-10 WITH CHECK: arming the GUC makes a foreign-tenant INSERT fail;
    with the GUC unset the same INSERT succeeds (permissive default)."""
    seeded = _seed_two_tenants("cr17-staged-write")
    tenant_a, tenant_b = seeded["tenants"]
    foreign_ws = seeded["workspaces"][1].id

    insert_sql = (
        "INSERT INTO as_domain_event_outbox "
        "(id, event_id, event_type, workspace_id, tenant_id, entity_id, payload, "
        " created_at, published, retry_count) "
        "VALUES (%s, %s, 'RequirementCreated', %s, %s, %s, '{}'::jsonb, now(), "
        " false, 0)"
    )
    params = [
        str(uuid.uuid4()),
        str(uuid.uuid4()),
        str(foreign_ws),
        str(tenant_b.id),
        str(uuid.uuid4()),
    ]

    rejected = None
    _arm_app_role()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
            with pytest.raises(Exception) as excinfo:
                cursor.execute(insert_sql, params)
            rejected = excinfo.value
    finally:
        _disarm_app_role()

    assert "row-level security" in str(rejected).lower(), (
        "writing a row stamped for another tenant was not rejected under "
        f"enforcement: {rejected}"
    )

    # Permissive branch: SET ROLE but leave both GUCs unset -> the predicate is
    # TRUE and the write must go through (THIS IS THE DEFAULT-OFF SHIP).
    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        try:
            cursor.execute(insert_sql, params)
        finally:
            cursor.execute("RESET ROLE")


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

    This keeps the row's exposure unreachable over the API, and it is asserted
    here so the control is reported as a control. It is a service-layer control,
    not a database one: while the flag is OFF the row itself stays readable by
    any code path that queries ``DomainEventDLQ`` directly. Since issue #1136
    the table no longer sits in ``RLS_EXEMPT_TABLES`` — it carries a
    GUC-guarded, staged policy — but that policy is permissive until
    ``RLS_AS_ENFORCED`` is flipped, so this compensating control still carries
    the guarantee in the default state.
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
# Staged plain-child tables (#1136): declaration + tenant key + policy
# ---------------------------------------------------------------------------
#
# These four tables used to be declared cross-tenant-readable (an exemption).
# They are now covered by a staged, GUC-guarded policy, so the tests below
# assert what the project guarantees today: the declaration moved to
# ``RLS_STAGED_TABLES`` and carries a new, verbatim claim set; the live schema
# carries the tenant key and the policy; and the compensating controls that
# still matter while the flag is OFF are code-path arguments, not a database
# guarantee.


def test_module_inventory_matches_the_rls_staged_registry():
    """:data:`STAGED_PLAIN_CHILD_TABLES` and the staged registry must name one
    set, and the four must actually be guarded now.

    Without this, either list could drift: a table could be added here and
    quietly left out of ``RLS_STAGED_TABLES``, or staged there while this module
    still claims it is unguarded.
    """
    assert STAGED_PLAIN_CHILD_TABLES == set(RLS_STAGED_TABLES) & set(
        PLAIN_CHILD_TABLES
    ), (
        "this module's staged inventory and test_rls_coverage's RLS_STAGED_TABLES "
        "have diverged: "
        f"{sorted(STAGED_PLAIN_CHILD_TABLES ^ (set(RLS_STAGED_TABLES) & set(PLAIN_CHILD_TABLES)))}"
    )
    assert STAGED_PLAIN_CHILD_TABLES <= set(PLAIN_CHILD_TABLES), (
        "STAGED_PLAIN_CHILD_TABLES names a table that CR-17 does not inventory"
    )
    assert RLS_GUARDED_TABLES == set(PLAIN_CHILD_TABLES), (
        "the guarded plain-child set moved: "
        f"{sorted(RLS_GUARDED_TABLES)}. Every plain child table carries a policy "
        "since #1136; a newly unguarded one needs a staged entry and the "
        "declaration assertions instead."
    )
    assert not RLS_EXEMPT_PLAIN_TABLES, (
        "a plain child table is still declared exempt; the four as_* tables are "
        "staged now, so RLS_EXEMPT_PLAIN_TABLES must stay empty"
    )
    assert set(STAGED_ALL_CLAIMS) == set(STAGED_PLAIN_CHILD_TABLES), (
        "the staged claim contract and the staged inventory have drifted: "
        f"{sorted(set(STAGED_ALL_CLAIMS) ^ set(STAGED_PLAIN_CHILD_TABLES))}. A "
        "newly staged table has no required claims yet, so its justification "
        "could be shortened back to a generic paragraph without any test noticing"
    )


@pytest.mark.parametrize("table", sorted(STAGED_PLAIN_CHILD_TABLES))
def test_staged_table_is_declared_staged_with_a_justification(table):
    """Each of the four tables must be declared *staged* (not exempt), in
    writing, and the declaration must still carry every specific claim.

    This replaces the old exemption test (F-02): that one read
    ``RLS_EXEMPT_TABLES[table]`` and would now raise ``KeyError``. The staged
    record is what makes the coverage a reviewed decision rather than a silent
    claim: delete the entry, empty the justification, replace it with a bare
    "TODO" or shorten it back to a generic paragraph, and this test fails.
    """
    assert table in RLS_STAGED_TABLES, (
        f"{table} ({PLAIN_CHILD_TABLES[table]}) carries a staged policy but is "
        "not declared in RLS_STAGED_TABLES - the coverage is unreported"
    )
    assert table not in RLS_EXEMPT_TABLES, (
        f"{table} is both staged (policy shipped) and exempt; a table can only "
        "be one of the two"
    )

    justification = RLS_STAGED_TABLES[table].strip()
    assert len(justification) > 200, (
        f"the RLS_STAGED_TABLES entry for {table} is {len(justification)} "
        "characters long; the convention is a justification that names the GUC, "
        "the tenant_id source and the residuals, not a placeholder"
    )

    claims = STAGED_ALL_CLAIMS[table]
    missing = [claim for marker, claim in claims if marker not in justification]
    assert not missing, (
        f"the RLS_STAGED_TABLES entry for {table} no longer states "
        + "; ".join(f"({i + 1}) {claim}" for i, claim in enumerate(missing))
        + ". The staged record is the only place this table's coverage and its "
        "residuals are written down, so shortening it back to a generic "
        "paragraph is a silent deletion of the finding: re-derive the claim "
        "against application/admin.py, application/models.py and the migration, "
        "and restore the exact wording, or amend STAGED_JUSTIFICATION_CLAIMS in "
        "this module if the claim itself is no longer true."
    )


@_pg_only
@pytest.mark.parametrize("table", sorted(STAGED_PLAIN_CHILD_TABLES))
def test_staged_plain_child_table_carries_tenant_key_and_policy(table):
    """The three facts that make the table staged, asserted on the live schema:
    the ``tenant_id`` column exists, a policy exists, and the table is not
    exempt. Also checks the raw FK is validated.
    """
    columns = _column_names(table)
    assert "tenant_id" in columns, (
        f"{table} has no tenant_id column: the staged migration "
        f"(application/0030) did not land. Columns: {sorted(columns)}"
    )

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT policyname FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = %s",
            [table],
        )
        policies = {row[0] for row in cursor.fetchall()}
    assert policies, f"{table} carries no RLS policy on the live schema"

    assert table not in RLS_EXEMPT_TABLES, (
        f"{table} still has an RLS_EXEMPT_TABLES entry although it is staged"
    )

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT convalidated FROM pg_constraint WHERE conname = %s",
            [f"{table}_tenant_id_fk"],
        )
        constraint = cursor.fetchone()
    assert constraint is not None, (
        f"{table} has no tenant_id FK constraint (application/0030/0031)"
    )
    assert constraint[0] is True, (
        f"{table}.tenant_id FK is not VALIDATED (application/0031)"
    )


@pytest.mark.parametrize("table", sorted(WEBHOOK_TABLES))
def test_webhook_table_has_no_reader_outside_the_worker_and_the_admin(table):
    """COMPENSATING CONTROL, AND IT IS NOT A DATABASE GUARANTEE.

    For the two webhook tables the only non-test references in the backend tree
    are the model definitions, the Django admin (tenant-scoped per request by
    ``TenantScopedAdminMixin``, i.e. application code) and the poller-driven
    subscriber — and the subscriber filters on the ``workspace_id`` carried by
    the event it was handed, not on a tenant identity the database vouched for.
    No REST view, no serializer and no MCP tool reads either table, so the
    cross-tenant readability of the raw table is not reachable by any
    tenant-scoped API today.

    That is a CODE-PATH argument, checked here as one: this scans the sources,
    and it fails the moment a reader appears outside
    :data:`WEBHOOK_READER_ALLOWLIST`. It is not RLS, and it would not survive a
    raw query, a management command, a new endpoint or a second service. The
    staged policy shipped (application/0032) but is permissive while
    ``RLS_AS_ENFORCED`` is unset, so the compensating control is still not a
    database guarantee while the flag is OFF; it is defense-in-depth until A4 +
    the flag flip.
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
    set today, so the cross-tenant readability of the raw table is not reachable
    by any tenant-scoped API. It would not survive a raw query, a second service
    or a new poller written against a different table. The staged policy shipped
    (application/0032) but is permissive while ``RLS_AS_ENFORCED`` is unset, so
    the compensating control is still not a database guarantee while the flag is
    OFF; it is defense-in-depth until A4 + the flag flip.
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
        "outbox row, because the staged policy is permissive while the flag is "
        "OFF, so it has to be tenant-scoped and the staged outbox justification "
        "updated with it rather than inherited from this allowlist. Details: "
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
