"""#1709 — non-string ICD contract list entries are refused and repairable.

Three layers:

* the DB-free validator: every element of ``preconditions``/``postconditions``/
  ``invariants`` must be a ``str`` (the wire contract is ``string[]``);
* the manager: ``create_icd`` and ``update_icd`` both route through that check,
  so a non-string payload is a clean ``ValueError`` (→ HTTP 400), never a 500;
* the repair command: legacy rows are cleaned, parameter objects move to the
  structured ``parameters``, and a second run is a no-op.

The frontend half (defensive rendering in ``IcdDetailPane``) is covered by
``frontend/src/components/IcdView/IcdDetailPane.test.tsx``.
"""
from __future__ import annotations

import io
import uuid

import pytest
from django.core.management import call_command

from icd.contract_validator import ContractValidator
from icd.icd_manager import IcdCreateDTO, IcdManager, IcdUpdateDTO
from icd.models import Icd, IcdParameter
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# validator
# ---------------------------------------------------------------------------


def _payload(**overrides) -> dict:
    base = {
        "direction": "unidirectional",
        "interface_type": "data",
        "semantic_description": "contract",
        "preconditions": ["caller is authenticated"],
        "postconditions": ["result is stored"],
        "invariants": ["unit stays constant"],
    }
    base.update(overrides)
    return base


def test_non_string_element_is_a_syntax_error() -> None:
    result = ContractValidator().validate_syntax(
        _payload(preconditions=[{"name": "voltage", "unit": "V", "ordering": 1}])
    )

    assert result.is_valid_syntax is False
    assert any(
        "preconditions" in error and "list of strings" in error
        for error in result.syntax_errors
    ), result.syntax_errors


def test_valid_string_lists_still_pass() -> None:
    result = ContractValidator().validate_syntax(_payload())

    assert result.is_valid_syntax is True
    assert result.syntax_errors == []


def test_a_non_list_still_reports_the_container_type_error() -> None:
    result = ContractValidator().validate_syntax(_payload(invariants="not a list"))

    assert result.is_valid_syntax is False
    assert any("must be a list" in error for error in result.syntax_errors)


def test_validate_contract_ignores_legacy_non_string_entries() -> None:
    """A pre-repair row must not turn the compatibility check into a 500."""
    result = ContractValidator().validate_contract(
        old_preconditions=[{"name": "legacy"}, "keep me"],
        old_postconditions=[],
        old_invariants=[],
        new_preconditions=["keep me"],
        new_postconditions=[],
        new_invariants=[],
    )

    assert result.is_breaking is False


# ---------------------------------------------------------------------------
# manager (create + update use the same check)
# ---------------------------------------------------------------------------


def test_create_rejects_a_non_string_entry() -> None:
    manager = IcdManager()

    with pytest.raises(ValueError, match="list of strings"):
        manager.create_icd(
            IcdCreateDTO(
                tenant_id=uuid.uuid4(),
                workspace_id=uuid.uuid4(),
                name="Bad ICD",
                source_element_id=uuid.uuid4(),
                target_element_id=uuid.uuid4(),
                preconditions=[{"name": "voltage", "unit": "V"}],
            )
        )


@pytest.fixture
def icd_row() -> tuple[Icd, Tenant]:
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"Icd-{suffix}", slug=f"icd-{suffix}")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="icd ws", preset={"name": "extended"}
        )
        icd = Icd.objects.create(
            tenant=tenant,
            workspace_id=workspace.id,
            name="Legacy ICD",
            source_element_id=uuid.uuid4(),
            target_element_id=uuid.uuid4(),
            direction="unidirectional",
            interface_type="data",
            semantic_description="legacy",
            preconditions=[
                {"name": "voltage", "unit": "V", "ordering": 0, "data_type": "float"},
                "plain clause",
            ],
            postconditions=[],
            invariants=[],
        )
    finally:
        TenantContext.clear_tenant()
    return icd, tenant


def test_update_rejects_a_non_string_entry(icd_row) -> None:
    icd, tenant = icd_row

    with pytest.raises(ValueError, match="list of strings"):
        IcdManager().update_icd(
            icd.id,
            IcdUpdateDTO(postconditions=[{"name": "temperature", "unit": "C"}]),
            tenant.id,
        )


# ---------------------------------------------------------------------------
# repair command
# ---------------------------------------------------------------------------


def test_repair_is_dry_run_by_default(icd_row) -> None:
    icd, _tenant = icd_row
    out = io.StringIO()

    call_command("repair_icd_contract_lists", stdout=out)

    stored = Icd.unscoped.get(pk=icd.pk)
    assert isinstance(stored.preconditions[0], dict), "dry-run must not write"
    assert "re-run with --apply" in out.getvalue()


def test_repair_moves_parameter_objects_and_stringifies_the_rest(icd_row) -> None:
    icd, _tenant = icd_row

    call_command("repair_icd_contract_lists", "--apply", stdout=io.StringIO())

    stored = Icd.unscoped.get(pk=icd.pk)
    assert stored.preconditions == ["plain clause"]
    parameter = IcdParameter.unscoped.get(icd_id=icd.id, name="voltage")
    assert parameter.unit == "V"
    assert parameter.data_type == "float"


def test_repair_is_idempotent(icd_row) -> None:
    call_command("repair_icd_contract_lists", "--apply", stdout=io.StringIO())
    out = io.StringIO()

    call_command("repair_icd_contract_lists", "--apply", stdout=out)

    assert "No ICD contract lists to repair." in out.getvalue()
