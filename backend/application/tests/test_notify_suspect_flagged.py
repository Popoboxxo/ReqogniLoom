"""suspect_flagged: notify the affected artifact's owner and reporter (spec §5.2)."""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.models import Notification
from application.notification_service import notify_suspect_flagged


@pytest.mark.django_db
def test_notifies_owner_and_reporter():
    owner, reporter, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    artifact_id = uuid.uuid4()
    artifact = MagicMock()
    artifact.pk = artifact_id
    artifact.title = "REQ-1"

    with patch(
        "application.notification_service._load_artifact", return_value=artifact
    ), patch(
        "application.notification_service._recipient_user_ids_for_artifact",
        return_value=[owner, reporter],
    ), patch(
        "application.notification_service.create_notifications", return_value=2
    ) as notify:
        written = notify_suspect_flagged(
            artifact_id=artifact_id, tenant_id=uuid.uuid4(), actor_user_id=actor
        )

    assert written == 2
    kwargs = notify.call_args.kwargs
    assert kwargs["user_ids"] == [owner, reporter]
    assert kwargs["kind"] == Notification.KIND_SUSPECT_FLAGGED
    assert kwargs["artifact_id"] == artifact_id


@pytest.mark.django_db
def test_notifies_nobody_when_no_internal_recipient_exists():
    """An artifact without a human owner/reporter yields zero notifications.

    ``create_notifications`` receives the (empty) candidate list and returns 0;
    dropping external actors is ``notify_user_ids_for_artifact``'s job (OD-4),
    not this producer's.
    """
    artifact = MagicMock()
    artifact.pk = uuid.uuid4()
    artifact.title = "REQ-1"

    with patch(
        "application.notification_service._load_artifact", return_value=artifact
    ), patch(
        "application.notification_service._recipient_user_ids_for_artifact",
        return_value=[],
    ), patch(
        "application.notification_service.create_notifications", return_value=0
    ) as notify:
        assert notify_suspect_flagged(
            artifact_id=uuid.uuid4(), tenant_id=uuid.uuid4()
        ) == 0

    assert notify.call_args.kwargs["user_ids"] == []


@pytest.mark.django_db
def test_a_missing_artifact_is_not_fatal():
    """Never raises: the propagation that triggered the producer must survive."""
    with patch(
        "application.notification_service._load_artifact", return_value=None
    ), patch("application.notification_service.create_notifications") as notify:
        assert notify_suspect_flagged(
            artifact_id=uuid.uuid4(), tenant_id=uuid.uuid4()
        ) == 0

    notify.assert_not_called()
