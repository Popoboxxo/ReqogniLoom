"""
IcdParameterService — Tests (COMP-ICD-001).

leaf_id: COMP-ICD-001
req_id:  REQ-L2-ICD-002

Coverage:
  create_parameter: happy path, blank-name rejection, unknown Icd
  update_parameter: partial update, blank-name rejection, not-found
  delete_parameter: happy path, not-found
  list_parameters: ordering, tenant isolation

Architecture: docs/se/L1/Gesamtsystem/L2/IcdManagementSystem/L2_IcdManagementSystem_Architecture.md
"""
from __future__ import annotations

import contextlib
import uuid
from decimal import Decimal
from typing import Iterator
from unittest.mock import patch

import pytest

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def active_tenant(tenant: "Tenant") -> Iterator[None]:
    """Activate tenant context within block (app-layer manager)."""
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear_tenant_context() -> Iterator[None]:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _mock_resolve_arch_artifact_id() -> Iterator[None]:
    with patch("icd.icd_manager.IcdManager._resolve_arch_artifact_id"):
        yield


@pytest.fixture
def tenant_a(db) -> Tenant:
    return Tenant.objects.create(name="Tenant A", slug="ta-icd-param")


@pytest.fixture
def tenant_b(db) -> Tenant:
    return Tenant.objects.create(name="Tenant B", slug="tb-icd-param")


@pytest.fixture
def workspace_id(tenant_a: Tenant) -> uuid.UUID:
    """A real Workspace row's id.

    Datenmodell-Konsolidierung Phase 3 (Task 19): ``create_icd`` now calls
    ``ensure_artifact``, which inserts a ``persistence.Artifact`` row with a
    real (non-nullable) FK to ``Workspace`` — a bare random UUID here would
    violate that FK (only caught at the deferred constraint check on test
    teardown, not at insert time). Which tenant owns the row does not matter
    for this fixture's purpose: it exists purely to satisfy the FK.
    """
    return Workspace.unscoped.create(tenant=tenant_a, name="ws-icd-param").id


@pytest.fixture
def src_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def tgt_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_create_dto(tenant, workspace_id, src, tgt, **kwargs):
    """Build an IcdCreateDTO with sensible defaults (mirrors test_icd.py)."""
    from icd.icd_manager import IcdCreateDTO

    defaults = dict(
        tenant_id=tenant.id,
        workspace_id=workspace_id,
        name="Test ICD",
        source_element_id=src,
        target_element_id=tgt,
        direction="unidirectional",
        interface_type="REST",
        semantic_description="A test interface.",
        preconditions=["auth_required"],
        postconditions=["response_200"],
        invariants=["latency_under_500ms"],
    )
    defaults.update(kwargs)
    return IcdCreateDTO(**defaults)


@pytest.fixture
def icd_id(tenant_a, workspace_id, src_id, tgt_id):
    """Create an ICD (revision 1) for tenant_a and return its id."""
    from icd.services import create_icd

    with active_tenant(tenant_a):
        dto = _make_create_dto(tenant_a, workspace_id, src_id, tgt_id)
        with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
            result = create_icd(dto)
    return result.icd.id


# ===========================================================================
# create_parameter
# ===========================================================================

@pytest.mark.django_db
class TestCreateParameter:
    """REQ-L2-ICD-002: create structured parameter on an Icd."""

    def test_create_parameter_persists_all_fields(self, tenant_a, icd_id):
        from icd.icd_parameter_service import get_parameter_service

        svc = get_parameter_service()
        param = svc.create_parameter(
            icd_id=icd_id,
            name="Altitude",
            tenant_id=tenant_a.id,
            unit="m",
            data_type="float",
            direction="output",
            description="Altitude above ground level.",
            min_value=Decimal("0"),
            max_value=Decimal("15000"),
            nominal_value="1000",
            tolerance="±5%",
            ordering=2,
        )

        assert param.id is not None
        assert param.icd_id == icd_id
        assert param.name == "Altitude"
        assert param.unit == "m"
        assert param.data_type == "float"
        assert param.direction == "output"
        assert param.description == "Altitude above ground level."
        assert param.min_value == Decimal("0")
        assert param.max_value == Decimal("15000")
        assert param.nominal_value == "1000"
        assert param.tolerance == "±5%"
        assert param.ordering == 2

    def test_create_parameter_defaults(self, tenant_a, icd_id):
        from icd.icd_parameter_service import get_parameter_service

        svc = get_parameter_service()
        param = svc.create_parameter(
            icd_id=icd_id,
            name="Flag",
            tenant_id=tenant_a.id,
        )

        assert param.unit == ""
        assert param.data_type == "other"
        assert param.direction == "input"
        assert param.min_value is None
        assert param.max_value is None
        assert param.ordering == 0

    def test_blank_name_raises(self, tenant_a, icd_id):
        from icd.icd_parameter_service import get_parameter_service

        svc = get_parameter_service()
        with pytest.raises(ValueError):
            svc.create_parameter(
                icd_id=icd_id,
                name="   ",
                tenant_id=tenant_a.id,
            )

    def test_unknown_icd_raises(self, tenant_a):
        from icd.models import Icd
        from icd.icd_parameter_service import get_parameter_service

        svc = get_parameter_service()
        with pytest.raises(Icd.DoesNotExist):
            svc.create_parameter(
                icd_id=uuid.uuid4(),
                name="Ghost",
                tenant_id=tenant_a.id,
            )

    def test_wrong_tenant_cannot_create_on_others_icd(self, tenant_a, tenant_b, icd_id):
        """A version created for tenant_a must not be reachable via tenant_b's id."""
        from icd.models import Icd
        from icd.icd_parameter_service import get_parameter_service

        svc = get_parameter_service()
        with pytest.raises(Icd.DoesNotExist):
            svc.create_parameter(
                icd_id=icd_id,
                name="Trespasser",
                tenant_id=tenant_b.id,
            )


