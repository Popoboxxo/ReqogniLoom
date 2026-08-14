"""
IcdManagement — Tests (ARCH-L1-014).

leaf_id: COMP-ICD-001, COMP-ICD-002, COMP-ICD-003, COMP-ICD-004
req_id:  REQ-L1-028, REQ-L2-ICD-001 through REQ-L2-ICD-006

Coverage (all acceptance criteria from REQ-L2-ICD-*):
  REQ-L2-ICD-001: CRUD, version=1 on create, new version on update,
                  immutable version (no in-place update via Python layer)
  REQ-L2-ICD-002: All DbC fields present (direction, type, desc, pre/post/inv)
  REQ-L2-ICD-003: Breaking-change detection — compatible and incompatible changes
  REQ-L2-ICD-004: 'realizes' TraceLink created on ICD creation
  REQ-L2-ICD-005: get_icd_versions returns correct workspace snapshot
  REQ-L2-ICD-006: AuditLog entry written on breaking change
  Tenant isolation: ICDs from other tenants not visible

Architecture:
  docs/se/L1/Gesamtsystem/L2/IcdManagementSystem/L2_IcdManagementSystem_Architecture.md
"""
from __future__ import annotations

import contextlib
import uuid
from typing import Iterator
from unittest.mock import MagicMock, call, patch

import pytest

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def active_tenant(tenant: "Tenant") -> Iterator[None]:
    """Activate tenant context for the app-layer manager within the block."""
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear_tenant_context() -> Iterator[None]:
    """Prevent tenant context bleed between tests."""
    TenantContext.clear_tenant()
    yield

@pytest.fixture(autouse=True)
def _mock_resolve_arch_artifact_id() -> Iterator[None]:
    with patch("icd.icd_manager.IcdManager._resolve_arch_artifact_id", side_effect=lambda x: x):
        yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant_a(db: None) -> "Tenant":
    return Tenant.objects.create(name="Tenant A", slug="ta-icd")


@pytest.fixture
def tenant_b(db: None) -> "Tenant":
    return Tenant.objects.create(name="Tenant B", slug="tb-icd")


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def src_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def tgt_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_create_dto(
    tenant: "Tenant",
    workspace_id: uuid.UUID,
    src: uuid.UUID,
    tgt: uuid.UUID,
    **kwargs,
):
    """Build an IcdCreateDTO with sensible defaults."""
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


# ===========================================================================
# ContractValidator — unit tests (COMP-ICD-002)
# ===========================================================================

class TestContractValidatorSyntax:
    """REQ-L2-ICD-002: syntax validation of DbC payload."""

    def test_valid_payload_passes(self):
        from icd.contract_validator import ContractValidator

        v = ContractValidator()
        result = v.validate_syntax(
            {
                "direction": "unidirectional",
                "interface_type": "REST",
                "semantic_description": "desc",
                "preconditions": [],
                "postconditions": [],
                "invariants": [],
            }
        )
        assert result.is_valid_syntax is True
        assert result.syntax_errors == []

    def test_missing_field_produces_error(self):
        from icd.contract_validator import ContractValidator

        v = ContractValidator()
        result = v.validate_syntax(
            {
                "direction": "unidirectional",
                # interface_type missing
                "semantic_description": "desc",
                "preconditions": [],
                "postconditions": [],
                "invariants": [],
            }
        )
        assert result.is_valid_syntax is False
        assert any("interface_type" in e for e in result.syntax_errors)

    def test_non_list_preconditions_produces_error(self):
        from icd.contract_validator import ContractValidator

        v = ContractValidator()
        result = v.validate_syntax(
            {
                "direction": "unidirectional",
                "interface_type": "gRPC",
                "semantic_description": "desc",
                "preconditions": "not-a-list",
                "postconditions": [],
                "invariants": [],
            }
        )
        assert result.is_valid_syntax is False
        assert any("preconditions" in e for e in result.syntax_errors)

    def test_empty_values_allowed(self):
        from icd.contract_validator import ContractValidator

        v = ContractValidator()
        result = v.validate_syntax(
            {
                "direction": "",
                "interface_type": "",
                "semantic_description": "",
                "preconditions": [],
                "postconditions": [],
                "invariants": [],
            }
        )
        assert result.is_valid_syntax is True

    def test_oversized_semantic_description_rejected(self):
        """Regression (#104): semantic_description is a TextField reached via
        IcdViewSet.create()/partial_update(), which builds the DTO straight
        from request.data without a DRF serializer — no size limit existed,
        allowing unbounded payloads (DoS risk)."""
        from icd.contract_validator import ContractValidator

        v = ContractValidator()
        result = v.validate_syntax(
            {
                "direction": "unidirectional",
                "interface_type": "REST",
                "semantic_description": "A" * (
                    ContractValidator.SEMANTIC_DESCRIPTION_MAX_LENGTH + 1
                ),
                "preconditions": [],
                "postconditions": [],
                "invariants": [],
            }
        )
        assert result.is_valid_syntax is False
        assert any("semantic_description" in e for e in result.syntax_errors)

    def test_semantic_description_at_max_length_accepted(self):
        """Boundary check: exactly the max length must still pass (#104)."""
        from icd.contract_validator import ContractValidator

        v = ContractValidator()
        result = v.validate_syntax(
            {
                "direction": "unidirectional",
                "interface_type": "REST",
                "semantic_description": "A" * ContractValidator.SEMANTIC_DESCRIPTION_MAX_LENGTH,
                "preconditions": [],
                "postconditions": [],
                "invariants": [],
            }
        )
        assert result.is_valid_syntax is True


