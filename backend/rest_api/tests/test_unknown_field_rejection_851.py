"""#851 — unknown-field rejection must be consistent across Create/Update.

Before this fix, only the ``CustomFieldsSerializerMixin``-based serializers
(plus ``TestCaseSerializer``, which carried a hand-rolled copy of the same
check) rejected request keys that no declared field accepted. Every other
artifact serializer silently dropped such a key: the create/update returned
201/200, the value was absent from both the response and the persisted row —
indistinguishable from success (the #73/#580/QIRK-002 failure class).

These tests pin the single shared guard
(:class:`rest_api.serializers.UnknownFieldRejectionMixin`) for the
newly-covered artifact serializers. They also prove the guard does not
false-positive: every declared, optional and write-only field still passes,
and the always-allowed write keys (``change_reason``/``custom_fields``/
``expected_version``) keep passing even where a serializer does not declare
them.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory

from auth_tenancy.context import AuthContext, AuthMethod
from rest_api.serializers import (
    BaselineSerializer,
    ChangeRequestSerializer,
    GlossaryTermSerializer,
    GoalSerializer,
    MainGoalSerializer,
    TraceLinkSerializer,
)
from rest_api.views import BaselineViewSet, ChangeRequestViewSet

pytestmark = pytest.mark.django_db

TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()

#: Every serializer newly covered by the shared guard, with a payload that
#: uses all of its declared / optional / write-only write fields.
_FULL_PAYLOADS: dict[type, dict] = {
    BaselineSerializer: {
        "workspace_id": str(uuid.uuid4()),
        "name": "Full baseline",
        "scope": "project",
        "description": "everything the create form can send",
        "override_reason": "SE-Auditor waiver justification",
    },
    ChangeRequestSerializer: {
        "workspace_id": str(uuid.uuid4()),
        "title": "Full CR",
        "description": "desc",
        "impact_assessment": "medium",
        "change_reason": "why it changed",
        "assigned_reviewer_id": str(uuid.uuid4()),
    },
    GlossaryTermSerializer: {
        "workspace_id": str(uuid.uuid4()),
        "term": "Guard",
        "definition": "an unknown-field guard",
        "synonyms": ["protection"],
        "abbreviation": "G",
    },
    GoalSerializer: {
        "workspace_id": str(uuid.uuid4()),
        "title": "Full goal",
        "description": "desc",
        "lineage_id": str(uuid.uuid4()),
    },
    MainGoalSerializer: {
        "workspace_id": str(uuid.uuid4()),
        "content": "the aggregate main goal",
    },
    TraceLinkSerializer: {
        "source_id": str(uuid.uuid4()),
        "target_id": str(uuid.uuid4()),
        "link_type": "verifies",
        "rationale": "why the link exists",
    },
}


@pytest.fixture(autouse=True)
def _tenant_context():
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(TENANT_ID)
    yield
    TenantContext.clear_tenant()


def _auth_context() -> AuthContext:
    return AuthContext(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        active_roles=("editor", "admin"),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


# ---------------------------------------------------------------------------
# Serializer-level: the guard rejects undeclared keys, keeps declared ones
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("serializer_cls", list(_FULL_PAYLOADS))
def test_full_supported_payload_is_accepted(serializer_cls: type) -> None:
    """The positive control: a complete, legitimate payload still validates."""
    serializer = serializer_cls(data=dict(_FULL_PAYLOADS[serializer_cls]))
    assert serializer.is_valid(), serializer.errors


@pytest.mark.parametrize("serializer_cls", list(_FULL_PAYLOADS))
def test_undeclared_key_is_rejected(serializer_cls: type) -> None:
    """A key no declared field accepts is a 400, not a silent drop."""
    payload = dict(_FULL_PAYLOADS[serializer_cls])
    payload["totally_unknown_key"] = "should be rejected"

    serializer = serializer_cls(data=payload)

    assert not serializer.is_valid()
    assert serializer.errors.get("totally_unknown_key") == ["Unknown field."]


@pytest.mark.parametrize("serializer_cls", list(_FULL_PAYLOADS))
def test_always_allowed_write_keys_are_accepted_even_when_undeclared(
    serializer_cls: type,
) -> None:
    """The UI save paths send these on every entity; rejecting them would break
    working PATCH calls (see ``_ALWAYS_ALLOWED_PATCH_FIELDS``)."""
    payload = dict(_FULL_PAYLOADS[serializer_cls])
    payload.update(
        {
            "change_reason": "reason",
            "custom_fields": {"key": "value"},
            "expected_version": 1,
        }
    )

    serializer = serializer_cls(data=payload)

    assert serializer.is_valid(), serializer.errors
    # ``custom_fields`` is undeclared on all six serializers, so the allowlist
    # lets the key through but the serializer still does not persist it — the
    # pre-#851 behaviour for that key is preserved.
    assert "custom_fields" not in serializer.validated_data


# ---------------------------------------------------------------------------
# HTTP-level: Baseline — the verified silent-drop endpoint
# ---------------------------------------------------------------------------


class _BaselineServiceStub:
    """Minimal stand-in for ``BaselineFacade`` used by the create path."""

    def __init__(self) -> None:
        self.baseline_id = uuid.uuid4()
        self.workspace_id = uuid.uuid4()

    def create_baseline(self, **_kwargs) -> uuid.UUID:
        return self.baseline_id

    def get_baseline(self, _baseline_id, _ctx) -> MagicMock:
        detail = MagicMock()
        detail.baseline_id = self.baseline_id
        detail.workspace_id = self.workspace_id
        detail.name = "Baseline test"
        detail.scope = "project"
        detail.description = ""
        detail.version = 1
        detail.created_at = None
        detail.entries = []
        return detail


def _post_baseline(payload: dict, svc: _BaselineServiceStub):
    factory = APIRequestFactory()
    request = factory.post("/api/v1/baselines/", data=payload, format="json")
    request.auth_context = _auth_context()
    view = BaselineViewSet.as_view({"post": "create"})
    with (
        patch.object(BaselineViewSet, "_check_preset"),
        patch.object(BaselineViewSet, "_svc", return_value=svc),
    ):
        return view(request)


def test_baseline_create_rejects_unknown_field() -> None:
    """#851: the #724 comment proved the serializer used to drop it silently."""
    payload = dict(_FULL_PAYLOADS[BaselineSerializer])
    payload["not_a_real_baseline_field"] = "dropped"

    response = _post_baseline(payload, _BaselineServiceStub())

    assert response.status_code == 400, response.data
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    details = {d["field"] for d in response.data["error"]["details"]}
    assert "not_a_real_baseline_field" in details


