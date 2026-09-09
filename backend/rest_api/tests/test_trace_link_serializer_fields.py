"""TraceLinkSerializer exposes rationale and the suspect markers."""
from __future__ import annotations

import uuid

from django.utils import timezone

from rest_api.serializers import TraceLinkSerializer


class _Link:
    def __init__(self, **kwargs):
        self.id = uuid.uuid4()
        self.source_id = uuid.uuid4()
        self.target_id = uuid.uuid4()
        self.link_type = "derives-from"
        self.version = 1
        self.created_at = timezone.now()
        self.rationale = ""
        self.suspect_flagged_at = None
        self.suspect_source_change = None
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_rationale_is_returned():
    data = TraceLinkSerializer(_Link(rationale="workshop decision")).data
    assert data["rationale"] == "workshop decision"


def test_suspect_markers_are_returned():
    audit_id = uuid.uuid4()
    flagged = timezone.now()
    data = TraceLinkSerializer(
        _Link(suspect_flagged_at=flagged, suspect_source_change=audit_id)
    ).data
    assert data["suspect_flagged_at"] is not None
    assert str(data["suspect_source_change"]) == str(audit_id)


def test_rationale_is_writable():
    serializer = TraceLinkSerializer(
        data={
            "source_id": str(uuid.uuid4()),
            "target_id": str(uuid.uuid4()),
            "link_type": "derives-from",
            "rationale": "because the stakeholder asked for it",
        }
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["rationale"] == "because the stakeholder asked for it"


def test_rationale_is_optional():
    serializer = TraceLinkSerializer(
        data={
            "source_id": str(uuid.uuid4()),
            "target_id": str(uuid.uuid4()),
            "link_type": "derives-from",
        }
    )
    assert serializer.is_valid(), serializer.errors


def test_rationale_is_length_capped():
    serializer = TraceLinkSerializer(
        data={
            "source_id": str(uuid.uuid4()),
            "target_id": str(uuid.uuid4()),
            "link_type": "derives-from",
            "rationale": "x" * 2001,
        }
    )
    assert not serializer.is_valid()
    assert "rationale" in serializer.errors


def test_suspect_markers_are_read_only():
    serializer = TraceLinkSerializer(
        data={
            "source_id": str(uuid.uuid4()),
            "target_id": str(uuid.uuid4()),
            "link_type": "derives-from",
            "suspect_flagged_at": timezone.now().isoformat(),
            "suspect_source_change": str(uuid.uuid4()),
        }
    )
    assert serializer.is_valid(), serializer.errors
    assert "suspect_flagged_at" not in serializer.validated_data
    assert "suspect_source_change" not in serializer.validated_data