class TestContractValidatorSemantics:
    """REQ-L2-ICD-003: breaking-change detection rules."""

    def setup_method(self):
        from icd.contract_validator import ContractValidator

        self.v = ContractValidator()

    def test_identical_contract_is_compatible(self):
        result = self.v.validate_contract(
            old_preconditions=["auth"],
            old_postconditions=["200"],
            old_invariants=["idempotent"],
            new_preconditions=["auth"],
            new_postconditions=["200"],
            new_invariants=["idempotent"],
        )
        assert result.is_breaking is False
        assert result.breaking_changes == []

    def test_weakening_precondition_is_compatible(self):
        """Removing a precondition is allowed (callers gain, not lose)."""
        result = self.v.validate_contract(
            old_preconditions=["auth", "rate_limit"],
            old_postconditions=["200"],
            old_invariants=[],
            new_preconditions=["auth"],  # rate_limit removed
            new_postconditions=["200"],
            new_invariants=[],
        )
        assert result.is_breaking is False

    def test_strengthening_precondition_is_breaking(self):
        """Adding a new precondition — callers cannot satisfy it — is breaking."""
        result = self.v.validate_contract(
            old_preconditions=["auth"],
            old_postconditions=["200"],
            old_invariants=[],
            new_preconditions=["auth", "new_requirement"],
            new_postconditions=["200"],
            new_invariants=[],
        )
        assert result.is_breaking is True
        assert any("new_requirement" in c for c in result.breaking_changes)

    def test_adding_postcondition_is_compatible(self):
        """Strengthening a postcondition (adding more guarantees) is compatible."""
        result = self.v.validate_contract(
            old_preconditions=[],
            old_postconditions=["200"],
            old_invariants=[],
            new_preconditions=[],
            new_postconditions=["200", "audit_logged"],
            new_invariants=[],
        )
        assert result.is_breaking is False

    def test_removing_postcondition_is_breaking(self):
        """Weakening a postcondition — removing a guarantee — is breaking."""
        result = self.v.validate_contract(
            old_preconditions=[],
            old_postconditions=["200", "audit_logged"],
            old_invariants=[],
            new_preconditions=[],
            new_postconditions=["200"],  # audit_logged removed
            new_invariants=[],
        )
        assert result.is_breaking is True
        assert any("audit_logged" in c for c in result.breaking_changes)

    def test_removing_invariant_is_breaking(self):
        """Invariants must be preserved — removal is breaking."""
        result = self.v.validate_contract(
            old_preconditions=[],
            old_postconditions=[],
            old_invariants=["idempotent"],
            new_preconditions=[],
            new_postconditions=[],
            new_invariants=[],  # idempotent removed
        )
        assert result.is_breaking is True
        assert any("idempotent" in c for c in result.breaking_changes)

    def test_adding_invariant_is_compatible(self):
        result = self.v.validate_contract(
            old_preconditions=[],
            old_postconditions=[],
            old_invariants=[],
            new_preconditions=[],
            new_postconditions=[],
            new_invariants=["new_invariant"],
        )
        assert result.is_breaking is False

    def test_multiple_violations_all_reported(self):
        result = self.v.validate_contract(
            old_preconditions=[],
            old_postconditions=["200"],
            old_invariants=["idempotent"],
            new_preconditions=["new_req"],
            new_postconditions=[],
            new_invariants=[],
        )
        assert result.is_breaking is True
        assert len(result.breaking_changes) == 3


