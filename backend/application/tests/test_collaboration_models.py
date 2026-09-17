"""Comment and Notification model shape (Menschen-im-System spec §4 / §5)."""
import pytest
from django.db import models

from application.models import Comment, Notification
from persistence.models import Artifact, TenantScopedModel, User


def test_comment_is_tenant_scoped():
    assert issubclass(Comment, TenantScopedModel)
    assert Comment._meta.db_table == "as_comment"


def test_comment_hangs_on_the_generic_artifact():
    field = Comment._meta.get_field("artifact")
    assert field.related_model is Artifact
    assert field.remote_field.on_delete is models.CASCADE
    assert field.remote_field.related_name == "comments"


def test_comment_author_survives_user_deletion():
    field = Comment._meta.get_field("author")
    assert field.related_model is User
    assert field.remote_field.on_delete is models.SET_NULL


def test_comment_resolution_fields():
    assert Comment._meta.get_field("resolved").default is False
    assert Comment._meta.get_field("resolved_by").null is True
    assert Comment._meta.get_field("resolved_at").null is True


def test_comment_reuses_the_inherited_created_at():
    """AuditableModel already provides created_at; redeclaring it would shadow it."""
    assert Comment._meta.get_field("created_at").auto_now_add is True


def test_notification_kinds_are_exactly_the_four_from_the_spec():
    kinds = {value for value, _label in Notification.KIND_CHOICES}
    assert kinds == {
        "transition_pending",
        "suspect_flagged",
        "assigned",
        "comment_added",
    }


def test_notification_artifact_is_optional():
    field = Notification._meta.get_field("artifact")
    assert field.null is True
    assert field.remote_field.on_delete is models.CASCADE


def test_notification_user_cascade():
    field = Notification._meta.get_field("user")
    assert field.remote_field.on_delete is models.CASCADE
    assert field.remote_field.related_name == "notifications"
