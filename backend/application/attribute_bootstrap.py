"""Shared attribute-definition bootstrap for tenant provisioning (REQ-188, #29).

Both the first-start self-init receiver (:mod:`application.self_init`) and the
optional ``seed_demo`` management command need the same step: seed a tenant's
``GlobalAttributeDefinition`` rows so the custom-fields / attribute feature has
a non-empty definition set. Only ``self_init`` used to do this, so a database
populated via ``seed_demo`` alone ended up with zero global definitions and
every artifact form rendered "No global attribute definition for
'<type>/<preset>'" instead of its fields.

Keeping the call in one shared helper stops the two provisioning paths from
drifting apart (the same reason ``application.workspace_provisioning`` is
shared by both).
"""
from __future__ import annotations

from uuid import UUID

from django.core.management import call_command


def bootstrap_attribute_definitions_for_tenant(tenant_id: UUID | str) -> None:
    """Seed the tenant's ``GlobalAttributeDefinition`` rows (idempotent).

    Thin wrapper around the ``bootstrap_attribute_definitions`` management
    command, which owns the model introspection and its own get-then-initialize
    guard: a repeat call for the same tenant creates no duplicate rows and
    leaves existing (possibly admin-customized) definitions untouched.

    Args:
        tenant_id: Tenant whose global definitions should be bootstrapped.

    Raises:
        Exception: Whatever the underlying command raises. Callers that must
            not raise — ``run_self_init`` runs inside ``post_migrate``, where an
            exception would abort the whole ``migrate`` step — are responsible
            for their own guard.
    """
    call_command("bootstrap_attribute_definitions", tenant=str(tenant_id))


__all__ = ["bootstrap_attribute_definitions_for_tenant"]