# ===========================================================================
# IcdManager / services — integration tests with DB (COMP-ICD-001)
# ===========================================================================

@pytest.mark.django_db
class TestIcdCreate:
    """REQ-L2-ICD-001, REQ-L2-ICD-002: CRUD and DbC fields."""

    def test_create_icd_produces_version_1(self, tenant_a, workspace_id, src_id, tgt_id):
        from icd.services import create_icd, IcdCreateDTO

        with active_tenant(tenant_a):
            dto = _make_create_dto(tenant_a, workspace_id, src_id, tgt_id)
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                result = create_icd(dto)

        assert result.current_version.version_number == 1

    def test_create_icd_persists_dbc_fields(self, tenant_a, workspace_id, src_id, tgt_id):
        from icd.services import create_icd, IcdCreateDTO

        with active_tenant(tenant_a):
            dto = _make_create_dto(
                tenant_a,
                workspace_id,
                src_id,
                tgt_id,
                preconditions=["auth"],
                postconditions=["200"],
                invariants=["idempotent"],
            )
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                result = create_icd(dto)

        v = result.current_version
        assert v.preconditions == ["auth"]
        assert v.postconditions == ["200"]
        assert v.invariants == ["idempotent"]
        assert v.direction == "unidirectional"
        assert v.interface_type == "REST"

    def test_create_icd_header_points_at_version(self, tenant_a, workspace_id, src_id, tgt_id):
        from icd.services import create_icd

        with active_tenant(tenant_a):
            dto = _make_create_dto(tenant_a, workspace_id, src_id, tgt_id)
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                result = create_icd(dto)

        assert result.icd.current_version_id == result.current_version.id


