"""Tests for the Phase 4 PromptTemplate model shape (REQ-L2-PT-001).

Covers the new named, versioned, workspace-overridable model: multiple
templates per tenant (open-ended ``name``), tenant-global vs. per-workspace
override scoping (``workspace_id``), and the "at most one active row per
(tenant, workspace_id, name)" invariant, enforced at the application level in
``PromptTemplate.save()`` (see backend/persistence/models.py docstring for the
DB-level-vs-application-level decision).

Tests activate the tenant context via ``active_tenant`` (persistence/tests/
conftest.py) before touching ``PromptTemplate.objects`` because it is a
``TenantScopedModel`` whose default manager requires an active
``TenantContext`` (ARCH-L1-011), same convention as
``persistence/tests/test_entity_schema.py``.
"""
from __future__ import annotations

import threading

import pytest
from django.db import IntegrityError, connection

from persistence.tenancy import TenantContext
from persistence.tests.conftest import active_tenant


@pytest.mark.django_db
def test_create_tenant_global_template(tenant):
    from persistence.models import PromptTemplate

    with active_tenant(tenant):
        tpl = PromptTemplate.objects.create(
            tenant=tenant, name="need_to_sysreq", content="Derive from {need_title}",
            version=1, is_active=True, workspace_id=None,
        )
    assert tpl.workspace_id is None
    assert tpl.is_active is True


@pytest.mark.django_db
def test_only_one_active_version_per_name_and_scope(tenant):
    from persistence.models import PromptTemplate

    with active_tenant(tenant):
        PromptTemplate.objects.create(
            tenant=tenant, name="need_to_sysreq", content="v1", version=1, is_active=True
        )
        # Application-level enforcement (see PromptTemplate.save()): a second
        # active=True row for the same (tenant, workspace_id=None, name) scope
        # raises IntegrityError, mirroring the codebase's existing idiom of
        # raising/catching IntegrityError around uniqueness violations (e.g.
        # CustomFieldDefinitionService).
        with pytest.raises(IntegrityError):
            PromptTemplate.objects.create(
                tenant=tenant, name="need_to_sysreq", content="v2", version=2, is_active=True
            )


@pytest.mark.django_db
def test_inactive_version_can_coexist_with_active_version(tenant):
    from persistence.models import PromptTemplate

    with active_tenant(tenant):
        PromptTemplate.objects.create(
            tenant=tenant, name="need_to_sysreq", content="v1", version=1, is_active=True
        )
        # A second, inactive version in the same scope is allowed - only
        # is_active=True rows are constrained to at most one per scope.
        inactive = PromptTemplate.objects.create(
            tenant=tenant, name="need_to_sysreq", content="v2 draft", version=2, is_active=False
        )
        assert inactive.pk is not None
        assert PromptTemplate.objects.filter(
            tenant=tenant, name="need_to_sysreq", workspace_id=None
        ).count() == 2


@pytest.mark.django_db
def test_workspace_override_and_tenant_global_coexist(tenant, workspace):
    from persistence.models import PromptTemplate

    with active_tenant(tenant):
        PromptTemplate.objects.create(
            tenant=tenant, name="need_to_sysreq", content="global v1", version=1,
            is_active=True, workspace_id=None,
        )
        PromptTemplate.objects.create(
            tenant=tenant, name="need_to_sysreq", content="workspace override v1", version=1,
            is_active=True, workspace_id=workspace.id,
        )
        assert PromptTemplate.objects.filter(
            tenant=tenant, name="need_to_sysreq", workspace_id=None, is_active=True
        ).count() == 1
        assert PromptTemplate.objects.filter(
            tenant=tenant, name="need_to_sysreq", workspace_id=workspace.id, is_active=True
        ).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_active_template_creation_only_one_succeeds(tenant):
    """Two overlapping writers targeting the same scope must not both win.

    Regression test for the TOCTOU race in ``PromptTemplate.save()``: a
    plain ``exists()`` check followed by an ``INSERT`` lets two concurrent
    processes both observe "no conflict" before either commits, producing
    two active rows for the same ``(tenant, workspace_id, name)`` scope.

    Uses real OS threads (each gets its own DB connection and, since
    ``TenantContext`` is thread-local — see ``persistence/tenancy.py`` — its
    own tenant context) racing to create the *same* active row via
    ``threading.Barrier`` to start both writers as close together as
    possible. With the ``select_for_update()``-based fix in ``save()``, the
    second writer blocks on the DB lock until the first commits, then loses
    the conflict check deterministically — so exactly one of the two must
    succeed and the other must raise ``IntegrityError``, regardless of
    scheduling order. ``transaction=True`` (``TransactionTestCase``
    semantics) is required: the default ``django_db`` fixture wraps a test
    in one outer transaction, which would make the second connection unable
    to see the first connection's row at all.
    """
    from persistence.models import PromptTemplate

    outcomes: dict[str, str] = {}
    start_barrier = threading.Barrier(2)

    def _worker(key: str, content: str) -> None:
        try:
            start_barrier.wait(timeout=5)
            with active_tenant(tenant):
                PromptTemplate.objects.create(
                    tenant=tenant,
                    name="need_to_sysreq",
                    content=content,
                    version=1,
                    is_active=True,
                    workspace_id=None,
                )
            outcomes[key] = "ok"
        except IntegrityError:
            outcomes[key] = "conflict"
        except Exception as exc:  # pragma: no cover - diagnostic aid only
            outcomes[key] = f"error:{exc!r}"
        finally:
            TenantContext.clear_tenant()
            connection.close()

    t1 = threading.Thread(target=_worker, args=("writer_1", "v1 from writer 1"))
    t2 = threading.Thread(target=_worker, args=("writer_2", "v1 from writer 2"))
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert not t1.is_alive() and not t2.is_alive(), "worker thread did not finish in time"
    assert set(outcomes) == {"writer_1", "writer_2"}
    assert list(outcomes.values()).count("ok") == 1, outcomes
    assert list(outcomes.values()).count("conflict") == 1, outcomes

    with active_tenant(tenant):
        assert PromptTemplate.objects.filter(
            tenant=tenant, name="need_to_sysreq", workspace_id=None, is_active=True
        ).count() == 1
