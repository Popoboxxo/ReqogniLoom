"""
Tests for COMP-RA-001 — IcdViewSet.create / partial_update error mapping.

leaf_id : COMP-RA-001
req_id  : REQ-L2-ICD-001, REQ-L2-ICD-002

Covers #104 (see docs/ANALYSE_SYSENG20_TESTBERICHT_FIXLISTE.md): IcdViewSet
builds the IcdCreateDTO/IcdUpdateDTO straight from request.data — there is no
DRF serializer in this path, so the only guard against unbounded free-text
(``semantic_description``) is ContractValidator.validate_syntax(), which
raises ValueError via icd.services.create_icd()/update_icd(). Before this
fix that ValueError fell through to the generic ``except Exception`` handler
and surfaced as an unhelpful HTTP 500. It must now map to a clean HTTP 400
(VALIDATION_ERROR), mirroring the CR-02 fix for DiagramViewSet
(test_diagram_crud_views.py).

All tests use mock services to avoid a database dependency, consistent with
rest_api/tests/test_diagram_crud_views.py.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from rest_framework.test import APIRequestFactory

from rest_api.icd_views import IcdViewSet

FAKE_TENANT_ID = uuid.uuid4()
FAKE_USER_ID = uuid.uuid4()
FAKE_ICD_ID = uuid.uuid4()


def _make_auth_context() -> MagicMock:
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=FAKE_USER_ID,
        tenant_id=FAKE_TENANT_ID,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


class TestIcdViewSetCreateValidation:
    """#104: syntax/size ValueError from create_icd() must surface as HTTP 400, not 500."""

    def test_create_with_oversized_semantic_description_returns_400(self) -> None:
        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/icds/",
            data={
                "name": "My ICD",
                "workspace_id": str(uuid.uuid4()),
                "source_element_id": str(uuid.uuid4()),
                "target_element_id": str(uuid.uuid4()),
                "semantic_description": "A" * 10001,
            },
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = IcdViewSet.as_view({"post": "create"})

        with patch(
            "rest_api.icd_views.get_auth_context", return_value=req.auth_context
        ):
            with patch("rest_api.icd_views.get_tenant"), patch("rest_api.icd_views.get_user"):
                with patch(
                    "rest_api.icd_views.create_icd",
                    side_effect=ValueError(
                        "ICD payload failed syntax validation: "
                        "[\"Field 'semantic_description' exceeds maximum length "
                        "of 10000 characters (got 10001)\"]"
                    ),
                ):
                    response = view(req)

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        assert "semantic_description" in response.data["error"]["message"]

    def test_create_success_still_returns_201(self) -> None:
        """Sanity check: a valid payload is unaffected by the new error mapping."""
        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/icds/",
            data={
                "name": "My ICD",
                "workspace_id": str(uuid.uuid4()),
                "source_element_id": str(uuid.uuid4()),
                "target_element_id": str(uuid.uuid4()),
                "semantic_description": "short",
            },
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = IcdViewSet.as_view({"post": "create"})

        fake_icd = MagicMock()
        fake_icd.id = FAKE_ICD_ID
        fake_icd.name = "My ICD"
        fake_icd.workspace_id = uuid.uuid4()
        fake_icd.source_element_id = uuid.uuid4()
        fake_icd.target_element_id = uuid.uuid4()
        fake_icd.created_at = None
        fake_result = MagicMock()
        fake_result.icd = fake_icd
        fake_result.current_version.version_number = 1

        with patch(
            "rest_api.icd_views.get_auth_context", return_value=req.auth_context
        ):
            with patch("rest_api.icd_views.get_tenant"), patch("rest_api.icd_views.get_user"):
                with patch(
                    "rest_api.icd_views.create_icd", return_value=fake_result
                ):
                    response = view(req)

        assert response.status_code == 201
        assert response.data["name"] == "My ICD"

    def test_partial_update_oversized_semantic_description_returns_400(self) -> None:
        """PATCH with an oversized payload must also fail cleanly with 400."""
        factory = APIRequestFactory()
        req = factory.patch(
            f"/api/v1/icds/{FAKE_ICD_ID}/",
            data={"semantic_description": "A" * 10001},
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = IcdViewSet.as_view({"patch": "partial_update"})

        with patch(
            "rest_api.icd_views.get_auth_context", return_value=req.auth_context
        ):
            with patch("rest_api.icd_views.get_user"):
                with patch(
                    "rest_api.icd_views.update_icd",
                    side_effect=ValueError(
                        "ICD update payload failed syntax validation: "
                        "[\"Field 'semantic_description' exceeds maximum length "
                        "of 10000 characters (got 10001)\"]"
                    ),
                ):
                    response = view(req, pk=str(FAKE_ICD_ID))

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        assert "semantic_description" in response.data["error"]["message"]