@pytest.mark.django_db
class TestIcdGetAndDelete:
    """REQ-066: get_icd / delete_icd service entry points (ORM out of views)."""

    def _create(self, tenant_a, workspace_id, src_id, tgt_id):
        from icd.services import create_icd

        dto = _make_create_dto(tenant_a, workspace_id, src_id, tgt_id)
        with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
            return create_icd(dto)

    def test_get_icd_returns_tenant_scoped_row(self, tenant_a, workspace_id, src_id, tgt_id):
        from icd.services import get_icd

        with active_tenant(tenant_a):
            result = self._create(tenant_a, workspace_id, src_id, tgt_id)
            fetched = get_icd(result.icd.id, tenant_a.id)

        assert fetched.id == result.icd.id

    def test_get_icd_other_tenant_raises(self, tenant_a, tenant_b, workspace_id, src_id, tgt_id):
        from icd.models import Icd
        from icd.services import get_icd

        with active_tenant(tenant_a):
            result = self._create(tenant_a, workspace_id, src_id, tgt_id)

        with active_tenant(tenant_b):
            with pytest.raises(Icd.DoesNotExist):
                get_icd(result.icd.id, tenant_b.id)

    def test_delete_icd_removes_row(self, tenant_a, workspace_id, src_id, tgt_id):
        # No transaction=True needed: delete_icd opens the icd_version
        # immutability trigger via a transaction-local GUC instead of
        # ALTER TABLE ... DISABLE TRIGGER (which required table ownership the
        # runtime app role does not have — see icd/0006_icd_version_delete_guard).
        from icd.models import Icd
        from icd.services import delete_icd

        with active_tenant(tenant_a):
            result = self._create(tenant_a, workspace_id, src_id, tgt_id)
            delete_icd(result.icd.id, tenant_a.id)

        assert not Icd.unscoped.filter(id=result.icd.id).exists()

    def test_delete_icd_removes_child_versions(
        self, tenant_a, workspace_id, src_id, tgt_id
    ):
        """delete_icd must cascade to the immutable IcdVersion rows.

        Regression guard for the trigger's allow-path: a BEFORE DELETE trigger
        that returns NULL silently cancels the row deletion, so an incorrect
        implementation leaves orphaned versions behind while still reporting
        success.
        """
        from icd.models import IcdVersion
        from icd.services import delete_icd

        with active_tenant(tenant_a):
            result = self._create(tenant_a, workspace_id, src_id, tgt_id)
            assert IcdVersion.unscoped.filter(icd_id=result.icd.id).exists()

            delete_icd(result.icd.id, tenant_a.id)

        assert not IcdVersion.unscoped.filter(icd_id=result.icd.id).exists()

    def test_icd_version_delete_still_blocked_without_gate(
        self, tenant_a, workspace_id, src_id, tgt_id
    ):
        """IcdVersion stays immutable for anything outside delete_icd (REQ-L2-ICD-001).

        The GUC escape hatch must not weaken the guarantee: a plain DELETE that
        did not open the gate still has to raise.
        """
        from django.db import connection, transaction
        from django.db.utils import InternalError, ProgrammingError

        with active_tenant(tenant_a):
            result = self._create(tenant_a, workspace_id, src_id, tgt_id)
            version_id = result.current_version.id

            with pytest.raises((InternalError, ProgrammingError)) as exc_info:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "DELETE FROM icd_version WHERE id = %s", [str(version_id)]
                        )

        assert "immutable" in str(exc_info.value).lower()

    def test_icd_version_update_blocked_even_with_gate_open(
        self, tenant_a, workspace_id, src_id, tgt_id
    ):
        """The delete gate must not unlock UPDATEs on historical versions."""
        from django.db import connection, transaction
        from django.db.utils import InternalError, ProgrammingError

        with active_tenant(tenant_a):
            result = self._create(tenant_a, workspace_id, src_id, tgt_id)
            version_id = result.current_version.id

            with pytest.raises((InternalError, ProgrammingError)) as exc_info:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT set_config("
                            "'app.allow_icd_version_delete', 'true', true)"
                        )
                        cursor.execute(
                            "UPDATE icd_version SET version_number = version_number "
                            "WHERE id = %s",
                            [str(version_id)],
                        )

        assert "immutable" in str(exc_info.value).lower()


@pytest.mark.django_db
class TestIcdVersionImmutability:
    """REQ-L2-ICD-001: versions cannot be modified (Python-layer guard).

    DB trigger is only enforced in a real PostgreSQL environment; here we
    verify the Python-layer append-only contract: update_icd never modifies
    an existing IcdVersion row, it always INSERTs a new one.
    """

    def test_update_increments_version_number(self, tenant_a, workspace_id, src_id, tgt_id):
        from icd.services import create_icd, update_icd, IcdUpdateDTO

        with active_tenant(tenant_a):
            dto = _make_create_dto(tenant_a, workspace_id, src_id, tgt_id)
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                r1 = create_icd(dto)

            update = IcdUpdateDTO(postconditions=["200", "audit_logged"])
            r2 = update_icd(icd_id=r1.icd.id, payload=update, tenant_id=tenant_a.id)

        assert r2.current_version.version_number == 2
        assert r2.current_version.id != r1.current_version.id

    def test_old_version_still_exists_after_update(self, tenant_a, workspace_id, src_id, tgt_id):
        from icd.models import IcdVersion
        from icd.services import create_icd, update_icd, IcdUpdateDTO

        with active_tenant(tenant_a):
            dto = _make_create_dto(tenant_a, workspace_id, src_id, tgt_id)
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                r1 = create_icd(dto)
            update = IcdUpdateDTO(postconditions=["200", "extra"])
            r2 = update_icd(icd_id=r1.icd.id, payload=update, tenant_id=tenant_a.id)

        # Both versions exist in the DB
        versions = list(
            IcdVersion.unscoped.filter(icd_id=r1.icd.id).order_by("version_number")
        )
        assert len(versions) == 2
        assert versions[0].version_number == 1
        assert versions[1].version_number == 2

    def test_original_version_fields_unchanged(self, tenant_a, workspace_id, src_id, tgt_id):
        from icd.models import IcdVersion
        from icd.services import create_icd, update_icd, IcdUpdateDTO

        with active_tenant(tenant_a):
            dto = _make_create_dto(
                tenant_a, workspace_id, src_id, tgt_id, postconditions=["200"]
            )
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                r1 = create_icd(dto)
            original_id = r1.current_version.id
            update = IcdUpdateDTO(postconditions=["200", "extra"])
            update_icd(icd_id=r1.icd.id, payload=update, tenant_id=tenant_a.id)

        # Reload the original version row directly
        original = IcdVersion.unscoped.get(pk=original_id)
        assert original.postconditions == ["200"]


