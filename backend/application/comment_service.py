"""Comments on artifacts (Menschen-im-System spec §4).

Comments hang on the generic ``persistence.Artifact``, so this service has no
per-type branch at all: ``owner``/``reporter`` are columns on ``Artifact``
itself (Attribut v3), and the ``comment_added`` recipients are simply the
internal actors behind those two FKs.

Comments are not editable: create, resolve, delete. ``author`` /
``resolved_by`` / ``resolved_at`` are the whole history (spec §3.3).
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from django.utils import timezone

from auth_tenancy.context import AuthContext
from persistence.errors import NotFoundError, PermissionDeniedError, ValidationError
from persistence.free_text import find_free_text_violation
from persistence.models import Artifact, Tenant
from persistence.transactions import atomic_transaction

from application.base import ServiceBase
from application.models import Comment, Notification
from application.notification_service import create_notifications

logger = logging.getLogger(__name__)


def notify_user_ids_for_artifact(artifact: Any) -> list[UUID]:
    """User ids to notify for an artifact: owner + reporter, internal actors only.

    ``Actor.kind == "external"`` is dropped — an external placeholder has no
    login and therefore no notification feed. Order is owner-then-reporter and
    duplicates collapse (the same person may own and report the artifact).
    """
    ids: list[UUID] = []
    for actor in (artifact.owner, artifact.reporter):
        if actor is None:
            continue
        if getattr(actor, "kind", None) != "user":
            continue
        user_id = getattr(actor, "user_id", None)
        if user_id is not None and user_id not in ids:
            ids.append(user_id)
    return ids


class CommentService(ServiceBase):
    """Comment CRUD over the generic Artifact (COMP-AS-Comment)."""

    def list_for_artifact(
        self,
        artifact_id: UUID,
        ctx: AuthContext,
        *,
        include_resolved: bool = True,
    ) -> list[Comment]:
        """Return an artifact's comments, oldest first.

        Raises :class:`NotFoundError` for an unknown artifact id (issue #983):
        the write path already 404s, so the read path must not answer ``200 []``
        and let a caller with the wrong id-space (requirement entity id vs.
        ``artifact_id``) read "no comments" instead of "artifact not found".
        """
        self._set_tenant_context(ctx)
        if not Artifact.objects.filter(pk=artifact_id).exists():
            raise NotFoundError(f"Artifact {artifact_id} not found")
        qs = Comment.objects.filter(artifact_id=artifact_id).select_related(
            "author", "resolved_by"
        )
        if not include_resolved:
            qs = qs.filter(resolved=False)
        return list(qs)

    @atomic_transaction
    def create_comment(self, *, artifact_id: UUID, text: str, ctx: AuthContext) -> Comment:
        """Create a comment and notify the artifact's owner and reporter.

        The candidate recipients come from :func:`notify_user_ids_for_artifact`;
        the preference filter runs inside ``create_notifications`` (OD-1) — do
        not add a producer-local preference check here. Delivery is best-effort:
        a notification failure must never roll back the comment, hence the
        ``try/except`` around the fan-out (spec §6/A3).

        ``text`` is free text and obeys the shared policy
        (:mod:`persistence.free_text`, #820): markup / script-capable URIs are
        rejected, everything else — quotes, ``&``, umlauts, a bare ``<``, or a
        SQL-shaped string such as ``'; DROP TABLE users; --`` — is stored
        byte-identically. The REST view already enforces this through
        ``CommentSerializer``; the check is repeated here because the MCP
        comment tool calls this service directly (#269 finding 4 pattern).
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        cleaned = (text or "").strip()
        if not cleaned:
            raise ValidationError("Comment text is required")

        violation = find_free_text_violation(cleaned)
        if violation is not None:
            raise ValidationError(f"text {violation}")

        artifact = Artifact.objects.filter(pk=artifact_id).first()
        if artifact is None:
            raise NotFoundError(f"Artifact {artifact_id} not found")

        tenant = Tenant.objects.filter(pk=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")

        comment = Comment.unscoped.create(
            tenant=tenant,
            artifact=artifact,
            author_id=ctx.user_id,
            text=cleaned,
        )

        try:
            # The generic Artifact carries no human title of its own (the title
            # lives on the type-specific row), so fall back to the id rather
            # than let an AttributeError silence the whole fan-out.
            artifact_label = getattr(artifact, "title", None) or str(artifact.pk)
            create_notifications(
                user_ids=notify_user_ids_for_artifact(artifact),
                kind=Notification.KIND_COMMENT_ADDED,
                message=f"New comment on {artifact_label}",
                artifact_id=artifact.pk,
                tenant_id=ctx.tenant_id,
                exclude_user_id=ctx.user_id,
            )
        except Exception:
            logger.exception(
                "CommentService.create_comment: notification fan-out failed "
                "for artifact %s",
                artifact_id,
            )

        self._audit(
            ctx=ctx,
            operation="create",
            entity_type="Comment",
            entity_id=comment.pk,
            details={"artifact_id": str(artifact.pk)},
        )
        return comment

    @atomic_transaction
    def resolve_comment(self, comment_id: UUID, ctx: AuthContext) -> Comment:
        """Mark a comment resolved. Idempotent — re-resolving keeps the first stamp."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        comment = Comment.objects.filter(pk=comment_id).first()
        if comment is None:
            raise NotFoundError(f"Comment {comment_id} not found")

        if not comment.resolved:
            comment.resolved = True
            comment.resolved_by_id = ctx.user_id
            comment.resolved_at = timezone.now()
            comment.save(update_fields=["resolved", "resolved_by_id", "resolved_at"])
            self._audit(
                ctx=ctx,
                operation="update",
                entity_type="Comment",
                entity_id=comment.pk,
                details={"resolved": True},
            )
        return comment

    @atomic_transaction
    def delete_comment(self, comment_id: UUID, ctx: AuthContext) -> None:
        """Delete a comment. Author or admin only (spec §4)."""
        self._set_tenant_context(ctx)

        comment = Comment.objects.filter(pk=comment_id).first()
        if comment is None:
            raise NotFoundError(f"Comment {comment_id} not found")

        is_author = comment.author_id == ctx.user_id
        is_admin = "admin" in (ctx.active_roles or [])
        if not (is_author or is_admin):
            raise PermissionDeniedError("Only the comment author or an admin may delete it")

        self._audit(
            ctx=ctx,
            operation="delete",
            entity_type="Comment",
            entity_id=comment.pk,
            details={"artifact_id": str(comment.artifact_id)},
        )
        comment.delete()


__all__ = ["CommentService", "notify_user_ids_for_artifact"]
