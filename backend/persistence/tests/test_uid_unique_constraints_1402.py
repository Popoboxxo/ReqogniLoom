"""G1.3/#1402 — per-workspace ``uid`` uniqueness for the eight uid models.

Requirement's constraint shipped in persistence/0055; this PR extends the same
partial, workspace-scoped invariant to the other seven. The tests pin both
halves of the migration pair:

* the resulting DB constraints (duplicates rejected, cross-workspace reuse and
  blank uids allowed), and
* the migration's own behaviour (it renames pre-existing collisions, and the
  reverse/forward round-trip is clean).

Rollback/target migration names are used verbatim, never bare numbers (Plan
Index §e rule 4). At the time of writing the predecessor of
``0117_entity_workspace_fk_backfill`` is ``0116_index_hygiene_1411`` — the index
table's expected 0116 was already taken on ``main``, so the whole G1.3 pair
shifted by one (rule 1).

The invariant is a *partial* ``UniqueConstraint``, and Django emits such a
constraint as ``CREATE UNIQUE INDEX … WHERE …`` (schema editor
``_create_unique_sql`` picks ``sql_create_unique_index`` whenever ``condition``
is set). The objects therefore live in ``pg_indexes`` and can never appear in
``pg_constraint`` — the catalog assertions below read ``pg_indexes``.
"""

from __future__ import annotations

import uuid

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test.utils import CaptureQueriesContext

from persistence.models import (
    Adr,
    ArchitectureElement,
    Artifact,
    Issue,
    Risk,
    StakeholderNeed,
    TestCase,
    TestRun,
    Workspace,
)
from persistence.tests.factories import active_tenant, make_workspace

pytestmark = pytest.mark.django_db

_PREREQUISITE = "0117_entity_workspace_fk_backfill"
_CONSTRAINTS = "0118_uid_workspace_unique_constraints"

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


def _artifact(tenant, workspace, artifact_type: str) -> Artifact:
    return Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type=artifact_type
    )


def _build(tenant, workspace, model_name: str, uid: str):
    """Create one row of *model_name* with an explicit uid in *workspace*."""
    if model_name == "TestCase":
        return TestCase.objects.create(
            tenant=tenant,
            artifact=_artifact(tenant, workspace, "TestCase"),
            workspace=workspace,
            title=f"TC {uid}",
            uid=uid,
        )
    if model_name == "ArchitectureElement":
        return ArchitectureElement.objects.create(
            tenant=tenant,
            artifact=_artifact(tenant, workspace, "ArchitectureElement"),
            workspace=workspace,
            title=f"ARCH {uid}",
            uid=uid,
        )
    if model_name == "StakeholderNeed":
        return StakeholderNeed.objects.create(
            tenant=tenant,
            artifact=_artifact(tenant, workspace, "StakeholderNeed"),
            workspace=workspace,
            title=f"NEED {uid}",
            uid=uid,
        )
    if model_name == "TestRun":
        return TestRun.objects.create(
            tenant=tenant, workspace=workspace, name=f"RUN {uid}", uid=uid
        )
    if model_name == "Adr":
        return Adr.objects.create(
            tenant=tenant, workspace_id=workspace.id, title=f"ADR {uid}", uid=uid
        )
    if model_name == "Risk":
        return Risk.objects.create(
            tenant=tenant,
            workspace_id=workspace.id,
            title=f"RISK {uid}",
            probability="low",
            impact="low",
            uid=uid,
        )
    if model_name == "Issue":
        return Issue.objects.create(
            tenant=tenant, workspace_id=workspace.id, title=f"ISSUE {uid}", uid=uid
        )
    raise AssertionError(f"unknown model {model_name}")


_MODELS = ("TestCase", "ArchitectureElement", "StakeholderNeed", "TestRun", "Adr", "Risk", "Issue")

#: The full per-workspace ``uid`` invariant: 0055 owns the Requirement index,
#: ``_CONSTRAINTS`` owns the seven below.
_UID_INDEXES = frozenset(
    {
        "uq_requirement_workspace_uid",
        "uq_testcase_workspace_uid",
        "uq_architecture_element_workspace_uid",
        "uq_stakeholder_need_workspace_uid",
        "uq_test_run_workspace_uid",
        "uq_adr_workspace_uid",
        "uq_risk_workspace_uid",
        "uq_issue_workspace_uid",
    }
)