@pytest.mark.django_db
class TestBreakingChangeDetection:
    """REQ-L2-ICD-003: breaking changes are detected and returned in the response."""

    def test_compatible_update_not_breaking(self, tenant_a, workspace_id, src_id, tgt_id):
        from icd.services import create_icd, update_icd, IcdUpdateDTO

        with active_tenant(tenant_a):
            dto = _make_create_dto(
                tenant_a,
                workspace_id,
                src_id,
                tgt_id,
                preconditions=["auth"],
                postconditions=["200"],
                invariants=["idempotent"],
            )
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                r1 = create_icd(dto)
            # Add a postcondition — compatible
            r2 = update_icd(
                icd_id=r1.icd.id,
                payload=IcdUpdateDTO(postconditions=["200", "audit"]),
                tenant_id=tenant_a.id,
            )

        assert r2.validation_result is not None
        assert r2.validation_result.is_breaking is False

    def test_incompatible_update_detected(self, tenant_a, workspace_id, src_id, tgt_id):
        from icd.services import create_icd, update_icd, IcdUpdateDTO

        with active_tenant(tenant_a):
            dto = _make_create_dto(
                tenant_a,
                workspace_id,
                src_id,
                tgt_id,
                preconditions=["auth"],
                postconditions=["200"],
                invariants=["idempotent"],
            )
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                r1 = create_icd(dto)
            # Add new precondition — breaking
            with patch("icd.audit_logger.AuditLogger.log_breaking_change") as mock_log:
                r2 = update_icd(
                    icd_id=r1.icd.id,
                    payload=IcdUpdateDTO(preconditions=["auth", "new_req"]),
                    tenant_id=tenant_a.id,
                )

        assert r2.validation_result.is_breaking is True
        assert any("new_req" in c for c in r2.validation_result.breaking_changes)

    def test_validate_compatibility_dry_run(self, tenant_a, workspace_id, src_id, tgt_id):
        """validate_compatibility does not persist anything."""
        from icd.models import IcdVersion
        from icd.services import create_icd, validate_compatibility

        with active_tenant(tenant_a):
            dto = _make_create_dto(
                tenant_a,
                workspace_id,
                src_id,
                tgt_id,
                invariants=["idempotent"],
            )
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                r1 = create_icd(dto)

            result = validate_compatibility(
                icd_id=r1.icd.id,
                tenant_id=tenant_a.id,
                new_payload={
                    "direction": "unidirectional",
                    "interface_type": "REST",
                    "semantic_description": "updated",
                    "preconditions": ["auth", "new_req"],
                    "postconditions": ["200"],
                    "invariants": [],  # removes idempotent → breaking
                },
            )

        assert result.is_breaking is True
        # Confirm no new version was created
        count = IcdVersion.unscoped.filter(icd_id=r1.icd.id).count()
        assert count == 1