def test_baseline_create_with_full_payload_returns_201() -> None:
    """Positive control: every declared/write-only key still creates the row."""
    response = _post_baseline(
        dict(_FULL_PAYLOADS[BaselineSerializer]), _BaselineServiceStub()
    )

    assert response.status_code == 201, response.data


# ---------------------------------------------------------------------------
# HTTP-level: ChangeRequest — a second, previously-lenient serializer
# ---------------------------------------------------------------------------


def _post_change_request(payload: dict, svc: MagicMock):
    factory = APIRequestFactory()
    request = factory.post("/api/v1/change-requests/", data=payload, format="json")
    request.auth_context = _auth_context()
    view = ChangeRequestViewSet.as_view({"post": "create"})
    with patch.object(ChangeRequestViewSet, "_svc", return_value=svc):
        return view(request)


def _change_request_stub() -> MagicMock:
    cr = MagicMock()
    cr.id = uuid.uuid4()
    cr.workspace_id = uuid.uuid4()
    cr.tenant_id = TENANT_ID
    cr.title = "Full CR"
    cr.description = "desc"
    cr.impact_assessment = "medium"
    cr.change_reason = "why it changed"
    cr.status = "draft"
    cr.requestor_id = USER_ID
    cr.assigned_reviewer_id = None
    cr.version = 1
    cr.created_at = "2026-09-12T10:00:00Z"
    cr.updated_at = "2026-09-12T10:00:00Z"
    return cr


def test_change_request_create_rejects_unknown_field() -> None:
    payload = dict(_FULL_PAYLOADS[ChangeRequestSerializer])
    payload["not_a_real_cr_field"] = "dropped"

    response = _post_change_request(payload, MagicMock())

    assert response.status_code == 400, response.data
    details = {d["field"] for d in response.data["error"]["details"]}
    assert "not_a_real_cr_field" in details


def test_change_request_create_with_full_payload_returns_201() -> None:
    svc = MagicMock()
    svc.create_change_request.return_value = _change_request_stub()

    response = _post_change_request(
        dict(_FULL_PAYLOADS[ChangeRequestSerializer]), svc
    )

    assert response.status_code == 201, response.data
