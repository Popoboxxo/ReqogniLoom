"""ActorService — the single Layer-2 entry point for ``Actor`` values.

Attribut v3 WS2 (#936), spec section 4. ``Actor`` is the entity carrier behind
the artifact-level ``owner``/``reporter`` fields and behind the ``actor``
attribute type. REST views and MCP handlers must never touch
``persistence.models.Actor`` directly (ADR-01 Single Entry Point); they resolve
or create actors through this service, and the DB-free ``actor`` structure check
stays in ``attribute_definitions.field_validation``.

Two uniqueness rules apply (spec section 4, migration 0085):

* ``kind="user"``  — one actor per ``(tenant, user)``;
* ``kind="external"`` — one actor per ``(tenant, lower(display_name))``.

Both are enforced by PostgreSQL partial unique indexes, so this service's
lookup-then-create pattern is additionally wrapped in a retry on
``IntegrityError`` (belt and braces for the concurrent-create race, exactly like
``User``/username creation elsewhere in the codebase).
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional
from uuid import UUID

from django.db import IntegrityError, transaction

from auth_tenancy.context import AuthContext
from persistence.errors import NotFoundError, ValidationError
from persistence.models import Actor, User

from application.base import ServiceBase

logger = logging.getLogger(__name__)


class ActorService(ServiceBase):
    """Layer-2 facade over the :class:`~persistence.models.Actor` entity."""

    # ---------- Read ---------------------------------------------------------

    def list_actors(
        self,
        ctx: AuthContext,
        *,
        query: Optional[str] = None,
        kind: Optional[str] = None,
        include_inactive: bool = False,
    ) -> "Iterable[Actor]":
        """Return the tenant's actors for the picker (spec section 4).

        Args:
            query: Optional case-insensitive substring of ``display_name``.
            kind: Optional ``"user"``/``"external"`` filter.
            include_inactive: Include deactivated actors (default: active only).
        """
        self._set_tenant_context(ctx)
        qs = Actor.objects.all()
        if not include_inactive:
            qs = qs.filter(is_active=True)
        if kind is not None:
            if kind not in Actor.Kind.values:
                raise ValidationError(
                    f"Unknown actor kind '{kind}'; expected one of {list(Actor.Kind.values)}"
                )
            qs = qs.filter(kind=kind)
        if query:
            qs = qs.filter(display_name__icontains=query.strip())
        return qs.order_by("display_name")

    def resolve(self, ctx: AuthContext, actor_id: Any) -> Actor:
        """Return the ``Actor`` with *actor_id* in the active tenant.

        Raises:
            NotFoundError: no such actor in this tenant.
        """
        self._set_tenant_context(ctx)
        actor = Actor.objects.filter(id=_as_uuid(actor_id, "actor id")).first()
        if actor is None:
            raise NotFoundError(f"Actor {actor_id} not found")
        return actor

    def resolve_reference(self, ctx: AuthContext, reference_id: Any) -> Actor:
        """Resolve an actor *or* user id to an ``Actor`` (spec section 4).

        The wire value form's ``"id"`` is documented as "user-or-actor-uuid", so
        the write adapter accepts both: an existing ``Actor`` id wins; otherwise
        the id is treated as a ``User`` id and the actor is created on demand.
        """
        self._set_tenant_context(ctx)
        identifier = _as_uuid(reference_id, "actor id")
        actor = Actor.objects.filter(id=identifier).first()
        if actor is not None:
            return actor
        return self.get_or_create_for_user(ctx, identifier)

    # ---------- Write --------------------------------------------------------

    @transaction.atomic
    def get_or_create_external(
        self,
        ctx: AuthContext,
        display_name: str,
        *,
        email: str = "",
        organization: str = "",
        notes: str = "",
    ) -> Actor:
        """Return the tenant's external actor named *display_name*, creating it.

        Uniqueness is ``(tenant, lower(display_name))`` (spec section 4), so the
        lookup is case-insensitive and an existing actor is reused verbatim.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        name = (display_name or "").strip()
        if not name:
            raise ValidationError("An external actor requires a non-empty display name")

        existing = Actor.objects.filter(
            kind=Actor.Kind.EXTERNAL, display_name__iexact=name
        ).first()
        if existing is not None:
            return existing

        try:
            with transaction.atomic():
                return Actor.objects.create(
                    kind=Actor.Kind.EXTERNAL,
                    display_name=name,
                    email=email,
                    organization=organization,
                    notes=notes,
                )
        except IntegrityError:
            # Concurrent create won the unique-index race; return its row.
            existing = Actor.objects.filter(
                kind=Actor.Kind.EXTERNAL, display_name__iexact=name
            ).first()
            if existing is None:  # pragma: no cover - defensive
                raise
            return existing

    @transaction.atomic
    def get_or_create_for_user(self, ctx: AuthContext, user_id: Any) -> Actor:
        """Return the ``Actor`` for ``User`` *user_id*, creating it if needed.

        Uniqueness is ``(tenant, user)`` (spec section 4). ``display_name``
        mirrors the user's name at creation time so the attribution survives a
        later rename or deletion.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        identifier = _as_uuid(user_id, "user id")

        existing = Actor.objects.filter(user_id=identifier).first()
        if existing is not None:
            return existing

        user = User.objects.filter(id=identifier).first()
        if user is None:
            raise NotFoundError(f"User {user_id} not found")

        try:
            with transaction.atomic():
                return Actor.objects.create(
                    kind=Actor.Kind.USER,
                    user=user,
                    display_name=_user_display_name(user),
                    email=getattr(user, "email", "") or "",
                )
        except IntegrityError:
            existing = Actor.objects.filter(user_id=identifier).first()
            if existing is None:  # pragma: no cover - defensive
                raise
            return existing

    # ---------- Value validation (DB-backed half of §4) ----------------------

    def validate_actor_value(
        self,
        ctx: AuthContext,
        value: Any,
        *,
        multiple: bool = False,
        allow_external: bool = False,
    ) -> list[Actor]:
        """Resolve *value* to concrete actors, enforcing existence and policy.

        The DB-free structure check lives in
        ``attribute_definitions.field_validation._check_type`` (spec section 4);
        this method is the service-layer half that the pure validator
        deliberately cannot do: it verifies that each referenced actor/user
        exists in the tenant and that ``allow_external`` is respected.

        Args:
            ctx: Request identity.
            value: Actor value form (single dict, or
                ``{"multiple": true, "items": [...]}`` when *multiple*).
            multiple: The attribute's ``multiple`` property.
            allow_external: The attribute's ``allow_external`` property.

        Returns:
            The resolved actors, in input order (empty list for an empty
            selection).

        Raises:
            ValidationError: malformed shape, unknown actor/user, or an external
                actor while ``allow_external`` is false.
        """
        self._set_tenant_context(ctx)
        if multiple:
            if not isinstance(value, dict) or value.get("multiple") is not True:
                raise ValidationError(
                    "actor value must be {'multiple': true, 'items': [...]}"
                )
            items = value.get("items")
            if not isinstance(items, list):
                raise ValidationError("actor value 'items' must be a list")
            entries = items
        else:
            if value is None:
                return []
            if not isinstance(value, dict) or "kind" not in value:
                raise ValidationError(
                    "actor value must be {'kind': 'user'|'external', ...}"
                )
            entries = [value]

        return [
            self._resolve_entry(ctx, entry, index=index, allow_external=allow_external)
            for index, entry in enumerate(entries)
        ]

    def _resolve_entry(
        self,
        ctx: AuthContext,
        entry: Any,
        *,
        index: int,
        allow_external: bool,
    ) -> Actor:
        if not isinstance(entry, dict):
            raise ValidationError(f"actor item {index} must be an object")
        kind = entry.get("kind")
        if kind == Actor.Kind.EXTERNAL:
            if not allow_external:
                raise ValidationError(
                    f"actor item {index}: external actors are not allowed "
                    "(allow_external is false)"
                )
            return self.get_or_create_external(
                ctx,
                entry.get("name") or "",
                email=entry.get("email") or "",
                organization=entry.get("organization") or "",
            )
        if kind == Actor.Kind.USER:
            actor = self.resolve_reference(ctx, entry.get("id"))
            if actor.kind == Actor.Kind.EXTERNAL:
                raise ValidationError(
                    f"actor item {index}: kind 'user' points at an external actor"
                )
            return actor
        raise ValidationError(
            f"actor item {index}: 'kind' must be 'user' or 'external'"
        )


def _as_uuid(value: Any, label: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        raise ValidationError(f"Invalid {label}: {value!r}")


def _user_display_name(user: Any) -> str:
    full_name = getattr(user, "get_full_name", None)
    name = full_name() if callable(full_name) else ""
    if not name:
        first = getattr(user, "first_name", "") or ""
        last = getattr(user, "last_name", "") or ""
        name = f"{first} {last}".strip()
    return name or getattr(user, "username", "") or "Unknown user"


__all__ = ["ActorService"]