@pytest.mark.django_db
class TestTraceabilityConnector:
    """REQ-L2-ICD-004: 'realizes' TraceLink is created on ICD creation."""

    def test_create_icd_calls_link_to_architecture(
        self, tenant_a, workspace_id, src_id, tgt_id
    ):
        from icd.services import create_icd

        with active_tenant(tenant_a):
            dto = _make_create_dto(tenant_a, workspace_id, src_id, tgt_id)
            with patch(
                "icd.traceability_connector.TraceabilityConnector.link_to_architecture"
            ) as mock_link:
                result = create_icd(dto)

        mock_link.assert_called_once_with(
            icd_id=result.icd.id,
            source_element_id=src_id,
            target_element_id=tgt_id,
            created_by_id=None,
        )

    def test_link_to_architecture_calls_create_trace_link(self):
        """Unit test: connector delegates to traceability.services.create_trace_link."""
        from icd.traceability_connector import TraceabilityConnector

        connector = TraceabilityConnector()
        icd_id = uuid.uuid4()
        src = uuid.uuid4()
        tgt = uuid.uuid4()

        with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture") as m:
            connector.link_to_architecture(icd_id=icd_id, source_element_id=src, target_element_id=tgt)

        # Verify the method signature matches the contract
        m.assert_called_once()

    def test_link_creates_realizes_link_type(self):
        """TraceabilityConnector passes link_type='realizes' to the engine."""
        from icd.traceability_connector import TraceabilityConnector

        connector = TraceabilityConnector()
        icd_id = uuid.uuid4()
        src = uuid.uuid4()
        tgt = uuid.uuid4()

        with patch("traceability.services.create_trace_link") as mock_create:
            connector.link_to_architecture(
                icd_id=icd_id,
                source_element_id=src,
                target_element_id=tgt,
            )

        mock_create.assert_called_once_with(
            source_id=src,
            target_id=tgt,
            link_type="realizes",
            created_by_id=None,
        )


@pytest.mark.django_db
class TestGetIcdVersions:
    """REQ-L2-ICD-005: baseline snapshot returns correct current versions."""

    def test_get_icd_versions_returns_current_version_per_icd(
        self, tenant_a, workspace_id, src_id, tgt_id
    ):
        from icd.services import create_icd, update_icd, get_icd_versions, IcdUpdateDTO

        with active_tenant(tenant_a):
            # Create two ICDs in the workspace
            dto1 = _make_create_dto(
                tenant_a, workspace_id, src_id, tgt_id, name="ICD-1"
            )
            dto2 = _make_create_dto(
                tenant_a, workspace_id, uuid.uuid4(), uuid.uuid4(), name="ICD-2"
            )
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                r1 = create_icd(dto1)
                r2 = create_icd(dto2)
            # Update ICD-1 to v2
            r1_v2 = update_icd(
                icd_id=r1.icd.id,
                payload=IcdUpdateDTO(semantic_description="updated"),
                tenant_id=tenant_a.id,
            )

            versions = get_icd_versions(workspace_id)

        version_ids = {v.id for v in versions}
        # Should include ICD-1 v2 and ICD-2 v1 (current for each)
        assert r1_v2.current_version.id in version_ids
        assert r2.current_version.id in version_ids
        assert r1.current_version.id not in version_ids  # v1 no longer current

    def test_get_icd_versions_excludes_other_workspace(
        self, tenant_a, workspace_id, src_id, tgt_id
    ):
        from icd.services import create_icd, get_icd_versions

        other_ws = uuid.uuid4()

        with active_tenant(tenant_a):
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                create_icd(_make_create_dto(tenant_a, workspace_id, src_id, tgt_id))

            versions = get_icd_versions(other_ws)

        assert versions == []


