"""CommentService — create / list / resolve / delete plus the ``comment_added`` trigger.

Adapted from Plan #6 Task 15 Step 1. ``owner``/``reporter`` are columns on the
generic ``Artifact`` now, so the two type-aware probe tests are replaced by the
``notify_user_ids_for_artifact`` contract (re-scope §3 Task 15).
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from application.comment_service import CommentService, notify_user_ids_for_artifact
from application.models import Comment, Notification
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.errors import PermissionDeniedError, ValidationError
from persistence.models import Actor, Artifact, Tenant, User, Workspace


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def workspace(db, tenant):
    return Workspace.unscoped.create(tenant=tenant, name="W")


@pytest.fixture
def alice(db, tenant):
    return User.objects.create(
        username=f"alice-{uuid.uuid4().hex[:6]}",
        email=f"a{uuid.uuid4().hex[:6]}@example.com",
        tenant=tenant,
    )


@pytest.fixture
def bob(db, tenant):
    return User.objects.create(
        username=f"bob-{uuid.uuid4().hex[:6]}",
        email=f"b{uuid.uuid4().hex[:6]}@example.com",
        tenant=tenant,
    )


@pytest.fixture
def artifact(db, tenant, workspace):
    return Artifact.unscoped.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )


@pytest.fixture
def ctx(alice, tenant, workspace):
    return AuthContext(
        user_id=alice.pk,
        tenant_id=tenant.pk,
        workspace_id=workspace.pk,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _actor(tenant, *, name, kind=Actor.Kind.USER, user=None):
    return Actor.unscoped.create(
        tenant=tenant, kind=kind, user=user, display_name=name
    )


@pytest.mark.django_db
def test_create_comment_records_the_author(ctx, artifact, alice):
    with patch("application.comment_service.create_notifications"):
        comment = CommentService().create_comment(
            artifact_id=artifact.pk, text="looks wrong", ctx=ctx
        )
    assert comment.author_id == alice.pk
    assert comment.text == "looks wrong"
    assert comment.resolved is False


@pytest.mark.django_db
def test_create_comment_rejects_empty_text(ctx, artifact):
    with pytest.raises(ValidationError):
        CommentService().create_comment(artifact_id=artifact.pk, text="   ", ctx=ctx)


@pytest.mark.django_db
def test_create_comment_rejects_markup(ctx, artifact):
    """#820: comment text obeys the shared free-text policy, not just REST.

    The MCP comment tool calls the service directly and never runs
    ``CommentSerializer``, so the rule is enforced here as well — the same
    defense-in-depth shape ``ArtifactService.clean_free_text_field`` uses.
    """
    with pytest.raises(ValidationError) as excinfo:
        CommentService().create_comment(
            artifact_id=artifact.pk, text="<img src=x onerror=alert(1)>", ctx=ctx
        )

    assert "disallowed content" in str(excinfo.value)
    assert not Comment.unscoped.filter(artifact=artifact).exists()


@pytest.mark.django_db
def test_create_comment_keeps_sql_shaped_text_verbatim(ctx, artifact):
    """SQL-looking text is data: the ORM parameterises, so it round-trips."""
    hostile = "'; DROP TABLE users; --"
    with patch("application.comment_service.create_notifications"):
        comment = CommentService().create_comment(
            artifact_id=artifact.pk, text=f"Failed with {hostile}", ctx=ctx
        )

    assert comment.text == f"Failed with {hostile}"


@pytest.mark.django_db
def test_create_comment_notifies_the_artifact_recipients(ctx, artifact, bob):
    with patch(
        "application.comment_service.notify_user_ids_for_artifact",
        return_value=[bob.pk],
    ), patch("application.comment_service.create_notifications") as notify:
        CommentService().create_comment(artifact_id=artifact.pk, text="hi", ctx=ctx)

    kwargs = notify.call_args.kwargs
    assert kwargs["kind"] == Notification.KIND_COMMENT_ADDED
    assert kwargs["user_ids"] == [bob.pk]
    assert kwargs["exclude_user_id"] == ctx.user_id
    assert kwargs["artifact_id"] == artifact.pk
    assert kwargs["tenant_id"] == ctx.tenant_id


@pytest.mark.django_db
def test_list_for_artifact_is_chronological(ctx, artifact):
    svc = CommentService()
    with patch("application.comment_service.create_notifications"):
        svc.create_comment(artifact_id=artifact.pk, text="first", ctx=ctx)
        svc.create_comment(artifact_id=artifact.pk, text="second", ctx=ctx)

    assert [c.text for c in svc.list_for_artifact(artifact.pk, ctx)] == ["first", "second"]


@pytest.mark.django_db
def test_list_can_hide_resolved(ctx, artifact):
    svc = CommentService()
    with patch("application.comment_service.create_notifications"):
        first = svc.create_comment(artifact_id=artifact.pk, text="first", ctx=ctx)
        svc.create_comment(artifact_id=artifact.pk, text="second", ctx=ctx)
    svc.resolve_comment(first.pk, ctx)

    open_only = svc.list_for_artifact(artifact.pk, ctx, include_resolved=False)
    assert [c.text for c in open_only] == ["second"]


@pytest.mark.django_db
def test_resolve_stamps_who_and_when(ctx, artifact, alice):
    svc = CommentService()
    with patch("application.comment_service.create_notifications"):
        comment = svc.create_comment(artifact_id=artifact.pk, text="x", ctx=ctx)

    resolved = svc.resolve_comment(comment.pk, ctx)
    assert resolved.resolved is True
    assert resolved.resolved_by_id == alice.pk
    assert resolved.resolved_at is not None


@pytest.mark.django_db
def test_resolve_is_idempotent(ctx, artifact):
    svc = CommentService()
    with patch("application.comment_service.create_notifications"):
        comment = svc.create_comment(artifact_id=artifact.pk, text="x", ctx=ctx)

    first = svc.resolve_comment(comment.pk, ctx)
    second = svc.resolve_comment(comment.pk, ctx)
    assert first.resolved_at == second.resolved_at


@pytest.mark.django_db
def test_author_may_delete_own_comment(ctx, artifact):
    svc = CommentService()
    with patch("application.comment_service.create_notifications"):
        comment = svc.create_comment(artifact_id=artifact.pk, text="x", ctx=ctx)

    svc.delete_comment(comment.pk, ctx)
    assert not Comment.unscoped.filter(pk=comment.pk).exists()


@pytest.mark.django_db
def test_non_author_non_admin_may_not_delete(ctx, artifact, bob, tenant, workspace):
    svc = CommentService()
    with patch("application.comment_service.create_notifications"):
        comment = svc.create_comment(artifact_id=artifact.pk, text="x", ctx=ctx)

    other_ctx = AuthContext(
        user_id=bob.pk,
        tenant_id=tenant.pk,
        workspace_id=workspace.pk,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    with pytest.raises(PermissionDeniedError):
        svc.delete_comment(comment.pk, other_ctx)


@pytest.mark.django_db
def test_admin_may_delete_any_comment(ctx, artifact, bob, tenant, workspace):
    svc = CommentService()
    with patch("application.comment_service.create_notifications"):
        comment = svc.create_comment(artifact_id=artifact.pk, text="x", ctx=ctx)

    admin_ctx = AuthContext(
        user_id=bob.pk,
        tenant_id=tenant.pk,
        workspace_id=workspace.pk,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    svc.delete_comment(comment.pk, admin_ctx)
    assert not Comment.unscoped.filter(pk=comment.pk).exists()


@pytest.mark.django_db
def test_replaces_probe_a_internal_owner_with_external_reporter_is_one_recipient(
    ctx, tenant, workspace, bob
):
    """(a) An internal owner plus an external reporter yields exactly one recipient."""
    owner = _actor(tenant, name="Bob", user=bob)
    external = _actor(tenant, name="Frau Mueller (TUEV)", kind=Actor.Kind.EXTERNAL)
    artifact = Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="Requirement",
        owner=owner,
        reporter=external,
    )

    assert notify_user_ids_for_artifact(artifact) == [bob.pk]

    CommentService().create_comment(artifact_id=artifact.pk, text="hi", ctx=ctx)
    rows = Notification.unscoped.filter(kind=Notification.KIND_COMMENT_ADDED)
    assert rows.count() == 1
    assert rows.get().user_id == bob.pk


@pytest.mark.django_db
def test_replaces_probe_b_the_author_with_owner_equals_reporter_gets_nothing(
    ctx, tenant, workspace, alice
):
    """(b) Owner == reporter == the commenting user: the duplicate collapses and
    the author exclusion drops the last candidate, so no row is written."""
    actor = _actor(tenant, name="Alice", user=alice)
    artifact = Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="Requirement",
        owner=actor,
        reporter=actor,
    )

    assert notify_user_ids_for_artifact(artifact) == [alice.pk]

    CommentService().create_comment(artifact_id=artifact.pk, text="hi", ctx=ctx)
    assert Comment.unscoped.filter(artifact=artifact).count() == 1
    assert Notification.unscoped.count() == 0