#: The subset the ``0117``/``0118`` pair owns — everything but the 0055 index.
_CONSTRAINT_INDEXES = _UID_INDEXES - {"uq_requirement_workspace_uid"}


def _uid_index_names() -> set[str]:
    """Partial unique indexes backing the per-workspace ``uid`` invariant.

    Read from ``pg_indexes``, not ``pg_constraint``: a ``UniqueConstraint``
    with a ``condition`` is a unique *index* (see the module docstring).
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE indexname LIKE 'uq_%_workspace_uid'"
        )
        return {row[0] for row in cursor.fetchall()}


def _assert_reversed_by_name() -> None:
    """The reverse must drop exactly 0118's indexes and keep 0055's."""
    after_reverse = _uid_index_names()
    assert "uq_requirement_workspace_uid" in after_reverse, (
        "Reversing 0118 must leave the 0055-owned index untouched"
    )
    leftover = after_reverse & _CONSTRAINT_INDEXES
    assert not leftover, (
        f"Reverse of {_CONSTRAINTS} left indexes behind: {sorted(leftover)}"
    )


@pytest.mark.parametrize("model_name", _MODELS)
def test_duplicate_uid_same_workspace_rejected(model_name):
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        _build(tenant, workspace, model_name, "DUP-001")

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                _build(tenant, workspace, model_name, "DUP-001")


@pytest.mark.parametrize("model_name", _MODELS)
def test_same_uid_other_workspace_allowed(model_name):
    """ReqIF semantics: the same identifier may exist in another workspace."""
    with active_tenant() as tenant:
        first = make_workspace(tenant, name="WS A")
        second = make_workspace(tenant, name="WS B")

        _build(tenant, first, model_name, "SAME-001")
        _build(tenant, second, model_name, "SAME-001")

        if model_name in {"Adr", "Risk", "Issue"}:
            model = {"Adr": Adr, "Risk": Risk, "Issue": Issue}[model_name]
            workspace_ids = set(
                model.objects.filter(uid="SAME-001").values_list(
                    "workspace_id", flat=True
                )
            )
        else:
            model = {
                "TestCase": TestCase,
                "ArchitectureElement": ArchitectureElement,
                "StakeholderNeed": StakeholderNeed,
                "TestRun": TestRun,
            }[model_name]
            workspace_ids = set(
                model.objects.filter(uid="SAME-001").values_list(
                    "workspace_id", flat=True
                )
            )
        assert workspace_ids == {first.id, second.id}


@pytest.mark.parametrize("model_name", _MODELS)
def test_blank_uid_not_constrained(model_name):
    """Two blank uids are allowed — the constraint is partial."""
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)

        _build(tenant, workspace, model_name, "")
        _build(tenant, workspace, model_name, "")


@pytest.mark.django_db(transaction=True)
def test_migration_dedupes_existing_collisions(transactional_db):
    """Pre-existing duplicates are renamed by the migration, never deleted."""
    tenant_name = f"G1.3 dedupe {uuid.uuid4().hex[:8]}"
    from persistence.models import Tenant

    tenant = Tenant.objects.create(name=tenant_name, slug=tenant_name, is_active=True)
    from persistence.middleware import clear_request_tenant, set_request_tenant

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="Dedupe WS")

        # Step 1: move the persistence app back to the state *before* the
        # constraints, so duplicates can exist at all.
        executor = MigrationExecutor(connection)
        executor.migrate([("persistence", _PREREQUISITE)])
        old_apps = executor.loader.project_state(
            [("persistence", _PREREQUISITE)]
        ).apps
        OldArtifact = old_apps.get_model("persistence", "Artifact")
        OldTestCase = old_apps.get_model("persistence", "TestCase")

        artifact_id = uuid.uuid4()
        OldArtifact.objects.create(
            id=artifact_id,
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            artifact_type="TestCase",
        )
        OldTestCase.objects.create(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            artifact_id=artifact_id,
            workspace_id=workspace.id,
            title="Oldest duplicate",
            uid="TC-001",
            version=1,
        )
        second_artifact = uuid.uuid4()
        OldArtifact.objects.create(
            id=second_artifact,
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            artifact_type="TestCase",
        )
        OldTestCase.objects.create(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            artifact_id=second_artifact,
            workspace_id=workspace.id,
            title="Later duplicate",
            uid="TC-001",
            version=1,
        )

        # W0-02: a duplicate whose uid already fills the whole column. The old
        # ``f"{uid} ({n})"[:64]`` form truncated the suffix back off, produced
        # the base uid again (always present in ``taken``) and never left the
        # ``while True`` loop. Two more artifacts carry that case.
        full_length_uid = "X" * 64
        expected_full_length_rename = "X" * 60 + " (2)"
        for title in ("Full-length oldest", "Full-length later"):
            full_artifact = uuid.uuid4()
            OldArtifact.objects.create(
                id=full_artifact,
                tenant_id=tenant.id,
                workspace_id=workspace.id,
                artifact_type="TestCase",
            )
            OldTestCase.objects.create(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                artifact_id=full_artifact,
                workspace_id=workspace.id,
                title=title,
                uid=full_length_uid,
                version=1,
            )

        # Step 2: forward again — the dedupe step must rename the later rows.
        executor = MigrationExecutor(connection)
        executor.migrate([("persistence", _CONSTRAINTS)])

        uids = sorted(
            TestCase.objects.filter(workspace_id=workspace.id).values_list(
                "uid", flat=True
            )
        )
        assert uids == sorted(
            ["TC-001", "TC-001 (2)", full_length_uid, expected_full_length_rename]
        )
        assert all(len(uid) <= 64 for uid in uids)
    finally:
        clear_request_tenant()


@pytest.mark.django_db(transaction=True)
def test_migration_reverse_roundtrip(transactional_db):
    """``0117`` → ``0118`` → ``0117`` → ``0118`` is clean by name.

    The session starts at the leaf, so the first step is the reverse probe:
    0118's seven indexes must disappear while 0055's survives. The final
    forward pass must restore all eight.
    """
    executor = MigrationExecutor(connection)
    executor.migrate([("persistence", _PREREQUISITE)])
    _assert_reversed_by_name()

    executor = MigrationExecutor(connection)
    executor.migrate([("persistence", _CONSTRAINTS)])

    executor = MigrationExecutor(connection)
    executor.migrate([("persistence", _PREREQUISITE)])
    _assert_reversed_by_name()

    executor = MigrationExecutor(connection)
    executor.migrate([("persistence", _CONSTRAINTS)])
    assert _UID_INDEXES <= _uid_index_names()


def _dedupe_module():
    """Import the 0118 migration module (its name starts with a digit)."""
    import importlib

    return importlib.import_module(
        "persistence.migrations.0118_uid_workspace_unique_constraints"
    )


def test_next_free_uid_keeps_the_suffix_at_max_length():
    """W0-02: the suffix is reserved *before* truncation, so it always shows."""
    module = _dedupe_module()
    base = "A" * 64

    candidate = module._next_free_uid(base, {base})

    assert candidate == "A" * 60 + " (2)"
    assert candidate != base
    assert len(candidate) <= module.MAX_UID_LENGTH


def test_next_free_uid_skips_taken_candidates():
    """The candidate search still honours the incremental ``taken`` set."""
    module = _dedupe_module()
    base = "A" * 64
    taken = {base, "A" * 60 + " (2)", "A" * 60 + " (3)"}

    assert module._next_free_uid(base, taken) == "A" * 60 + " (4)"


# ---------------------------------------------------------------------------
# RLS guard on the dedupe scan (PR #1482)
# ---------------------------------------------------------------------------
#
# ``pl_testcase`` (and three of its six siblings) carries ENABLE + FORCE ROW
# LEVEL SECURITY, so the dedupe's ``SELECT`` is filtered by the tenant policy.
# Without the guard the scan matched zero rows on any role that cannot bypass
# RLS, the rename loop did nothing, and the ``ADD CONSTRAINT`` that follows
# aborted on the untouched duplicate. The two tests below pin both halves:
# the guard really runs before the read, and a role that cannot bypass RLS can
# no longer turn the scan into a silent no-op.


def _historical_apps():
    """The model registry a ``RunPython`` receives — plain, unscoped managers."""
    return MigrationExecutor(connection).loader.project_state().apps


def _set_app_role() -> None:
    """Become the least-privilege application role (migration 0048).

    Same ``SET ROLE`` pattern the project already uses to reproduce production
    RLS conditions — ``persistence/tests/test_migrations_and_indexes.py::
    test_rls_blocks_raw_query_without_set_local`` and
    ``admin_ops/tests/test_banner_rls.py``. The test connection authenticates
    as the superuser, which bypasses RLS unconditionally.
    """
    from persistence.db_roles import APP_DB_ROLE

    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')


def _reset_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")


@_pg_only
@pytest.mark.django_db(transaction=True)
def test_dedupe_scan_fails_loudly_under_app_role(transactional_db):
    """A non-BYPASSRLS role must never get a silent 0-row dedupe scan.

    ``reqogniloom_app`` is NOSUPERUSER, owns none of the tables and is subject
    to FORCE RLS, so its ``SELECT`` on ``pl_testcase`` returns nothing while
    ``app.current_tenant`` is unarmed. Before the guard the dedupe simply
    renamed nothing and reported success; with it, PostgreSQL refuses the read
    outright ("query would be affected by row-level security policy") and the
    migration stops instead of leaving duplicates behind for ``ADD CONSTRAINT``
    to trip over. This test is red without the guard: ``pytest.raises`` gets no
    exception because ``_dedupe_uid_collisions`` completes on zero rows.
    """
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        _build(tenant, workspace, "TestCase", "RLS-DEDUPE-001")
        workspace_id = workspace.id

    # Written by the superuser connection, so the row really exists ...
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pl_testcase WHERE workspace_id = %s",
            [workspace_id],
        )
        assert cursor.fetchone()[0] == 1, "fixture row was not created"

    # ... and is invisible to the application role: FORCE RLS, no
    # ``app.current_tenant`` armed (``active_tenant`` resets it on exit).
    _set_app_role()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pl_testcase WHERE workspace_id = %s",
                [workspace_id],
            )
            assert cursor.fetchone()[0] == 0, (
                "the application role saw the row, so this test is not "
                "exercising RLS at all"
            )
    finally:
        _reset_role()

    module = _dedupe_module()
    apps = _historical_apps()
    try:
        with pytest.raises(DatabaseError, match="row-level security"):
            with transaction.atomic(), connection.schema_editor() as schema_editor:
                _set_app_role()
                module._dedupe_uid_collisions(apps, schema_editor)
    finally:
        _reset_role()


@_pg_only
@pytest.mark.django_db(transaction=True)
def test_dedupe_scan_disables_row_security_before_reading(transactional_db):
    """The ``SET LOCAL`` must reach the same connection *before* the scan.

    This is the positive half of the guard: the statement 0117 established
    (``SET LOCAL row_security = off``, scoped to the atomic migration block) is
    issued on the dedupe's own cursor, and every duplicate ``SELECT`` follows
    it. Red without the guard, because no such statement is executed at all.
    """
    module = _dedupe_module()
    apps = _historical_apps()

    with transaction.atomic(), connection.schema_editor() as schema_editor:
        with CaptureQueriesContext(connection) as captured:
            module._dedupe_uid_collisions(apps, schema_editor)

    statements = [query["sql"] for query in captured.captured_queries]
    guard = [
        index
        for index, sql in enumerate(statements)
        if "SET LOCAL row_security = off" in sql
    ]
    assert guard, (
        "the dedupe scan ran without SET LOCAL row_security = off; on a "
        f"non-BYPASSRLS connection it would silently see zero rows. "
        f"Captured statements: {statements}"
    )

    reads = [
        index
        for index, sql in enumerate(statements)
        # ``.iterator()`` streams through a server-side cursor, so the logged
        # statement is ``DECLARE … FOR SELECT`` rather than a bare ``SELECT``.
        if "SELECT" in sql.upper() and "pl_testcase" in sql
    ]
    assert reads, f"the dedupe never read pl_testcase: {statements}"
    assert guard[0] < reads[0], (
        "row security was disabled only after the duplicate scan had already "
        f"run. Captured statements: {statements}"
    )