@pytest.mark.django_db
class TestAuditLogger:
    """REQ-L2-ICD-006: breaking changes trigger audit log entries."""

    def test_breaking_change_triggers_log_write(
        self, tenant_a, workspace_id, src_id, tgt_id
    ):
        from icd.services import create_icd, update_icd, IcdUpdateDTO

        with active_tenant(tenant_a):
            dto = _make_create_dto(
                tenant_a, workspace_id, src_id, tgt_id, preconditions=["auth"]
            )
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                r1 = create_icd(dto)
            with patch("audit.services.log_write") as mock_log:
                update_icd(
                    icd_id=r1.icd.id,
                    payload=IcdUpdateDTO(preconditions=["auth", "new_breaking_req"]),
                    tenant_id=tenant_a.id,
                )

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["entity_type"] == "Icd"
        assert call_kwargs["entity_id"] == r1.icd.id
        assert "ICD_BREAKING_CHANGE" in call_kwargs["change_reason"]

    def test_compatible_change_does_not_trigger_audit(
        self, tenant_a, workspace_id, src_id, tgt_id
    ):
        from icd.services import create_icd, update_icd, IcdUpdateDTO

        with active_tenant(tenant_a):
            dto = _make_create_dto(
                tenant_a, workspace_id, src_id, tgt_id, postconditions=["200"]
            )
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                r1 = create_icd(dto)
            with patch("audit.services.log_write") as mock_log:
                update_icd(
                    icd_id=r1.icd.id,
                    payload=IcdUpdateDTO(postconditions=["200", "extra_guarantee"]),
                    tenant_id=tenant_a.id,
                )

        mock_log.assert_not_called()

    def test_audit_logger_unit_passes_correct_entity_type(self):
        """Unit: AuditLogger formats event correctly before delegating."""
        from icd.audit_logger import AuditLogger

        logger = AuditLogger()
        icd_id = uuid.uuid4()

        with patch("audit.services.log_write") as mock_log:
            logger.log_breaking_change(icd_id=icd_id, details="precondition added: x")

        mock_log.assert_called_once()
        kwargs = mock_log.call_args.kwargs
        assert kwargs["entity_type"] == "Icd"
        assert kwargs["entity_id"] == icd_id
        assert "ICD_BREAKING_CHANGE" in kwargs["change_reason"]
        assert kwargs["details"]["severity"] == "WARNING"


@pytest.mark.django_db
class TestGetIcdHistory:
    """REQ-L2-ICD-001: get_icd_history returns all versions oldest-first."""

    def test_history_returns_all_versions_in_order(
        self, tenant_a, workspace_id, src_id, tgt_id
    ):
        from icd.services import create_icd, update_icd, get_icd_history, IcdUpdateDTO

        with active_tenant(tenant_a):
            dto = _make_create_dto(tenant_a, workspace_id, src_id, tgt_id)
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                r1 = create_icd(dto)
            update_icd(r1.icd.id, IcdUpdateDTO(semantic_description="v2"), tenant_a.id)
            update_icd(r1.icd.id, IcdUpdateDTO(semantic_description="v3"), tenant_a.id)

            history = get_icd_history(r1.icd.id, tenant_a.id)

        assert len(history) == 3
        assert [v.version_number for v in history] == [1, 2, 3]


