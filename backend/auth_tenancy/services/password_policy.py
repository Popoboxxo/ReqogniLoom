"""Shared password-strength policy for user-driven password writes (N21).

Before this module existed, :class:`~auth_tenancy.services.user_account.
UserAccountService` enforced only a minimum length on the password a tenant
admin sets for a new user, and the MCP admin tool did the same — Django's
configured validators (``AUTH_PASSWORD_VALIDATORS`` in
``reqogniloom/settings.py``: similarity, minimum length, common password,
numeric) were never consulted on **any** user-driven creation or change path.

This module is the single place that applies them, so the REST/MCP user
creation path and the self-service password change cannot drift apart.

Deliberately **not** used by the operator provisioning paths
(``auth_tenancy.provisioning.provision_admin``, ``bootstrap_admin``,
``self_init``, ``seed_demo``): those write a password supplied out-of-band via
``SYSTEM_ADMIN_PASSWORD`` and must keep working for disaster recovery even
when the operator picks a short password. See the comment at the write site in
``provisioning.py``.

leaf_id : COMP-AT-002 / COMP-AT-004
req_id  : REQ-L2-AT-003, N21 (beta.29 bugfix cluster C2-T4)
"""
from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from persistence.models import User

__all__ = ["PasswordPolicyError", "validate_new_password"]


class PasswordPolicyError(ValueError):
    """A password was rejected by Django's configured validators.

    Subclasses :class:`ValueError` on purpose: every existing caller of
    ``UserAccountService.create`` already maps ``ValueError`` to a 400 /
    ``VALIDATION_ERROR`` (REST ``UserViewSet.create``, MCP
    ``users._create_user_account``), so adding validation cannot change the
    transport contract — only which inputs are accepted.

    Attributes:
        messages: One human-readable sentence per failed validator. Never
            contains the password itself.
    """

    def __init__(self, messages: list[str]) -> None:
        self.messages: tuple[str, ...] = tuple(messages)
        super().__init__(" ".join(self.messages))


def validate_new_password(
    password: str, *, username: str = "", email: str = ""
) -> None:
    """Raise :class:`PasswordPolicyError` unless *password* passes all validators.

    The validators run against an **unsaved** :class:`~persistence.models.User`
    carrying only ``username``/``email``: ``UserAttributeSimilarityValidator``
    reads exactly those attributes (plus the empty ``first_name``/
    ``last_name``), so similarity to the account name is enforced without
    touching the database or the real row.

    Args:
        password: The cleartext candidate. Never logged or echoed.
        username: Username the password will belong to (similarity check).
        email: Email the password will belong to (similarity check).

    Raises:
        PasswordPolicyError: At least one configured validator rejected the
            password; ``messages`` carries every rejection.
    """
    candidate = User(username=username or "", email=email or "")
    try:
        validate_password(password, user=candidate)
    except DjangoValidationError as exc:
        raise PasswordPolicyError(list(exc.messages)) from exc
