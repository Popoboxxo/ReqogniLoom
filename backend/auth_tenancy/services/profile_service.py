"""ARCH-L1-011 AuthAndTenancy — UserProfileService (REQ-006, REQ-066).

Owns read + write access to the authenticated caller's own ``User`` record so
the REST layer (``rest_api/auth_views.py``) stays free of direct ORM access
(Option B, REQ-066).

Only ``first_name`` / ``last_name`` are writable — a user may edit their own
display name but never username, email, tenant or roles. Persistence mirrors the
former view/serializer behaviour exactly: each touched column is trimmed and
saved via ``update_fields`` (PATCH semantics), so behaviour and error codes are
unchanged.

req_id: REQ-066, REQ-006
leaf_id: COMP-AT-PROFILE
"""
from __future__ import annotations

from typing import Any

from auth_tenancy.context import AuthContext
from persistence.models import User

# Fields a user may edit on their own profile.
_EDITABLE_PROFILE_FIELDS = ("first_name", "last_name")


class UserProfileService:
    """Read/update the authenticated caller's own profile (REQ-006, REQ-066)."""

    def get_current_user(self, ctx: AuthContext) -> User | None:
        """Return the ``User`` for ``ctx.user_id`` or ``None`` if absent."""
        return User.objects.filter(id=ctx.user_id).first()

    def update_profile(
        self, ctx: AuthContext, validated_data: dict[str, Any]
    ) -> User | None:
        """Apply editable profile fields and persist the touched columns.

        Args:
            ctx:            Authenticated request context (identifies the user).
            validated_data: Serializer-validated payload; only ``first_name`` /
                ``last_name`` are honoured.

        Returns:
            The updated ``User``, or ``None`` when the user no longer exists
            (caller maps this to a 401, preserving prior behaviour).
        """
        user = self.get_current_user(ctx)
        if user is None:
            return None

        updated_fields: list[str] = []
        for field in _EDITABLE_PROFILE_FIELDS:
            if field in validated_data:
                setattr(user, field, str(validated_data[field]).strip())
                updated_fields.append(field)
        if updated_fields:
            user.save(update_fields=updated_fields)
        return user


__all__ = ["UserProfileService"]