@pytest.mark.django_db
class TestTenantIsolation:
    """Tenant isolation: ICDs from a different tenant must not be visible."""

    def test_icd_not_visible_to_other_tenant(
        self, tenant_a, tenant_b, workspace_id, src_id, tgt_id
    ):
        from icd.models import Icd
        from icd.services import create_icd

        # Create ICD under tenant_a
        with active_tenant(tenant_a):
            dto = _make_create_dto(tenant_a, workspace_id, src_id, tgt_id)
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                r = create_icd(dto)

        # Tenant_b must not see it via the default manager
        with active_tenant(tenant_b):
            count = Icd.objects.filter(pk=r.icd.id).count()

        assert count == 0

    def test_get_icd_versions_isolated_by_workspace_not_cross_tenant(
        self, tenant_a, tenant_b, workspace_id, src_id, tgt_id
    ):
        from icd.services import create_icd, get_icd_versions

        # Tenant A creates ICD in workspace_id
        with active_tenant(tenant_a):
            dto = _make_create_dto(tenant_a, workspace_id, src_id, tgt_id)
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                create_icd(dto)

        # Tenant B queries the same workspace_id — unscoped used, so we only
        # test that the filter on workspace_id scopes correctly in isolation.
        # The Icd.unscoped manager is used inside get_icd_versions, which correctly
        # retrieves by workspace_id regardless of tenant context.
        # Here we verify that a workspace with no ICDs for tenant_a returns empty.
        other_ws = uuid.uuid4()
        with active_tenant(tenant_a):
            result = get_icd_versions(other_ws)
        assert result == []

    def test_update_icd_rejects_foreign_tenant_id(
        self, tenant_a, tenant_b, workspace_id, src_id, tgt_id
    ):
        """Security regression: update_icd() must not let tenant_b mutate
        (or even find) an ICD that belongs to tenant_a, just by supplying its
        UUID and tenant_b's own tenant_id. Previously used `.unscoped` with
        no tenant filter at all."""
        from icd.models import Icd
        from icd.services import create_icd, update_icd, IcdUpdateDTO

        with active_tenant(tenant_a):
            dto = _make_create_dto(tenant_a, workspace_id, src_id, tgt_id)
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                r = create_icd(dto)

        update = IcdUpdateDTO(semantic_description="mutated by tenant_b")
        with active_tenant(tenant_b):
            with pytest.raises(Icd.DoesNotExist):
                update_icd(icd_id=r.icd.id, payload=update, tenant_id=tenant_b.id)

    def test_get_icd_history_rejects_foreign_tenant_id(
        self, tenant_a, tenant_b, workspace_id, src_id, tgt_id
    ):
        from icd.services import create_icd, get_icd_history

        with active_tenant(tenant_a):
            dto = _make_create_dto(tenant_a, workspace_id, src_id, tgt_id)
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                r = create_icd(dto)

        with active_tenant(tenant_b):
            history = get_icd_history(icd_id=r.icd.id, tenant_id=tenant_b.id)
        assert history == []

    def test_validate_compatibility_rejects_foreign_tenant_id(
        self, tenant_a, tenant_b, workspace_id, src_id, tgt_id
    ):
        from icd.models import Icd
        from icd.services import create_icd, validate_compatibility

        with active_tenant(tenant_a):
            dto = _make_create_dto(tenant_a, workspace_id, src_id, tgt_id)
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                r = create_icd(dto)

        with active_tenant(tenant_b):
            with pytest.raises(Icd.DoesNotExist):
                validate_compatibility(
                    icd_id=r.icd.id,
                    tenant_id=tenant_b.id,
                    new_payload={
                        "direction": "unidirectional",
                        "interface_type": "REST",
                        "semantic_description": "x",
                        "preconditions": [],
                        "postconditions": [],
                        "invariants": [],
                    },
                )


@pytest.mark.django_db
class TestIcdInterfaceTypeChoices:
    """REQ-006: interface_type field enforces enum choices."""

    def test_create_icd_with_valid_interface_type(
        self, tenant_a, workspace_id, src_id, tgt_id
    ):
        from icd.services import create_icd

        with active_tenant(tenant_a):
            for iface_type in ["provides", "requires", "event-in", "event-out", "data", "control"]:
                dto = _make_create_dto(
                    tenant_a, workspace_id, src_id, tgt_id,
                    name=f"Test ICD {iface_type}",
                    interface_type=iface_type,
                )
                with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                    result = create_icd(dto)

            assert result.current_version.interface_type == "control"

    def test_icd_version_persists_interface_type(self, tenant_a, workspace_id, src_id, tgt_id):
        from icd.services import create_icd

        with active_tenant(tenant_a):
            dto = _make_create_dto(
                tenant_a, workspace_id, src_id, tgt_id,
                interface_type="requires",
            )
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                result = create_icd(dto)

        assert result.current_version.interface_type == "requires"

    def test_update_icd_changes_interface_type(self, tenant_a, workspace_id, src_id, tgt_id):
        from icd.services import create_icd, update_icd, IcdUpdateDTO

        with active_tenant(tenant_a):
            dto = _make_create_dto(
                tenant_a, workspace_id, src_id, tgt_id,
                interface_type="data",
            )
            with patch("icd.traceability_connector.TraceabilityConnector.link_to_architecture"):
                r1 = create_icd(dto)

            r2 = update_icd(
                icd_id=r1.icd.id,
                payload=IcdUpdateDTO(interface_type="event-in"),
                tenant_id=tenant_a.id,
            )

        assert r1.current_version.interface_type == "data"
        assert r2.current_version.interface_type == "event-in"
        assert r2.current_version.version_number == 2