# ===========================================================================
# update_parameter
# ===========================================================================

@pytest.mark.django_db
class TestUpdateParameter:
    """REQ-L2-ICD-002: partial in-place update of an IcdParameter."""

    def test_update_changes_only_given_fields(self, tenant_a, icd_id):
        from icd.icd_parameter_service import get_parameter_service

        svc = get_parameter_service()
        param = svc.create_parameter(
            icd_id=icd_id,
            name="Speed",
            tenant_id=tenant_a.id,
            unit="m/s",
            data_type="float",
        )

        updated = svc.update_parameter(
            parameter_id=param.id,
            tenant_id=tenant_a.id,
            unit="km/h",
        )

        assert updated.unit == "km/h"
        assert updated.name == "Speed"
        assert updated.data_type == "float"

    def test_update_blank_name_raises(self, tenant_a, icd_id):
        from icd.icd_parameter_service import get_parameter_service

        svc = get_parameter_service()
        param = svc.create_parameter(
            icd_id=icd_id,
            name="Speed",
            tenant_id=tenant_a.id,
        )

        with pytest.raises(ValueError):
            svc.update_parameter(parameter_id=param.id, tenant_id=tenant_a.id, name="   ")

    def test_update_unknown_parameter_raises(self, tenant_a):
        from icd.icd_parameter_service import get_parameter_service, IcdParameterNotFoundError

        svc = get_parameter_service()
        with pytest.raises(IcdParameterNotFoundError):
            svc.update_parameter(parameter_id=uuid.uuid4(), tenant_id=tenant_a.id, name="X")

    def test_update_wrong_tenant_raises(self, tenant_a, tenant_b, icd_id):
        from icd.icd_parameter_service import get_parameter_service, IcdParameterNotFoundError

        svc = get_parameter_service()
        param = svc.create_parameter(
            icd_id=icd_id,
            name="Speed",
            tenant_id=tenant_a.id,
        )

        with pytest.raises(IcdParameterNotFoundError):
            svc.update_parameter(parameter_id=param.id, tenant_id=tenant_b.id, name="Hacked")


# ===========================================================================
# delete_parameter
# ===========================================================================

@pytest.mark.django_db
class TestDeleteParameter:
    """REQ-L2-ICD-002: hard delete of an IcdParameter."""

    def test_delete_removes_parameter(self, tenant_a, icd_id):
        from icd.models import IcdParameter
        from icd.icd_parameter_service import get_parameter_service

        svc = get_parameter_service()
        param = svc.create_parameter(
            icd_id=icd_id,
            name="ToDelete",
            tenant_id=tenant_a.id,
        )

        svc.delete_parameter(parameter_id=param.id, tenant_id=tenant_a.id)

        assert not IcdParameter.unscoped.filter(id=param.id).exists()

    def test_delete_unknown_parameter_raises(self, tenant_a):
        from icd.icd_parameter_service import get_parameter_service, IcdParameterNotFoundError

        svc = get_parameter_service()
        with pytest.raises(IcdParameterNotFoundError):
            svc.delete_parameter(parameter_id=uuid.uuid4(), tenant_id=tenant_a.id)

    def test_delete_wrong_tenant_raises(self, tenant_a, tenant_b, icd_id):
        from icd.icd_parameter_service import get_parameter_service, IcdParameterNotFoundError

        svc = get_parameter_service()
        param = svc.create_parameter(
            icd_id=icd_id,
            name="Protected",
            tenant_id=tenant_a.id,
        )

        with pytest.raises(IcdParameterNotFoundError):
            svc.delete_parameter(parameter_id=param.id, tenant_id=tenant_b.id)


# ===========================================================================
# list_parameters
# ===========================================================================

@pytest.mark.django_db
class TestListParameters:
    """REQ-L2-ICD-002: list + ordering + tenant isolation."""

    def test_list_orders_by_ordering_then_name(self, tenant_a, icd_id):
        from icd.icd_parameter_service import get_parameter_service

        svc = get_parameter_service()
        svc.create_parameter(
            icd_id=icd_id, name="Zeta", tenant_id=tenant_a.id, ordering=1
        )
        svc.create_parameter(
            icd_id=icd_id, name="Alpha", tenant_id=tenant_a.id, ordering=1
        )
        svc.create_parameter(
            icd_id=icd_id, name="Beta", tenant_id=tenant_a.id, ordering=0
        )

        names = list(
            svc.list_parameters(icd_id=icd_id, tenant_id=tenant_a.id).values_list(
                "name", flat=True
            )
        )

        assert names == ["Beta", "Alpha", "Zeta"]

    def test_list_is_tenant_scoped(self, tenant_a, tenant_b, icd_id):
        from icd.icd_parameter_service import get_parameter_service

        svc = get_parameter_service()
        svc.create_parameter(
            icd_id=icd_id, name="OnlyTenantA", tenant_id=tenant_a.id
        )

        result = svc.list_parameters(icd_id=icd_id, tenant_id=tenant_b.id)

        assert list(result) == []

    def test_list_empty_for_unknown_version(self, tenant_a):
        from icd.icd_parameter_service import get_parameter_service

        svc = get_parameter_service()
        result = svc.list_parameters(icd_id=uuid.uuid4(), tenant_id=tenant_a.id)

        assert list(result) == []
